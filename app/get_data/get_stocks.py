import asyncio
import html
import logging
from datetime import datetime

from app.database.models import Goods_cost

from app.database.apirequests import ApiClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.admin.admin_message import send_message_to_admin
from app.checks import check_seller_stocks_downloaded_today
from app.database.api_functions import unauthorised_api_notification
from app.database.classes.stocks import Stock
from app.database.models import Seller
from app.database.support_functions import get_api_by_seller_id, get_seller_inn_by_seller_id
from app.wrappers import log_and_notify_admin, with_session
from config import warehouse_remains_create_url, warehouse_remains_status_url, warehouse_remains_download_url

# Эти "склады" в ответе WB - служебные агрегаты, а не физические склады.
IN_WAY_TO_CLIENT_LABEL = 'В пути до получателей'
IN_WAY_FROM_CLIENT_LABEL = 'В пути возвраты на склад WB'
TOTAL_LABEL = 'Всего находится на складах'
NO_WAREHOUSE_PLACEHOLDER = 'Нет данных о складе'


# Ежедневное скачивание остатков товаров (проверка себестоимости раз в неделю после выгрузки продаж):
@with_session
async def daily_get_stocks_data(session):
    """Ежедневное скачивание остатков товаров"""
    try:
        sellers = await session.execute(
            select(Seller.id).where(
                Seller.status == 'Active',
                Seller.service_status == True
            )
        )
        tasks = [
            get_and_check_stocks_data(seller_id=seller_id)
            for seller_id in sellers.scalars()
        ]
        await asyncio.gather(*tasks)
    except Exception as e:
        logging.exception("Ошибка при выгрузке остатков")
        await send_message_to_admin(f"Ошибка при выгрузке остатков: {str(e)}")


@with_session
async def get_and_check_stocks_data(session, seller_id):
    try:
        if await check_seller_stocks_downloaded_today(session=session, seller_id=seller_id):
            logging.info(f'Seller_id: {seller_id}. Остатки товаров уже выгружены: Ок')
            return True
        logging.info(f'Seller_id: {seller_id}. Выгружаем остатки товаров.')
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        if not active_api:
            await unauthorised_api_notification(session=session, seller_id=seller_id)
            return False

        task_id = await create_warehouse_remains_report(session, seller_id, active_api)
        if not task_id:
            return False

        if not await wait_for_warehouse_remains_ready(session, seller_id, active_api, task_id):
            return False

        report_items = await download_warehouse_remains_report(session, seller_id, active_api, task_id)
        stock_data = flatten_warehouse_remains_report(report_items or [])

        if stock_data:
            await process_stock_response(session, seller_id, stock_data)
        return True

    except Exception as e:
        logging.exception(f"Ошибка в выгрузке остатков для seller {seller_id}")
        error_message = (f"Ошибка в выгрузке остатков для seller {seller_id}: "
                         f"{html.escape(str(e))}")
        # Обрезаем сообщение до 4000 символов
        await send_message_to_admin(error_message[:4000])


async def create_warehouse_remains_report(session, seller_id, active_api):
    """Создает задачу на формирование отчета 'Остатки на складах' (замена /api/v1/supplier/stocks)."""
    async with ApiClient(db_session=session, seller_id=seller_id, api_key=active_api) as client:
        response = await client.fetch(
            method="GET",
            url=warehouse_remains_create_url,
            headers={"Authorization": active_api}
        )
    task_id = (response or {}).get('data', {}).get('taskId')
    if not task_id:
        logging.error(f'Seller_id: {seller_id}. Не удалось создать задачу отчета остатков: {response}')
    return task_id


async def wait_for_warehouse_remains_ready(session, seller_id, active_api, task_id, max_attempts=15):
    status_url = warehouse_remains_status_url.format(task_id=task_id)
    async with ApiClient(db_session=session, seller_id=seller_id, api_key=active_api) as client:
        for attempt in range(max_attempts):
            response = await client.fetch(method="GET", url=status_url, headers={"Authorization": active_api})
            status = (response or {}).get('data', {}).get('status')
            if status == 'done':
                return True
            if status in ('purged', 'canceled'):
                logging.info(f'Seller_id: {seller_id}. Task_id: {task_id}. Статус отчета остатков: {status}.')
                return False
            await asyncio.sleep(5)
    logging.info(f'Seller_id: {seller_id}. Task_id: {task_id}. Превышено время ожидания отчета остатков.')
    return False


async def download_warehouse_remains_report(session, seller_id, active_api, task_id):
    download_url = warehouse_remains_download_url.format(task_id=task_id)
    async with ApiClient(db_session=session, seller_id=seller_id, api_key=active_api) as client:
        return await client.fetch(method="GET", url=download_url, headers={"Authorization": active_api})


