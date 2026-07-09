import numpy as np
from datetime import timedelta, datetime
from app.database.models import Marketing_costs_by_SKU, Storage_costs, Supplies, Seller, \
    Orders_nm
from app.database.classes.stocks import Stock
from app.database.models import Goods_cost
from app.database.classes.sales import Sales
from sqlalchemy import select, func, cast, Float
from sqlalchemy import and_
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
import warnings

from app.wrappers import log_and_notify_admin

warnings.simplefilter(action='ignore', category=FutureWarning)


@log_and_notify_admin
async def get_detailed_stock_table_by_subject(session, ws, seller_id, date_from, date_to):
    reporting_period_length = (date_to - date_from).days + 1
    date_end_str = datetime.strftime(date_to + timedelta(days=1), '%Y-%m-%d')
    # Проверяем, есть ли по селлеру остатки на конец отчетной недели
    seller_stocks = await session.scalar(select(Stock.id).
                                         where(Stock.seller_id == seller_id,
                                               Stock.date_in_stock_str == date_end_str))
    if not seller_stocks:
        date_end_for_stock = date_to
        date_end_for_stock_str = None
        while not date_end_for_stock_str:
            date_end_for_stock = date_end_for_stock + timedelta(days=1)
            date_start_for_stock = date_end_for_stock.replace(hour=00, minute=00, second=00, microsecond=000000)
            date_end_for_stock_str = await session.scalar(select(Stock.date_in_stock_str).
                                                          where(Stock.seller_id == seller_id,
                                                                Stock.total_at_cost != 0,
                                                                Stock.date_in_stock >= date_start_for_stock,
                                                                Stock.date_in_stock <= date_end_for_stock))
        date_end_for_stock = datetime.strptime(date_end_for_stock_str, '%Y-%m-%d').replace(hour=23, minute=59,
                                                                                           second=59,
                                                                                           microsecond=999999)
        date_start_for_stock = date_end_for_stock.replace(hour=00, minute=00, second=00, microsecond=000000)
        add_date_end_name = f'(на {date_end_for_stock_str})'
    else:
        date_end_for_stock = date_to + timedelta(days=1)
        date_start_for_stock = date_end_for_stock.replace(hour=00, minute=00, second=00, microsecond=000000)
        add_date_end_name = '(на отчетную дату)'

    stocks_result = (select(Goods_cost.subject_name,
                            func.sum(Stock.quantity).label('quantity'),
                            func.sum(Stock.inwaytoclient).label('inWayToClient'),
                            func.sum(Stock.inwayfromclient).label('inWayFromClient'),
                            func.sum(Stock.quantityfull).label('quantityFull'),
                            func.sum(Stock.total_at_cost).label('total_at_cost'),
                            func.sum(Stock.total_at_sell_price).label('total_at_sell_price')).
                     outerjoin(Stock, Stock.barcode == Goods_cost.barcode).
                     where(and_(Goods_cost.seller_id == seller_id,
                                Stock.seller_id == seller_id,
                                Stock.date_in_stock >= date_start_for_stock,
                                Stock.date_in_stock <= date_end_for_stock)).
                     group_by(Goods_cost.subject_name).subquery())

    sales_result = (select(Goods_cost.subject_name,
                           func.sum(Sales.goods_quantity).label('goods_quantity'),
                           cast(func.sum(Sales.revenue), Float).label('revenue'),
                           func.sum(Sales.cost_of_sales).label('cost_of_sales'),
                           func.sum(Sales.full_comission).label('full_comission'),
                           func.sum(Sales.delivery_rub).label('logistic_costs'),
                           func.sum(Sales.storage_fee).label('storage_fee'),
                           func.sum(Sales.other_deductions).label('other_deductions'),
                           func.sum(Sales.penalty).label('penalty'),
                           func.sum(Sales.tax_costs).label('tax_costs'),
                           func.sum(Sales.net_profit).label('net_profit'),
                           func.sum(Sales.revenue_before_spp).label('revenue_before_spp'),
                           func.sum(Sales.commission_before_spp).label('commission_before_spp'),
                           func.sum(Sales.spp_amount).label('spp_amount')).
                    outerjoin(Sales, Sales.barcode == Goods_cost.barcode).
                    where(and_(Goods_cost.seller_id == seller_id,
                               Sales.seller_id == seller_id,
                               Sales.transaction_date.between(date_from, date_to))).
                    group_by(Goods_cost.subject_name).subquery())

    marketing_result = (select(Goods_cost.subject_name,
                               func.sum(Marketing_costs_by_SKU.cost_sum).label('marketing'),
                               func.sum(Marketing_costs_by_SKU.tax_costs).label('marketing_tax_costs'),
                               func.sum(Marketing_costs_by_SKU.net_profit).label('marketing_net_profit'),
                               ).
                        outerjoin(Marketing_costs_by_SKU, Marketing_costs_by_SKU.barcode == Goods_cost.barcode).
                        where(and_(Goods_cost.seller_id == seller_id,
                                   Marketing_costs_by_SKU.seller_id == seller_id,
                                   Marketing_costs_by_SKU.cost_date.between(date_from, date_to))).
                        group_by(Goods_cost.subject_name).subquery())

    orders_result = (select(Orders_nm.subject_name,
                            func.sum(Orders_nm.quantity).label('orders_number'),
                            func.sum(Orders_nm.total_sum).label('orders_sum')
                            ).
                     where(and_(Orders_nm.seller_id == seller_id,
                                Orders_nm.order_date.between(date_from, date_to))).
                     group_by(Orders_nm.subject_name).subquery())

    storage_result = (select(Goods_cost.subject_name,
                             func.sum(Storage_costs.warehouseprice).label('storage_costs')
                             ).
                      outerjoin(Storage_costs, Storage_costs.barcode == Goods_cost.barcode).
                      where(and_(Goods_cost.seller_id == seller_id,
                                 Storage_costs.seller_id == seller_id,
                                 Storage_costs.cost_date.between(date_from, date_to))).
                      group_by(Goods_cost.subject_name).subquery())

    paid_acceptance_result = (select(Goods_cost.subject_name,
                                     func.sum(Supplies.total_supply_costs).label('paid_acceptance')
                                     ).
                              outerjoin(Supplies, Supplies.barcode == Goods_cost.barcode).
                              where(and_(Goods_cost.seller_id == seller_id,
                                         Supplies.seller_id == seller_id,
                                         Supplies.transaction_date.between(date_from, date_to))).
                              group_by(Goods_cost.subject_name).subquery())

    # Расчет средних недельных остатков
    average_subquery = (select(Stock.subject,
                               Stock.date_in_stock_str,
                               func.sum(Stock.quantityfull).label('total_stocks_quantity'),
                               func.sum(Stock.total_at_cost).label('total_at_cost')).
                        where(and_(Stock.seller_id == seller_id,
                                   Stock.date_in_stock >= date_start_for_stock,
                                   Stock.date_in_stock <= date_end_for_stock)).
                        group_by(Stock.subject,
                                 Stock.date_in_stock_str).subquery())

    average_stocks_result = (select(Stock.subject,
                                    cast(func.avg(average_subquery.c.total_stocks_quantity), Float).label(
                                        'average_quantity'),
                                    cast(func.avg(average_subquery.c.total_at_cost), Float).label('average_at_cost')).
                             where(Stock.seller_id == seller_id).
                             outerjoin(average_subquery, Stock.subject == average_subquery.c.subject).
                             group_by(Stock.subject).subquery())

    goods_subq = (select(Goods_cost.subject_name).
                  where(Goods_cost.seller_id == seller_id).
                  group_by(Goods_cost.subject_name).subquery())

    result = await session.execute(select(goods_subq.c.subject_name.label('Предмет'),
                                          cast(func.sum(stocks_result.c.quantity), Float).label('На складе ВБ, шт'),
                                          cast(func.sum(stocks_result.c.inWayToClient), Float).label(
                                              'В пути к клиенту, шт.'),
                                          cast(func.sum(stocks_result.c.inWayFromClient), Float).label(
                                              'В пути от клиента, шт.'),
                                          cast(func.sum(stocks_result.c.quantityFull), Float).label(
                                              f'Всего остатки на ВБ, шт. {add_date_end_name}'),
                                          cast(func.sum(stocks_result.c.total_at_cost), Float).label(
                                              'Остатки по себестоимости, руб.'),
                                          cast(func.sum(stocks_result.c.total_at_sell_price), Float).label(
                                              'Остатки по цене продажи, руб.'),
                                          cast(func.sum(orders_result.c.orders_sum), Float).label('Заказы, руб.'),
                                          cast(func.sum(orders_result.c.orders_number), Float).label('Заказы, шт.'),
                                          cast(func.sum(sales_result.c.goods_quantity), Float).label('Продажи, шт.'),
                                          cast(func.sum(sales_result.c.revenue_before_spp), Float).label(
                                              'Выручка до СПП, руб.'),
                                          cast(func.sum(sales_result.c.commission_before_spp), Float).label(
                                              'Комиссия до СПП, руб.'),
                                          cast(func.sum(sales_result.c.spp_amount), Float).label('СПП, руб.'),
                                          cast(func.sum(sales_result.c.revenue), Float).label(
                                              'Выручка после СПП (в ОПУ), руб.'),
                                          cast(func.sum(sales_result.c.full_comission), Float).label(
                                              'Комиссия после СПП, руб.'),
                                          cast(func.sum((sales_result.c.cost_of_sales * (-1))), Float).label(
                                              'Себестоимость, руб.'),
                                          cast(func.sum(sales_result.c.logistic_costs), Float).label('Логистика, руб.'),
                                          cast(func.sum(sales_result.c.other_deductions), Float).label(
                                              'other_deductions'),
                                          cast(func.sum(sales_result.c.penalty), Float).label('penalty'),
                                          cast(func.sum(storage_result.c.storage_costs), Float).label('storage'),
                                          cast(func.sum(paid_acceptance_result.c.paid_acceptance), Float).label(
                                              'paid_acceptance'),
                                          cast(func.sum(average_stocks_result.c.average_quantity), Float).label(
                                              'average_stocks'),
                                          cast(func.sum(average_stocks_result.c.average_at_cost), Float).label(
                                              'average_at_cost'),
                                          cast(func.sum(marketing_result.c.marketing), Float).label('marketing')
                                          ).
                                   outerjoin(stocks_result, goods_subq.c.subject_name == stocks_result.c.subject_name).
                                   outerjoin(sales_result, goods_subq.c.subject_name == sales_result.c.subject_name).
                                   outerjoin(marketing_result,
                                             goods_subq.c.subject_name == marketing_result.c.subject_name).
                                   outerjoin(orders_result, goods_subq.c.subject_name == orders_result.c.subject_name).
                                   outerjoin(storage_result,
                                             goods_subq.c.subject_name == storage_result.c.subject_name).
                                   outerjoin(paid_acceptance_result,
                                             goods_subq.c.subject_name == paid_acceptance_result.c.subject_name).
                                   outerjoin(average_stocks_result,
                                             goods_subq.c.subject_name == average_stocks_result.c.subject).
                                   group_by(goods_subq.c.subject_name).
                                   order_by(goods_subq.c.subject_name))

    stocks = pd.DataFrame(result)
    stock_columns = stocks.columns.get_loc('Остатки по цене продажи, руб.')

    # Подготавливаем "безопасные делители"
    safe_orders = stocks['Заказы, шт.'].replace(0, np.nan)
    safe_revenue_before = stocks['Выручка до СПП, руб.'].replace(0, np.nan)
    safe_revenue_after = stocks['Выручка после СПП (в ОПУ), руб.'].replace(0, np.nan)
    safe_cost = stocks['Себестоимость, руб.'].replace(0, np.nan)

    # Добавляем процент выкупа
    stocks.insert(stock_columns + 4, 'Процент выкупа, %', stocks['Продажи, шт.'] / safe_orders)

    # Добавляем показатели до СПП
    stocks.insert(stock_columns + 7, 'Комиссия до СПП, %', stocks['Комиссия до СПП, руб.'] / safe_revenue_before)
    stocks.insert(stock_columns + 9, 'СПП, %', stocks['СПП, руб.'] / safe_revenue_before)

    # Добавляем маркетинг
    stocks.insert(stock_columns + 11, 'Маркетинг, руб.', stocks.pop('marketing'))
    stocks.insert(stock_columns + 12, 'ДРР до СПП, %', stocks['Маркетинг, руб.'] / safe_revenue_before)
    stocks.insert(stock_columns + 13, 'ДРР после СПП, %', stocks['Маркетинг, руб.'] / safe_revenue_after)

    # Добавляем комиссию после СПП
    stocks.insert(stock_columns + 15, 'Комиссия после СПП, %', stocks['Комиссия после СПП, руб.'] / safe_revenue_after)

    # Добавляем наценку
    stocks.insert(stock_columns + 17, 'Наценка до СПП, %',
                  (stocks['Выручка до СПП, руб.'] - stocks['Себестоимость, руб.']) / safe_cost)
    stocks.insert(stock_columns + 18, 'Наценка после СПП, %',
                  (stocks['Выручка после СПП (в ОПУ), руб.'] - stocks['Себестоимость, руб.']) / safe_cost)

    # Добавляем хранение, платную приемку, прочие удержания и штрафы
    stocks.insert(stock_columns + 20, 'Хранение, руб.', stocks.pop('storage'))
    stocks.insert(stock_columns + 21, 'Платная приемка, руб.', stocks.pop('paid_acceptance'))
    stocks.insert(stock_columns + 22, 'Прочие удержания и штрафы, руб.',
                  (stocks.pop('other_deductions') + stocks.pop('penalty')))

    # Заполняем пустые ячейки нулями до расчетов:
    cols_to_fill_zero = [
        'На складе ВБ, шт', 'В пути к клиенту, шт.', 'В пути от клиента, шт.',
        f'Всего остатки на ВБ, шт. {add_date_end_name}', 'Остатки по себестоимости, руб.',
        'Остатки по цене продажи, руб.', 'Заказы, руб.', 'Заказы, шт.', 'Продажи, шт.',
        'Выручка до СПП, руб.', 'Комиссия до СПП, руб.', 'Комиссия до СПП, %', 'СПП, руб.',
        'СПП, %', 'Процент выкупа, %', 'Выручка после СПП (в ОПУ), руб.', 'Маркетинг, руб.',
        'ДРР до СПП, %', 'ДРР после СПП, %', 'Комиссия после СПП, руб.', 'Комиссия после СПП, %',
        'Себестоимость, руб.', 'Наценка до СПП, %', 'Наценка после СПП, %', 'Логистика, руб.',
        'Хранение, руб.', 'Платная приемка, руб.', 'Прочие удержания и штрафы, руб.'
    ]
    for col in cols_to_fill_zero:
        stocks[col] = stocks[col].fillna(0)

    # Добавляем Налоги и чистую прибыль
    tax_base = await session.scalar(select(Seller.tax_base).where(Seller.id == seller_id))
    tax_rate = await session.scalar(select(Seller.tax_rate).where(Seller.id == seller_id))

    stocks.insert(stock_columns + 23, 'pbt',
                  (stocks['Выручка после СПП (в ОПУ), руб.'] - stocks['Комиссия после СПП, руб.']
                   - stocks['Маркетинг, руб.'] - stocks['Себестоимость, руб.']
                   - stocks['Логистика, руб.'] - stocks['Хранение, руб.']
                   - stocks['Платная приемка, руб.'] - stocks['Прочие удержания и штрафы, руб.']))

    if tax_base == "income":
        stocks.insert(stock_columns + 23, 'Налоги, руб.', (stocks['Выручка после СПП (в ОПУ), руб.'] * tax_rate))
    elif tax_base == "income_less_exp":
        stocks.insert(stock_columns + 23, 'Налоги, руб.', (stocks['pbt'] * tax_rate))

    stocks.insert(stock_columns + 24, 'Чистая прибыль, руб.', (stocks.pop('pbt') - stocks['Налоги, руб.']))

    stocks['Налоги, руб.'] = stocks['Налоги, руб.'].fillna(0)
    stocks['Чистая прибыль, руб.'] = stocks['Чистая прибыль, руб.'].fillna(0)

    # Маржинальность, Оборачиваемость и ROI
    safe_revenue_before_2 = stocks['Выручка до СПП, руб.'].replace(0, np.nan)
    safe_revenue_after_2 = stocks['Выручка после СПП (в ОПУ), руб.'].replace(0, np.nan)
    safe_sales_2 = stocks['Продажи, шт.'].replace(0, np.nan)
    safe_avg_cost = stocks.pop('average_at_cost').replace(0, np.nan)

    stocks.insert(stock_columns + 25, 'Маржинальность до СПП, %',
                  stocks['Чистая прибыль, руб.'] / safe_revenue_before_2)
    stocks.insert(stock_columns + 26, 'Маржинальность после СПП, %',
                  stocks['Чистая прибыль, руб.'] / safe_revenue_after_2)
    stocks['Маржинальность до СПП, %'] = stocks['Маржинальность до СПП, %'].fillna('н/п')
    stocks['Маржинальность после СПП, %'] = stocks['Маржинальность после СПП, %'].fillna('н/п')

    stocks.insert(stock_columns + 27, 'Оборачиваемость, дней',
                  (stocks.pop('average_stocks') * reporting_period_length / safe_sales_2))
    stocks['Оборачиваемость, дней'] = stocks['Оборачиваемость, дней'].fillna('н/п')

    stocks.insert(stock_columns + 28, 'ROI, %',
                  (stocks['Чистая прибыль, руб.'] * (365 / reporting_period_length) / safe_avg_cost))
    stocks['ROI, %'] = stocks['ROI, %'].fillna('н/п')

    # Добавляем блок на 1 ед
    stocks.insert(stock_columns + 29, ' ', '')
    stocks.insert(stock_columns + 30, 'Сумма к выводу (чистая прибыль + налоги + себестоимость)',
                  (stocks['Чистая прибыль, руб.'] + stocks['Налоги, руб.'] + stocks['Себестоимость, руб.']))
    stocks.insert(stock_columns + 31, '  ', '')

    stocks.insert(stock_columns + 32, 'Средняя цена продажи до СПП, руб.',
                  stocks['Выручка до СПП, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 33, 'Комиссия на 1 ед продаж, до СПП, руб.',
                  stocks['Комиссия до СПП, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 34, 'Себестоимость продаж 1 ед., руб.', stocks['Себестоимость, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 35, 'Логистика на 1 ед. продаж, руб.', stocks['Логистика, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 36, 'Хранение на 1 ед. продаж, руб.', stocks['Хранение, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 37, 'Платная приемка на 1 ед. продаж, руб.',
                  stocks['Платная приемка, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 38, 'Налоги на 1 ед. продаж, руб.', stocks['Налоги, руб.'] / safe_sales_2)

    stocks.insert(stock_columns + 39, 'Итого расходы на 1 ед. (без маркетинга, прочих расходов и штрафов), руб.',
                  (stocks['Комиссия на 1 ед продаж, до СПП, руб.'] + stocks['Себестоимость продаж 1 ед., руб.']
                   + stocks['Логистика на 1 ед. продаж, руб.'] + stocks['Хранение на 1 ед. продаж, руб.']
                   + stocks['Платная приемка на 1 ед. продаж, руб.'] + stocks['Налоги на 1 ед. продаж, руб.']))

    stocks.insert(stock_columns + 40, 'Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), руб.',
                  (stocks['Средняя цена продажи до СПП, руб.'] - stocks[
                      'Итого расходы на 1 ед. (без маркетинга, прочих расходов и штрафов), руб.']))

    safe_price = stocks['Средняя цена продажи до СПП, руб.'].replace(0, np.nan)

    stocks.insert(stock_columns + 41, 'Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), %',
                  stocks['Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), руб.'] / safe_price)

    stocks.insert(stock_columns + 42, 'Маркетинг на 1 ед. продаж, руб.', stocks['Маркетинг, руб.'] / safe_sales_2)
    stocks.insert(stock_columns + 43, 'ДРР на 1 ед, %', stocks['Маркетинг, руб.'] / safe_price)

    stocks.insert(stock_columns + 44, 'Итого прибыль на 1 ед. (без прочих расходов и штрафов), руб.',
                  (stocks['Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), руб.'] - stocks[
                      'Маркетинг на 1 ед. продаж, руб.']))

    stocks.insert(stock_columns + 45, 'Маржинальность на 1 ед. (без прочих расходов и штрафов), %',
                  stocks['Итого прибыль на 1 ед. (без прочих расходов и штрафов), руб.'] / safe_price)

    # Финальное заполнение нулями для новых колонок
    cols_to_fill_zero_2 = [
        'Средняя цена продажи до СПП, руб.', 'Комиссия на 1 ед продаж, до СПП, руб.',
        'Себестоимость продаж 1 ед., руб.',
        'Логистика на 1 ед. продаж, руб.', 'Хранение на 1 ед. продаж, руб.', 'Платная приемка на 1 ед. продаж, руб.',
        'Налоги на 1 ед. продаж, руб.', 'Итого расходы на 1 ед. (без маркетинга, прочих расходов и штрафов), руб.',
        'Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), руб.',
        'Итого прибыль на 1 ед. (до вычета маркетинга, прочих расходов и штрафов), %',
        'Маркетинг на 1 ед. продаж, руб.', 'ДРР на 1 ед, %',
        'Итого прибыль на 1 ед. (без прочих расходов и штрафов), руб.',
        'Маржинальность на 1 ед. (без прочих расходов и штрафов), %',
        'Сумма к выводу (чистая прибыль + налоги + себестоимость)'
    ]
    for col in cols_to_fill_zero_2:
        stocks[col] = stocks[col].fillna(0)

    # Скрываем строки с нулевыми остатками и продажами
    stocks['temp_for_zero_columns'] = (stocks[f'Всего остатки на ВБ, шт. {add_date_end_name}'] +
                                       stocks['Заказы, шт.'] +
                                       stocks['Продажи, шт.'] +
                                       stocks['Чистая прибыль, руб.'])

    stocks = stocks[stocks['temp_for_zero_columns'] != 0]
    del stocks['temp_for_zero_columns']

    # заполняем лист Еженедельный отчет
    ws = ws
    for r in dataframe_to_rows(stocks, header=True, index=False):
        ws.append(r)

    # Форматирование листа "Детализация по SKU"
    acc_format = r'_(* #,##0_);_* \(#,##0\);_(* "-"_);_(@_)'
    percent_format = r'0.0%;-0.0%;_(* "-"_);_(@_)'

    # Раскрашиваем недельные столбцы:
    thin_color = Side(border_style="thin", color="BFBFBF")
    light_green_fill = PatternFill(start_color='F4F7ED', end_color='F4F7ED', fill_type='solid')
    mid_green_fill = PatternFill(start_color='E5EDD3', end_color='E5EDD3', fill_type='solid')
    dark_green_fill = PatternFill(start_color='D8E4BC', end_color='D8E4BC', fill_type='solid')
    light_orange_fill = PatternFill(start_color='FDE9D9', end_color='FDE9D9', fill_type='solid')
    dark_orange_fill = PatternFill(start_color='FCD5B4', end_color='FCD5B4', fill_type='solid')
    dark_grey_fill = PatternFill(start_color='BFBFBF', end_color='BFBFBF', fill_type='solid')
    right_align = Alignment(horizontal='right')

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
                cell.number_format = acc_format
                cell.font = Font(name='Calibri', size=10)
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Меняем ширину всех столбцов
    ws.column_dimensions['AF'].width = 16
    ws.column_dimensions['AG'].width = 16
    ws.column_dimensions['AH'].width = 16
    ws.column_dimensions['AK'].width = 16
    ws.column_dimensions['AT'].width = 16
    ws.column_dimensions['AU'].width = 17
    ws.column_dimensions['AV'].width = 17
    ws.column_dimensions['AY'].width = 16
    ws.column_dimensions['AZ'].width = 16

    number_columns = ['B', 'C', 'D']
    for col in number_columns:
        ws.column_dimensions[col].width = 10

    number_columns2 = ['E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V',
                       'W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AI',
                       'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AW', 'AX']
    for col in number_columns2:
        ws.column_dimensions[col].width = 13

    # Процентный формат и темно-зеленый цвет:
    percent_columns = ['K', 'S', 'T', 'V', 'X', 'Y', 'AF', 'AG', 'AI', 'AV', 'AZ']
    for col in percent_columns:
        for cell in ws[col]:
            cell.number_format = percent_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = dark_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Процентный формат и средне-зеленый цвет:
    columns = ['AX']
    for col in columns:
        for cell in ws[col]:
            cell.number_format = percent_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = mid_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Процентный формат и светло-зеленый цвет:
    percent_columns = []
    for col in percent_columns:
        for cell in ws[col]:
            cell.number_format = percent_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = light_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Числовой формат и темно-зеленый цвет:
    acc_columns = ['H', 'AE', 'AH', 'AU', 'AY']
    for col in acc_columns:
        for cell in ws[col]:
            cell.number_format = acc_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = dark_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Числовой формат и средне-зеленый цвет:
    acc_columns = ['AT']
    for col in acc_columns:
        for cell in ws[col]:
            cell.number_format = acc_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = mid_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Числовой формат и светло-зеленый цвет:
    acc_columns = ['E', 'F', 'G', 'I', 'J', 'Q', 'R', 'U', 'W',
                   'Z', 'AA', 'AB', 'AC', 'AD', 'AK', 'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AW']
    for col in acc_columns:
        for cell in ws[col]:
            cell.number_format = acc_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = light_green_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Процентный формат и темно-оранжевый цвет:
    columns = ['N', 'P']
    for col in columns:
        for cell in ws[col]:
            cell.number_format = percent_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = dark_orange_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Числовой формат и светло-оранжевый цвет:
    columns = ['L', 'M', 'O']
    for col in columns:
        for cell in ws[col]:
            cell.number_format = acc_format
            cell.font = Font(name='Calibri', size=10)
            cell.fill = light_orange_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)
            cell.alignment = right_align

    # Меняем высоту первой строки:
    ws.row_dimensions[1].height = 68

    # Один темный узкий столбец:
    ws.column_dimensions['AJ'].width = 1
    dark_grey_columns = ['AJ']
    for col in dark_grey_columns:
        for cell in ws[col]:
            cell.fill = dark_grey_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)

    # Второй темный узкий столбец:
    ws.column_dimensions['AL'].width = 1
    dark_grey_columns = ['AL']
    for col in dark_grey_columns:
        for cell in ws[col]:
            cell.fill = dark_grey_fill
            cell.border = Border(left=thin_color, right=thin_color, bottom=thin_color, top=thin_color)

    # Форматируем шапку:
    ft = Font(name='Calibri', size=10, bold=True)
    thin = Side(border_style="thin", color="000000")
    for row in ws["A1:AZ1"]:
        for cell in row:
            cell.font = ft
            cell.border = Border(bottom=thin, left=thin_color, right=thin_color, top=thin_color)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrapText=True)

    # Возвращаем значения
    return ws