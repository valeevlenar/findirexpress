import asyncio
import logging
import json
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

# Константы API
WB_SUPPLIES_LIST_URL = "https://supplies-api.wildberries.ru/api/v1/supplies"
WB_SUPPLIES_GOODS_URL_TEMPLATE = "https://supplies-api.wildberries.ru/api/v1/supplies/{}/goods"
WB_SUPPLIES_DETAILS_URL_TEMPLATE = "https://supplies-api.wildberries.ru/api/v1/supplies/{}"

CHUNK_SIZE_SUPPLIES = 1000

# Маппинг статусов
STATUS_MAPPING = {
    1: 'Не запланировано',
    2: 'Запланировано',
    3: 'Отгрузка разрешена',
    4: 'Идёт приёмка',
    5: 'Принято',
    6: 'Отгружено на воротах'
}


def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]


@log_and_notify_admin
async def get_supplies_by_seller_id(session, seller_id):
    try:
        # 1. Определяем дату начала загрузки
        last_acceptance_date_in_db = await session.scalar(
            select(func.max(Supplies.lastchangedate)).where(Supplies.seller_id == seller_id)
        )

        logging.info(f'Seller_id: {seller_id}. last_acceptance_date_in_db: {str(last_acceptance_date_in_db)}')

        # Логика определения типа даты для поиска
        date_type = 'updatedDate'

        if not last_acceptance_date_in_db:
            date_from = await start_for_downloading_data_func()
            date_type = 'createDate'
        else:
            date_from = last_acceptance_date_in_db - timedelta(days=7)
            date_type = 'updatedDate'

        logging.info(f'Seller_id: {seller_id}. Ищем поставки с {date_from} по типу {date_type}')

        # 2. Получаем список поставок (Headers)
        supplies_list = await get_supplies_list_from_wb(session, seller_id, date_from, date_type)

        if not supplies_list:
            logging.info(f'Seller_id: {seller_id}. Нет новых поставок с {date_from}')
            return True

        logging.info(f'Seller_id: {seller_id}. Найдено {len(supplies_list)} поставок для проверки.')

        full_supplies_data = []
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)

        # Здесь создается клиент с ключом
        async with ApiClient(session, seller_id, active_api) as client:
            for i, supply in enumerate(supplies_list):
                supply_id = supply.get('supplyID')
                if not supply_id:
                    continue

                # --- ШАГ 1: Получаем товары ---
                goods = await get_supply_goods_from_wb(client, supply_id)
                await asyncio.sleep(1.0)

                if not goods:
                    continue

                # --- ШАГ 2: Получаем детали (ради warehouseName) ---
                details = await get_supply_details_from_wb(client, supply_id)
                await asyncio.sleep(1.2)

                warehouse_name = details.get('warehouseName') if details else None

                # Собираем данные
                for item in goods:
                    status_id = supply.get('statusID')
                    status_text = STATUS_MAPPING.get(status_id, str(status_id))

                    row = {
                        'incomeid': supply_id,
                        'nmid': item.get('nmID'),
                        'supplierarticle': item.get('vendorCode'),
                        'techsize': item.get('techSize'),
                        'barcode': item.get('barcode'),

                        'date': supply.get('createDate'),
                        'dateclose': supply.get('factDate'),
                        'lastchangedate': supply.get('updatedDate'),

                        'quantity': item.get('acceptedQuantity') if status_id == 5 else item.get('quantity'),

                        'status': status_text,
                        'warehousename': warehouse_name,
                    }
                    full_supplies_data.append(row)

                if i % 10 == 0:
                    logging.info(f'Seller_id: {seller_id}. Обработано {i + 1} из {len(supplies_list)} поставок.')

        # 4. Создаем DataFrame и сохраняем
        if not full_supplies_data:
            logging.info(f'Seller_id: {seller_id}. Данные получены, но итоговая таблица пуста.')
            return True

        acceptance_reports_df = pd.DataFrame(full_supplies_data)

        lastchangedate, acceptance_reports_filtered_df = await prepare_acceptance_report(seller_id,
                                                                                         acceptance_reports_df)

        if acceptance_reports_filtered_df.empty:
            logging.info(f'Seller_id: {seller_id}. Нет данных для сохранения после фильтрации.')
            return True

        if await bulk_save_supplies(session=session,
                                    seller_id=seller_id,
                                    acceptance_report_df=acceptance_reports_filtered_df):
            logging.info(f'Seller_id: {seller_id}. Успешно сохранено.')
            return True
        else:
            await send_message_to_admin(f'Ошибка в сохранении поставок seller_id: {seller_id}')
            return False

    except Exception as e:
        await send_message_to_admin(f'Критическая ошибка (get_supplies_by_seller_id): {seller_id}\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return False


async def get_supplies_list_from_wb(session, seller_id, date_from, date_type='updatedDate'):
    """POST /v1/supplies - список поставок"""
    all_supplies = []
    active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)

    # Здесь заголовки формируются явно, поэтому первый запрос работал
    headers = {'Authorization': active_api, 'Content-Type': 'application/json'}

    if isinstance(date_from, datetime):
        date_from_str = date_from.strftime('%Y-%m-%d')
    else:
        date_from_str = str(date_from).split('T')[0]

    date_till_str = datetime.now().strftime('%Y-%m-%d')

    url = WB_SUPPLIES_LIST_URL
    limit = 1000
    current_offset = 0
    has_more = True

    try:
        async with ApiClient(session, seller_id, active_api) as client:
            while has_more:
                params = {'limit': limit, 'offset': current_offset}

                payload = {
                    "dates": [
                        {
                            "from": date_from_str,
                            "till": date_till_str,
                            "type": date_type
                        }
                    ]
                }

                logging.info(f"[DEBUG] Requesting URL: {url}")
                logging.info(f"[DEBUG] Params: {params}")

                result = await client.fetch(
                    method="POST",
                    url=url,
                    headers=headers,
                    params=params,
                    json=payload
                )

                if result:
                    count = len(result) if isinstance(result, list) else len(result.get('supplies', []))
                    logging.info(f"[DEBUG] Result Count: {count}")
                else:
                    logging.info(f"[DEBUG] Result is Empty/None")

                current_batch = []

                if isinstance(result, dict):
                    current_batch = result.get('supplies', [])
                    if 'next' in result and isinstance(result['next'], int) and result['next'] > 0:
                        current_offset = result['next']
                    else:
                        current_offset += limit
                    has_more = len(current_batch) > 0

                elif isinstance(result, list):
                    current_batch = result
                    current_offset += limit
                    has_more = len(current_batch) >= limit
                else:
                    logging.warning(f"[DEBUG] Unexpected result format: {result}")
                    break

                all_supplies.extend(current_batch)

                if not current_batch:
                    has_more = False

                await asyncio.sleep(0.5)

        return all_supplies

    except Exception as e:
        logging.error(f"Error fetching supplies list for {seller_id}: {e}")
        return []


