from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.admin.admin_message import send_message_to_admin
from app.database.models import Seller, User, Invoices, Subscriptions, ApiKeys, Goods_cost
from app.database.classes.sales import Sales
from sqlalchemy import select
import sqlalchemy.orm
from app.main_bot.main_bot import bot
from app.subscriptions.subscription_types import SubscriptionTypes, get_subscription_name_by_subscription_type
from app.wrappers import log_and_notify_admin, with_session

# Получить юзера по tg_id:
@with_session
async def get_user_by_tg_id(session, tg_id):
    user_id = await session.scalar(select(User.id).where(User.tg_id == tg_id))
    return user_id

# Получить список компаний по юзеру:
@with_session
async def get_companies_list(session, tg_id):
    user_id = await get_user_by_tg_id(session, tg_id)
    result = await session.execute(select(Seller.seller_title,
                                          Seller.id.label('seller_id')).
                                   where(Seller.user_id == user_id,
                                         Seller.status !='Deleted',
                                         Seller.status !='Blocked'))
    companies_list = result.mappings().all()
    return companies_list

# Получить баланс по seller_id:
@with_session
async def get_seller_balance(session, seller_id):
    balance = await session.scalar(select(Seller.balance).
                                   where(Seller.id == seller_id))
    return balance

# Получить название компании по seller_id из базы:
@with_session
async def get_company_name_by_seller_id(session, seller_id):
    company_name = await session.scalar(select(Seller.seller_title).
                                            where(Seller.id == seller_id))
    return company_name

# Получить seller_type по seller_id из базы:
@with_session
async def get_seller_type_by_seller_id(session, seller_id):
    seller_type = await session.scalar(select(Seller.seller_type).
                                        where(Seller.id == seller_id))
    return seller_type

# Получить seller_inn по seller_id из базы:
@with_session
async def get_seller_inn_by_seller_id(session, seller_id):
    seller_inn = await session.scalar(select(Seller.seller_inn).
                                            where(Seller.id == seller_id))
    return seller_inn

# Получить chat_id по selle_id из базы:
@with_session
async def get_chat_id_by_seller_id(session, seller_id):
    chat_id = await session.scalar(select(Seller.user_tg_id).
                                        where(Seller.id == seller_id))
    return chat_id

# Получить chat_id по user_id из базы:
@with_session
async def get_chat_id_by_user_id(session, user_id):
    chat_id = await session.scalar(select(User.tg_id).
                                        where(User.id == user_id))
    return chat_id

# Получить имя по user_id из базы:
@with_session
async def get_user_name_by_user_id(session, user_id):
    user_name = await session.scalar(select(User.username).
                                        where(User.id == user_id))
    return user_name

# Получить api по ИНН из базы:
@with_session
async def get_api_by_seller_id(session, seller_id):
    api_key = await session.scalar(select(ApiKeys.wb_api).
                                        where(ApiKeys.seller_id == seller_id,
                                              ApiKeys.api_status=='active'))
    return api_key

# Получить email по ИНН из базы:
@with_session
async def get_email_by_seller_id(session, seller_id):
    email_adress = await session.scalar(select(Seller.e_mail).
                                            where(Seller.id == seller_id))
    return email_adress

# Проверяем статус компании для обслуживания:
@with_session
async def check_company_status(session, seller_id):
    if (await session.scalar(select(Seller.status).where(Seller.id==seller_id)) != 'Deleted' and
        await session.scalar(select(Seller.status).where(Seller.id == seller_id)) != 'Blocked' and
            await session.scalar(select(Seller.service_status).where(Seller.id == seller_id)) != 'False'):
        return True
    else: return False

# Удалить компанию в базе:
@with_session
async def delete_company_from_database(session, tg_id, seller_id):
    async with session.begin_nested():
        query = (sqlalchemy.update(Seller).
                 where(Seller.id == seller_id,
                       Seller.user_tg_id==tg_id).
                 values(status='Deleted',
                        date_updated=datetime.now(),
                        service_status=False,
                        date_updated_ss=datetime.now()))
        await session.execute(query)
    await session.commit()

# Проверяем статус первой загрузки себестоимости:
@with_session
async def check_first_cost_set_status(session, seller_id):
    check = await session.scalar(select(Seller.first_cost_set).where(Seller.id==seller_id))
    if check:
       return True
    else: return False

# Обновляем статус загрузки шаблона с себестоимостью
@with_session
async def update_first_cost_template_status_true (session, seller_id):
    async with session.begin_nested():
        await session.execute(sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(first_cost_set=True))
    await session.commit()

# Обновляем дату отправки недельного отчета
@with_session
async def update_weekly_report_sent_date (session, seller_id, date_to: datetime):
    async with session.begin_nested():
        await session.execute(sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(last_weekly_pl_sent_date=date_to))
    await session.commit()

# Обновляем дату отправки месячного отчета
@with_session
async def update_monthly_report_sent_date (session, seller_id, date_to: datetime):
    async with session.begin_nested():
        await session.execute(sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(last_monthly_pl_sent_date=date_to))
    await session.commit()

# Обновляем дату расчета PL
@with_session
async def update_weekly_pl_calculation_date (session, seller_id, date_to: datetime):
    async with session.begin_nested():
        await session.execute(sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(last_pl_calculated_date=date_to))
    await session.commit()

