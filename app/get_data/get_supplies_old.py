import asyncio
import logging
from datetime import timedelta, datetime
import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import Supplies
from app.database.support_functions import get_api_by_seller_id
from app.dates import start_for_downloading_data_func
from app.wrappers import log_and_notify_admin
from config import supplies_url

CHUNK_SIZE_SUPPLIES = 1000  # Размер пакета для bulk-операций

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

@log_and_notify_admin
async def get_supplies_by_seller_id(session, seller_id):
    try:
        # Смотрим, есть ли акты приемки в базе:
        last_acceptance_date_in_db = await session.scalar(select(func.max(Supplies.lastchangedate)).
                                                            where(Supplies.seller_id == seller_id))

        logging.info(f'Seller_id: {seller_id}. last_acceptance_date_in_db: {str(last_acceptance_date_in_db)}')

        # Считаем даты для выгрузки:
        if not last_acceptance_date_in_db:
            date_from = await start_for_downloading_data_func()
        else:
            date_from = last_acceptance_date_in_db - timedelta(days=7)

        #Выгружаем в цикле, чтобы выгрузить все акты приемки
        status = 'pending'
        supply_counter=1
        while status != 'done' and supply_counter<5:
            date_from_utc = date_from.isoformat()
            acceptance_reports_df = await get_acceptance_report_from_wb(session=session,
                                                                        seller_id=seller_id,
                                                                        date_from=date_from_utc)
            # print(acceptance_reports_df)
            # Если есть акты приемки, то фильтруем по "Принято" и сохраняем в базу:
            if not acceptance_reports_df.empty:
                logging.info(f'Seller_id: {seller_id}. Выгрузили акты приемки с:{str(date_from)}')
                lastchangedate, acceptance_reports_filtered_df = await prepare_acceptance_report(seller_id, acceptance_reports_df)

                if acceptance_reports_filtered_df.empty:
                    logging.info(f'Seller_id: {seller_id}. Выгрузили акты приемки с:{str(date_from)}-нет данных для сохранения')
                    status = 'done'
                    return True

                if lastchangedate is None:
                    await send_message_to_admin(f'Ошибка в обработке актов приемки по селлеру: {seller_id}')
                    return False

                if await bulk_save_supplies(session=session,
                                            seller_id=seller_id,
                                            acceptance_report_df=acceptance_reports_filtered_df):
                    date_from = lastchangedate + timedelta(microseconds=1)
                    logging.info(f'Seller_id: {seller_id}. Ждем 60 и пробуем выгружать дальше.')
                    supply_counter +=1
                    await asyncio.sleep(60)
                else:
                    await send_message_to_admin(f'Ошибка в сохранении актов приемки по селлеру:'
                                                f'\nseller_id: {seller_id}')
                    return False

            # Если нет актов приемки, то выходим из цикла
            else:
                logging.info(f'Seller_id: {seller_id}. Выгружаем акты приемки. Выгрузили с:{str(date_from)}. Нет актов приемки.')
                status = 'done'
                return True

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке актов приемки по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def get_acceptance_report_from_wb (session, seller_id, date_from):
    try:
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = {'dateFrom': date_from}

        async with ApiClient(session, seller_id, active_api) as client:
            result = await client.fetch(
                method="GET",
                url=supplies_url,
                headers=headers,
                params=params
            )
        result_df = pd.DataFrame(result)

        # print(result)
        # print(res.text)
        # result_df.to_excel('поставки.xlsx')
        return result_df

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке актов приемки по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def prepare_acceptance_report(seller_id, acceptance_reports_df):
    try:
        # print(acceptance_reports_df)
        # acceptance_reports_filtered_df = acceptance_reports_df[(acceptance_reports_df['status'] == 'Принято')].copy()
        acceptance_reports_filtered_df = acceptance_reports_df.copy()

        # Проверяем, не пуст ли DataFrame после фильтрации
        if acceptance_reports_filtered_df.empty:
            logging.info(f'Seller_id {seller_id}: Нет данных для обработки.')
            return None, acceptance_reports_filtered_df

        # Сначала переименовываем столбцы
        acceptance_reports_filtered_df = acceptance_reports_filtered_df.rename(columns={
            'warehouseName': 'warehousename',
            'nmId': 'nmid',
            'dateClose': 'dateclose',
            'lastChangeDate': 'lastchangedate',
            'incomeId': 'incomeid',
            'supplierArticle': 'supplierarticle',
            'techSize': 'techsize'
        })

        # Затем работаем с переименованными столбцами
        date_columns = ['date', 'lastchangedate', 'dateclose']
        for col in date_columns:
            acceptance_reports_filtered_df.loc[:, col] = pd.to_datetime(
                acceptance_reports_filtered_df[col],
                errors='coerce',
                format='ISO8601'
            )

        # Создаем маску для некорректных dateclose
        mask = (
                acceptance_reports_filtered_df['dateclose'].isna() |
                (acceptance_reports_filtered_df['dateclose'] < pd.Timestamp.min) |
                (acceptance_reports_filtered_df['dateclose'] > pd.Timestamp.max)
        )
        # Заменяем некорректные значения dateclose на lastchangedate
        acceptance_reports_filtered_df.loc[mask, 'dateclose'] = acceptance_reports_filtered_df.loc[
            mask, 'lastchangedate']

        # Добавление transaction_date
        acceptance_reports_filtered_df['transaction_date'] = acceptance_reports_filtered_df['dateclose']

        # Удаляем столбец totalPrice если он существует
        if 'totalPrice' in acceptance_reports_filtered_df.columns:
            del acceptance_reports_filtered_df['totalPrice']


        # # Фильтрация оставшихся некорректных дат
        # acceptance_reports_filtered_df = acceptance_reports_filtered_df[
        #     (acceptance_reports_filtered_df['dateclose'] >= pd.Timestamp.min) &
        #     (acceptance_reports_filtered_df['dateclose'] <= pd.Timestamp.max)
        #     ]
        #
        # if acceptance_reports_filtered_df.empty:
        #     return None, acceptance_reports_filtered_df

        lastchangedate = acceptance_reports_filtered_df['lastchangedate'].iloc[-1]
        return lastchangedate, acceptance_reports_filtered_df

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в обработке актов приемки по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return None, pd.DataFrame()

