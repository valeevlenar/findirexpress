import io

import config
from aiogram.types import BufferedInputFile
from datetime import timedelta, datetime

from app.admin.admin_message import send_message_to_admin
from app.checks import check_user_access_to_seller_id_by_user_tg_id
from app.database.classes.stocks import Stock
from openpyxl import load_workbook
from app.database.support_functions import get_chat_id_by_seller_id, \
    get_user_by_tg_id
from app.managers.managers_functions import get_managers_chat_ids_by_seller_id
from app.reports.dashboard import create_dashboard
from app.reports.report_calc_functions import fetch_financial_data
from app.reports.tax_report import get_tax_report
from app.reports.weekly_finreport import send_to_admin, get_company_info
from app.user_communication.email_func import send_report_via_email, add_report_delivery_to_db
from app.reports.stocks_reports.stocks_report_detailed_by_SKU import get_detailed_stock_table
from app.reports.stocks_reports.stocks_report_detailed_by_article import \
    get_detailed_stock_table_by_article
from app.reports.stocks_reports.stocks_report_detailed_by_subject import \
    get_detailed_stock_table_by_subject
from app.main_bot.main_bot import bot
from app.wrappers import log_and_notify_admin

# Функция формирует отчетный файл и отправляет пользователю
@log_and_notify_admin
async def get_monthly_pl(session, seller_id, report_creation_type, date_from, date_to, requestor_chat_id):
    # Инициализация данных
    company_info = await get_company_info(session=session, seller_id=seller_id)
    date_ranges = await calculate_monthly_date_ranges(date_from, date_to)

    # Получение финансовых данных
    current_metrics = await fetch_financial_data(session, seller_id, 'monthly', date_from, date_to)
    previous_week_metrics = await fetch_financial_data(session, seller_id, 'monthly', date_ranges['prior_date_from'],
                                                       date_ranges['prior_date_to'])
    # Формирование отчета
    report = await generate_monthly_excel_report(session,
                                                seller_id,
                                                company_info,
                                                current_metrics,
                                                previous_week_metrics,
                                                date_from,
                                                date_to,
                                                date_ranges)

    # Отправка отчета
    await send_monthly_report(session,
                              report,
                              seller_id,
                              company_info['name'],
                              report_creation_type,
                              requestor_chat_id,
                              date_from,
                              date_to)
    return True

    # Вспомогательные функции расчета

    # Генерация Excel-отчета

