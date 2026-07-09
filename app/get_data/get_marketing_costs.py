import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
from sqlalchemy import select, func
from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import Marketing_costs_wb
from app.database.support_functions import get_api_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_yesterday_func, get_end_of_month
from config import marketing_costs_url

CHUNK_SIZE_MARKETING = 500

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

async def get_marketing_costs_for_seller_id(session, seller_id):
    try:
        latest_marketing_costs_in_db_date = await session.scalar(select(func.max(Marketing_costs_wb.cost_date)).
                                                           where(Marketing_costs_wb.seller_id == seller_id))
        end_of_yesterday = await end_of_yesterday_func()
        start_for_downloading_data = await start_for_downloading_data_func()

        if not latest_marketing_costs_in_db_date:
            latest_marketing_costs_in_db_date = start_for_downloading_data - timedelta(microseconds=1)
            logging.info(f'Seller_id={seller_id}: Начальная выгрузка с {start_for_downloading_data}')

        date_from = latest_marketing_costs_in_db_date + timedelta(microseconds=1) - timedelta(days=1)

        while date_from < end_of_yesterday:
            # Рассчитываем конец периода (неделя или остаток дней)
            date_to_candidate = (date_from + timedelta(days=30)).replace(hour=23, minute=59, second=59,
                                                                         microsecond=999999)
            end_of_month = await get_end_of_month(date_from)
            date_to = min(date_to_candidate, end_of_yesterday, end_of_month)
            logging.info(f'Seller_id={seller_id}, обработка периода {str(date_from)}-{str(date_to)}')

            if await process_marketing_costs_period(session=session,
                                                    seller_id=seller_id,
                                                    date_from=date_from,
                                                    date_to=date_to):

                logging.info(f'Seller_id={seller_id}, завершили период {str(date_from)}-{str(date_to)}.')

                date_from = date_to + timedelta(microseconds=1)
                if date_from < end_of_yesterday:
                    logging.info(f'Seller_id={seller_id}. Ждем 5 и продолжаем.')
                    await asyncio.sleep(5)
            else:
                return False

        return True

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке маркетинговых расходов по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def process_marketing_costs_period(session, seller_id, date_from, date_to):
    try:
        marketing_costs_df = await get_marketing_costs_from_wb(session=session,
                                                               seller_id=seller_id,
                                                               date_from=date_from,
                                                               date_to=date_to)
        if not marketing_costs_df.empty:
            logging.info(f'Seller_id={seller_id}, период: {str(date_from)}-{str(date_to)}-выгрузили расходы.')

            if await save_marketing_costs_to_db(session=session,
                                                seller_id=seller_id,
                                                marketing_costs_df=marketing_costs_df):
                logging.info(f'Seller_id={seller_id}, период: {str(date_from)}-{str(date_to)}-сохранили в базу.')
                return True
            else:
                return False
        else:
            logging.info(f'Seller_id={seller_id}, период: {str(date_from)}-{str(date_to)}-нет расходов.')
            return True

    except Exception as e:
        logging.exception(f"Error processing period {str(date_from)}-{str(date_to)}")
        return False

async def get_marketing_costs_from_wb (session, seller_id, date_from, date_to):
    try:
        date_from_str = datetime.strftime(date_from,'%Y-%m-%d')
        date_to_str = datetime.strftime(date_to,'%Y-%m-%d')
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        params = {'from': date_from_str, 'to': date_to_str}

        async with ApiClient(session, seller_id, active_api) as client:
            response = await client.fetch(method="GET",
                                          url=marketing_costs_url,
                                          headers={"Authorization": active_api},
                                          params=params)

            if not response:
                return pd.DataFrame()

            df = pd.DataFrame(response)
            if not df.empty:
                # df['cost_date'] = pd.to_datetime(df['updTime']).dt.tz_localize(None).dt.normalize() + pd.Timedelta('23:59:59.999999') версия от бота
                df['cost_date'] = (pd.to_datetime(df.updTime,format='ISO8601').dt.tz_localize(None)).dt.normalize() + pd.Timedelta('23:59:59.999999')
                # df.to_excel('история марк затрат.xlsx')
                return df[df['cost_date'] <= await end_of_yesterday_func()]
            return pd.DataFrame()

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке маркетинговых расходов:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return pd.DataFrame()

async def save_marketing_costs_to_db(session, seller_id, marketing_costs_df):
    try:
        marketing_data = []
        for record in marketing_costs_df.to_dict('records'):
            marketing_data.append({
                'seller_id': seller_id,
                'cost_date': record['cost_date'],
                'updtime': record['updTime'],
                'campname': record['campName'],
                'paymenttype': record['paymentType'],
                'updnum': record['updNum'],
                'updsum': record['updSum'],
                'advertid': record['advertId'],
                'adverttype': record['advertType'],
                'advertstatus': record['advertStatus'],
                'cost_allocated': False,
                'updated_at': datetime.now()
            })
        async with session.begin_nested():

            for chunk in chunker(marketing_data, CHUNK_SIZE_MARKETING):
                stmt = insert(Marketing_costs_wb).values(chunk)

                await session.execute(stmt.on_conflict_do_nothing(
                    constraint='marketing_costs_unique_constraint'
                ))

        await session.commit()
        return True

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False
