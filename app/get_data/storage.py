# -*- coding: utf-8 -*-
import asyncio
from datetime import timedelta, datetime
import pandas as pd
import logging
from sqlalchemy import select, func
from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import async_session, Seller, Storage_costs
from app.database.support_functions import get_api_by_seller_id
from app.dates import end_of_yesterday_func, start_for_downloading_data_func, \
    yesterday_str_func
from app.wrappers import log_and_notify_admin, with_session
from config import storage_report_creation_url
from sqlalchemy.dialects.postgresql import insert

CHUNK_SIZE_STORAGE = 500

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

@with_session
async def daily_get_storage_data(session):
    try:
        companies = await session.execute(select(Seller.id).
                                          where(Seller.status=='Active',
                                                Seller.service_status==True))
        companies = companies.mappings().all()

        # Создаем список корутин
        tasks = [get_storage_costs_by_seller(session=session, seller_id=seller['id']) for seller in companies]

        # Запускаем все корутины параллельно
        await asyncio.gather(*tasks)

        await admin_storage_download_status()
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в ежедневной функции по выгрузке хранения'
                                         f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def get_storage_costs_by_seller(session,seller_id):

    try:
        logging.info(f'Seller_id={seller_id}. Начало выгрузки хранения')

        # Получаем последнюю дату в базе
        last_storage_in_db_date = await session.scalar(select(func.max(Storage_costs.cost_date)).
                                                              where(Storage_costs.seller_id == seller_id))

        end_of_yesterday = await end_of_yesterday_func()
        start_for_downloading_data = await start_for_downloading_data_func()

        # Если нет данных в БД, начинаем с начальной даты
        if not last_storage_in_db_date:
            last_storage_in_db_date = start_for_downloading_data - timedelta(microseconds=1)
            logging.info(f'Seller_id={seller_id}: Начальная выгрузка с {start_for_downloading_data}')

        date_from = last_storage_in_db_date + timedelta(microseconds=1)

        # Главный цикл обработки периодов
        while date_from <= end_of_yesterday:
            # Рассчитываем конец периода (неделя или остаток дней)
            date_to_candidate = (date_from + timedelta(days=6)).replace(hour=23,minute=59,second=59,microsecond=999999)

            date_to = min(date_to_candidate, end_of_yesterday)

            logging.info(f'Seller_id={seller_id}, хранение-обработка недели {str(date_from)}-{str(date_to)}')

            # Выполняем выгрузку

            if await process_storage_period(session=session,
                                            seller_id=seller_id,
                                            date_from=date_from,
                                            date_to=date_to):
                logging.info(f'Seller_id={seller_id}, завершили период {str(date_from)}-{str(date_to)}. Ждем 60 и продолжаем.')
                date_from = date_to + timedelta(microseconds=1)
            else:
                break

        return True

    except Exception as e:
        logging.exception(f"Storage processing error for seller {seller_id}")
        await send_message_to_admin(f'Ошибка обработки хранения для seller_id={seller_id}: {e}')
        return False


async def process_storage_period(session, seller_id, date_from, date_to):
    try:
        date_from_str = date_from.strftime('%Y-%m-%d')
        date_to_str = date_to.strftime('%Y-%m-%d')

        logging.info(f'Seller_id={seller_id}. Processing period: {date_from_str} - {date_to_str}')

        task_id = await create_storage_report(session, seller_id, date_from_str, date_to_str)
        if not task_id:
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str} - no task ID')
            return False

        logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-task_id:{task_id}')
        if await wait_for_report_ready(session, seller_id, task_id):
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-task_id:{task_id}-ready')
            logging.info(f'Seller_id={seller_id}. Period: {date_from_str}-{date_to_str}-ждем 60 и скачиваем отчет')
            await asyncio.sleep(60)
            report_data = await download_storage_report(session, seller_id, task_id)
            storage_df = pd.DataFrame(report_data)

            if storage_df.empty:
                logging.info(f"No data for {seller_id} {date_from}-{date_to}")
                return True

            else:
                return await save_storage_data(session, seller_id, storage_df, date_from, date_to)

        return False

    except Exception as e:
        logging.exception(f"Error processing period {str(date_from)}-{str(date_to)}")
        return False