@log_and_notify_admin
async def generate_monthly_excel_report(session, seller_id, company_info, metrics, prev_metrics, date_from, date_to,
                                       date_ranges):
    wb = load_workbook(config.templates_path + 'Шаблон seller PL (monthly).xlsx')
    ws = wb["Месячный отчет"]

    # Основные данные
    ws['B2'] = f"{company_info['name']}, ИНН {company_info['inn']}"
    ws['C5'] = date_from.strftime('%Y-%m-%d')
    ws['C6'] = date_to.strftime('%Y-%m-%d')

    # остатки запасов на конец прошлой недели
    prev_stock_data = await Stock.get_stock_data_at_date_end(session=session, seller_id=seller_id, date_to=(date_to - timedelta(days=7)))

    # Финансовые показатели
    financial_data = [
        # (curr_cell, prev_cell, change_cell, percent_cell, curr_val, prev_val)
        # PL
        ('C10', 'D10', 'E10', 'F10', metrics.revenue, prev_metrics.revenue),
        ('C11', 'D11', 'E11', 'F11', -metrics.commission, -prev_metrics.commission),
        ('C12', 'D12', 'E12', 'F12', metrics.cost_of_sales, prev_metrics.cost_of_sales),
        ('C13', 'D13', 'E13', 'F13', -metrics.logistics, -prev_metrics.logistics),
        ('C14', 'D14', 'E14', 'F14', -metrics.storage, -prev_metrics.storage),
        ('C15', 'D15', 'E15', 'F15', -metrics.acceptance, -prev_metrics.acceptance),
        ('C16', 'D16', 'E16', 'F16', -metrics.marketing, -prev_metrics.marketing),
        ('C17', 'D17', 'E17', 'F17', -metrics.other_deductions, -prev_metrics.other_deductions),
        ('C18', 'D18', 'E18', 'F18', metrics.profit_before_tax, prev_metrics.profit_before_tax),
        ('C19', 'D19', 'E19', 'F19', metrics.tax_costs, prev_metrics.tax_costs),
        ('C20', 'D20', 'E20', 'F20', metrics.net_profit, prev_metrics.net_profit),

        # кэш-флоу
        ('C24', 'D24', 'E24', 'F24', metrics.net_profit, prev_metrics.net_profit),
        ('C25', 'D25', 'E25', 'F25', -metrics.cost_of_sales, -prev_metrics.cost_of_sales),
        ('C26', 'D26', 'E26', 'F26', metrics.change_in_accounts_receivable_from_wb,
         prev_metrics.change_in_accounts_receivable_from_wb),
        ('C27', 'D27', 'E27', 'F27', metrics.change_in_marketing_balance, prev_metrics.change_in_marketing_balance),
        ('C28', 'D28', 'E28', 'F28', -metrics.tax_costs, -prev_metrics.tax_costs),
        ('C29', 'D29', 'E29', 'F29', metrics.cash_inflow,prev_metrics.cash_inflow),
        ('C30', 'D30', 'E30', 'F30', -metrics.stock_purchase, -prev_metrics.stock_purchase),
        ('C31', 'D31', 'E31', 'F31', metrics.net_cash_flow, prev_metrics.net_cash_flow),

        # баланс
        ('C35', 'D35', 'E35', 'F35', metrics.stocks_total_at_cost, prev_stock_data['stocks_total_at_cost']),
        ('C36', 'D36', 'E36', 'F36', metrics.stocks_quantity, prev_stock_data['stocks_quantity']),
        ('C37', 'D37', 'E37', 'F37', metrics.stocks_total_at_sell_price, prev_stock_data['stocks_total_at_sell_price']),
        ('C38', 'D38', 'E38', 'F38', metrics.accounts_receivable_from_wb, prev_metrics.accounts_receivable_from_wb),
        ('C39', 'D39', 'E39', 'F39', metrics.tax_payable, prev_metrics.tax_payable),
        ('C40', 'D40', 'E40', 'F40', metrics.accumulated_profit, prev_metrics.accumulated_profit)
    ]

    for curr_cell, prev_cell, change_cell, percent_cell, curr_val, prev_val in financial_data:
        ws[curr_cell] = curr_val
        ws[prev_cell] = prev_val

        # Расчет абсолютного изменения
        change = curr_val - prev_val
        ws[change_cell] = change

        # Расчет процентного изменения
        if prev_val != 0:
            change_percent = (curr_val / prev_val - 1)
        else:
            change_percent = 0.0 if curr_val == 0 else 1.0  # Обработка нулевого предыдущего значения

        ws[percent_cell] = change_percent  # Округление до 1 знака после запятой

    # Заполняем дэшборд
    ws = wb["Дэшборд"]
    ws = await create_dashboard(session=session,
                                ws=ws,
                                seller_id=seller_id,
                                metrics=metrics,
                                prev_metrics=prev_metrics,
                                date_from=date_from,
                                date_to=date_to,
                                prev_date_from=date_ranges['prior_date_from'],
                                prev_date_to=date_ranges['prior_date_to'])

    ws = wb["Детализация по SKU"]
    ws = await get_detailed_stock_table(session=session,
                                        ws=ws,
                                        seller_id=seller_id,
                                        date_from=date_from,
                                        date_to=date_to)

    # # выполняем функцию по формированию детальной таблицы по артикулам:
    ws = wb["Детализация по артикулам"]
    ws = await get_detailed_stock_table_by_article(session=session,
                                                   ws=ws,
                                                   seller_id=seller_id,
                                                   date_from=date_from,
                                                   date_to=date_to)

    # выполняем функцию по формированию детальной таблицы по предметам:

    ws = wb["Детализация по предметам"]
    ws = await get_detailed_stock_table_by_subject(session=session,
                                                   ws=ws,
                                                   seller_id=seller_id,
                                                   date_from=date_from,
                                                   date_to=date_to)

    # считаем налоги:

    ws = wb["Налоги"]
    ws = await get_tax_report(session=session,
                              ws=ws,
                              seller_id=seller_id,
                              date_from=date_from,
                              date_to=date_to,
                              company_info=company_info)

    # Сохранение в буфер
    ws = wb["Дэшборд"]
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# Отправка отчета
@log_and_notify_admin
async def send_monthly_report(session, report_data, seller_id, company_name, report_type, requestor_id, date_from, date_to):
    # Список месяцев на русском в именительном падеже с заглавной буквы
    months_ru = [
        '', 'Январь', 'Февраль', 'Март',
        'Апрель', 'Май', 'Июнь', 'Июль',
        'Август', 'Сентябрь', 'Октябрь',
        'Ноябрь', 'Декабрь'
    ]

    # Форматируем дату окончания отчетного периода
    date_to_str = f"{months_ru[date_to.month]} {date_to.year}"

    filename = f"{company_name}_ежемесячный отчет_{date_to_str}.xlsx"

    if report_type == 'auto':
        await send_monthly_to_automated_recipients(session, seller_id, report_data, filename, date_from, date_to)
    elif report_type == 'on_demand':
        await send_monthly_to_user(session, requestor_id, seller_id, report_data, filename, date_from, date_to)
    elif report_type == 'admin':
        await send_to_admin(report_data, filename)

