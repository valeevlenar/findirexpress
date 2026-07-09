from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, func, cast, Float

from app.database.classes.stocks import Stock
from app.database.classes.sales import Sales
from app.database.models import Marketing_costs_by_SKU, Marketing_costs_wb, Orders_nm
from app.dates import start_of_quarter_func, get_end_of_prior_week_for_ar
from app.wrappers import log_and_notify_admin


# Модели данных
class FinancialMetrics(BaseModel):
    revenue: float = 0.0
    commission: float = 0.0
    cost_of_sales: float = 0.0
    marketing: float = 0.0
    storage: float = 0.0
    logistics: float = 0.0
    other_deductions: float = 0.0
    penalty: float = 0.0
    deduction: float = 0.0
    acceptance: float = 0.0
    profit_before_tax: float = 0.0
    tax_costs: float = 0.0
    net_profit: float = 0.0
    revenue_before_spp: float = 0.0
    commission_before_spp: float = 0.0
    commission_before_spp_rate: float = 0.0
    spp_amount: float = 0.0
    spp_rate: float = 0.0
    stocks_quantity: float = 0.0
    stocks_total_at_cost: float = 0.0
    stocks_total_at_sell_price: float = 0.0
    accounts_receivable_from_wb: float = 0.0
    pw_accounts_receivable_from_wb: float = 0.0
    change_in_accounts_receivable_from_wb: float = 0.0
    change_in_marketing_balance: float = 0.0
    stock_purchase: float = 0.0
    cash_inflow: float = 0.0
    net_cash_flow: float = 0.0
    tax_payable: float = 0.0
    accumulated_profit: float = 0.0
    sales_count: int = 0
    orders_count: int = 0
    orders_sum: float = 0.0
    buyout_percent: float = 0.0
    margin_rate: float = 0.0
    margin_rate_before_spp: float = 0.0
    roi: float = 0.0
    drr: float = 0.0
    drr_before_spp: float = 0.0
    commission_rate: float = 0.0
    aop: float = 0.0
    markup: float = 0.0
    turnover_days: float = 0.0

# Модели данных
class FinancialMetricsCondensed(BaseModel):
    revenue: float = 0.0
    commission: float = 0.0
    cost_of_sales: float = 0.0
    marketing: float = 0.0
    storage: float = 0.0
    logistics: float = 0.0
    other_deductions: float = 0.0
    penalty: float = 0.0
    deduction: float = 0.0
    acceptance: float = 0.0
    profit_before_tax: float = 0.0
    tax_costs: float = 0.0
    net_profit: float = 0.0


class ServiceCosts(BaseModel):
    marketing: float = 0.0
    storage: float = 0.0
    photostudio: float = 0.0
    goods_prep_center: float = 0.0
    personal_manager: float = 0.0
    other_services: float = 0.0

# Вспомогательные функции
async def safe_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0

