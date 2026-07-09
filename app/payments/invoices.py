from datetime import datetime, timedelta
import logging
from sqlalchemy import select
import sqlalchemy.orm
import io
from aiogram.types import BufferedInputFile

from app.admin.admin_message import send_message_to_admin
from app.database.models import async_session, Invoices, Subscriptions, Seller
from app.database.support_functions import get_chat_id_by_seller_id, \
    get_end_of_subscription, get_subscription_type_by_subscription_id
from app.managers.managers_functions import get_managers_chat_ids_by_seller_id
from app.user_communication.email_func import send_invoice_via_email
from app.payments.bank import create_new_invoice_in_bank, get_invoice_from_bank, check_invoice_status
from app.main_bot.main_bot import bot
from app.wrappers import log_and_notify_admin, with_session


# Деактивируем старые подписки со статусом pending_payment
@log_and_notify_admin
async def deactivate_pending_invoices(session, seller_id):
    pending_invoices = await session.execute(select(Invoices.id).
                                            where(Invoices.seller_id == seller_id,
                                                  Invoices.status=='payment_waiting'))
    for item in pending_invoices:
        async with session.begin_nested():
            query = sqlalchemy.update(Invoices).where(Invoices.id == item[0]).values(status='canceled')
            await session.execute(query)
        await session.commit()

@log_and_notify_admin
async def create_new_invoice(session, seller_id, subscription_id, requestor_tg_id, subscription_duration):
    await deactivate_pending_invoices(session=session,
                                      seller_id=seller_id)
    last_prev_invoice = await session.scalar(select(Invoices.id).order_by(Invoices.created_at.desc()))
    new_number = 0
    if not last_prev_invoice:
        new_number = 1
    else:
        new_number = last_prev_invoice+1
    invoice_letters = ['A','B','C','D','E','F','G','H','I','J','K','L']
    month = datetime.now().month-1
    new_invoice_number = f'{datetime.now().year}FE{invoice_letters[month]}{new_number}'
    amount = await session.scalar(select(Subscriptions.net_amount).where(Subscriptions.id == subscription_id))
    # print(amount)
    subscription_duration = subscription_duration
    async with session.begin_nested():
        invoice = Invoices(invoice_number = new_invoice_number,
                           seller_id = seller_id,
                           amount = amount,
                           subscription_id = subscription_id,
                           status = 'payment_waiting',
                           created_at = datetime.now(),
                           tochka_invoice_id = '',
                           file_name = '')
        session.add(invoice)
        # print(invoice.invoice_number)
        await session.flush()
        invoice_id = invoice.id
    await session.commit()
    # print(invoice_id)

    # Создаем счет в банке
    bank_invoice_id = await create_new_invoice_in_bank(session=session,
                                                       seller_id=seller_id,
                                                       invoice_id=invoice_id,
                                                       subscription_duration=subscription_duration,
                                                       amount=amount,
                                                       invoice_number=new_invoice_number)
    # print(bank_invoice_id)
    # Скачиваем счет
    result = await get_invoice_from_bank(session=session,
                                         seller_id=seller_id,
                                         invoice_number=new_invoice_number,
                                         invoice_id=invoice_id,
                                         bank_invoice_id=bank_invoice_id)

    if not result:
        raise ValueError("Bank invoice response is empty")
    file_name, res = result

    # Добавить проверку перед использованием res.content
    if not res or not res.content:
        raise ValueError("Invalid response from bank")

    # Отправляем файл пользователю в тг
    pdf_content = io.BytesIO(res.content)
    file_to_send=pdf_content.getvalue()

    if requestor_tg_id:
        await bot.send_document(chat_id=requestor_tg_id,
                                document=BufferedInputFile(file_to_send, file_name),
                                caption='Направляем счет на оплату подписки')

    else:

        owner_chat_id = await get_chat_id_by_seller_id(session, seller_id)
        await bot.send_document(chat_id=int(owner_chat_id),
                                document=BufferedInputFile(file_to_send, file_name),
                                caption='Направляем счет на оплату подписки')

        managers_chat_ids = await get_managers_chat_ids_by_seller_id(session, seller_id)
        for manager_chat_id in managers_chat_ids:
            await bot.send_document(chat_id=int(manager_chat_id), document=BufferedInputFile(file_to_send, file_name),
                                    caption='Направляем счет на оплату подписки')
    await send_invoice_via_email(session=session,
                                 seller_id=seller_id,
                                 file_to_send=file_to_send,
                                 filename=file_name)

    # Обновляем номер bank_invoice_id из банка в БД
    async with session.begin_nested():
        query = (sqlalchemy.update(Invoices).
                 where(Invoices.id == invoice_id).
                 values(tochka_invoice_id=bank_invoice_id,
                        file_name = file_name))
        await session.execute(query)
    await session.commit()

