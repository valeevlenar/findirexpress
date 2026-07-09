import logging
from app.database.apirequests import ApiClient
from app.wrappers import with_session

# URL для API v5
sales_url = 'https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod'


# Проверяем статус компании и выгружаем продажи из ВБ:
@with_session
async def get_sales_data(session, seller_id, date_from, date_to, rrdid, wb_api):
    try:
        # Параметры для API v5
        sales_params = {
            'dateFrom': date_from,
            'limit': 100000,  # Лимит v5
            'dateTo': date_to,
            'rrdid': rrdid,
            # 'period': 'weekly' # Можно добавить при необходимости
        }

        async with ApiClient(db_session=session,
                             seller_id=seller_id,
                             api_key=wb_api) as client:
            sales_report = await client.fetch(
                method="GET",
                url=sales_url,
                headers={"Authorization": wb_api},  # Для v5 токен в заголовке
                params=sales_params
            )

        # Если API вернул None или ошибку внутри клиента, возвращаем пустой список,
        # чтобы цикл в вызывающей функции корректно завершился
        if sales_report is None:
            return []

        return sales_report

    except Exception as e:
        # Запись ошибки в лог
        logging.exception(f"Seller_id: {seller_id}. An error occurred in get_sales_data: {e}", exc_info=e)
        return []