@log_and_notify_admin
async def fetch_financial_data(session, seller_id: int, report_type, date_from: datetime, date_to: datetime) -> FinancialMetrics:
    result = await session.execute(
        select(func.sum(Sales.revenue).label('revenue'),
               func.sum(Sales.full_comission).label('commission'),
               func.sum(Sales.cost_of_sales).label('cost_of_sales'),
               func.sum(Sales.storage_fee).label('storage'),
               func.sum(Sales.delivery_rub).label('logistics'),
               func.sum(Sales.penalty).label('penalty'),
               func.sum(Sales.acceptance).label('acceptance'),
               func.sum(Sales.other_deductions).label('deduction'),
               func.sum(Sales.for_withdraw).label('for_withdraw'),
               func.sum(Sales.tax_costs).label('tax_costs'),
               func.sum(Sales.net_profit).label('net_profit'),
               func.sum(Sales.revenue_before_spp).label('revenue_before_spp'),
               func.sum(Sales.commission_before_spp).label('commission_before_spp'),
               func.sum(Sales.spp_amount).label('spp_amount')
               ).where(
            Sales.seller_id == seller_id,
            Sales.transaction_date.between(date_from, date_to)
        )
    )
    sales = result.mappings().first() or {}

    revenue = await safe_float(sales.get('revenue'))
    commission = await safe_float(sales.get('commission'))
    commission_rate = await safe_division(commission, revenue)
    cost_of_sales = await safe_float(sales.get('cost_of_sales'))

    # СПП
    revenue_before_spp = await safe_float(sales.get('revenue_before_spp'))
    commission_before_spp = await safe_float(sales.get('commission_before_spp'))
    commission_before_spp_rate = await safe_division(commission_before_spp, revenue_before_spp)
    spp_amount = await safe_float(sales.get('spp_amount'))
    spp_rate = await safe_division(spp_amount, revenue_before_spp)


    # Расходы
    storage = await safe_float(sales.get('storage'))
    logistics = await safe_float(sales.get('logistics'))
    penalty = await safe_float(sales.get('penalty'))
    acceptance = await safe_float(sales.get('acceptance'))
    deduction = await safe_float(sales.get('deduction'))
    for_withdraw = await safe_float(sales.get('for_withdraw'))
    profit_before_tax = revenue + cost_of_sales - commission - storage - logistics - penalty - acceptance - deduction
    tax_costs = await safe_float(sales.get('tax_costs'))
    net_profit = await safe_float(sales.get('net_profit'))

    # Выгружаем прочие показатели
    sales_count = (select(func.coalesce(func.sum(Sales.goods_quantity), 0))
        .where(Sales.seller_id == seller_id, Sales.transaction_date.between(date_from, date_to))
        .scalar_subquery())

    orders_sum = (select(func.coalesce(func.sum(Orders_nm.total_sum), 0))
        .where(Orders_nm.seller_id == seller_id, Orders_nm.order_date >= date_from, Orders_nm.order_date <= date_to)
        .scalar_subquery())

    orders_count = (select(func.coalesce(func.sum(Orders_nm.quantity), 0))
                    .where(Orders_nm.seller_id == seller_id, Orders_nm.order_date.between(date_from, date_to))
                    .scalar_subquery())

    result = await session.execute(select(
        cast(sales_count, Float).label('sales_count'),
        cast(orders_sum, Float).label('orders_sum'),
        cast(orders_count, Float).label('orders_count')
    ))

    other_financials = result.mappings().first()

    sales_count = other_financials['sales_count']
    orders_sum = other_financials['orders_sum']
    orders_count = other_financials['orders_count']
    # print(date_from, date_to)
    # print(orders_sum)
    # print(orders_count)

    # Собираем расходы на маркетинг
    marketing_costs = await get_marketing_costs_from_db(session, seller_id, date_from, date_to)
    # print(marketing_costs)

    marketing = float(marketing_costs['marketing'])
    marketing_tax_costs = float(marketing_costs['tax_costs'])
    marketing_net_profit = float(marketing_costs['net_profit'])
    marketing_promotion = float(marketing_costs['marketing_promotion'])
    marketing_accumulated_net_profit = float(marketing_costs['marketing_accumulated_net_profit'])
    marketing_tax_balance = float(marketing_costs['marketing_tax_balance'])
    drr = await safe_division(marketing,revenue)
    drr_before_spp = await safe_division(marketing, revenue_before_spp)

    # Закупка товаров
    stock_purchase = 0
    stock_change = await Stock.get_stock_change(session=session,
                                                seller_id=seller_id,
                                                  date_from=date_from,
                                                  date_to=date_to)
    # print('stock_change', stock_change)
    if stock_change != 0:
        stock_purchase =  stock_change - cost_of_sales
    else:
        stock_purchase = 0
    # print('cost_of_sales', cost_of_sales)
    # print('stock_purchase', stock_purchase)

    # Считаем прибыль до налогообложения
    full_profit_before_tax = profit_before_tax - marketing

    # Считаем налоги
    full_tax_costs = tax_costs + marketing_tax_costs

    # Считаем чистую прибыль
    full_net_profit = net_profit + marketing_net_profit

    # Считаем данные для сверки кэш флоу
    marketing_balance_additions = await session.scalar(select(func.sum(Sales.deduction)).
                                                       where(Sales.seller_id == seller_id,
                                                             Sales.transaction_date.between(date_from, date_to),
                                                             Sales.bonus_type_name.contains(
                                                                 'Оказание услуг «WB Продвижение»'))) or 0.0


    # print(date_from, date_to)
    # print('marketing_promotion', marketing_promotion)
    # print('marketing_balance_additions', marketing_balance_additions)

    change_in_marketing_balance = marketing_promotion - marketing_balance_additions

    # Считаем данные для баланса
    # Товары
    stock_data = await Stock.get_stock_data_at_date_end_or_current(session=session,
                                                                   seller_id = seller_id,
                                                                   date_to = date_to)

    #Дебиторка
    if report_type == 'weekly':
        accounts_receivable_from_wb = await Sales.get_reporting_week_accounts_receivable(session=session, seller_id=seller_id,date_to=date_to)
        prior_accounts_receivable_from_wb = await Sales.get_reporting_week_accounts_receivable(session=session, seller_id=seller_id,date_to=(date_to-timedelta(days=7)))
        cash_inflow = await Sales.get_reporting_week_cash_inflow(session=session, seller_id=seller_id, date_to=date_to)
    else:
        accounts_receivable_from_wb = await get_monthly_accounts_receivable(session=session, seller_id=seller_id, date_from=date_from, date_to=date_to)
        # print('accounts_receivable_from_wb', accounts_receivable_from_wb)
        # Берем конец предыдущего месяца и на него считаем дебиторку
        end_of_prior_month = (date_to.replace(day=1)) - timedelta(days=1)
        prior_accounts_receivable_from_wb = await get_monthly_accounts_receivable(session=session, seller_id=seller_id, date_from=date_from, date_to=end_of_prior_month)
        # print('prior_accounts_receivable_from_wb', prior_accounts_receivable_from_wb)
        # print('for_withdraw', for_withdraw)
        cash_inflow = prior_accounts_receivable_from_wb + for_withdraw - accounts_receivable_from_wb


    change_in_accounts_receivable_from_wb = prior_accounts_receivable_from_wb - accounts_receivable_from_wb

    # Итоги кэш флоу
    net_cash_flow = cash_inflow - stock_purchase

    # Налоги
    tax_payable = await Sales.get_tax_payable(session=session,
                                              seller_id=seller_id,
                                              date_from=date_from,
                                              date_to=date_to) + marketing_tax_balance

    # НРП
    accumulated_profit = await Sales.get_accumulated_profit(session=session,
                                                            seller_id=seller_id,
                                                            date_to=date_to) + marketing_accumulated_net_profit

    # Считаем доп. показатели
    buyout_percent = await safe_division(sales_count, orders_count)
    margin_rate = await safe_division(full_net_profit, revenue)
    margin_rate_before_spp = await safe_division(full_net_profit, revenue_before_spp)

    aop = await safe_division(revenue_before_spp,sales_count)
    markup = await safe_division((revenue_before_spp+cost_of_sales),-cost_of_sales)

    # Считаем ROI
    average_stocks = await Stock.get_average_stocks_at_cost_or_current(session=session, seller_id=seller_id, date_from=date_from, date_to=date_to)
    reporting_period_length = (date_to - date_from).days + 1
    roi = await safe_division((full_net_profit * (365 / reporting_period_length)), average_stocks)

    # Считаем оборачиваемость
    average_stocks_count = await Stock.get_average_stocks_count_or_current(session=session, seller_id=seller_id, date_from=date_from,date_to=date_to)
    turnover_days = await safe_division(average_stocks_count * reporting_period_length, sales_count)

    return FinancialMetrics(
        revenue = revenue,
        commission = commission,
        cost_of_sales = cost_of_sales,
        marketing = marketing,
        storage = storage,
        logistics = logistics,
        other_deductions = penalty + deduction,
        acceptance = acceptance,
        profit_before_tax = full_profit_before_tax,
        tax_costs=full_tax_costs,
        net_profit=full_net_profit,
        revenue_before_spp = revenue_before_spp,
        commission_before_spp = commission_before_spp,
        commission_before_spp_rate = commission_before_spp_rate,
        spp_amount = spp_amount,
        spp_rate = spp_rate,
        stocks_quantity = await safe_float(stock_data['stocks_quantity']),
        stocks_total_at_cost = await safe_float(stock_data['stocks_total_at_cost']),
        stocks_total_at_sell_price = await safe_float(stock_data['stocks_total_at_sell_price']),
        accounts_receivable_from_wb = accounts_receivable_from_wb,
        pw_accounts_receivable_from_wb = prior_accounts_receivable_from_wb,
        change_in_accounts_receivable_from_wb = change_in_accounts_receivable_from_wb,
        change_in_marketing_balance = change_in_marketing_balance,
        stock_purchase = stock_purchase,
        cash_inflow = cash_inflow,
        net_cash_flow = net_cash_flow,
        tax_payable = tax_payable,
        accumulated_profit = accumulated_profit,
        sales_count = sales_count,
        orders_count = orders_count,
        orders_sum = orders_sum,
        buyout_percent = buyout_percent,
        margin_rate = margin_rate,
        margin_rate_before_spp = margin_rate_before_spp,
        roi = roi,
        drr = drr,
        drr_before_spp = drr_before_spp,
        commission_rate = commission_rate,
        aop = aop,
        markup = markup,
        turnover_days = turnover_days
    )

