from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.admin.admin_reports import admin_system_status_daily, daily_promocodes_check_admin_report
from app.app_logic import main_regular_reporting_function
from app.get_data.get_stocks import daily_get_stocks_data
from apscheduler.triggers.cron import CronTrigger
from app.database.api_functions import daily_check_api


from app.get_data.storage import daily_get_storage_data
from app.payments.invoices import check_invoices_status
from app.prices.price_api_functions import daily_check_price_api
from app.prices.price_control_functions import main_prices_check_function
from app.subscriptions.subscriptions_functions import check_subscriptions_dates, check_subscriptions_status
from app.transactions.closing_documents import monthly_prepare_and_send_closing_documents
from app.transactions.transactions import subscriptions_revenue_recognition

scheduler = AsyncIOScheduler()

# Основная отчетная функция - каждые 4 часа
# main_reporting_function_trigger = CronTrigger(hour='08', minute='15') #сделать каждые 4 часа!
main_reporting_function_trigger_2 = CronTrigger(hour='12', minute='00') #сделать каждые 4 часа!
# main_reporting_function_trigger_3 = CronTrigger(hour='16', minute='00') #сделать каждые 4 часа!
# main_reporting_function_trigger_4 = CronTrigger(hour='20', minute='00') #сделать каждые 4 часа!
# main_reporting_function_trigger_5 = CronTrigger(hour='22', minute='00') #сделать каждые 4 часа!

# Выгрузки и проверки 1 раз в день
daily_stock_trigger = CronTrigger(hour='00', minute='02') #1 раз в день
daily_api_check_trigger = CronTrigger(hour='08', minute='00') #1 раз в день
daily_price_api_check_trigger = CronTrigger(hour='08', minute='00') #1 раз в день
daily_subscriptions_status_check_trigger = CronTrigger(hour='11', minute='00') #1 раз в день
daily_promocodes_check_trigger = CronTrigger(hour='00', minute='15') #1 раз в день
daily_revenue_recognition_trigger = CronTrigger(hour='00', minute='17') #1 раз в день
daily_admin_report_trigger = CronTrigger(hour='00', minute='20') #1 раз в день
# daily_orders_download_trigger = CronTrigger(hour='10', minute='00') #1 раз в день
# daily_storage_download_trigger = CronTrigger(hour='10', minute='30') #1 раз в день
# daily_paid_acceptance_download_trigger = CronTrigger(hour='11', minute='00') #1 раз в день
# daily_get_marketing_costs_trigger = CronTrigger(hour='11', minute='30') #1 раз в день

#Проверка подписок и счетов
hourly_subscriptions_date_check_trigger = CronTrigger(hour='07', minute='00') #сделать каждые 6 часов!
hourly_subscriptions_date_check_trigger_2 = CronTrigger(hour='13', minute='00') #сделать каждые 6 часов!
hourly_subscriptions_date_check_trigger_3 = CronTrigger(hour='18', minute='00') #сделать каждые 6 часов!
hourly_subscriptions_date_check_trigger_4 = CronTrigger(hour='23', minute='00') #сделать каждые 6 часов!

hourly_invoices_status_check_trigger = CronTrigger(hour='08', minute='00') #сделать каждые 6 часов!
hourly_invoices_status_check_trigger_2 = CronTrigger(hour='11', minute='30') #сделать каждые 6 часов!
hourly_invoices_status_check_trigger_3 = CronTrigger(hour='17', minute='00') #сделать каждые 6 часов!
hourly_invoices_status_check_trigger_4 = CronTrigger(hour='22', minute='00') #сделать каждые 6 часов!

# 1 раз в месяц
monthly_closing_documents_trigger = CronTrigger(day='1' ,hour='10', minute='00') #1 раз в месяц, первого числа

# Проверка цен - каждый час
main_prices_check_function_trigger_1 = CronTrigger(hour='00', minute='05') #сделать каждый час!
main_prices_check_function_trigger_2 = CronTrigger(hour='01', minute='05') #сделать каждый час!
main_prices_check_function_trigger_3 = CronTrigger(hour='02', minute='05') #сделать каждый час!
main_prices_check_function_trigger_4 = CronTrigger(hour='03', minute='05') #сделать каждый час!
main_prices_check_function_trigger_5 = CronTrigger(hour='04', minute='05') #сделать каждый час!
main_prices_check_function_trigger_6 = CronTrigger(hour='05', minute='05') #сделать каждый час!
main_prices_check_function_trigger_7 = CronTrigger(hour='06', minute='05') #сделать каждый час!
main_prices_check_function_trigger_8 = CronTrigger(hour='07', minute='05') #сделать каждый час!
main_prices_check_function_trigger_9 = CronTrigger(hour='08', minute='05') #сделать каждый час!
main_prices_check_function_trigger_10 = CronTrigger(hour='09', minute='05') #сделать каждый час!
main_prices_check_function_trigger_11 = CronTrigger(hour='10', minute='05') #сделать каждый час!
main_prices_check_function_trigger_12 = CronTrigger(hour='11', minute='05') #сделать каждый час!
main_prices_check_function_trigger_13 = CronTrigger(hour='12', minute='05') #сделать каждый час!
main_prices_check_function_trigger_14 = CronTrigger(hour='13', minute='05') #сделать каждый час!
main_prices_check_function_trigger_15 = CronTrigger(hour='14', minute='05') #сделать каждый час!
main_prices_check_function_trigger_16 = CronTrigger(hour='15', minute='05') #сделать каждый час!
main_prices_check_function_trigger_17 = CronTrigger(hour='16', minute='05') #сделать каждый час!
main_prices_check_function_trigger_18 = CronTrigger(hour='17', minute='05') #сделать каждый час!
main_prices_check_function_trigger_19 = CronTrigger(hour='18', minute='05') #сделать каждый час!
main_prices_check_function_trigger_20 = CronTrigger(hour='19', minute='05') #сделать каждый час!
main_prices_check_function_trigger_21 = CronTrigger(hour='20', minute='05') #сделать каждый час!
main_prices_check_function_trigger_22 = CronTrigger(hour='21', minute='05') #сделать каждый час!
main_prices_check_function_trigger_23 = CronTrigger(hour='22', minute='05') #сделать каждый час!
main_prices_check_function_trigger_24 = CronTrigger(hour='23', minute='05') #сделать каждый час!


