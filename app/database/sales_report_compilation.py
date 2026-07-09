import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.admin.admin_message import send_message_to_admin
from app.database.classes.sales import Sales
from app.database.models import Goods_cost
from app.database.support_functions import get_seller_inn_by_seller_id
from app.wrappers import log_and_notify_admin
from sqlalchemy.exc import SQLAlchemyError

# Константы
CHUNK_SIZE_CHECK_EXISTING = 10000
CHUNK_SIZE_GOODS_COST = 1000
CHUNK_SIZE_SALES = 500


def chunker(sequence, chunk_size):
    """Генератор для разбиения последовательности на чанки."""
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]


@log_and_notify_admin
async def sales_report_compilation(session, seller_id, sales_report):
    try:
        seller_inn = await get_seller_inn_by_seller_id(session=session, seller_id=seller_id)
        current_date = datetime.now()

        # --- ВРЕМЕННЫЙ ЛОГ ДЛЯ ОТЛАДКИ ---
        # Печатаем первые 2 элемента из отчета, чтобы увидеть реальные ключи и значения
        if sales_report:
            logging.info(f"DEBUG: Seller {seller_id}. First 2 items from WB Sales Report:")
            for i, item in enumerate(sales_report[:2]):
                logging.info(f"Item {i}: {item}")
        # ---------------------------------

        # 1. Обработка Goods_cost
        await bulk_upsert_sales_barcodes(session, seller_id, seller_inn, sales_report)

        # 2. Проверка существующих rrd_id
        all_rrd_ids = [item['rrd_id'] for item in sales_report]
        existing_rrd_ids = set()

        for chunk in chunker(all_rrd_ids, CHUNK_SIZE_CHECK_EXISTING):
            result = await session.scalars(
                select(Sales.rrd_id).where(Sales.rrd_id.in_(chunk))
            )
            existing_rrd_ids.update(result.all())

        # 3. Подготовка данных для вставки
        sales_to_insert = [
            prepare_sales_item(seller_id, seller_inn, item, current_date)
            for item in sales_report
            if item['rrd_id'] not in existing_rrd_ids
        ]

        # 4. Вставка продаж
        if sales_to_insert:
            success = await bulk_upsert_sales(session, sales_to_insert)
            if success:
                logging.info(f'Seller_id: {seller_id}. Успешно загружено: {len(sales_to_insert)} строк.')
                return True
        return False

    except SQLAlchemyError as e:
        await session.rollback()
        logging.exception(f"Database error in sales_report_compilation: {str(e)}")
        await send_message_to_admin(f'Seller_id: {seller_id}. Ошибка БД: {str(e)}')
        return False
    except Exception as e:
        logging.exception(f"Unexpected error in sales_report_compilation: {str(e)}")
        await send_message_to_admin(f'Seller_id: {seller_id}. Неожиданная ошибка: {str(e)}')
        return False


async def bulk_upsert_sales_barcodes(session, seller_id, seller_inn, items):
    try:
        unique_barcodes = {}
        for item in items:
            if barcode := item.get("barcode"):
                key = (seller_id, barcode)

                # Ищем данные сначала по ключам Продаж (v5), затем по ключам Склада
                subj = item.get("subject_name") or item.get("subject") or ''
                nm = item.get("nm_id") or item.get("nmId") or 0
                sa = item.get("sa_name") or item.get("supplierArticle") or ''

                # ИСПРАВЛЕНО: Безопасное получение размера
                # item.get('ts_name') может вернуть 0 (число) или None.
                # '0' or '' даст '', а нам нужен '0'.
                ts_val = item.get("ts_name")
                if ts_val is None:
                    ts_val = item.get("techSize")

                # Приводим к строке, если это число (0), иначе пустая строка
                ts = str(ts_val) if ts_val is not None else ''

                br = item.get("brand_name") or item.get("brand") or ''

                unique_barcodes[key] = {
                    "seller_id": seller_id,
                    "seller_inn": seller_inn,
                    "barcode": barcode,
                    "subject_name": subj,
                    "nm_id": nm,
                    "sa_name": sa.lower(),
                    "ts_name": ts,
                    "cost": 0.0,
                    "brand": br.upper()
                }

        barcode_data = list(unique_barcodes.values())
        if not barcode_data:
            return

        async with session.begin_nested():
            for chunk in chunker(barcode_data, CHUNK_SIZE_GOODS_COST):
                if not chunk:
                    continue

                stmt = insert(Goods_cost).values(chunk)

                stmt = stmt.on_conflict_do_update(
                    constraint='uix_seller_barcode',
                    set_={
                        'nm_id': func.coalesce(
                            func.nullif(stmt.excluded.nm_id, 0),
                            Goods_cost.nm_id
                        ),
                        'subject_name': func.coalesce(
                            func.nullif(stmt.excluded.subject_name, ''),
                            Goods_cost.subject_name
                        ),
                        'sa_name': func.coalesce(
                            func.nullif(stmt.excluded.sa_name, ''),
                            Goods_cost.sa_name
                        ),
                        'ts_name': func.coalesce(
                            func.nullif(stmt.excluded.ts_name, ''),
                            Goods_cost.ts_name
                        ),
                        'brand': func.coalesce(
                            func.nullif(stmt.excluded.brand, ''),
                            Goods_cost.brand
                        )
                    }
                )
                await session.execute(stmt)

        await session.commit()

    except SQLAlchemyError as e:
        await session.rollback()
        logging.error(f"Barcode upsert error: {str(e)}")
        raise
    except Exception as e:
        logging.exception(f"Unexpected error in bulk_upsert_sales_barcodes: {str(e)}")
        raise


