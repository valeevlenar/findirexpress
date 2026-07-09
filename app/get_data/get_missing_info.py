import asyncio
import logging
from sqlalchemy import select, or_, update
from app.database.apirequests import ApiClient
from app.database.models import Goods_cost
from app.database.support_functions import get_api_by_seller_id
from app.wrappers import log_and_notify_admin, with_session

# URL методов API Контента
WB_CONTENT_LIST_URL = "https://content-api.wildberries.ru/content/v2/get/cards/list"
WB_CONTENT_TRASH_URL = "https://content-api.wildberries.ru/content/v2/get/cards/trash"


@with_session
async def repair_missing_goods_info(session, seller_id):
    """
    Основная функция для поиска и исправления неполных записей в goods_cost.
    Ищет товары с пустыми полями и дозапрашивает их в WB Content API.
    """
    try:
        # Ищем записи с пропущенными данными
        # Выбираем конкретные поля (id, barcode), чтобы избежать ошибки MissingGreenlet
        stmt = select(Goods_cost.id, Goods_cost.barcode).where(
            Goods_cost.seller_id == seller_id,
            or_(
                Goods_cost.ts_name == '',
                Goods_cost.ts_name.is_(None),
                Goods_cost.subject_name == '',
                Goods_cost.subject_name.is_(None),
                Goods_cost.brand == '',
                Goods_cost.brand.is_(None),
                Goods_cost.nm_id == 0,
                Goods_cost.nm_id.is_(None)
            )
        )

        incomplete_goods = await session.execute(stmt)
        goods_list = incomplete_goods.all()

        if not goods_list:
            logging.info(f"Seller_id: {seller_id}. Неполных карточек товаров не найдено.")
            return True

        logging.info(f"Seller_id: {seller_id}. Найдено {len(goods_list)} неполных карточек. Начинаем восстановление.")

        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        if not active_api:
            return False

        updated_count = 0

        async with ApiClient(session, seller_id, active_api) as client:
            for row in goods_list:
                row_id = row.id
                barcode = row.barcode

                if not barcode:
                    continue

                # 1. Пытаемся найти карточку (активные или корзина)
                card_info = await find_card_by_barcode(client, barcode)

                # 2. Если нашли - парсим и обновляем
                if card_info:
                    parsed_data = parse_card_data(card_info, barcode)

                    if parsed_data:
                        await update_good_in_db(session, row_id, parsed_data)
                        updated_count += 1

                # Лимит API контента: 100 запросов в минуту.
                await asyncio.sleep(0.7)

        logging.info(
            f"Seller_id: {seller_id}. Восстановление завершено. Обновлено {updated_count} из {len(goods_list)} карточек.")
        return True

    except Exception as e:
        logging.exception(f"Error in repair_missing_goods_info for seller {seller_id}: {e}")
        return False


async def find_card_by_barcode(client, barcode):
    """Ищет карточку сначала в списке активных, затем в корзине."""
    # Попытка 1: Активные карточки
    card = await fetch_card_from_api(client, WB_CONTENT_LIST_URL, barcode)
    if card:
        return card

    await asyncio.sleep(0.7)

    # Попытка 2: Корзина
    card = await fetch_card_from_api(client, WB_CONTENT_TRASH_URL, barcode)
    return card


async def fetch_card_from_api(client, url, barcode):
    """Выполняет запрос к API контента с фильтром по баркоду."""
    payload = {
        "settings": {
            "filter": {
                "textSearch": str(barcode),
                "withPhoto": -1
            },
            "cursor": {
                "limit": 10
            }
        }
    }

    headers = {"Authorization": client.api_key}

    try:
        response = await client.fetch(
            method="POST",
            url=url,
            headers=headers,
            json=payload
        )

        if response and isinstance(response, dict) and 'cards' in response:
            cards = response['cards']
            if cards:
                return cards[0]
        return None

    except Exception as e:
        logging.warning(f"Failed to fetch card for barcode {barcode}: {e}")
        return None


def parse_card_data(card, target_barcode):
    """
    Парсит ответ от ВБ и извлекает ВСЕ необходимые поля.
    """
    try:
        target_barcode_str = str(target_barcode).strip()

        # 1. Базовые поля
        sa_val = card.get('vendorCode', '')
        sa_name = sa_val.lower() if sa_val else ''

        brand_val = card.get('brand', '')
        brand = brand_val.upper() if brand_val else ''

        subject_name = card.get('subjectName', '')
        nm_id = card.get('nmID') or 0

        # 2. Поиск размера
        ts_name = ''
        sizes = card.get('sizes', [])

        for size in sizes:
            skus = size.get('skus', [])
            # Приводим все skus к строкам для надежного сравнения
            skus_str = [str(s).strip() for s in skus]

            if target_barcode_str in skus_str:
                ts_name = size.get('techSize', '')
                break

        return {
            'nm_id': nm_id,
            'subject_name': subject_name,
            'brand': brand,
            'sa_name': sa_name,
            'ts_name': ts_name
        }
    except Exception as e:
        logging.error(f"Error parsing card data: {e}")
        return None


async def update_good_in_db(session, row_id, data):
    """
    Обновляет запись в базе данных.
    """
    try:
        values_to_update = {
            'nm_id': data['nm_id'],
            'subject_name': data['subject_name'],
            'brand': data['brand'],
            'sa_name': data['sa_name'],
            'ts_name': data['ts_name']
        }

        stmt = update(Goods_cost).where(Goods_cost.id == row_id).values(**values_to_update)
        await session.execute(stmt)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logging.error(f"Error updating Goods_cost id {row_id}: {e}")