# Запуск функций
# Запланировано ежедневная выгрузка остатков с ВБ:
scheduler.add_job(daily_get_stocks_data, trigger=daily_stock_trigger)

# # Запланировано ежедневная выгрузка заказов за вчера с ВБ:
# scheduler.add_job(daily_get_orders_data, trigger=daily_orders_download_trigger)
#
# # Запланировано ежедневная выгрузка расходов на хранение за вчера с ВБ:
# scheduler.add_job(daily_get_storage_data, trigger=daily_storage_download_trigger)
#
# # Запланировано ежедневная выгрузка приемки и платной приемки за вчера с ВБ:
# scheduler.add_job(daily_get_paid_acceptance_data, trigger=daily_paid_acceptance_download_trigger)
#
# # Запланировано ежедневная выгрузка и обработка маркетинговых расходов:
# scheduler.add_job(daily_get_marketing_costs, trigger=daily_get_marketing_costs_trigger)

# Запланирована основная отчетная функиция:
# scheduler.add_job(main_regular_reporting_function, trigger=main_reporting_function_trigger)
scheduler.add_job(main_regular_reporting_function, trigger=main_reporting_function_trigger_2)
# scheduler.add_job(main_regular_reporting_function, trigger=main_reporting_function_trigger_3)
# scheduler.add_job(main_regular_reporting_function, trigger=main_reporting_function_trigger_4)
# scheduler.add_job(main_regular_reporting_function, trigger=main_reporting_function_trigger_5)

# Запланировано ежедневная проверка API-ключей:
scheduler.add_job(daily_check_api, trigger=daily_api_check_trigger)
scheduler.add_job(daily_check_price_api, trigger=daily_price_api_check_trigger)

# Запланировано ежедневная проверка промокодов:
scheduler.add_job(daily_promocodes_check_admin_report, trigger=daily_promocodes_check_trigger)

# Запланировано ежедневная проверка сроков подписок и счетов:
scheduler.add_job(check_subscriptions_dates, trigger=hourly_subscriptions_date_check_trigger)
scheduler.add_job(check_subscriptions_dates, trigger=hourly_subscriptions_date_check_trigger_2)
scheduler.add_job(check_subscriptions_dates, trigger=hourly_subscriptions_date_check_trigger_3)
scheduler.add_job(check_subscriptions_dates, trigger=hourly_subscriptions_date_check_trigger_4)

# Интеграция с банком Точка (счета/выручка/закрывающие документы) временно отключена -
# проект сейчас некоммерческий. Чтобы включить обратно, раскомментируйте и задайте JWTTOKEN в .env.
# scheduler.add_job(check_invoices_status, trigger=hourly_invoices_status_check_trigger)
# scheduler.add_job(check_invoices_status, trigger=hourly_invoices_status_check_trigger_2)
# scheduler.add_job(check_invoices_status, trigger=hourly_invoices_status_check_trigger_3)
# scheduler.add_job(check_invoices_status, trigger=hourly_invoices_status_check_trigger_4)

# Запланировано ежедневное отражение выручки:
# scheduler.add_job(subscriptions_revenue_recognition, trigger=daily_revenue_recognition_trigger)

# Запланировано ежедневная проверка статусов подписок:
scheduler.add_job(check_subscriptions_status, trigger=daily_subscriptions_status_check_trigger)

# Запланировано ежедневная отправка admin-отчета:
#scheduler.add_job(monthly_prepare_and_send_closing_documents, trigger=daily_admin_report_trigger)

# Запланировано ежедневная отправка admin-отчета:
scheduler.add_job(admin_system_status_daily, trigger=daily_admin_report_trigger)

# Запланирована основная функиция по проверке цен:
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_1)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_2)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_3)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_4)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_5)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_6)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_7)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_8)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_9)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_10)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_11)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_12)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_13)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_14)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_15)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_16)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_17)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_18)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_19)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_20)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_21)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_22)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_23)
scheduler.add_job(main_prices_check_function, trigger=main_prices_check_function_trigger_24)