def flatten_warehouse_remains_report(report_items):
    """
    Приводит вложенный ответ нового отчета WB (один item на баркод, вложенный список
    'warehouses' на физические + служебные "склады") к плоскому списку строк в старом
    формате /api/v1/supplier/stocks, который уже понимает prepare_stock_item().

    Важно: inWayToClient/inWayFromClient переносятся только на первую строку баркода,
    иначе SUM(...) по баркоду в отчетах (group_by(Goods_cost.barcode)) задвоит значения
    на количество складов.
    """
    rows = []
    for item in report_items:
        in_way_to_client = 0
        in_way_from_client = 0
        real_warehouses = []
        for wh in item.get('warehouses', []):
            name = wh.get('warehouseName')
            qty = wh.get('quantity', 0) or 0
            if name == IN_WAY_TO_CLIENT_LABEL:
                in_way_to_client = qty
            elif name == IN_WAY_FROM_CLIENT_LABEL:
                in_way_from_client = qty
            elif name == TOTAL_LABEL:
                continue
            else:
                real_warehouses.append((name, qty))

        if not real_warehouses:
            real_warehouses = [(NO_WAREHOUSE_PLACEHOLDER, 0)]

        for idx, (warehouse_name, quantity) in enumerate(real_warehouses):
            rows.append({
                'warehouseName': warehouse_name,
                'quantity': quantity,
                'inWayToClient': in_way_to_client if idx == 0 else 0,
                'inWayFromClient': in_way_from_client if idx == 0 else 0,
                'quantityFull': quantity,
                'nmId': item.get('nmId'),
                'barcode': item.get('barcode'),
                'supplierArticle': item.get('vendorCode'),
                'subject': item.get('subjectName'),
                'brand': item.get('brand'),
                'techSize': item.get('techSize'),
                'category': '',
                # WB больше не отдает цену/скидку в этом отчете - себестоимость на остатках
                # по-прежнему считается отдельно через set_cost_to_stock(), а вот
                # "стоимость остатков по продажной цене" (current_price/total_at_sell_price)
                # сейчас всегда 0, пока не подключим отдельный источник цен.
                'Price': 0,
                'Discount': 0,
            })
    return rows


async def process_stock_response(session, seller_id, stock_data):
    """Обработка полученных данных об остатках"""
    if not stock_data:
        return

    # Подготовка данных
    seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
    current_date = datetime.now()

    # Обработка штрихкодов
    await bulk_upsert_barcodes(session, seller_id, seller_inn, stock_data)

    # Массовая вставка остатков
    stocks_to_insert = [
        prepare_stock_item(seller_id, seller_inn, item, current_date)
        for item in stock_data
    ]

    await bulk_upsert_stocks(session, stocks_to_insert)
    await session.commit()
    logging.info(f'Seller_id: {seller_id}. Сохранены остатки в базу {len(stocks_to_insert)} строк.')


def prepare_stock_item(seller_id, seller_inn, item, date):
    """Подготовка данных для вставки. Ключи словаря приведены к формату БД"""
    return {
        "seller_id": seller_id,
        "seller_inn": seller_inn,
        "date_in_stock": date,
        "date_in_stock_str": date.strftime('%Y-%m-%d'),
        "warehouse_name": item.get('warehouseName'),  # Было warehouseName
        "supplier_article": item.get('supplierArticle'),  # Было supplierArticle
        "nmid": item.get('nmId'),  # Было nmId
        "barcode": item.get('barcode'),
        "quantity": item.get('quantity', 0),
        "inwaytoclient": item.get('inWayToClient', 0),  # Было inWayToClient
        "inwayfromclient": item.get('inWayFromClient', 0),  # Было inWayFromClient
        "quantityfull": item.get('quantityFull', 0),  # Было quantityFull
        "category": item.get('category'),
        "subject": item.get('subject'),
        "brand": item.get('brand'),
        "techsize": item.get('techSize'),  # Было techSize
        "price": float(item.get('Price', 0)),  # Было Price
        "discount": float(item.get('Discount', 0)),  # Было Discount
        "current_price": calculate_current_price(item),
        "total_at_sell_price": calculate_total_price(item),
        "cost_per_item": 0.0,
        "total_at_cost": 0.0
    }


def calculate_current_price(item):
    """Расчет текущей цены"""
    # Здесь ключи остаются от API, так как функция принимает сырой 'item'
    price = float(item.get('Price', 0))
    discount = float(item.get('Discount', 0))
    return price - (price * discount / 100)


def calculate_total_price(item):
    """Расчет общей стоимости"""
    quantity = int(item.get('quantityFull', 0))
    return quantity * calculate_current_price(item)


async def bulk_upsert_barcodes(session, seller_id, seller_inn, items):
    unique_barcodes = {}
    for item in items:
        barcode = item.get("barcode")
        if not barcode:
            continue
        # Используем комбинацию seller_id и barcode как уникальный ключ
        key = (seller_id, barcode)
        # Сохраняем последнее вхождение для каждого ключа
        unique_barcodes[key] = {
            "seller_id": seller_id,
            "seller_inn": seller_inn,
            "barcode": barcode,
            "subject_name": item.get("subject"),
            "nm_id": item.get("nmId"),
            "sa_name": str(item.get("supplierArticle", "")).lower(),
            "ts_name": str(item.get("techSize", "")),
            "cost": 0.0,
            "brand": str(item.get('brand', "")).upper(),
        }

    barcode_data = list(unique_barcodes.values())

    if not barcode_data:
        return

    chunk_size = 500
    for i in range(0, len(barcode_data), chunk_size):
        chunk = barcode_data[i:i + chunk_size]
        async with session.begin_nested():
            stmt = insert(Goods_cost).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint='uix_seller_barcode',
                set_={
                    'subject_name': stmt.excluded.subject_name,
                    'sa_name': stmt.excluded.sa_name,
                    'ts_name': stmt.excluded.ts_name,
                    'brand': stmt.excluded.brand,
                }
            )

            try:
                await session.execute(stmt)
            except Exception as e:
                logging.error(f"Barcode upsert error in chunk {i // chunk_size}: {str(e)}")
                raise
        await session.commit()


async def bulk_upsert_stocks(session, stocks_data):
    """Массовая вставка остатков"""
    if not stocks_data:
        return

    chunk_size = 500  # Добавляем пакетную обработку
    for i in range(0, len(stocks_data), chunk_size):
        chunk = stocks_data[i:i + chunk_size]
        async with session.begin_nested():
            stmt = insert(Stock).values(chunk)
            await session.execute(stmt)
        await session.commit()