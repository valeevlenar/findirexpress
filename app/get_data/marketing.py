import asyncio
from datetime import datetime, timedelta
import sqlalchemy
from sqlalchemy.dialects.postgresql import insert
import requests
import logging

from sqlalchemy import select, func

from app.admin.admin_message import send_message_to_admin
from app.database.api_functions import unauthorised_api_identified
from app.database.models import Seller, Marketing_costs_wb, Marketing_campaigns_stats, Orders, \
    Marketing_costs_by_SKU, Goods_cost
from app.database.classes.stocks import Stock
from app.database.support_functions import get_api_by_seller_id, get_barcode_by_nm_id_and_size
from app.dates import end_of_yesterday_func, start_for_downloading_data_func, end_of_Reporting_Week_func
from app.get_data.get_marketing_costs import get_marketing_costs_for_seller_id
from app.get_data.get_marketing_stats import get_marketing_statistics_for_seller_id
from app.get_data.orders import get_orders_by_seller
from config import get_reviews_data_url

#
# @with_session
# async def daily_get_marketing_costs(session):
#     try:
#         companies = await session.execute(select(Seller.id).
#                                           where(Seller.status=='Active',
#                                                 Seller.service_status==True))
#         companies = companies.mappings().all()
#
#         # Создаем список корутин
#         tasks = [get_prepare_marketing_costs_for_seller(session=session, seller_id=seller['id']) for seller in companies]
#
#         # Запускаем все корутины параллельно
#         await asyncio.gather(*tasks)
#
#         # await admin_paid_acceptance_download_status()
#     except Exception as e:
#         await send_message_to_admin(text=f'Ошибка в ежедневной функции по выгрузке маркетинговых расходов'
#                                          f'\nОшибка: {e}')
#         # Запись ошибки в лог
#         logging.exception("An error occurred: %s", exc_info=e)