async def bulk_save_supplies(session, seller_id, acceptance_report_df):
    if not acceptance_report_df.empty:
        try:
            acceptance_report_data = acceptance_report_df.to_dict('records')

            # Пакетная вставка актов приемки
            supplies_to_insert = [{
                **supply,
                'seller_id': seller_id,
                'supply_cost_per_item': 0,
                'total_supply_costs': 0,
                'cost_calculated': False,
                'updated_at': datetime.now()

            } for supply in acceptance_report_data]

            async with session.begin_nested():
                for chunk in chunker(supplies_to_insert, CHUNK_SIZE_SUPPLIES):
                    stmt = insert(Supplies).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        constraint='supplies_unique_constraint',
                        set_={
                            'date': stmt.excluded.date,
                            'lastchangedate': stmt.excluded.lastchangedate,
                            'quantity': stmt.excluded.quantity,
                            'dateclose': stmt.excluded.dateclose,
                            'status': stmt.excluded.status,
                            'transaction_date': stmt.excluded.transaction_date,
                            'updated_at': stmt.excluded.updated_at
                        }
                    )

                    await session.execute(stmt)
            await session.commit()
            logging.info(f'Seller {seller_id}: Inserted {len(supplies_to_insert)} supplies')
            return True

        except Exception as e:
            await session.rollback()
            await send_message_to_admin(f'Ошибка в сохранении актов приемки по селлеру:'
                                        f'\nseller_id: {seller_id}'
                                        f'\nОшибка: {e}')
            logging.exception("An error occurred: %s", exc_info=e)

