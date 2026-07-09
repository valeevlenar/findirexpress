import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from app.admin.admin_message import send_message_to_admin

from app.database.apirequests import ApiClient
from app.database.models import async_session, Orders, Seller, Goods_cost
from app.database.support_functions import get_api_by_seller_id, get_seller_inn_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_yesterday_func, yesterday_str_func
from app.wrappers import log_and_notify_admin
from config import get_orders_url

CHUNK_SIZE_GOODS_COST = 500
CHUNK_SIZE_ORDERS = 500


def chunker(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


# Убрали @with_session
async def daily_get_orders_data():
    try:
        # Сессия №1: только чтобы достать селлеров
        async with async_session() as session:
            companies = await session.execute(select(Seller.id).
                                              where(Seller.status == 'Active',
                                                    Seller.service_status == True))
            companies = companies.mappings().all()

        for seller in companies:
            seller_id = seller['id']
            # Передаем только seller_id
            await get_orders_by_seller(seller_id=seller_id)

            # Делаем паузу между селлерами, чтобы размазать нагрузку
            await asyncio.sleep(5)

        await admin_orders_download_status()
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в ежедневной функции по выгрузке заказов'
                                         f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


@log_and_notify_admin
async def get_orders_by_seller(seller_id):
    try:
        end_of_yesterday = await end_of_yesterday_func()

        # Сессия №2: узнать последнюю дату и апи-ключ
        async with async_session() as session:
            last_orders_in_db_date = await session.scalar(
                select(Orders.order_date)
                .where(Orders.seller_id == seller_id)
                .order_by(Orders.order_date.desc())
            )
            active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)

        logging.info(f'Seller_id: {seller_id}. Last order date: {last_orders_in_db_date}')

        if not active_api:
            return False

        if not last_orders_in_db_date:
            return await handle_initial_upload(seller_id=seller_id,
                                               active_api=active_api,
                                               end_of_yesterday=end_of_yesterday)

        if last_orders_in_db_date >= end_of_yesterday:
            logging.info(f'Seller_id: {seller_id}. Orders already uploaded')
            return True

        return await handle_incremental_upload(seller_id=seller_id,
                                               active_api=active_api,
                                               last_date=last_orders_in_db_date,
                                               end_of_yesterday=end_of_yesterday)

    except Exception as e:
        await handle_error(f'Main orders processing error (seller {seller_id})', e)


@log_and_notify_admin
async def handle_initial_upload(seller_id, active_api, end_of_yesterday):
    date_from = await start_for_downloading_data_func()
    date_from_str = date_from.strftime('%Y-%m-%d')

    orders_df = await get_orders_data(seller_id=seller_id, active_api=active_api, date_from=date_from_str, flag=0)
    if orders_df.empty:
        logging.info(f'Seller_id: {seller_id}. No initial orders')
        return True

    last_date = orders_df['order_date'].max()
    filtered_df = orders_df[orders_df['order_date'] != last_date]

    if not filtered_df.empty:
        logging.info(f'Seller_id: {seller_id}. Сохраняем заказы c {date_from_str}')
        await bulk_save_orders(seller_id, filtered_df.to_dict('records'))

    if last_date < end_of_yesterday:
        return await handle_incremental_upload(seller_id=seller_id,
                                               active_api=active_api,
                                               last_date=last_date,
                                               end_of_yesterday=end_of_yesterday)

    return True


@log_and_notify_admin
async def handle_incremental_upload(seller_id, active_api, last_date, end_of_yesterday):
    try:
        date_str = last_date.strftime('%Y-%m-%d')
        logging.info(f'Seller_id: {seller_id}. Дозагрузка данных. Делаем ОДИН запрос с {date_str} по сейчас.')

        # БД закрыта. Спокойно ждем WB.
        orders_data = await get_orders_data(
            seller_id=seller_id,
            active_api=active_api,
            date_from=date_str,
            flag=0
        )

        if not orders_data.empty:
            filtered_df = orders_data[pd.to_datetime(orders_data['order_date']) <= pd.to_datetime(end_of_yesterday)]

            if not filtered_df.empty:
                logging.info(
                    f'Seller_id: {seller_id}. Нашли {len(filtered_df)} строк за пропущенный период. Сохраняем...')
                await bulk_save_orders(seller_id, filtered_df.to_dict('records'))
            else:
                logging.info(f'Seller_id: {seller_id}. Новых заказов до даты {end_of_yesterday} не найдено.')
        else:
            logging.info(f'Seller_id: {seller_id}. API WB вернул пустой список заказов.')

        logging.info(f'Seller_id: {seller_id}. Успешно обработан. Пауза 65с перед следующим селлером.')
        await asyncio.sleep(65)

        return True

    except Exception as e:
        await handle_error(f'Incremental upload error (seller {seller_id})', e)
        return False


@log_and_notify_admin
async def get_orders_data(seller_id, active_api, date_from, flag):
    try:
        async with ApiClient(seller_id=seller_id) as client:
            orders_data = await client.fetch(
                method="GET",
                url=get_orders_url,
                headers={"Authorization": active_api},
                params={'dateFrom': date_from, 'flag': flag}
            )
        if orders_data:
            return process_orders_data(orders_data)
        else:
            return pd.DataFrame()

    except Exception as e:
        await handle_error(f'Orders data fetch error (seller {seller_id})', e)
        return pd.DataFrame()


