from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
from app.database.classes.sales import Sales
from app.database.models import Seller, Marketing_costs_by_SKU
from sqlalchemy import select, func, Float
import warnings
from app.dates import start_of_quarter_func
from app.wrappers import log_and_notify_admin

warnings.simplefilter(action='ignore', category=FutureWarning)

@log_and_notify_admin
async def get_tax_report(session, ws, seller_id, date_from, date_to, company_info):
    # Основные данные
    ws['B2'] = f"{company_info['name']}, ИНН {company_info['inn']}"
    ws['C5'] = date_from.strftime('%Y-%m-%d')
    ws['C6'] = date_to.strftime('%Y-%m-%d')

    # Считаем даты для каждого месяца:
    first_month_date_from = start_of_quarter_func(date_to)
    second_month_date_from = first_month_date_from + relativedelta(months=1)
    third_month_date_from = second_month_date_from + relativedelta(months=1)
    first_month_date_to = second_month_date_from - timedelta(microseconds=1)
    second_month_date_to = third_month_date_from - timedelta(microseconds=1)
    third_month_date_to = third_month_date_from + relativedelta(months=1) - timedelta(microseconds=1)

    # print(first_month_date_from, first_month_date_to)
    # print(second_month_date_from, second_month_date_to)
    # print(third_month_date_from, third_month_date_to)

    # Словарь с названиями месяцев на русском
    months = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель', 5: 'Май', 6: 'Июнь',
        7: 'Июль', 8: 'Август', 9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }

    # Получаем название месяца и год
    first_month_name = months[first_month_date_to.month]
    second_month_name = months[second_month_date_to.month]
    third_month_name = months[third_month_date_to.month]
    year = date_to.year

    fist_month_str = f"{first_month_name} {year}"
    second_month_str = f"{second_month_name} {year}"
    third_month_str = f"{third_month_name} {year}"
    total_month = f'Итого за квартал'

    # print(fist_month_str)
    # print(second_month_str)
    # print(third_month_str)

    # Считаем за каждый месяц
    revenue_first_month = await Sales.get_sales_sum(session=session,
                                                    seller_id=seller_id,
                                                    date_from=first_month_date_from,
                                                    date_to=first_month_date_to)

    revenue_second_month = await Sales.get_sales_sum(session=session,
                                                     seller_id=seller_id,
                                                    date_from=second_month_date_from,
                                                    date_to=second_month_date_to)

    revenue_third_month = await Sales.get_sales_sum(session=session,
                                                    seller_id=seller_id,
                                                     date_from=third_month_date_from,
                                                     date_to=third_month_date_to)
    total_revenue =  revenue_first_month + revenue_second_month + revenue_third_month

    # Добавляем Налоги и чистую прибыль
    tax_base = await session.scalar(select(Seller.tax_base).
                                    where(Seller.id == seller_id))
    tax_rate = await session.scalar(select(Seller.tax_rate).
                                    where(Seller.id == seller_id))

    first_month_expenses = 0
    second_month_expenses = 0
    third_month_expenses = 0
    first_month_tax_base = revenue_first_month
    second_month_tax_base = revenue_second_month
    third_month_tax_base = revenue_third_month

    if tax_base == "income":
        pass

    elif tax_base == "income_less_exp":
        first_month_expenses = await get_tax_expenses(session, seller_id, first_month_date_from, first_month_date_to)
        second_month_expenses = await get_tax_expenses(session, seller_id, second_month_date_from, second_month_date_to)
        third_month_expenses = await get_tax_expenses(session, seller_id, third_month_date_from, third_month_date_to)

    first_month_tax_base = revenue_first_month - first_month_expenses
    second_month_tax_base = revenue_second_month - second_month_expenses
    third_month_tax_base = revenue_third_month - third_month_expenses

    total_expenses = first_month_expenses + second_month_expenses + third_month_expenses
    total_tax_base = first_month_tax_base + second_month_tax_base + third_month_tax_base

    first_month_tax_sum = first_month_tax_base * tax_rate
    second_month_tax_sum = second_month_tax_base * tax_rate
    third_month_tax_sum =third_month_tax_base * tax_rate
    total_tax_sum = first_month_tax_sum + second_month_tax_sum + third_month_tax_sum

    financial_data = [
        # (month, revenue, expenses, tax_base, tax_rate, tax_sum)
        ('B10', 'C10', 'D10', 'E10', 'F10', 'G10',
         fist_month_str, revenue_first_month, first_month_expenses, first_month_tax_base, tax_rate, first_month_tax_sum),
        ('B11', 'C11', 'D11', 'E11', 'F11', 'G11',
         second_month_str, revenue_second_month, second_month_expenses, second_month_tax_base, tax_rate, second_month_tax_sum),
        ('B12', 'C12', 'D12', 'E12', 'F12', 'G12',
         third_month_str, revenue_third_month, third_month_expenses, third_month_tax_base, tax_rate, third_month_tax_sum),
        ('B13', 'C13', 'D13', 'E13', 'F13', 'G13',
         total_month, total_revenue, total_expenses, total_tax_base, tax_rate, total_tax_sum)]

    for (month_cell, rev_cell, exp_cell, base_cell, rate_cell, tax_sum_cell,
         month, revenue, expenses, tax_base, tax_rate, tax_sum) in financial_data:
        ws[month_cell] = month
        ws[rev_cell] = revenue
        ws[exp_cell] = expenses
        ws[base_cell] = tax_base
        ws[rate_cell] = tax_rate
        ws[tax_sum_cell] = tax_sum


@log_and_notify_admin
async def get_tax_expenses(session, seller_id, date_from, date_to):
    total_costs = await session.scalar(
        select(
            func.coalesce(
                func.sum(
                    Sales.full_comission +
                    Sales.storage_fee +
                    Sales.delivery_rub +
                    Sales.penalty +
                    Sales.acceptance +
                    Sales.other_deductions
                ),
                0.0
            )
        ).where(
            Sales.seller_id == seller_id,
            Sales.transaction_date.between(date_from, date_to)
        )
    )

    marketing_costs = await session.scalar(
        select(
            func.coalesce(
                func.cast(func.sum(Marketing_costs_by_SKU.cost_sum), Float),
                0.0
            )
        ).where(
            Marketing_costs_by_SKU.seller_id == seller_id,
            Marketing_costs_by_SKU.cost_date.between(date_from, date_to)
        )
    )

    total_taxable_costs = total_costs + marketing_costs
    return total_taxable_costs
