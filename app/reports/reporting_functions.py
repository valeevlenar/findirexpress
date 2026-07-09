import logging

import pandas as pd
from sqlalchemy import select

from app.app_logic import weekly_reports_calculation_and_send, run_with_semaphore
from app.database.classes.sales import Sales
from app.database.dates_functions import get_latest_weekly_report_sent_date
from app.database.models import async_session
from app.database.classes.stocks import Stock
from app.database.support_functions import check_company_status, get_chat_id_by_seller_id
from app.dates import end_of_Reporting_Week_func, start_of_Reporting_Week_func
from app.locks import per_seller_lock
from app.main_bot import keyboards as kb
from app.main_bot.main_bot import bot
from app.reports.monthly_finreport import get_monthly_pl
from app.reports.weekly_finreport import get_weekly_pl
from app.wrappers import log_and_notify_admin, with_session


# Отправка отчета по требованию пользователя:

@with_session
@per_seller_lock(seller_id_param="seller_id", timeout=300)
async def send_report_on_demand(session, seller_id, report_type, requestor_tg_id, date_from, date_to):
    if await check_company_status(session=session, seller_id=seller_id):
        if report_type == "weekly":
            try:
                report_creation_type = 'on_demand'
                # print(date_from, date_to)
                await get_weekly_pl(session=session,
                                    seller_id = seller_id,
                                    report_creation_type = report_creation_type,
                                    date_from = date_from,
                                    date_to = date_to,
                                    requestor_chat_id=requestor_tg_id)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        elif report_type == "monthly":
            try:
                report_creation_type = 'on_demand'
                await get_monthly_pl(session=session,
                                     seller_id = seller_id,
                                     report_creation_type = report_creation_type,
                                     date_from=date_from,
                                     date_to=date_to,
                                     requestor_chat_id=requestor_tg_id)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e,)
        else: pass
    else:
        chat_id = await get_chat_id_by_seller_id(session, seller_id)
        bot.send_message(chat_id=chat_id,text="Обслуживание Вашей компании приостановлено. "
                                              "\nПроверьте баланс. "
                                              "\nПри необходимости напишите в поддержку.",
                           reply_markup=kb.main_kb(chat_id))

# Пользователь загрузил новую себестоимость и попросил пересчитать результаты за прошедшую неделю:
@with_session
@per_seller_lock(seller_id_param="seller_id", timeout=600)
async def recalculate_results_for_last_week (session, seller_id: int, recalc_bool: bool):
    # Берем все возможные даты:
    end_of_Reporting_Week = await end_of_Reporting_Week_func()
    date_to = end_of_Reporting_Week
    start_of_Reporting_Week = await start_of_Reporting_Week_func()
    date_from_for_report = start_of_Reporting_Week
    date_from_for_pl = start_of_Reporting_Week
    latest_weekly_report_sent_date = await get_latest_weekly_report_sent_date(session=session, seller_id=seller_id)

    # Если хочет пересчитать PL:
    if recalc_bool == True:
        # и если уже отправляли отчет
        if latest_weekly_report_sent_date == date_to:
            # то запускаем пересчет PL и отправку отчета:
            await weekly_reports_calculation_and_send(session=session,
                                                      seller_id=seller_id,
                                                      date_from_for_pl=date_from_for_pl,
                                                      date_from_for_report=date_from_for_report,
                                                      date_to=date_to)

            # Если еще не отправляли отчет, то просто запускаем основную функцию по нему:
        else:
            await run_with_semaphore(seller_id=seller_id)
    elif recalc_bool==False:
        # Если не хочет пересчитывать, то просто запускаем основную функцию по нему:
        await run_with_semaphore(seller_id=seller_id)


# Временная функция для сохранения базы в эксель

async def get_db_to_excel():
    async with (async_session() as session):
        query = select(Sales.__table__.columns)
        result=await session.execute(query)
        await session.commit()
        df=pd.DataFrame(result)
        df.to_excel("База продажи.xlsx")

# Временная функция для сохранения остатков в эксель
async def save_stocks_to_excel():
    async with (async_session() as session):
        query = select(Stock.__table__.columns)
        result=await session.execute(query)
        await session.commit()
        df=pd.DataFrame(result)
        df.to_excel("Таблица остатки.xlsx")