@log_and_notify_admin
async def calculate_monthly_date_ranges(date_from: datetime, date_to: datetime):
    date_from = date_from
    date_to = date_to
    prior_date_to = date_from - timedelta(microseconds=1)
    prior_date_from = prior_date_to.replace(day=1).replace(hour=00,minute=00,second=00,microsecond=00)
    date_ranges = {'date_from': date_from,
                   'date_to': date_to,
                   'prior_date_from': prior_date_from,
                   'prior_date_to': prior_date_to}
    return date_ranges

@log_and_notify_admin
async def send_monthly_to_automated_recipients(session, seller_id, report_data, filename, date_from, date_to):
    owner_chat_id = await get_chat_id_by_seller_id(session, seller_id)
    await bot.send_document(chat_id=owner_chat_id,
                            document=BufferedInputFile(file=report_data,
                                                       filename=filename),
                            disable_notification=False)
    # Записываем отправку отчета в базу:
    owner_user_id = await get_user_by_tg_id(session=session, tg_id=owner_chat_id)
    await add_report_delivery_to_db(session=session,
                                    seller_id=seller_id,
                                    report_type="monthly",
                                    report_creation_type='auto',
                                    date_to=date_to,
                                    user_id=owner_user_id)
    manager_chat_ids = await get_managers_chat_ids_by_seller_id(session, seller_id)
    if manager_chat_ids:
        for chat_id in manager_chat_ids:
            await bot.send_document(chat_id=chat_id,
                                    document=BufferedInputFile(file=report_data,
                                                               filename=filename),
                                    disable_notification=False)
            # Записываем отправку отчета в базу:
            manager_user_id = await get_user_by_tg_id(session=session, tg_id=int(chat_id))
            await add_report_delivery_to_db(session=session,
                                            seller_id=seller_id,
                                            report_type="monthly",
                                            report_creation_type='auto',
                                            date_to=date_to,
                                            user_id=manager_user_id)
    else:
        pass

    # Отправляем отчет на электронную почту:
    # try:
    #     await send_report_via_email(session=session,
    #                                 seller_id=seller_id,
    #                                 report_type="monthly",
    #                                 report_creation_type='auto',
    #                                 file_to_send=report_data,
    #                                 filename=filename,
    #                                 date_from=date_from,
    #                                 date_to=date_to)
    #
    # except Exception as e:
    #     await send_message_to_admin(f'Ошибка при отправке отчета на электронную почту:'
    #                                 f'\nSeller_id: {seller_id}'
    #                                 f'\nUser_id: {owner_user_id}')


@log_and_notify_admin
async def send_monthly_to_user(session, requestor_id, seller_id, report_data, filename, date_from, date_to):
    if await check_user_access_to_seller_id_by_user_tg_id(session=session,
                                                          seller_id=seller_id,
                                                          user_tg_id=requestor_id):
        await bot.send_document(chat_id=requestor_id,
                                document=BufferedInputFile(file=report_data,
                                                           filename=filename),
                                disable_notification=False)
        # Записываем отправку отчета в базу:
        user_id = await get_user_by_tg_id(session=session, tg_id=requestor_id)
        await add_report_delivery_to_db(session=session,
                                        seller_id=seller_id,
                                        report_type="monthly",
                                        report_creation_type='manual',
                                        date_to=date_to,
                                        user_id=user_id)
        # Отправляем отчет на электронную почту:
        # try:
        #     await send_report_via_email(session=session,
        #                                 seller_id=seller_id,
        #                                 report_type="monthly",
        #                                 report_creation_type='manual',
        #                                 file_to_send=report_data,
        #                                 filename=filename,
        #                                 date_from=date_from,
        #                                 date_to=date_to)
        # except Exception as e:
        #     await send_message_to_admin(f'Ошибка при отправке отчета на электронную почту:'
        #                                 f'\nSeller_id: {seller_id}'
        #                                 f'\nUser_id: {user_id}')
    else:
        pass