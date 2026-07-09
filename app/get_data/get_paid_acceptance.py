# -*- coding: utf-8 -*-
import asyncio
import sqlalchemy
from datetime import timedelta, datetime
import pandas as pd
import logging
from sqlalchemy import select, func
from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import Paid_acceptance, DataDates
from app.database.support_functions import get_api_by_seller_id
from app.dates import end_of_yesterday_func, start_for_downloading_data_func, get_end_of_month
from app.wrappers import log_and_notify_admin
from config import create_paid_acceptance_report_url
from sqlalchemy.dialects.postgresql import insert

CHUNK_SIZE_PAID_ACCEPTANCE = 500

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

@log_and_notify_admin
async def get_paid_acceptance_costs_by_seller(session,seller_id):

    try:
        logging.info(f'Seller_id={seller_id}. Начало выгрузки платной приемки')

        # Получаем последнюю дату в базе
        last_paid_acceptance_in_db_date = await session.scalar(select(func.max(Paid_acceptance.shkcreatedate)).
                                                              where(Paid_acceptance.seller_id == seller_id))

        end_of_yesterday = await end_of_yesterday_func()
        start_for_downloading_data = await start_for_downloading_data_func()

        last_paid_acceptance_checked_date = await session.scalar(select(DataDates.last_paid_acceptance_date_checked).
                                                              where(DataDates.seller_id == seller_id))

        if not last_paid_acceptance_checked_date:
            last_paid_acceptance_checked_date = start_for_downloading_data - timedelta(microseconds=1)

        # print(last_paid_acceptance_checked_date)
        # Если нет данных в БД, начинаем с начальной даты

        if not last_paid_acceptance_in_db_date:
            last_paid_acceptance_in_db_date = start_for_downloading_data - timedelta(microseconds=1)
            logging.info(f'Seller_id={seller_id}: Начальная выгрузка с {start_for_downloading_data}')

        # print(last_paid_acceptance_in_db_date)
        date_from_candidate = max(last_paid_acceptance_in_db_date,last_paid_acceptance_checked_date)
        # print(date_from_candidate)
        date_from = date_from_candidate + timedelta(microseconds=1) # - timedelta(days=7)
        # print(date_from)
        # Главный цикл обработки периодов
        while date_from < end_of_yesterday:
            # Рассчитываем конец периода (неделя или остаток дней)
            date_to_candidate = (date_from + timedelta(days=30)).replace(hour=23,minute=59,second=59,microsecond=999999)
            end_of_month = await get_end_of_month(date_from)
            date_to = min(date_to_candidate, end_of_yesterday, end_of_month)

            logging.info(f'Seller_id={seller_id}, платная приемка-обработка периода {str(date_from)}-{str(date_to)}')

            # Выполняем выгрузку

            if await process_paid_acceptance_period(session=session,
                                                    seller_id=seller_id,
                                                    date_from=date_from,
                                                    date_to=date_to):
                logging.info(f'Seller_id={seller_id}, завершили период {str(date_from)}-{str(date_to)}.')
                await set_paid_acceptance_checked_period(session, seller_id, date_to)
                date_from = date_to + timedelta(microseconds=1)
                if date_from <= end_of_yesterday:
                    logging.info(f'Seller_id={seller_id}. Ждем 60 и продолжаем.')
                    await asyncio.sleep(60)
            else:
                await send_message_to_admin(f'Ошибка обработки платной приемки для seller_id={seller_id}')
                return False
        return True

    except Exception as e:
        logging.exception(f"Paid acceptance processing error for seller {seller_id}")
        await send_message_to_admin(f'Ошибка обработки платной приемки для seller_id={seller_id}: {e}')
        return False

async def set_paid_acceptance_checked_period(session, seller_id, date_to):
    async with session.begin_nested():
        query = sqlalchemy.update(DataDates).where(DataDates.seller_id == seller_id).values(last_paid_acceptance_date_checked=date_to)
        await session.execute(query)

    await session.commit()

async def process_paid_acceptance_period(session, seller_id, date_from, date_to):
    try:
        date_from_str = date_from.strftime('%Y-%m-%d')
        date_to_str = date_to.strftime('%Y-%m-%d')

        logging.info(f'Seller_id={seller_id}. Processing period: {date_from_str} - {date_to_str}')

        task_id = await create_paid_acceptance_report(session, seller_id, date_from_str, date_to_str)
        if not task_id:
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str} - no task ID')
            return False

        logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-task_id:{task_id}')
        if await wait_for_paid_acceptance_report_ready(session, seller_id, task_id):
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-task_id:{task_id}-ready')
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-ждем 60 и скачиваем отчет')
            await asyncio.sleep(60)
            status, paid_acceptance_df = await download_paid_acceptance_report(session, seller_id, task_id)
            if status == 'downloaded':
                if not paid_acceptance_df.empty:
                    return await save_paid_acceptance_data(session, seller_id, paid_acceptance_df, date_from, date_to)
                return True
            else:
                return False
        return False

    except Exception as e:
        logging.exception(f"Error processing period {str(date_from)}-{str(date_to)}")
        return False