def process_orders_data(data):
    df = pd.DataFrame(data)
    if df.empty:
        return df

    try:
        df['order_date'] = pd.to_datetime(df['date']).dt.normalize() + pd.Timedelta('23:59:59.999999')
        df['quantity'] = 1

        df = df.rename(columns={
            'supplierArticle': 'supplier_article',
            'nmId': 'nmid',
            'techSize': 'techsize',
            'totalPrice': 'totalprice',
            'discountPercent': 'discountpercent',
            'finishedPrice': 'finishedprice',
            'priceWithDisc': 'pricewithdisc'
        })

        if 'pricewithdisc' in df.columns:
            df['total_sum'] = df['pricewithdisc']
        else:
            df['total_sum'] = 0.0

        group_cols = [
            'order_date', 'supplier_article', 'nmid',
            'barcode', 'category', 'subject',
            'brand', 'techsize'
        ]

        agg_dict = {'total_sum': 'sum', 'quantity': 'sum'}
        new_cols = ['totalprice', 'discountpercent', 'spp', 'finishedprice', 'pricewithdisc']

        for col in new_cols:
            if col in df.columns:
                agg_dict[col] = 'first'

        grouped = df.groupby(group_cols).agg(agg_dict).reset_index()
        grouped = grouped.where(pd.notnull(grouped), None)
        return grouped

    except KeyError as e:
        logging.error(f"KeyError in process_orders_data: {e}")
        return pd.DataFrame()


@log_and_notify_admin
async def bulk_save_orders(seller_id, orders_data):
    if not orders_data:
        return

    try:
        # Открываем сессию
        async with async_session() as session:
            # Начинаем транзакцию СРАЗУ, до любых запросов в базу!
            async with session.begin():
                # Теперь это чтение происходит внутри нашей явной транзакции
                seller_inn = await get_seller_inn_by_seller_id(session, seller_id)

                # Вложенная транзакция (begin_nested) внутри отработает отлично
                await bulk_upsert_orders_barcodes(session, seller_id, seller_inn, orders_data)

                # Пакетная вставка заказов
                orders_to_insert = [{
                    **order,
                    'seller_id': seller_id,
                    'updated_at': datetime.now()
                } for order in orders_data]

                for chunk in chunker(orders_to_insert, CHUNK_SIZE_ORDERS):
                    stmt = insert(Orders).values(chunk)

                    # === ВОТ ЗДЕСЬ МЕНЯЕМ ЛОГИКУ СОХРАНЕНИЯ ===
                    # Указываем базе: если заказ с таким seller_id, order_date и barcode уже есть,
                    # то просто обнови его количество, сумму и дату изменения.
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['seller_id', 'order_date', 'barcode'],
                        set_={
                            'quantity': stmt.excluded.quantity,
                            'total_sum': stmt.excluded.total_sum,
                            'updated_at': stmt.excluded.updated_at
                        }
                    )
                    await session.execute(stmt)
                    # ==========================================

            # Блок async with session.begin() сам сделает commit() здесь!
            logging.info(f'Seller {seller_id}: Inserted/Updated {len(orders_to_insert)} orders')

    except Exception as e:
        await handle_error(f'Bulk save error (seller {seller_id})', e)


async def bulk_upsert_orders_barcodes(session, seller_id, seller_inn, items):
    unique_barcodes = {}
    for item in items:
        if barcode := item.get("barcode"):
            key = (seller_id, barcode)
            unique_barcodes[key] = {
                "seller_id": seller_id,
                "seller_inn": seller_inn,
                "barcode": barcode,
                "subject_name": item.get("subject"),
                "nm_id": item.get("nmid"),
                "sa_name": str(item.get("supplier_article", "")).lower(),
                "ts_name": str(item.get("techsize", "")),
                "cost": 0.0,
                "brand": str(item.get("brand", "")).upper()
            }

    barcode_data = list(unique_barcodes.values())

    if not barcode_data:
        return

    try:
        async with session.begin_nested():
            for chunk in chunker(barcode_data, CHUNK_SIZE_GOODS_COST):
                if not chunk:
                    continue

                stmt = insert(Goods_cost).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint='uix_seller_barcode',
                    set_={
                        'subject_name': stmt.excluded.subject_name,
                        'sa_name': stmt.excluded.sa_name,
                        'ts_name': stmt.excluded.ts_name,
                        'brand': stmt.excluded.brand
                    }
                )
                await session.execute(stmt)
        # Обрати внимание: commit убран, так как транзакцией управляет внешний блок (или самозакрывающаяся сессия)
        logging.info(f'Seller_id: {seller_id}. Сохранили новые баркоды: {len(barcode_data)}')
    except SQLAlchemyError as e:
        logging.error(f"Barcode upsert error (seller {seller_id}): {str(e)}")
        raise


async def admin_orders_download_status():
    async with async_session() as session:
        try:
            active_companies = await session.scalar(
                select(func.count(Seller.id))
                .where(Seller.status == 'Active', Seller.service_status)
            )

            end_of_yesterday = await end_of_yesterday_func()
            yesterday_str = await yesterday_str_func()

            orders_stats = await session.execute(
                select(
                    func.count(Orders.seller_id.distinct()),
                    func.count(Orders.id)
                ).where(Orders.order_date == end_of_yesterday)
            )
            companies, rows = orders_stats.one()

            report = (
                f'Orders report for {yesterday_str}:\n'
                f'Active companies: {active_companies}\n'
                f'Companies with orders: {companies}\n'
                f'Total rows: {rows}'
            )
            await send_message_to_admin(report)

        except Exception as e:
            await handle_error('Admin report error', e)


async def handle_error(context, error):
    full_message = f'{context}\nError: {error}\n{error.__class__.__name__}'
    logging.exception(full_message)
    await send_message_to_admin(full_message)