@with_session
async def check_invoices_status(session):
    try:
        pending_invoices = await session.execute(select(Invoices.id,
                                                        Invoices.seller_id,
                                                  Invoices.subscription_id,
                                                  Invoices.created_at,
                                                  Invoices.tochka_invoice_id).
                                           where(Invoices.status=='payment_waiting'))
        pending_invoices = pending_invoices.mappings().all()
        invoice_expiry_date = datetime.now()-timedelta(days=30)
        for invoice in pending_invoices:
            seller_id = invoice['seller_id']
            subscription_id = invoice['subscription_id']
            if invoice['created_at']<invoice_expiry_date:
                async with session.begin_nested():
                    query = (sqlalchemy.update(Invoices).
                             where(Invoices.id == invoice['id']).
                             values(status='canceled'))
                    await session.execute(query)

                    query_subscription_cancel = (sqlalchemy.update(Subscriptions).
                             where(Subscriptions.id == subscription_id).
                             values(status='canceled',
                                    updated_at = datetime.now()))
                    await session.execute(query_subscription_cancel)
                await session.commit()
            else:
                # Проверяем статус счета в банке
                paymentStatus = await check_invoice_status(invoice['tochka_invoice_id'])
                # Если не оплачен, то ничего не делаем
                if paymentStatus == 'payment_waiting':
                    pass
                # Если счет оплачен
                elif paymentStatus == 'payment_paid':
                    # 1) обновляем статус счета и дату оплаты в бд в таблице invoices
                    async with session.begin_nested():
                        query = (sqlalchemy.update(Invoices).
                                 where(Invoices.id == invoice['id']).
                                 values(status='payment_paid',
                                        paid_at=datetime.now()))
                        await session.execute(query)
                    await session.commit()
                    # 2) обновляем статус и сроки подписки в бд в таблице subscriptions
                    subscription_type = await get_subscription_type_by_subscription_id(session=session, subscription_id=subscription_id)
                    date_start = datetime.now()
                    # проверяем, есть ли у селлера действующая подписка
                    active_subscription = await session.execute(select(Subscriptions.id,
                                                                      Subscriptions.end_date).
                                                               where(Subscriptions.seller_id==seller_id,
                                                                     Subscriptions.status == 'active').
                                                                order_by(Subscriptions.end_date.desc()))
                    active_subscription = active_subscription.mappings().first()
                    if not active_subscription:
                        # обновляем статус селлера, если не было активных подписок
                        async with session.begin_nested():
                            query2 = (sqlalchemy.update(Seller).
                                  where(Seller.id == seller_id).
                                  values(service_status=True))
                            await session.execute(query2)
                        await session.commit()
                        date_end = await get_end_of_subscription(subscription_type=subscription_type,
                                                                 date_start=date_start)
                    else:
                        date_start = active_subscription['end_date']
                        date_end = await get_end_of_subscription(subscription_type=subscription_type,
                                                                 date_start=date_start)
                    async with session.begin_nested():
                        query3 = (sqlalchemy.update(Subscriptions).
                             where(Subscriptions.id == invoice['subscription_id']).
                             values(start_date=date_start,
                                    end_date=date_end,
                                    status='active',
                                    updated_at = datetime.now()))
                        await session.execute(query3)
                        query4 = (sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(service_status = True))
                        await session.execute(query4)
                    await session.commit()
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при проверке статусов счетов'
                                         f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)
