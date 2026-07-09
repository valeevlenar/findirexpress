import asyncio
from datetime import datetime, timedelta
import logging
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import async_session, Seller, Orders_nm
from app.database.support_functions import get_api_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_yesterday_func, yesterday_str_func
from app.wrappers import log_and_notify_admin

CHUNK_SIZE_ORDERS_NM = 500
WB_RATE_LIMIT_SLEEP = 22


def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]


# Убрали @with_session
async def daily_get_orders_by_nm_data():
    try:
        # Сессия №1: только для получения селлеров
        async with async_session() as session:
            companies = await session.execute(select(Seller.id).
                                              where(Seller.status == 'Active',
                                                    Seller.service_status == True))
            companies = companies.mappings().all()

        # Каскадный старт
        for seller in companies:
            await get_orders_by_nm_by_seller(seller_id=seller['id'])
            await asyncio.sleep(5)

        await admin_orders_by_nm_download_status()
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в ежедневной функции по выгрузке заказов (Funnel)'
                                         f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


@log_and_notify_admin
async def get_orders_by_nm_by_seller(seller_id):
    try:
        # Сессия №2: узнать последнюю дату и апи-ключ
        async with async_session() as session:
            last_orders_by_nm_in_db_date = await session.scalar(select(func.max(Orders_nm.order_date)).
                                                                where(Orders_nm.seller_id == seller_id))
            active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)

        if not active_api:
            return False

        end_of_yesterday = await end_of_yesterday_func()

        if last_orders_by_nm_in_db_date and last_orders_by_nm_in_db_date >= end_of_yesterday:
            return True
        elif not last_orders_by_nm_in_db_date:
            date_from = await start_for_downloading_data_func()
        else:
            date_from = last_orders_by_nm_in_db_date + timedelta(days=1)

        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        current_date = date_from

        # Оставляем цикл по дням для сохранения корректной дневной аналитики
        while current_date <= end_of_yesterday:

            # Передаем active_api, чтобы не открывать БД внутри генератора
            cards = await get_orders_data_nm_generator(seller_id=seller_id,
                                                       active_api=active_api,
                                                       date_from=current_date,
                                                       date_to=current_date)

            day_end_for_db = current_date.replace(hour=23, minute=59, second=59)

            if cards:
                logging.info(
                    f'Seller_id: {seller_id}. Выгрузили заказы (Funnel) за {current_date.date()}. Сохраняем...')
                await bulk_save_orders_nm(seller_id=seller_id,
                                          cards=cards,
                                          report_date=day_end_for_db)
            else:
                logging.info(f'Seller_id: {seller_id}. Нет данных (Funnel) за {current_date.date()}')

            current_date += timedelta(days=1)

            # Спим после каждого дня для соблюдения лимита (3 запроса в минуту)
            await asyncio.sleep(WB_RATE_LIMIT_SLEEP)

        return True

    except Exception as e:
        await handle_error(f'Main orders processing error (Funnel, seller {seller_id})', e)
        return False


@log_and_notify_admin
async def get_orders_data_nm_generator(seller_id, active_api, date_from, date_to):
    try:
        date_from_str = datetime.strftime(date_from, '%Y-%m-%d')
        date_to_str = datetime.strftime(date_to, '%Y-%m-%d')

        url = 'https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products'

        async with ApiClient(seller_id=seller_id) as client:
            all_cards = []
            offset = 0
            limit = 1000

            while True:
                params = {
                    "selectedPeriod": {
                        "start": date_from_str,
                        "end": date_to_str
                    },
                    "limit": limit,
                    "offset": offset
                }

                response = await client.fetch(
                    method="POST",
                    url=url,
                    headers={"Authorization": active_api},
                    json=params
                )

                if not response or not isinstance(response, dict):
                    logging.error(
                        f"API request failed or returned None for seller_id {seller_id}. Response: {response}")
                    break

                if 'data' not in response:
                    logging.warning(f"No 'data' key in response for seller_id {seller_id}. Full response: {response}")
                    break

                products = response.get('data', {}).get('products', [])
                all_cards.extend(products)

                if len(products) < limit:
                    break

                offset += limit
                await asyncio.sleep(WB_RATE_LIMIT_SLEEP)

            return all_cards

    except Exception as e:
        logging.exception("API request error inside generator")
        raise e


@log_and_notify_admin
async def bulk_save_orders_nm(seller_id, cards, report_date):
    try:
        data_to_insert = []
        for item in cards:
            stats = item.get('statistic', {}).get('selected', {})
            product_info = item.get('product', {})

            order_count = stats.get('orderCount', 0)
            order_sum = stats.get('orderSum', 0)

            if order_count != 0 or order_sum != 0:
                order_date_fixed = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)

                data_to_insert.append({
                    "seller_id": seller_id,
                    "order_date": order_date_fixed,
                    "supplier_article": product_info.get('vendorCode'),
                    "subject_name": product_info.get('subjectName'),
                    "nm_id": product_info.get('nmId'),
                    "quantity": order_count,
                    "total_sum": order_sum,
                    "updated_at": datetime.now()
                })

        if not data_to_insert:
            return

        # Сессия №3: Сохранение данных
        async with async_session() as session:
            async with session.begin():
                for chunk in chunker(data_to_insert, CHUNK_SIZE_ORDERS_NM):
                    stmt = insert(Orders_nm).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        constraint='orders_nm_unique_constraint',
                        set_={
                            'quantity': stmt.excluded.quantity,
                            'total_sum': stmt.excluded.total_sum,
                            'updated_at': stmt.excluded.updated_at
                        }
                    )
                    await session.execute(stmt)

            logging.info(f'Seller_id: {seller_id}. Сохранили {len(data_to_insert)} строк в базу.')

    except Exception as e:
        await handle_error(f'Bulk save error in Orders_nm (Funnel, seller {seller_id})', e)


@log_and_notify_admin
async def admin_orders_by_nm_download_status():
    async with async_session() as session:
        try:
            active_companies = await session.scalar(select(func.count(Seller.id)).
                                                    where(Seller.status == 'Active',
                                                          Seller.service_status == True))
            end_of_yesterday = await end_of_yesterday_func()
            yesterday_str = await yesterday_str_func()

            orders_companies = await session.scalar(select(func.count()).
                                                    select_from(select(Orders_nm.seller_id).
                                                                where(Orders_nm.order_date == end_of_yesterday).
                                                                group_by(Orders_nm.seller_id).subquery()))

            orders_rows = await session.scalar(select(func.count(Orders_nm.id)).
                                               where(Orders_nm.order_date == end_of_yesterday))

            download_report = (f'Отчет по загрузке заказов (новый метод Funnel) за {yesterday_str}:'
                               f'\nВсего активных компаний: {active_companies}'
                               f'\nЗагружено заказов по компаниям: {orders_companies}'
                               f'\nЗагружено строк: {orders_rows}')
            await send_message_to_admin(download_report)
        except Exception as e:
            await handle_error('Admin report error (Funnel)', e)


async def handle_error(context, error):
    full_message = f'{context}\nError: {error}\n{error.__class__.__name__}'
    logging.exception(full_message)
    await send_message_to_admin(full_message)