async def create_paid_acceptance_report(session, seller_id, date_from, date_to):
    try:
        api_key = await get_api_by_seller_id(session, seller_id)
        # print(api_key)
        async with ApiClient(session, seller_id, api_key) as client:
            response = await client.fetch(
                method="GET",
                url=create_paid_acceptance_report_url,
                headers={"Authorization": api_key},
                params={'dateFrom': date_from, 'dateTo': date_to}
            )
            return response.get('data', {}).get('taskId')
    except Exception as e:
        logging.error(f"Report creation failed for {seller_id}: {str(e)}")
        return None

async def wait_for_paid_acceptance_report_ready(session, seller_id, task_id, max_attempts=30):
    check_url = f'https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report/tasks/{task_id}/status'

    try:
        api_key = await get_api_by_seller_id(session, seller_id)
        async with ApiClient(session, seller_id, api_key) as client:
            for attempt in range(max_attempts):
                response = await client.fetch(method="GET",
                                              url=check_url,
                                              headers={"Authorization": api_key})
                status = response.get('data', {}).get('status')

                if status == 'done':
                    logging.info(f'Seller_id={seller_id}. Task_id:{task_id}-отчет готов')
                    return True
                elif status == 'purged' or status == 'canceled':
                    logging.info(f'Seller_id={seller_id}. Task_id:{task_id}-статус отчета {status}.')
                    return False
                else:
                    await asyncio.sleep(5+5 ** attempt)
            logging.info(f'Seller_id={seller_id}. Task_id:{task_id}-превышено максимальное количество попыток.')
            return False
    except Exception as e:
        logging.error(f"Status check failed for {seller_id}: {str(e)}")
        return False

async def download_paid_acceptance_report(session, seller_id, task_id):
    download_url = f'https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report/tasks/{task_id}/download'

    try:
        api_key = await get_api_by_seller_id(session, seller_id)
        async with ApiClient(session, seller_id, api_key) as client:
            response = await client.fetch(method="GET",
                                          url=download_url,
                                          headers={"Authorization": api_key})
            logging.info(f'Seller_id={seller_id}. Task_id:{task_id}-скачали отчет')
            paid_acceptance_df = pd.DataFrame(response)
            status = 'downloaded'
            return status, paid_acceptance_df
    except Exception as e:
        logging.error(f"Report download failed for {seller_id}: {str(e)}")
        paid_acceptance_df = []
        status = 'Error'
        return status, paid_acceptance_df

async def save_paid_acceptance_data(session, seller_id, paid_acceptance_df, date_from, date_to):
    try:

        if paid_acceptance_df.empty:
            logging.info(f"No data for {seller_id} {date_from}-{date_to}")
            return True
        paid_acceptance_df['giCreateDate'] = pd.to_datetime(paid_acceptance_df['giCreateDate']).dt.normalize() + pd.Timedelta('23:59:59.999999')
        paid_acceptance_df['shkCreateDate'] = pd.to_datetime(paid_acceptance_df['shkCreateDate']).dt.normalize() + pd.Timedelta('23:59:59.999999')

        data = paid_acceptance_df.to_dict('records')
        if await bulk_insert_paid_acceptance_data(session, seller_id, data):
            logging.info(f'Seller_id: {seller_id}. Period: {date_from}-{date_to}-Completed')
            return True
    except Exception as e:
        logging.exception(f"Data processing error for {seller_id}")
        return False

async def bulk_insert_paid_acceptance_data(session, seller_id, data):
    try:
        insert_data = []
        for item in data:
            insert_data.append({
                "seller_id": seller_id,
                "count": item['count'],
                "gicreatedate": item['giCreateDate'],
                "incomeid": item['incomeId'],
                "nmid": item['nmID'],
                "shkcreatedate": item['shkCreateDate'],
                "subjectname": item['subjectName'],
                "total": item['total'],
                "is_distributed": False,
                "updated_at": datetime.now()
            })
        async with session.begin_nested():

            for chunk in chunker(insert_data, CHUNK_SIZE_PAID_ACCEPTANCE):
                stmt = insert(Paid_acceptance).values(chunk)
                await session.execute(stmt.on_conflict_do_nothing(
                    constraint='paid_acceptance_unique_constraint'
                        ))

        await session.commit()

        return True

    except Exception as e:
        await session.rollback()
        logging.exception("Bulk insert failed")
        return False