def prepare_sales_item(seller_id, seller_inn, sales_item, date):
    """Подготовка данных для вставки"""

    try:
        transaction_date = datetime.strptime(sales_item.get('rr_dt'), '%Y-%m-%d')
    except:
        try:
            transaction_date = datetime.strptime(sales_item.get('rr_dt')[0:10], "%Y-%m-%d")
        except:
            transaction_date = date

    return {
        "seller_id": seller_id,
        "seller_inn": seller_inn,
        "rrd_id": sales_item['rrd_id'],
        "realizationreport_id": sales_item['realizationreport_id'],
        "date_from": sales_item['date_from'],
        "date_to": sales_item['date_to'],
        "create_dt": sales_item['create_dt'],
        "subject_name": sales_item['subject_name'],
        "nm_id": sales_item['nm_id'],
        "brand_name": sales_item['brand_name'],
        "sa_name": sales_item['sa_name'],
        # Также обновляем здесь для таблицы Sales
        "ts_name": str(sales_item.get('ts_name', '')) if sales_item.get('ts_name') is not None else '',
        "barcode": sales_item['barcode'],
        "quantity": sales_item['quantity'],
        "retail_price": sales_item['retail_price'],
        "retail_amount": sales_item['retail_amount'],
        "sale_percent": sales_item['sale_percent'],
        "commission_percent": sales_item['commission_percent'],
        "office_name": sales_item['office_name'],
        "supplier_oper_name": sales_item['supplier_oper_name'],
        "order_dt": sales_item['order_dt'],
        "sale_dt": sales_item['sale_dt'],
        "rr_dt": sales_item['rr_dt'],
        "transaction_date": transaction_date,
        "retail_price_withdisc_rub": sales_item['retail_price_withdisc_rub'],
        "delivery_amount": sales_item['delivery_amount'],
        "return_amount": sales_item['return_amount'],
        "delivery_rub": sales_item['delivery_rub'],
        "product_discount_for_report": sales_item['product_discount_for_report'],
        "supplier_promo": sales_item['supplier_promo'],
        "rid": sales_item.get('rid', 0),
        "ppvz_spp_prc": sales_item['ppvz_spp_prc'],
        "ppvz_kvw_prc_base": sales_item['ppvz_kvw_prc_base'],
        "ppvz_kvw_prc": sales_item['ppvz_kvw_prc'],
        "sup_rating_prc_up": sales_item['sup_rating_prc_up'],
        "is_kgvp_v2": sales_item['is_kgvp_v2'],
        "ppvz_sales_commission": sales_item['ppvz_sales_commission'],
        "ppvz_for_pay": sales_item['ppvz_for_pay'],
        "ppvz_reward": sales_item['ppvz_reward'],
        "acquiring_fee": sales_item['acquiring_fee'],
        "ppvz_vw": sales_item['ppvz_vw'],
        "ppvz_vw_nds": sales_item['ppvz_vw_nds'],
        "ppvz_office_name": sales_item['ppvz_office_name'],
        "bonus_type_name": sales_item.get('bonus_type_name'),
        "site_country": sales_item['site_country'],
        "penalty": sales_item['penalty'],
        "additional_payment": sales_item['additional_payment'],
        "rebill_logistic_cost": sales_item['rebill_logistic_cost'],
        "storage_fee": sales_item['storage_fee'],
        "deduction": sales_item['deduction'],
        "acceptance": sales_item['acceptance'],
        "goods_quantity": 0,
        "revenue": 0,
        "full_comission": 0,
        "other_deductions": 0,
        "cost_of_sales": 0,
        "for_withdraw": 0,
        "tax_base_amount": 0,
        "tax_costs": 0,
        "net_profit": 0,
        "revenue_before_spp": 0,
        "commission_before_spp": 0,
        "spp_amount": 0,
        "doc_type_name": sales_item['doc_type_name'],
        "created_at": date
    }


async def bulk_upsert_sales(session, sales_data):
    try:
        """Массовая вставка продаж"""
        if not sales_data:
            return

        async with session.begin_nested():

            for chunk in chunker(sales_data, CHUNK_SIZE_SALES):
                stmt = insert(Sales).values(chunk).on_conflict_do_nothing(
                    index_elements=['rrd_id']
                )
                await session.execute(stmt)

        await session.commit()
        return True

    except SQLAlchemyError as e:
        await session.rollback()
        logging.error(f"Sales upsert error: {str(e)}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error in sales_report_compilation: {str(e)}")
        await send_message_to_admin(f'Ошибка при вставке выручки в базу: {str(e)}')
        return False