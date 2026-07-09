from app.admin.admin_message import send_message_to_admin
import logging
from app.database.classes.sales import Sales
from app.database.support_functions import get_seller_inn_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_Reporting_Week_func
from app.get_data.get_sales_data import get_and_check_sales_report
from app.wrappers import with_session, log_and_notify_admin
import asyncio
import sqlalchemy
from sqlalchemy import select


@with_session
async def add_doc_type_name (session, seller_id):
    logging.info(f'Начали обрабатывать seller_id {seller_id}')
    downloading_status = False
    downloading_counter = 0
    date_to = await end_of_Reporting_Week_func()
    date_from = await start_for_downloading_data_func()
    while downloading_status != True and downloading_counter < 15:

        status, sales_report = await get_and_check_sales_report(session=session,
                                                                seller_id=seller_id,
                                                                date_to=date_to,
                                                                date_from=date_from)
        logging.info(f'Выгрузили выручку по seller_id {seller_id} за период {date_from} - {date_to}, статус={status}')
        if status == 'unauthorised_api':
            await send_message_to_admin(f'Seller_id: {seller_id} - unauthorised api')
            downloading_status = True
        elif status == 'new_unauthorised_api':
            await send_message_to_admin(f'Seller_id: {seller_id} - unauthorised api')
            downloading_status = True
        elif status == 'unknown':
            await send_message_to_admin(f'Неизвестный ответ от ВБ в регулярной загрузке продаж!'
                                        f'\nSeller_id: {seller_id}'
                                        f'\nОтвет ВБ: '
                                        f'{sales_report}')
            downloading_status = True
        elif status == 'no_data':
            await send_message_to_admin(f'Seller_id: {seller_id} - no data')
            downloading_status = True
        elif status == 'Done':
            if await sales_report_add_doc_type(session=session, seller_id=seller_id, sales_report=sales_report):
                downloading_status = True
            else:
                await send_message_to_admin(f'Seller_id: {seller_id} - статус done, но sales report compilation не выполнен')
        elif status == 'not_complete':
            if await sales_report_add_doc_type(session=session, seller_id=seller_id, sales_report=sales_report):
                await send_message_to_admin(f'Seller_id: {seller_id} - статус not complete, то что получили обработали')
            else:
                await send_message_to_admin(f'Seller_id: {seller_id} - статус not complete, но sales report compilation не выполнен')
        else:
            await send_message_to_admin(f'Ошибка в latest_weekly_report_sent_date в основной отчетной функции!')
            reporting = False

@log_and_notify_admin
async def sales_report_add_doc_type (session, seller_id, sales_report):
    try:
        logging.info(f'Добавляем doctype по seller_id {seller_id}')
        counter_item = 0
        for item in sales_report:
            counter_item+=1
            await set_add_doctype(session=session,
                                  seller_id=seller_id,
                                  sales_item=item)
        logging.info(f'Добавляем doctype по seller_id {seller_id}'
                     f'Обновлено {counter_item} строк')

        return True
    except:
        return False

# Получаем выгрузку по продажам от ВБ и построчно заносим продажи в базу
@log_and_notify_admin
async def set_add_doctype (session, seller_id, sales_item):
    sales_id = await session.scalar(select(Sales.id).
                                   where(Sales.rrd_id==sales_item['rrd_id'],
                                         Sales.seller_id == seller_id))
    doc_type_name = sales_item['doc_type_name']
    print(doc_type_name)
    query = sqlalchemy.update(Sales).where(Sales.id == sales_id).values(doc_type_name=doc_type_name)
    await session.execute(query)
    await session.commit()