@log_and_notify_admin
async def fetch_financial_data_condensed(session, seller_id: int, date_from: datetime, date_to: datetime) -> FinancialMetricsCondensed:
    result = await session.execute(
        select(func.sum(Sales.revenue).label('revenue'),
               func.sum(Sales.full_comission).label('commission'),
               func.sum(Sales.cost_of_sales).label('cost_of_sales'),
               func.sum(Sales.storage_fee).label('storage'),
               func.sum(Sales.delivery_rub).label('logistics'),
               func.sum(Sales.penalty).label('penalty'),
               func.sum(Sales.acceptance).label('acceptance'),
               func.sum(Sales.other_deductions).label('deduction'),
               func.sum(Sales.for_withdraw).label('for_withdraw'),
               func.sum(Sales.tax_costs).label('tax_costs'),
               func.sum(Sales.net_profit).label('net_profit')
               ).where(
            Sales.seller_id == seller_id,
            Sales.transaction_date.between(date_from, date_to)
        )
    )
    sales = result.mappings().first() or {}

    revenue = await safe_float(sales.get('revenue'))
    commission = await safe_float(sales.get('commission'))
    cost_of_sales = await safe_float(sales.get('cost_of_sales'))

    # Расходы
    storage = await safe_float(sales.get('storage'))
    logistics = await safe_float(sales.get('logistics'))
    penalty = await safe_float(sales.get('penalty'))
    acceptance = await safe_float(sales.get('acceptance'))
    deduction = await safe_float(sales.get('deduction'))
    for_withdraw = await safe_float(sales.get('for_withdraw'))
    profit_before_tax = revenue + cost_of_sales - commission - storage - logistics - penalty - acceptance - deduction
    tax_costs = await safe_float(sales.get('tax_costs'))
    net_profit = await safe_float(sales.get('net_profit'))

    # Собираем расходы на маркетинг
    marketing_costs = await get_marketing_costs_from_db(session, seller_id, date_from, date_to)

    marketing = float(marketing_costs['marketing'])
    marketing_tax_costs = float(marketing_costs['tax_costs'])
    marketing_net_profit = float(marketing_costs['net_profit'])


    # Считаем прибыль до налогообложения
    full_profit_before_tax = profit_before_tax - marketing

    # Считаем налоги
    full_tax_costs = tax_costs + marketing_tax_costs

    # Считаем чистую прибыль
    full_net_profit = net_profit + marketing_net_profit

    return FinancialMetricsCondensed(
        revenue=revenue,
        commission=commission,
        cost_of_sales=cost_of_sales,
        marketing=marketing,
        storage=storage,
        logistics=logistics,
        other_deductions=penalty + deduction,
        acceptance=acceptance,
        profit_before_tax=full_profit_before_tax,
        tax_costs=full_tax_costs,
        net_profit=full_net_profit
    )

