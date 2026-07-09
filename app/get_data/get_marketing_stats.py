import asyncio
import logging
from datetime import timedelta, datetime
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from app.admin.admin_message import send_message_to_admin
from app.database.apirequests import ApiClient
from app.database.models import Marketing_campaigns_stats, Marketing_costs_wb
from app.database.support_functions import get_api_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_yesterday_func, get_end_of_month

# Прямо здесь зафиксируем новый URL v3
marketing_campaign_statistics_url = 'https://advert-api.wildberries.ru/adv/v3/fullstats'

CHUNK_SIZE_MARKETING_STATS = 500


def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]


async def get_marketing_statistics_for_seller_id(session, seller_id):
    try:
        latest_marketing_statistics_date = await session.scalar(select(func.max(Marketing_campaigns_stats.cost_date)).
                                                                where(Marketing_campaigns_stats.seller_id == seller_id))
        end_of_yesterday = await end_of_yesterday_func()
        start_for_downloading_data = await start_for_downloading_data_func()

        # Если первая загрузка, то выгружаем c самого начала
        if not latest_marketing_statistics_date:
            latest_marketing_statistics_date = start_for_downloading_data - timedelta(microseconds=1)
            logging.info(f'Seller_id={seller_id}: Начальная выгрузка с {start_for_downloading_data}')

        # берем запас 1 день
        date_from = latest_marketing_statistics_date + timedelta(microseconds=1) - timedelta(days=1)

        while date_from < end_of_yesterday:
            # Рассчитываем конец периода (неделя или остаток дней). v3 API поддерживает до 31 дня.
            date_to_candidate = (date_from + timedelta(days=30)).replace(hour=23, minute=59, second=59,
                                                                         microsecond=999999)
            end_of_month = await get_end_of_month(date_from)
            date_to = min(date_to_candidate, end_of_yesterday, end_of_month)
            logging.info(f'Seller_id={seller_id}, обработка периода {str(date_from)}-{str(date_to)}')

            # Обрабатываем период:
            if await process_marketing_stats_period(session=session,
                                                    seller_id=seller_id,
                                                    date_from=date_from,
                                                    date_to=date_to):
                logging.info(
                    f'Seller_id={seller_id}, завершили период {str(date_from)}-{str(date_to)}. Ждем 60 и продолжаем')
                date_from = date_to + timedelta(microseconds=1)
                await asyncio.sleep(60)
            else:
                return False

        return True

    except Exception as e:
        await send_message_to_admin(f'Ошибка в обработке статистики по маркетингу по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


async def process_marketing_stats_period(session, seller_id, date_from, date_to):
    try:
        status, advert_ids_list = await prepare_advert_ids_with_dates(session=session,
                                                                      seller_id=seller_id,
                                                                      date_from=date_from,
                                                                      date_to=date_to)
        if status == 'no_advert_ids':
            return True
        elif status:
            # === ВАЖНОЕ ИЗМЕНЕНИЕ: Лимит WB v3 - 50 кампаний в запросе ===
            chunks = list(chunker(advert_ids_list, 50))
            total_chunks = len(chunks)
            for index, advert_ids_chunk in enumerate(chunks):

                marketing_stats_data_raw = await get_marketing_stats_from_wb(session=session,
                                                                             seller_id=seller_id,
                                                                             advert_ids=advert_ids_chunk,
                                                                             date_from=date_from,
                                                                             date_to=date_to)
                if marketing_stats_data_raw:
                    if await save_marketing_campaign_statistics_to_db(session=session,
                                                                      seller_id=seller_id,
                                                                      marketing_stats_data_raw=marketing_stats_data_raw):
                        logging.info(
                            f"Seller_id={seller_id}. Обработан чанк {index + 1}/{total_chunks} в периоде {date_from}-{date_to}.")
                        # Ждём 25 секунд для соблюдения лимита (3 запроса в минуту, 1 раз в 20 сек)
                        if index < total_chunks - 1:
                            logging.info("Ждём 25 секунд перед следующим чанком (лимиты WB).")
                            await asyncio.sleep(25)
                    else:
                        return False
                else:
                    # Пустой ответ — не всегда ошибка, WB может просто не иметь данных. Пропускаем чанк.
                    logging.warning(f"Seller_id={seller_id}. Пустой ответ для чанка {index + 1}.")
            return True
        else:
            return False

    except Exception as e:
        await send_message_to_admin(f'Ошибка в обработке статистики по маркетингу по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


async def prepare_advert_ids_with_dates(session, seller_id, date_from, date_to):
    try:
        # v3 API: Теперь нам нужен просто плоский список уникальных ID кампаний за период!
        advert_ids = await session.execute(select(Marketing_costs_wb.advertid).
                                           where(Marketing_costs_wb.seller_id == seller_id,
                                                 Marketing_costs_wb.cost_date >= date_from,
                                                 Marketing_costs_wb.cost_date <= date_to).
                                           group_by(Marketing_costs_wb.advertid))

        # Получаем список чистых ID
        advert_ids_list = [int(row['advertid']) for row in advert_ids.mappings().all()]

        if not advert_ids_list:
            return 'no_advert_ids', []

        return True, advert_ids_list

    except Exception as e:
        await send_message_to_admin(f'Ошибка в подготовке списка маркетиновых кампаний:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return False, []


async def get_marketing_stats_from_wb(session, seller_id, advert_ids, date_from, date_to):
    try:
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)

        # === ВАЖНОЕ ИЗМЕНЕНИЕ: Формируем GET-параметры ===
        ids_str = ",".join(map(str, advert_ids))
        date_from_str = date_from.strftime('%Y-%m-%d')
        date_to_str = date_to.strftime('%Y-%m-%d')

        params = {
            "ids": ids_str,
            "beginDate": date_from_str,
            "endDate": date_to_str
        }

        async with ApiClient(session, seller_id, active_api) as client:
            response = await client.fetch(
                method="GET",  # Сменили POST на GET
                url=marketing_campaign_statistics_url,
                headers={"Authorization": active_api},
                params=params  # Передаем через params (URL Query), а не json
            )
            return response if response else []

    except Exception as e:
        await send_message_to_admin(f'Ошибка в выгрузке статистики маркетинговых кампаний:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


async def save_marketing_campaign_statistics_to_db(session, seller_id, marketing_stats_data_raw):
    try:
        marketing_stats_data_to_insert = []
        for advert in marketing_stats_data_raw:
            for day in advert.get('days', []):
                for app in day.get('apps', []):
                    # === ВАЖНОЕ ИЗМЕНЕНИЕ: ключ 'nm' изменился на 'nms' ===
                    for nm in app.get('nms', []):
                        marketing_stats_data_to_insert.append({
                            'seller_id': seller_id,
                            'advert_id': advert['advertId'],
                            'date': day['date'],
                            'cost_date': datetime.fromisoformat(day['date']).astimezone().replace(tzinfo=None).replace(
                                hour=23, minute=59, second=59, microsecond=999999),
                            'app_type': app['appType'],
                            'nmid': nm['nmId'],
                            'views': nm.get('views', 0),
                            'clicks': nm.get('clicks', 0),
                            'costs': nm.get('sum', 0),
                            'adds_to_cart': nm.get('atbs', 0),
                            'orders': nm.get('orders', 0),
                            'quantity': nm.get('shks', 0),
                            'orders_sum': nm.get('sum_price', 0),
                            'updated_at': datetime.now()
                        })

        if not marketing_stats_data_to_insert:
            return True

        async with session.begin_nested():
            for chunk in chunker(marketing_stats_data_to_insert, CHUNK_SIZE_MARKETING_STATS):
                stmt = insert(Marketing_campaigns_stats).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint='marketing_stats_unique_constraint',
                    set_={
                        'views': stmt.excluded.views,
                        'clicks': stmt.excluded.clicks,
                        'costs': stmt.excluded.costs,
                        'adds_to_cart': stmt.excluded.adds_to_cart,
                        'orders': stmt.excluded.orders,
                        'quantity': stmt.excluded.quantity,
                        'orders_sum': stmt.excluded.orders_sum,
                        'updated_at': stmt.excluded.updated_at
                    }
                )
                await session.execute(stmt)
        await session.commit()
        return True

    except Exception as e:
        logging.exception("An error occurred: %s", exc_info=e)
        return False