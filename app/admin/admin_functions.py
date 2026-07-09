from datetime import timedelta

from sqlalchemy import select
import logging

from app.admin.admin_message import send_message_to_admin
from app.database.models import async_session, Seller, User
from app.database.requests import set_pl_results
from app.dates import start_of_PriorMinusOne_Month_func
from app.wrappers import with_session
from app.main_bot.main_bot import bot


@with_session
async def admin_recalculate_pl_results_for_three_months(session):
    start_of_PriorMinusOne_Month = await start_of_PriorMinusOne_Month_func()
    date_from = start_of_PriorMinusOne_Month
    try:
        # Получаем список селлеров для выгрузки, подготовки отчетов и рассылки
        query = select(Seller.id).where(Seller.status=='Active', Seller.service_status==True)
        companies = await session.execute(query)

        # Последовательно для каждого селлера
        for row in companies:
            seller_id = row[0]
            await set_pl_results(session=session,
                                 seller_id=seller_id,
                                 date_start=date_from)
    except Exception as e:
        await send_message_to_admin(f'Ошибка при пересчете PL за 3 месяца')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def admin_recalculate_pl_results_for_three_months_for_seller_id(session, seller_id):
    start_of_PriorMinusOne_Month = await start_of_PriorMinusOne_Month_func()
    date_from = start_of_PriorMinusOne_Month - timedelta(days=200)
    try:
        await set_pl_results(session=session,
                             seller_id=seller_id,
                             date_start=date_from)
    except Exception as e:
        await send_message_to_admin(f'Ошибка при пересчете PL за 3 месяца')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def admin_recalculate_pl_results_for_seller_id_from_date(session, seller_id, date_from_for_pl):
    try:
        await set_pl_results(session=session,
                             seller_id=seller_id,
                             date_start=date_from_for_pl)
    except Exception as e:
        await send_message_to_admin(f'Ошибка при пересчете PL за 3 месяца')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def send_message_to_all_users(session, message_text):
    try:
        users = await session.execute(select(User.tg_id))
        users = users.mappings().all()
        for user in users:
            await bot.send_message(chat_id=user['tg_id'], text=message_text)
    except Exception as e:
        await send_message_to_admin(f'Ошибка при массовой рассылке сообщений')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)