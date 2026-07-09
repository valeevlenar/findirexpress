from datetime import datetime, timedelta
import logging
import io

from aiogram.types import BufferedInputFile

from app.admin.admin_message import send_message_to_admin
from app.user_communication.email_func import send_closing_document_via_email
from app.main_bot.main_bot import bot


from sqlalchemy import select, func

from app.database.models import async_session, Transactions, ClosingDocuments
from app.database.support_functions import get_chat_id_by_seller_id
from app.payments.bank import create_closing_document_in_bank, get_closing_document_from_bank
from app.wrappers import with_session


# Запускаем 1 раз первого числа каждого месяца за предыдущий месяц
@with_session
async def monthly_prepare_and_send_closing_documents(session):
    try:
        date_end = (datetime.now().replace(day=1)-timedelta(days=1)).replace(hour=23,minute=59,second=59,microsecond=999999)
        date_start = date_end.replace(day=1,hour=00,minute=00,second=00,microsecond=00)
        # date_end = datetime.now()
        # date_start = await start_of_yesterday_func()
        date_start_str = datetime.strftime(date_start, '%d.%m.%Y')
        date_end_str = datetime.strftime(date_end, '%d.%m.%Y')
        closing_documents = await session.execute(select(Transactions.seller_id,
                                                         func.sum(Transactions.amount).label('amount')
                                                         ).where(Transactions.transaction_stream=='net_revenue',
                                                                 Transactions.created_at>=date_start,
                                                                 Transactions.created_at<=date_end).
                                                  group_by(Transactions.seller_id))
        closing_documents = closing_documents.mappings().all()
        for closing_document in closing_documents:
            seller_id = closing_document.seller_id
            amount = round(closing_document.amount,2)
            if amount>0:
                last_prev_doc_number = await session.scalar(select(ClosingDocuments.id).order_by(ClosingDocuments.created_at.desc()))
                new_number = 0
                if not last_prev_doc_number:
                    new_number = 1
                else:
                    new_number = last_prev_doc_number+1
                month = date_end.month
                new_closing_doc_number = f'{datetime.now().year}-FE{month}{new_number}'
                closing_document_tochka_doc_id = await create_closing_document_in_bank(session=session,
                                                                                       seller_id=seller_id,
                                                                                       amount=amount,
                                                                                       date_start=date_start,
                                                                                       date_end=date_end,
                                                                                       closing_document_number=new_closing_doc_number)
                # Скачиваем закрывающий документ
                file_name, res = await get_closing_document_from_bank(session=session,
                                                                      seller_id=seller_id,
                                                                      closing_document_number=new_closing_doc_number,
                                                                      closing_document_tochka_doc_id=closing_document_tochka_doc_id)

                # Отправляем файл пользователю в тг
                chat_id = await get_chat_id_by_seller_id(session, seller_id)
                pdf_content = io.BytesIO(res.content)
                file_to_send=pdf_content.getvalue()
                await bot.send_document(chat_id=chat_id, document=BufferedInputFile(file_to_send, file_name))
                await send_closing_document_via_email(session=session,
                                                      seller_id=seller_id,
                                                      file_to_send=file_to_send,
                                                      filename=file_name,
                                                      date_start_str=date_start_str,
                                                      date_end_str=date_end_str)

                # Записываем новый закрывающий документ в БД
                async with session.begin_nested():
                    closing_document_for_db = ClosingDocuments(seller_id=seller_id,
                                                               amount=amount,
                                                               date_start=date_start,
                                                               date_end=date_end,
                                                               created_at=datetime.now(),
                                                               status='sent',
                                                               tochka_doc_id=closing_document_tochka_doc_id,
                                                               file_name=file_name)
                    session.add(closing_document_for_db)
                await session.commit()
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при формировании и рассылке закрывающих документов'
                                         f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)