# Обновляем статус, что первый отчет отправлен
@with_session
async def update_first_report_sent_status (session, seller_id):
    async with session.begin_nested():
        await session.execute(sqlalchemy.update(Seller).
                              where(Seller.id == seller_id).
                              values(first_reports_sent=True))
    await session.commit()

# удаляем сообщения
async def delete_four_messages (message):
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 3))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 2))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 1))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# удаляем сообщения
async def delete_three_messages (message):
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 2))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 1))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# удаляем сообщения
async def delete_two_messages (message):
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=(message.message_id - 1))
    except: pass
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# удаляем сообщения
async def delete_one_messages (message):
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except: pass

# Проверяем 3 баркода у нового селлера, что их нет у других селлеров:
@with_session
async def check_three_barcodes(session, report, seller_id):
    check = True
    barcodes = [report[0]['barcode'],report[1]['barcode'], report[2]['barcode'],report[3]['barcode'],report[4]['barcode']]
    for barcode_to_check in barcodes:
        barcode = await session.scalar(select(Sales.barcode).
                                                  where(Sales.barcode == barcode_to_check,
                                                        Sales.seller_id!=seller_id))
        if not barcode:
            check = True
        else:
            check = False
    return check

# Блокируем компанию:
@with_session
async def block_seller (session, seller_id):
    async with session.begin_nested():
        query = (sqlalchemy.update(Seller).where(Seller.id == seller_id).
                 values(status='Blocked',
                        service_status=False))
        await session.execute(query)
    await session.commit()
    chat_id = await get_chat_id_by_seller_id(session, seller_id)
    comp_name = await get_company_name_by_seller_id(session=session, seller_id=seller_id)
    # print(chat_id)
    await bot.send_message(chat_id=chat_id,
                           text=f'Ваша компания {comp_name} заблокирована.'
                                f'\nОбслуживание и отправка отчетов остановлены.'
                                f'\nДля продолжения обслуживания обратитесь в службу поддержки.')
    await send_message_to_admin(f'Новая компания заблокирована.'
                                f'\nИНН: {await get_seller_inn_by_seller_id(session=session, seller_id=seller_id)}'
                                f'\nSeller_id: {seller_id}'
                                f'\nКомпания: {comp_name}'
                                f'\ntg_id: {chat_id}')


# Получить номер счета из базы:
@with_session
async def get_invoice_number_by_invoice_id(session, invoice_id):
    invoice_number = await session.scalar(select(Invoices.invoice_number).
                                        where(Invoices.id == invoice_id))
    return invoice_number

# Получить данные по подписке:
@with_session
async def get_subscription_duration_by_invoice_id(session, invoice_id):
    subscription_id = await session.scalar(select(Invoices.subscription_id).
                                        where(Invoices.id == invoice_id))
    duration = await session.scalar((select(Subscriptions.duration).
                                        where(Subscriptions.id == subscription_id)))
    return duration

# Получить сумму счета:
@with_session
async def get_invoice_amount_by_invoice_id(session, invoice_id):
    amount = await session.scalar(select(Invoices.amount).
                                        where(Invoices.id == invoice_id))
    return amount

# Считаем конец подписки
@log_and_notify_admin
async def get_end_of_subscription(subscription_type, date_start):
    duration = 0
    for item in SubscriptionTypes.items:
        if item.subscription_type==subscription_type:
            duration = item.duration
    date_end = date_start + relativedelta(months=+duration)
    return date_end

# получаем тип подписки из базы
@with_session
async def get_subscription_type_by_subscription_id(session, subscription_id):
    subscription_type = await session.scalar(select(Subscriptions.subscription_type).where(Subscriptions.id == subscription_id))
    return subscription_type

# получаем срок и тип действующей подписки
@with_session
async def get_active_subscription_type_and_end_date_by_seller_id(session, seller_id):
    subscription_type = await session.scalar(select(Subscriptions.subscription_type).
                                              where(Subscriptions.seller_id == seller_id,
                                                    Subscriptions.status=='active').
                                             order_by(Subscriptions.created_at.desc()))
    date_end = await session.scalar(select(Subscriptions.end_date).
                                    where(Subscriptions.seller_id == seller_id,
                                          Subscriptions.status=='active').
                                    order_by(Subscriptions.created_at.desc()))
    if not subscription_type:
        subscription_name = None
        date_end_str = None
    else:
        subscription_name = await get_subscription_name_by_subscription_type(subscription_type=subscription_type)
        date_end_str = datetime.strftime(date_end, '%Y-%m-%d')
    return subscription_name, date_end_str

# Проверяем, включен ли контроль цен
@with_session
async def get_price_control_by_seller_id(session, seller_id):
    price_control = await session.scalar(select(Seller.price_control).where(Seller.id == seller_id))
    return price_control

# Проверяем, включен ли контроль цен
@with_session
async def get_barcode_by_nm_id_and_size(session, seller_id, nm_id, size):
    barcode = await session.scalar(select(Goods_cost.barcode).
                                       where(Goods_cost.seller_id == seller_id,
                                             Goods_cost.nm_id == nm_id,
                                             Goods_cost.ts_name == size))
    return barcode