async def get_supply_goods_from_wb(client, supply_id):
    """GET /v1/supplies/{id}/goods - товары в поставке"""
    url = WB_SUPPLIES_GOODS_URL_TEMPLATE.format(supply_id)
    # ИСПРАВЛЕНИЕ: Формируем заголовки, используя ключ из client
    headers = {'Authorization': client.api_key}

    try:
        # ИСПРАВЛЕНИЕ: Передаем headers в fetch
        result = await client.fetch(
            method="GET",
            url=url,
            headers=headers,
            params={'limit': 1000}
        )

        if isinstance(result, dict) and 'goods' in result:
            return result['goods']
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logging.warning(f"Error fetching goods for supply {supply_id}: {e}")
        return []


async def get_supply_details_from_wb(client, supply_id):
    """GET /v1/supplies/{id} - детали поставки"""
    url = WB_SUPPLIES_DETAILS_URL_TEMPLATE.format(supply_id)
    # ИСПРАВЛЕНИЕ: Формируем заголовки, используя ключ из client
    headers = {'Authorization': client.api_key}

    try:
        # ИСПРАВЛЕНИЕ: Передаем headers в fetch
        result = await client.fetch(
            method="GET",
            url=url,
            headers=headers
        )

        if isinstance(result, dict):
            return result
        return None
    except Exception as e:
        logging.warning(f"Error fetching details for supply {supply_id}: {e}")
        return None


async def prepare_acceptance_report(seller_id, acceptance_reports_df):
    try:
        df = acceptance_reports_df.copy()
        if df.empty:
            return None, df

        date_columns = ['date', 'lastchangedate', 'dateclose']
        for col in date_columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)

        mask = df['dateclose'].isna()
        df.loc[mask, 'dateclose'] = df.loc[mask, 'lastchangedate']

        mask2 = df['lastchangedate'].isna()
        df.loc[mask2, 'lastchangedate'] = df.loc[mask2, 'date']

        df['transaction_date'] = df['dateclose']

        for col in date_columns + ['transaction_date']:
            df[col] = df[col].dt.tz_localize(None)

        df = df.sort_values(by='lastchangedate')

        if not df.empty:
            lastchangedate = df['lastchangedate'].iloc[-1]
        else:
            lastchangedate = None

        return lastchangedate, df

    except Exception as e:
        await send_message_to_admin(f'Ошибка в prepare_acceptance_report seller_id: {seller_id}\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return None, pd.DataFrame()


async def bulk_save_supplies(session, seller_id, acceptance_report_df):
    if not acceptance_report_df.empty:
        try:
            acceptance_report_df = acceptance_report_df.where(pd.notnull(acceptance_report_df), None)
            acceptance_report_data = acceptance_report_df.to_dict('records')

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
                            'updated_at': stmt.excluded.updated_at,
                            'nmid': stmt.excluded.nmid,
                            'supplierarticle': stmt.excluded.supplierarticle,
                            'techsize': stmt.excluded.techsize,
                            'warehousename': stmt.excluded.warehousename
                        }
                    )
                    await session.execute(stmt)
            await session.commit()
            logging.info(f'Seller {seller_id}: Inserted/Updated {len(supplies_to_insert)} supplies rows')
            return True

        except Exception as e:
            await session.rollback()
            await send_message_to_admin(f'Ошибка bulk_save_supplies seller_id: {seller_id}\n{e}')
            logging.exception("An error occurred: %s", exc_info=e)
            return False
    return True