async def safe_division(value: any, denominator: any):
    try:
        if denominator != 0:
            division_result = (value / denominator )
        else:
            division_result = 0.0 if value == 0 else 1.0  # Обработка нулевого значения знаменателя

    except:
        division_result = 0.0
    return division_result

@log_and_notify_admin
async def get_marketing_costs_from_db(session, seller_id, date_from, date_to):
    try:
        # Основные данные маркетинговых расходов

        stmt = select(
            func.coalesce(
                func.cast(func.sum(Marketing_costs_by_SKU.cost_sum), Float),
                0.0
            ).label('marketing'),
            func.coalesce(
                func.cast(func.sum(Marketing_costs_by_SKU.tax_costs), Float),
                0.0
            ).label('tax_costs'),
            func.coalesce(
                func.cast(func.sum(Marketing_costs_by_SKU.net_profit), Float),
                0.0
            ).label('net_profit')
        ).where(
            Marketing_costs_by_SKU.seller_id == seller_id,
            Marketing_costs_by_SKU.cost_date.between(date_from, date_to)
        )

        result = await session.execute(stmt)
        row = result.mappings().first()

        marketing_costs = dict(row) if row else {
            'marketing': 0.0,
            'tax_costs': 0.0,
            'net_profit': 0.0
        }

        # Дополнительные поля
        marketing_costs['marketing_promotion'] = await session.scalar(
            select(func.coalesce(func.sum(Marketing_costs_wb.updsum), 0.0)).where(
                Marketing_costs_wb.seller_id == seller_id,
                Marketing_costs_wb.cost_date.between(date_from, date_to),
                Marketing_costs_wb.paymenttype != 'Бонус',
                Marketing_costs_wb.paymenttype != 'Кэшбэк'
            )
        ) or 0.0

        marketing_costs['marketing_accumulated_net_profit'] = await session.scalar(
            select(func.coalesce(func.sum(Marketing_costs_by_SKU.net_profit), 0.0)).where(
                Marketing_costs_by_SKU.seller_id == seller_id,
                Marketing_costs_by_SKU.cost_date <= date_to
            )
        ) or 0.0

        start_of_quarter = start_of_quarter_func(date_to)

        marketing_costs['marketing_tax_balance'] = await session.scalar(
            select(func.coalesce(func.sum(Marketing_costs_by_SKU.tax_costs), 0.0)).where(
                Marketing_costs_by_SKU.seller_id == seller_id,
                Marketing_costs_by_SKU.cost_date.between(start_of_quarter, date_to)
            )
        ) or 0.0

        return marketing_costs
    except Exception as e:
        # Обработка ошибки и логирование
        return {  # Всегда возвращаем словарь
            'marketing': 0.0,
            'tax_costs': 0.0,
            'net_profit': 0.0,
            'marketing_promotion': 0.0,
            'marketing_accumulated_net_profit': 0.0,
            'marketing_tax_balance': 0.0
        }

@log_and_notify_admin
async def get_monthly_accounts_receivable(session, seller_id, date_from, date_to):
    async def fetch_receivables(date_start, date_end):
        query = select(
            func.coalesce(func.cast(func.sum(Sales.for_withdraw), Float), 0.0)
        ).where(
            Sales.seller_id == seller_id,
            Sales.transaction_date >= date_start,
            Sales.transaction_date <= date_end
        )
        return (await session.execute(query)).scalar()

    # Текущий период
    start_of_prior_week_for_ar, end_of_prior_week_for_ar = await get_end_of_prior_week_for_ar(date_to)
    receivables_from_wb = await fetch_receivables(start_of_prior_week_for_ar, date_to)

    return receivables_from_wb