async def get_prepare_marketing_costs_for_seller(session, seller_id):
    try:
        if await get_marketing_costs_for_seller_id(session=session, seller_id=seller_id):

            if await get_marketing_statistics_for_seller_id(session=session, seller_id=seller_id):
                return True
        else:
            await send_message_to_admin(f'Ошибка в выгрузке маркетинговых расходов по селлеру:'
                                        f'\nseller_id: {seller_id}')
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке маркетинговых расходов по селлеру:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def allocate_marketing_costs_to_sku(session, seller_id):
    try:
        # 2. Проверяем, что заказы выгружены
        logging.info(f'Seller_id={seller_id}: Проверяем что заказы выгружены')
        if not await get_orders_by_seller(seller_id=seller_id):
             return False
        logging.info(f'Seller_id={seller_id}: Начали аллокацию маркетинговых расходов')
        # 1. Объединяем запросы для tax_base и tax_rate
        seller_data = await session.execute(
            select(Seller.tax_base, Seller.tax_rate).where(Seller.id == seller_id)
        )
        seller = seller_data.first()
        if not seller:
            return False
        tax_base, tax_rate = seller.tax_base, seller.tax_rate


        # 3. Получаем граничные даты
        end_of_yesterday = await end_of_yesterday_func()
        first_unallocated_date = await session.scalar(select(func.min(Marketing_costs_wb.cost_date)).
                                           where(Marketing_costs_wb.seller_id == seller_id,
                                                 Marketing_costs_wb.cost_allocated == False,
                                                 Marketing_costs_wb.paymenttype != 'Бонусы',
                                                 Marketing_costs_wb.paymenttype != 'Кэшбэк'
                                                 ))

        if first_unallocated_date:
            date_from = first_unallocated_date.replace(hour=00,minute=00,second=00,microsecond=00)
        else:
            logging.info(f'Seller_id={seller_id}: Маркетинг уже разаллоцирован')
            return True
        logging.info(f'Seller_id={seller_id}: Аллоцируем с {str(date_from)}')
        # 4. Основной цикл обработки дней
        while True:
            if date_from > end_of_yesterday:
                return True

            date_to = min(date_from.replace(hour=23, minute=59, second=59, microsecond=999999),end_of_yesterday)
            # print(date_from, date_to)
            if await process_marketing_allocation_period(session, seller_id, date_from, date_to, tax_base, tax_rate):
                # print('день ок')
                if date_to >= end_of_yesterday:
                    return True

                elif date_to < end_of_yesterday:
                    date_from = date_to + timedelta(microseconds=1)
            else:
                return False

    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в функции распределения маркетинговых расходов:'
                                         f'\nSeller_id:{seller_id}'
                                         f'\nОшибка: {e}')
        await session.rollback()
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def process_marketing_allocation_period(session, seller_id, date_from, date_to, tax_base, tax_rate):
    try:
        end_of_yesterday = await end_of_yesterday_func()
        # 5. Получаем все расходы за период одним запросом
        marketing_costs = await session.execute(select(Marketing_costs_wb.id,
                                                                      Marketing_costs_wb.cost_date,
                                                                      Marketing_costs_wb.advertid,
                                                                      Marketing_costs_wb.updsum).
                                                where(Marketing_costs_wb.seller_id == seller_id,
                                                      Marketing_costs_wb.cost_allocated == False,
                                                      Marketing_costs_wb.cost_date >= date_from,
                                                      Marketing_costs_wb.cost_date <= date_to,
                                                      Marketing_costs_wb.paymenttype != 'Бонусы',
                                                      Marketing_costs_wb.paymenttype != 'Кэшбэк'))
        if not marketing_costs:
            return True
        marketing_costs_for_allocation = marketing_costs.mappings().all()
        # print(f'К аллокации {len(marketing_costs_for_allocation)} штук. Период: {date_from} - {date_to}')
        # print(marketing_costs_for_allocation)

        # 6. Предварительная загрузка всех необходимых данных
        advert_ids = {cost['advertid'] for cost in marketing_costs_for_allocation}
        cost_dates = {cost['cost_date'] for cost in marketing_costs_for_allocation}
        # print(advert_ids)
        # print(cost_dates)

        # 7. Получаем статистику просмотров одним запросом
        views_query = (select(Marketing_campaigns_stats.advert_id,
                             Marketing_campaigns_stats.cost_date,
                             func.sum(Marketing_campaigns_stats.views).label('total_views')).
                       where(Marketing_campaigns_stats.seller_id == seller_id,
                                   Marketing_campaigns_stats.advert_id.in_(advert_ids),
                                   Marketing_campaigns_stats.cost_date.in_(cost_dates)).
                             group_by(Marketing_campaigns_stats.advert_id, Marketing_campaigns_stats.cost_date))

        views_data = await session.execute(views_query)
        views_mapping = {(r.advert_id, r.cost_date): r.total_views for r in views_data}
        # print(views_mapping)

        for marketing_cost in marketing_costs_for_allocation:
            wb_cost_id = marketing_cost['id']
            cost_date = marketing_cost['cost_date']
            advert_id = marketing_cost['advertid']
            upd_sum = marketing_cost['updsum']
            total_views_per_advert_id = views_mapping.get((advert_id, cost_date))
            # print(f'wb_cost_id:{wb_cost_id},cost_date {cost_date}, advert_id {advert_id}, total_views {total_views_per_advert_id}')
            cost_date_for_stats = cost_date

            # 9. Поиск статистики для следующих дней при необходимости
            if not total_views_per_advert_id:
                logging.info(f'Seller_id={seller_id}: Нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}.Берем статистику следующего дня.')
                cost_date_for_stats = cost_date + timedelta(days=1)
                while cost_date_for_stats <= end_of_yesterday:
                    total_views_per_advert_id = await session.scalar(select(func.sum(Marketing_campaigns_stats.views)).
                                                       where(Marketing_campaigns_stats.seller_id == seller_id,
                                                             Marketing_campaigns_stats.advert_id == advert_id,
                                                             Marketing_campaigns_stats.cost_date == cost_date_for_stats))
                    if total_views_per_advert_id:
                        break
                    cost_date_for_stats += timedelta(days=1)
            if not total_views_per_advert_id:
                logging.info(f'Seller_id={seller_id}: Нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}.Пробуем статистику предыдущих дней.')
                cost_date_for_stats = cost_date - timedelta(days=1)
                start_date = await start_for_downloading_data_func()
                while cost_date_for_stats >= start_date:
                    total_views_per_advert_id = await session.scalar(select(func.sum(Marketing_campaigns_stats.views)).
                                                       where(Marketing_campaigns_stats.seller_id == seller_id,
                                                             Marketing_campaigns_stats.advert_id == advert_id,
                                                             Marketing_campaigns_stats.cost_date == cost_date_for_stats))
                    if total_views_per_advert_id:
                        break
                    cost_date_for_stats = cost_date_for_stats - timedelta(days=1)

            if not total_views_per_advert_id:

                await send_message_to_admin(f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                logging.info(f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                logging.exception(f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                continue

            # 10. Расчет стоимости за просмотр
            cost_per_view = upd_sum / total_views_per_advert_id
            # print('cost_per_view=', cost_per_view)

            # 11. Получение статистики по номенклатурам
            stats_query = (select(Marketing_campaigns_stats.nmid,
                                 func.sum(Marketing_campaigns_stats.views).label('total_views_per_nm')).
                                 where(Marketing_campaigns_stats.seller_id == seller_id,
                                       Marketing_campaigns_stats.advert_id == advert_id,
                                       Marketing_campaigns_stats.cost_date == cost_date_for_stats).
                                 group_by(Marketing_campaigns_stats.nmid))

            stats_data = await session.execute(stats_query)
            marketing_stats_by_nm = {r.nmid: r.total_views_per_nm for r in stats_data}

            if not marketing_stats_by_nm:
                await send_message_to_admin(
                    f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                logging.info(
                    f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                logging.exception(
                    f'Seller_id={seller_id}:Ошибка-нет статистики по маркетинговым расходам. Advert_id:{advert_id},Date:{cost_date}')
                continue

            # print(marketing_stats)

            # 12. Обработка номенклатур
            for nm_id, views in marketing_stats_by_nm.items():
                cost_for_nm = cost_per_view * views
                if await process_nm_allocation(session=session,
                                               seller_id=seller_id,
                                               nm_id=nm_id,
                                               cost_date=cost_date,
                                               cost_for_nm=cost_for_nm,
                                               tax_base=tax_base,
                                               tax_rate=tax_rate,
                                               wb_cost_id=wb_cost_id,
                                               advert_id=advert_id):
                    pass
                else:
                    return False

        return True

    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в функции распределения маркетинговых расходов:'
                                         f'\nSeller_id:{seller_id}'
                                         f'\nОшибка: {e}')
        await session.rollback()
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def process_nm_allocation(session, seller_id, nm_id, cost_date, cost_for_nm,
                                tax_base, tax_rate, wb_cost_id, advert_id):
    try:
        orders = await session.execute(select(Orders.barcode,
                                              func.sum(Orders.quantity).label('total_qty')).
                                       where(Orders.seller_id == seller_id,
                                             Orders.nmid == nm_id,
                                             Orders.order_date == cost_date).
                                       group_by(Orders.barcode))
        orders_data = orders.mappings().all()

        if orders_data:
            total_qty = sum(orders['total_qty'] for orders in orders_data)
            cost_per_order = cost_for_nm / total_qty
            for barcode_orders in orders_data:
                barcode = barcode_orders['barcode']
                cost_for_barcode = cost_per_order * barcode_orders['total_qty']
                tax_costs, net_profit = calculate_tax_effects(cost_for_barcode,
                                                              tax_base,
                                                              tax_rate)

                await save_allocated_marketing_cost_to_db(session=session,
                                                          seller_id=seller_id,
                                                          wb_cost_id=wb_cost_id,
                                                          adv_type='wb_promotion',
                                                          advert_id=advert_id,
                                                          cost_date=cost_date,
                                                          nm_id=nm_id,
                                                          barcode=barcode,
                                                          cost_for_barcode=cost_for_barcode,
                                                          tax_costs=tax_costs,
                                                          net_profit=net_profit,
                                                          review_id=None)

        # Если не было заказов, то распределяем на количество баркодов в остатках:
        else:
            # print('нет заказов')
            barcodes = await session.execute(select(Stock.barcode).
                                             where(Stock.seller_id == seller_id,
                                                   Stock.date_in_stock >= cost_date.replace(hour=00,minute=00,second=00,microsecond=00),
                                                   Stock.date_in_stock <= cost_date,
                                                   Stock.nmid == nm_id,
                                                   Stock.quantity > 0).
                                             group_by(Stock.barcode))
            barcodes = barcodes.mappings().all()
            # print('баркоды из остатков:',barcodes)

            # Если нет в остатках, распределяем на Goods_cost:
            if not barcodes:
                barcodes = await session.execute(select(Goods_cost.barcode).
                                                 where(Goods_cost.seller_id == seller_id,
                                                       Goods_cost.nm_id == nm_id))
                barcodes = barcodes.mappings().all()
                # print('баркоды из Goods_cost:',barcodes)

            if barcodes:
                barcodes_count = len(barcodes)
                # print(barcodes_count)
                cost_for_barcode = cost_for_nm / barcodes_count
                tax_costs, net_profit = calculate_tax_effects(cost_for_barcode,
                                                              tax_base,
                                                              tax_rate)

                for barcode in barcodes:
                    await save_allocated_marketing_cost_to_db(session=session,
                                                              seller_id=seller_id,
                                                              wb_cost_id=wb_cost_id,
                                                              adv_type='wb_promotion',
                                                              advert_id=advert_id,
                                                              cost_date=cost_date,
                                                              nm_id=nm_id,
                                                              barcode=barcode['barcode'],
                                                              cost_for_barcode=cost_for_barcode,
                                                              tax_costs=tax_costs,
                                                              net_profit=net_profit,
                                                              review_id=None)
            elif not barcodes:
                tax_costs, net_profit = calculate_tax_effects(cost_for_nm,
                                                              tax_base,
                                                              tax_rate)

                await save_allocated_marketing_cost_to_db(session=session,
                                                          seller_id=seller_id,
                                                          wb_cost_id=wb_cost_id,
                                                          adv_type='wb_promotion',
                                                          advert_id=advert_id,
                                                          cost_date=cost_date,
                                                          nm_id=nm_id,
                                                          barcode=None,
                                                          cost_for_barcode=cost_for_nm,
                                                          tax_costs=tax_costs,
                                                          net_profit=net_profit,
                                                          review_id=None)

        await mark_wb_marketing_cost_as_allocated_in_db(session=session,
                                                        seller_id=seller_id,
                                                        wb_cost_id=wb_cost_id)

        return True
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка в функции распределения маркетинговых расходов:'
                                         f'\nSeller_id:{seller_id}'
                                         f'\nОшибка: {e}')
        await session.rollback()
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

async def save_allocated_marketing_cost_to_db(session,
                                              seller_id,
                                              wb_cost_id,
                                              adv_type,
                                              advert_id,
                                              cost_date,
                                              nm_id,
                                              barcode,
                                              cost_for_barcode,
                                              tax_costs,
                                              net_profit,
                                              review_id):
    try:
        async with session.begin_nested():
            marketing_by_sku_to_insert = {'seller_id': seller_id,
                                          'wb_cost_id': wb_cost_id,
                                          'type': adv_type,
                                          'advert_id': advert_id,
                                          'cost_date': cost_date,
                                          'nmid': nm_id,
                                          'barcode': barcode,
                                          'cost_sum': cost_for_barcode,
                                          'tax_costs': tax_costs,
                                          'net_profit': net_profit,
                                          'updated_at': datetime.now(),
                                          'review_id': review_id}
            stmt = insert(Marketing_costs_by_SKU).values(marketing_by_sku_to_insert)
            stmt = stmt.on_conflict_do_update(
                constraint='marketing_by_sku_unique_constraint',
                set_={
                    'cost_sum': stmt.excluded.cost_sum,
                    'tax_costs': stmt.excluded.tax_costs,
                    'net_profit': stmt.excluded.net_profit,
                    'updated_at': stmt.excluded.updated_at
                }
            )
            await session.execute(stmt)
        await session.commit()

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

async def mark_wb_marketing_cost_as_allocated_in_db(session, seller_id, wb_cost_id):
    try:
        async with session.begin_nested():
            query = sqlalchemy.update(Marketing_costs_wb).where(Marketing_costs_wb.seller_id == seller_id,
                                                            Marketing_costs_wb.id==wb_cost_id).values(cost_allocated=True)
            await session.execute(query)
        await session.commit()
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

async def save_and_allocate_reviews_payments_at_db(session, seller_id, sales_item):
    try:
        supplier_oper_name = sales_item['supplier_oper_name']
        bonus_type_name = sales_item['bonus_type_name']

        if supplier_oper_name == "Удержание":
            if 'Списание за отзыв' in bonus_type_name:
                nm_id = int(bonus_type_name.split('товар ')[1])
                review_id = (bonus_type_name.split('Списание за отзыв ')[1]).split(':')[0]
                advert_id = int((bonus_type_name.split('акция №')[1]).split(',')[0])
                # print(nm_id, review_id)
                barcode = await get_barcode_by_review_id_from_wb(session=session,
                                                                 seller_id=seller_id,
                                                                 review_id=review_id)
                if barcode:
                    nm_id_for_barcode = await session.scalar(select(Goods_cost.nm_id).
                                                             where(Goods_cost.seller_id == seller_id,
                                                                   Goods_cost.barcode==barcode))
                    tax_base = await session.scalar(select(Seller.tax_base).
                                                    where(Seller.id == seller_id))
                    tax_rate = await session.scalar(select(Seller.tax_rate).
                                                    where(Seller.id == seller_id))
                    tax_costs = 0
                    net_profit = 0
                    if tax_base == "income":
                        tax_costs = 0
                        net_profit = -sales_item['deduction']
                    elif tax_base == "income_less_exp":
                        tax_costs = sales_item['deduction'] * tax_rate
                        net_profit = -sales_item['deduction'] + tax_costs
                    # print(tax_base, tax_rate)
                    # print(nm_id_for_barcode, nm_id)
                    if nm_id_for_barcode == nm_id:
                        # print('все ок с баллами за отзыв')
                        await save_allocated_marketing_cost_to_db(session=session,
                                                                  seller_id=seller_id,
                                                                  wb_cost_id=0,
                                                                  adv_type='reviews',
                                                                  advert_id=advert_id,
                                                                  cost_date=sales_item['transaction_date'],
                                                                  nm_id=nm_id,
                                                                  barcode=barcode,
                                                                  cost_for_barcode=sales_item['deduction'],
                                                                  tax_costs=tax_costs,
                                                                  net_profit=net_profit,
                                                                  review_id=review_id)
                    else:
                        pass
                        # print('что-то не так')

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

async def get_barcode_by_review_id_from_wb (session, seller_id, review_id):
    try:
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = {'id': str(review_id)}
        res=requests.get(get_reviews_data_url,headers=headers, params=params)
        # print(res.status_code)
        # print(res.text)

        if res.status_code == 200:
            await asyncio.sleep(1)
            # print(res)
            result = res.json()
            # print(result)
            nm_id = result['data']['productDetails']['nmId']
            size = result['data']['productDetails']['size']
            if size =='':
                size = '0'
            barcode = await get_barcode_by_nm_id_and_size(session=session,
                                                          seller_id=seller_id,
                                                          nm_id = nm_id,
                                                          size=size)
            # print(barcode)
            return barcode

        elif res.status_code ==429:
            await asyncio.sleep(60)
            await get_barcode_by_review_id_from_wb(session=session,
                                                   seller_id=seller_id,
                                                   review_id=review_id)

        elif res.status_code == 401:
            await unauthorised_api_identified(session=session, seller_id=seller_id,wb_api=active_api)
            return False

        else:
            await send_message_to_admin(f'Ошибка в выгрузке детализации по отзыву:'
                                        f'\nseller_id: {seller_id}'
                                        f'\nОшибка: {res.status_code}, {res.text}')
            return False
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке детализации по отзыву:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

def calculate_tax_effects(amount, tax_base, tax_rate):
    tax_costs = 0
    net_profit = 0
    if tax_base == "income":
        tax_costs = 0
        net_profit = -amount
    elif tax_base == "income_less_exp":
        tax_costs = amount * tax_rate
        net_profit = -amount + tax_costs
    return tax_costs, net_profit

async def check_marketing_costs_allocation(session, seller_id):
    try:
        start_date = await start_for_downloading_data_func()
        end_date = await end_of_Reporting_Week_func()
        total_marketing_costs = await session.scalar(select(func.sum(Marketing_costs_wb.updsum)).
                                                                         where(Marketing_costs_wb.seller_id == seller_id,
                                                                               Marketing_costs_wb.cost_date>=start_date,
                                                                               Marketing_costs_wb.cost_date<=end_date,
                                                                               Marketing_costs_wb.cost_allocated == True,
                                                                               Marketing_costs_wb.paymenttype != 'Бонусы',
                                                                               Marketing_costs_wb.paymenttype != 'Кэшбэк'
                                                                               )) or 0.0
        total_allocated_marketing_costs = await session.scalar(select(func.sum(Marketing_costs_by_SKU.cost_sum)).
                                                                   where(Marketing_costs_by_SKU.seller_id == seller_id,
                                                                         Marketing_costs_by_SKU.type == 'wb_promotion',
                                                                         Marketing_costs_by_SKU.cost_date>=start_date,
                                                                         Marketing_costs_by_SKU.cost_date<=end_date)) or 0.0

        # print('total_marketing_costs', total_marketing_costs)
        # print('total_allocated_marketing_costs', total_allocated_marketing_costs)

        diff = total_marketing_costs - total_allocated_marketing_costs
        # print(diff)

        if abs(diff) <= 5:
            logging.info(f'Seller_id: {seller_id}. Аллокация маркетинговых расходов-Ок')
            logging.info(f'Seller_id: {seller_id}. total_marketing_costs: {total_marketing_costs}, total_allocated_marketing_costs: {total_allocated_marketing_costs}')
            return True
        else:
            await send_message_to_admin(f'Ошибка в проверке аллокации маркетинга:'
                                    f'\nSeller_id: {seller_id}'
                                        f'\ntotal_marketing_costs: {total_marketing_costs}'
                                        f'\ntotal_allocated_marketing_costs: {total_allocated_marketing_costs}')
            logging.info(f'Seller_id: {seller_id}. Аллокация маркетинговых расходов-не ок')
            logging.info(f'Seller_id: {seller_id}. total_marketing_costs: {total_marketing_costs}, total_allocated_marketing_costs: {total_allocated_marketing_costs}')
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в проверке распределении платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)