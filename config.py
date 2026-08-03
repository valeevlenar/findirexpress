import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_ID = int(os.getenv('ADMIN_ID'))

FROM_MAIL = "findirexpress@yandex.ru"
SERVER_ADR = "smtp.yandex.ru"
SERVER_PORT = 587

# Реквизиты и токен банка Точка. Пусты, если не заданы в .env -
# интеграция со счетами/закрывающими документами в этом случае отключена (см. app/payments/bank.py).
account_id = os.getenv('BANK_ACCOUNT_ID')
customer_code = os.getenv('BANK_CUSTOMER_CODE')
company_inn = os.getenv('COMPANY_INN')
client_id = os.getenv('BANK_CLIENT_ID')
bank_token = os.getenv('JWTTOKEN')
create_invoice_url = 'https://enter.tochka.com/uapi/invoice/v1.0/bills'
get_invoice_from_bank_url = 'https://enter.tochka.com/uapi/invoice/v1.0/bills/'
check_invoice_status_url = 'https://enter.tochka.com/uapi/invoice/v1.0/bills/'
create_closing_doc_url = 'https://enter.tochka.com/uapi/invoice/v1.0/closing-documents'
# create_closing_doc_url = 'https://enter.tochka.com/sandbox/v2/invoice/v1.0/closing-documents'
get_closing_document_from_bank_url = 'https://enter.tochka.com/uapi/invoice/v1.0/closing-documents/'
# get_closing_document_from_bank_url = 'https://enter.tochka.com/sandbox/v2/invoice/v1.0/closing-documents/'

# folders:
invoice_folder = r"app/invoices_archive/"
closing_documents_folder = r"app/closing_documents/"

#wb urls:
# GET /api/v1/supplier/stocks отключен WB навсегда с 14.07.2026 (см. app/get_data/get_stocks.py).
# Заменен на отчет "Остатки на складах" (создание задачи -> статус -> скачивание).
warehouse_remains_create_url = ('https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains'
                                '?groupByBrand=true&groupBySubject=true&groupBySa=true'
                                '&groupByNm=true&groupByBarcode=true&groupBySize=true&locale=ru')
warehouse_remains_status_url = 'https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains/tasks/{task_id}/status'
warehouse_remains_download_url = 'https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains/tasks/{task_id}/download'
goods_and_prices_url = 'https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter'
send_new_prices_and_discounts_url ='https://discounts-prices-api.wildberries.ru/api/v2/upload/task'
check_price_update_upload_id_status_url = 'https://discounts-prices-api.wildberries.ru/api/v2/history/tasks'
send_new_size_prices_url='https://discounts-prices-api.wildberries.ru/api/v2/upload/task/size'
send_new_wb_club_discounts_url='https://discounts-prices-api.wildberries.ru/api/v2/upload/task/club-discount'

get_orders_url = 'https://statistics-api.wildberries.ru/api/v1/supplier/orders'
storage_report_creation_url = 'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage'
paid_acceptance_url = 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/acceptance-report'
create_paid_acceptance_report_url = 'https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report'

supplies_url = 'https://statistics-api.wildberries.ru/api/v1/supplier/incomes'
marketing_costs_url = 'https://advert-api.wildberries.ru/adv/v1/upd'
marketing_campaign_statistics_url = 'https://advert-api.wildberries.ru/adv/v3/fullstats'
get_reviews_data_url = 'https://feedbacks-api.wildberries.ru/api/v1/feedback'



# main_bot_url_link = 'https://t.me/Findirexpress_test_bot'
main_bot_url_link = 'https://t.me/FindirExpress_bot'

templates_path = r'app/templates/'