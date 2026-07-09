import asyncio
from datetime import datetime
import pandas as pd
import logging
from app.admin.admin_message import send_message_to_admin
from app.database.api_functions import unauthorised_api_notification
from app.database.support_functions import get_api_by_seller_id
from app.get_data.wbrequests import get_sales_data
from app.wrappers import with_session


# Скачивание запросов, генератор и проверка ответов:
@with_session
async def get_and_check_sales_report(session, seller_id, date_from, date_to):
    try:
        # Форматирование дат для API v5 (YYYY-MM-DD)
        if isinstance(date_from, datetime):
            date_from_str = date_from.strftime('%Y-%m-%d')
        else:
            date_from_str = str(date_from).split('T')[0]

        if isinstance(date_to, datetime):
            date_to_str = date_to.strftime('%Y-%m-%d')
        else:
            date_to_str = str(date_to).split('T')[0]

        logging.info(f'Выгружаем выручку по seller_id {seller_id} за период {date_from_str} - {date_to_str}')

        rrdid = 0
        status = 'start'
        full_report = []  # Список для накопления всех страниц отчета

        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        if not active_api:
            await unauthorised_api_notification(session=session, seller_id=seller_id)
            return 'unauthorised_api', '[]'

        # Цикл выгрузки
        while status != 'Done':
            logging.info(f'Seller_id: {seller_id}. Запрос продаж с rrdid={rrdid}')

            # Получаем пачку данных
            batch = await get_sales_data(session=session,
                                         seller_id=seller_id,
                                         date_from=date_from_str,
                                         date_to=date_to_str,
                                         rrdid=rrdid,
                                         wb_api=active_api)

            # 1. Если вернулся пустой список, значит данных больше нет или их вообще не было
            if not batch:
                if not full_report:
                    logging.info(f'Seller_id: {seller_id}. Выгружаем выручку. First res: no_data.')
                    return 'no_data', []
                else:
                    logging.info(f'Seller_id: {seller_id}. Выгрузка завершена. Всего строк: {len(full_report)}')
                    status = 'Done'
                    break

            # 2. Добавляем пачку к общему отчету
            full_report.extend(batch)
            logging.info(f'Seller_id: {seller_id}. Выгрузили пачку {len(batch)} строк. Всего: {len(full_report)}')

            # 3. Получаем новый rrd_id для следующего запроса
            try:
                last_item = batch[-1]
                new_rrdid = last_item.get('rrd_id')
                if not new_rrdid:
                    logging.warning(f'Seller_id: {seller_id}. rrd_id не найден в последнем элементе. Прерываем.')
                    status = 'Done'
                    break
                rrdid = new_rrdid
            except (IndexError, AttributeError) as e:
                logging.error(f'Seller_id: {seller_id}. Ошибка при получении rrd_id: {e}')
                status = 'Done'
                break

            # 4. Проверка на необходимость следующего запроса
            # Если пачка меньше 100 000, значит это конец
            if len(batch) < 100000:
                status = 'Done'
            else:
                # Если пачка полная (100к), значит есть еще данные.
                # Лимит API v5 - 1 запрос в минуту. Ждем.
                logging.info(f'Seller_id: {seller_id}. Пачка полная (100к). Ждем 61 сек перед следующим запросом.')
                await asyncio.sleep(61)

        return 'Done', full_report

    except Exception as e:
        await send_message_to_admin(text=f'Ошибка при выгрузке выручки\nSeller_id = {seller_id}\n{e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return 'error', []