async def create_storage_report(session, seller_id, date_from, date_to):
    try:
        api_key = await get_api_by_seller_id(session, seller_id)
        # print(api_key)
        async with ApiClient(session, seller_id, api_key) as client:
            response = await client.fetch(
                method="GET",
                url=storage_report_creation_url,
                headers={"Authorization": api_key},
                params={'dateFrom': date_from, 'dateTo': date_to}
            )
            return response.get('data', {}).get('taskId')
    except Exception as e:
        logging.error(f"Report creation failed for {seller_id}: {str(e)}")
        return None

async def wait_for_report_ready(session, seller_id, task_id, max_attempts=30):
    check_url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/status'

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


async def download_storage_report(session, seller_id, task_id):
    download_url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download'

    try:
        api_key = await get_api_by_seller_id(session, seller_id)
        async with ApiClient(session, seller_id, api_key) as client:
            response = await client.fetch(method="GET",
                                          url=download_url,
                                          headers={"Authorization": api_key})
            logging.info(f'Seller_id={seller_id}. Task_id:{task_id}-скачали отчет')
            return response
    except Exception as e:
        logging.error(f"Report download failed for {seller_id}: {str(e)}")
        return None

async def save_storage_data(session, seller_id, storage_df, date_from, date_to):
    try:
        if storage_df.empty:
            logging.info(f"No data for {seller_id} {date_from}-{date_to}")
            return True

        storage_df['cost_date'] = pd.to_datetime(storage_df['date']).dt.normalize() + pd.Timedelta('23:59:59.999999')
        grouped = storage_df.groupby([
            'cost_date', 'warehouse', 'chrtId', 'size', 'barcode',
            'subject', 'brand', 'vendorCode', 'nmId'
        ]).agg({
            'warehousePrice': 'sum',
            'barcodesCount': 'sum',
            'loyaltyDiscount': 'sum'
        }).reset_index()

        data = grouped.to_dict('records')
        if await bulk_insert_storage_data(session, seller_id, data):
            logging.info(f'Seller_id: {seller_id}. Period: {date_from}-{date_to}-Completed')
            return True
    except Exception as e:
        logging.exception(f"Data processing error for {seller_id}")
        return False


async def bulk_insert_storage_data(session, seller_id, data):
    try:
        insert_data = []
        for item in data:
            insert_data.append({
                "seller_id": seller_id,
                "cost_date": item['cost_date'],
                "warehouse": item['warehouse'],
                "chrtid": item['chrtId'],
                "size": item['size'],
                "barcode": item['barcode'],
                "subject": item['subject'],
                "brand": item['brand'],
                "vendor_code": item['vendorCode'],
                "nmid": item['nmId'],
                "warehouseprice": item['warehousePrice'],
                "barcodescount": item['barcodesCount'],
                "loyaltyDiscount": item['loyaltyDiscount'],
                "updated_at": datetime.now()
            })
        async with session.begin_nested():

            for chunk in chunker(insert_data, CHUNK_SIZE_STORAGE):
                stmt = insert(Storage_costs).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint='storage_unique_constraint',
                    set_={
                        'warehouseprice': stmt.excluded.warehouseprice,
                        'barcodescount': stmt.excluded.barcodescount,
                        'loyaltyDiscount': stmt.excluded.loyaltyDiscount,
                        'updated_at': stmt.excluded.updated_at
                    }
                )
                await session.execute(stmt)

        await session.commit()

        return True

    except Exception as e:
        await session.rollback()
        logging.exception("Bulk insert failed")
        return False

async def admin_storage_download_status():
    async with async_session() as session:
        active_companies = await session.scalar(select(func.count(Seller.id)).
                                                 where(Seller.status=='Active',
                                                       Seller.service_status==True))
        end_of_yesterday = await end_of_yesterday_func()
        yesterday_str = await yesterday_str_func()
        storage_companies = await session.scalar(select(func.count()).
                                               select_from(select(Storage_costs.seller_id).
                                                           where(Storage_costs.cost_date == end_of_yesterday).
                                                           group_by(Storage_costs.seller_id).subquery()))
        storage_rows = await session.scalar(select(func.count(Storage_costs.id)).
                                               where(Storage_costs.cost_date == end_of_yesterday))
        download_report = (f'Отчет по загрузке расходов на хранение за {yesterday_str}:'
                         f'\nВсего активных компаний: {active_companies}'
                        f'\nЗагружено заказов по компаниям: {storage_companies}'
                         f'\nЗагружено строк: {storage_rows}')
        await send_message_to_admin(download_report)
