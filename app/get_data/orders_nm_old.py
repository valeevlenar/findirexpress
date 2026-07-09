import asyncio
from datetime import datetime, timedelta
import logging
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import async_session, Seller, Orders_nm
from app.database.support_functions import get_api_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_yesterday_func, yesterday_str_func, get_end_of_month
from app.wrappers import log_and_notify_admin, with_session

CHUNK_SIZE_ORDERS_NM = 500

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

@with_session
async def daily_get_orders_by_nm_data(session):
    try:
        companies = await session.execute(select(Seller.id).
                                          where(Seller.status=='Active',
                                                Seller.service_status==True))
        companies = companies.mappings().all()
        # Создаем список корутин
        tasks = [get_orders_by_nm_by_seller(session=session, seller_id=seller['id']) for seller in companies]

        # Запускаем все корутины параллельно
        await asyncio.gather(*tasks)

        await admin_orders_by_nm_download_status()
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в ежедневной функции по выгрузке заказов'
                                         f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def get_orders_by_nm_by_seller(session, seller_id):
    try:
        # Смотрим, какая последняя дата заказов в базе
        last_orders_by_nm_in_db_date = await session.scalar(select(func.max(Orders_nm.order_date)).
                                                            where(Orders_nm.seller_id == seller_id))
        # print(last_orders_by_nm_in_db_date)
        end_of_yesterday = await end_of_yesterday_func()

        # Если заказы есть по конец вчера то ничего не грузим
        if last_orders_by_nm_in_db_date and last_orders_by_nm_in_db_date >= end_of_yesterday:
            return True

        # Если нет заказов, то грузим с самого начала
        elif not last_orders_by_nm_in_db_date:
            date_from = await start_for_downloading_data_func()
            # print(f'дата в orders_nm', date_from)

        # Если заказы есть, но не по конец вчера, то грузим со следующего дня
        else:
            date_from = last_orders_by_nm_in_db_date + timedelta(microseconds=1)

        # Создаем генератор начала и конца недели и выгружаем в цикле:
        status = 'pending'
        while status != 'done':
            date_to = (date_from + timedelta(days=(7-date_from.isoweekday()))).replace(hour=23,minute=59,second=59,microsecond=999999)

            # Если date_to перевалил за конец месяца, то ограничиваем концом месяца
            end_of_month = await get_end_of_month(date_from)
            if date_to > end_of_month:
                date_to = end_of_month

            # Если date_to перевалил за конец вчера, то ограничиваем концом вчера
            end_of_yesterday = await end_of_yesterday_func()
            if date_to > end_of_yesterday:
                date_to = end_of_yesterday

            # print(date_from, date_to)
            cards = await get_orders_data_nm_generator(session=session,
                                                       seller_id=seller_id,
                                                       date_from=date_from,
                                                       date_to=date_to)

            # print(cards)

            if cards:
                logging.info(f'Seller_id: {seller_id}. Выгрузили заказы nm с {date_from} по {date_to}. Сохраняем в базу')
                await bulk_save_orders_nm(session=session,
                                              seller_id=seller_id,
                                              cards=cards)
            else:
                logging.info(f'Seller_id: {seller_id}. Выгрузили заказы nm с {date_from} по {date_to}. Нет заказов')

            # Проверяем, если дошли до конца вчера, то останавливаемся
            end_of_yesterday = await end_of_yesterday_func()
            if date_to >= end_of_yesterday:
                status = 'done'
                return True
            elif date_to < end_of_yesterday:
                date_from = date_to + timedelta(microseconds=1)
                logging.info(f'Seller_id: {seller_id}. Ждем 25 и выгружаем заказы c {date_from}')
                await asyncio.sleep(25)

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в основной функции по выгрузке заказов по артикулам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

# Проверяем статус компании и выгружаем продажи из ВБ:
@log_and_notify_admin
async def get_orders_data_nm_generator (session, seller_id,date_from, date_to):
    try:
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        date_from_str = datetime.strftime(date_from, '%Y-%m-%d %H:%M:%S')
        date_to_str = datetime.strftime(date_to, '%Y-%m-%d %H:%M:%S')
        # print(date_from_str, date_to_str)
        get_orders_by_nm_url = 'https://seller-analytics-api.wildberries.ru/api/v2/nm-report/detail'

        async with ApiClient(session, seller_id, active_api) as client:
            page = 1
            all_cards = []

            while True:
                params = {"brandNames": [],
                          "objectIDs": [],
                          "tagIDs": [],
                          "nmIDs": [],
                          "timezone": "Europe/Moscow",
                          "period": {
                              "begin": date_from_str,
                              "end": date_to_str},
                          "orderBy": {
                              "field": "ordersSumRub",
                              "mode": "asc"},
                          "page": page}

                orders_data = await client.fetch(
                    method="POST",
                    url=get_orders_by_nm_url,
                    headers={"Authorization": active_api},
                    json=params
                )

                all_cards.extend(orders_data.get('data', {}).get('cards', []))

                if not orders_data.get('data', {}).get('isNextPage', False):
                    break

                page += 1

            return all_cards

    except Exception as e:
        await send_message_to_admin(f'Ошибка при выгрузке заказов по артикулам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("API request error. An error occurred: %s", exc_info=e)
        return []

@log_and_notify_admin
async def bulk_save_orders_nm(session, seller_id, cards):
    try:
        data_to_insert = []
        for card in cards:
            selected_period = card['statistics']['selectedPeriod']

            # Проверяем что оба значения не равны нулю
            if selected_period['ordersCount'] != 0 and selected_period['ordersSumRub'] != 0:
                order_date = datetime.strptime(
                    selected_period['end'], '%Y-%m-%d %H:%M:%S'
                ).replace(hour=23, minute=59, second=59, microsecond=999999)

                data_to_insert.append({
                    "seller_id": seller_id,
                    "order_date": order_date,
                    "supplier_article": card['vendorCode'],
                    "subject_name": card['object']['name'],
                    "nm_id": card['nmID'],
                    "quantity": selected_period['ordersCount'],
                    "total_sum": selected_period['ordersSumRub'],
                    "updated_at": datetime.now()
                })
        async with session.begin_nested():

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

        await session.commit()
        logging.info(f'Seller_id: {seller_id}. Сохранили заказы nm в базу.')

    except Exception as e:
        await session.rollback()
        logging.exception("Bulk save error")

# Отчет по загрузке заказов
@log_and_notify_admin
async def admin_orders_by_nm_download_status():
    async with async_session() as session:
        active_companies = await session.scalar(select(func.count(Seller.id)).
                                                 where(Seller.status=='Active',
                                                       Seller.service_status==True))
        end_of_yesterday = await end_of_yesterday_func()
        yesterday_str = await yesterday_str_func()
        orders_companies = await session.scalar(select(func.count()).
                                               select_from(select(Orders_nm.seller_id).
                                                           where(Orders_nm.order_date == end_of_yesterday).
                                                           group_by(Orders_nm.seller_id).subquery()))
        orders_rows = await session.scalar(select(func.count(Orders_nm.id)).
                                               where(Orders_nm.order_date == end_of_yesterday))
        download_report = (f'Отчет по загрузке заказов по артикулам за {yesterday_str}:'
                         f'\nВсего активных компаний: {active_companies}'
                        f'\nЗагружено заказов по компаниям: {orders_companies}'
                         f'\nЗагружено строк: {orders_rows}')
        await send_message_to_admin(download_report)
