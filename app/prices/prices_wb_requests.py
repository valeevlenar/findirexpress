import logging
import asyncio
import requests
from sqlalchemy import select

from app.admin.admin_message import send_message_to_admin
from app.database.models import PriceApiKeys
from app.prices.price_api_functions import unauthorised_price_api_identified
from app.wrappers import with_session, log_and_notify_admin
from config import goods_and_prices_url, send_new_prices_and_discounts_url, check_price_update_upload_id_status_url, \
    send_new_size_prices_url, send_new_wb_club_discounts_url


# Получаем список товаров с ценами:
@log_and_notify_admin
async def get_goods_and_prices_from_wb(offset, price_api):
    try:
        headers = {'Authorization': price_api}
        params = {'limit': 1000, 'offset': offset}
        res=requests.get(goods_and_prices_url, headers=headers, params=params)
        status_code = res.status_code
        result = res.json()
        return status_code, result
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        # ИСПРАВЛЕНО: Возвращаем два None вместо неявного одного
        return None, None

@log_and_notify_admin
async def send_new_prices_and_discounts_to_wb(session, seller_id, products_for_price_and_discounts_update):
    try:
        active_api = await get_prices_api_for_seller_id(session, seller_id)
        headers = {'Authorization': active_api}
        params = []
        for product in products_for_price_and_discounts_update:
            params.append(product)
        # print('мы в функции обновления:', params)
        data = {"data": params}
        res=requests.post(send_new_prices_and_discounts_url, headers=headers, json=data)
        # print(res.status_code)
        # print(res.text)

        if res.status_code == 200:
            result = res.json()
            upload_id = result['data']['id']
            if upload_id:
                # print(upload_id)
                await asyncio.sleep(1)
                upload_id_status_checked = False
                while not upload_id_status_checked:
                    upload_id_status = await check_price_update_upload_id_status(session=session,
                                                                                 seller_id=seller_id,
                                                                                 upload_id=upload_id)
                    # === ДОБАВЬ ВОТ ЭТИ ДВЕ СТРОЧКИ ===
                    if upload_id_status is False or upload_id_status is None:
                        return False  # Прерываем цикл, так как произошел сбой
                    # ====================================

                    if int(upload_id_status) == 3:
                        return True
                    elif int(upload_id_status) == 4 or int(upload_id_status) == 5 or int(upload_id_status) == 6:
                        return False
                    elif int(upload_id_status) != 3 and int(upload_id_status) != 4 and int(upload_id_status) != 5 and int(upload_id_status) != 6:
                        await asyncio.sleep(10)
            else:
                await send_message_to_admin(f'Ошибка в функции обновления цен на ВБ'
                                            f'\nSeller_id: {seller_id}')

        elif res.status_code == 429:
            await asyncio.sleep(60)
            await send_new_prices_and_discounts_to_wb(session=session,
                                                      seller_id=seller_id,
                                                      products_for_price_and_discounts_update=products_for_price_and_discounts_update)

        elif res.status_code == 401:
            await unauthorised_price_api_identified(session=session,
                                                    seller_id=seller_id,
                                                    wb_api=active_api)
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления цен на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_size_prices_to_wb(session, seller_id, products_for_size_price_update):
    try:
        active_api = await get_prices_api_for_seller_id(session=session,
                                                        seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = []
        for product in products_for_size_price_update:
            params.append(product)

        data = {"data": params}
        res=requests.post(send_new_size_prices_url, headers=headers, json=data)

        if res.status_code == 200:
            result = res.json()
            upload_id = result['data']['id']
            if upload_id:
                # print(upload_id)
                await asyncio.sleep(1)
                upload_id_status_checked = False
                while not upload_id_status_checked:
                    upload_id_status = await check_price_update_upload_id_status(session=session,
                                                                                 seller_id=seller_id,
                                                                                 upload_id=upload_id)
                    # === ДОБАВЬ ВОТ ЭТИ ДВЕ СТРОЧКИ ===
                    if upload_id_status is False or upload_id_status is None:
                        return False  # Прерываем цикл, так как произошел сбой
                    # ====================================

                    if int(upload_id_status) == 3:
                        return True
                    elif int(upload_id_status) == 4 or int(upload_id_status) == 5 or int(upload_id_status) == 6:
                        return False
                    elif int(upload_id_status) != 3 and int(upload_id_status) != 4 and int(upload_id_status) != 5 and int(upload_id_status) != 6:
                        await asyncio.sleep(10)
            else:
                await send_message_to_admin(f'Ошибка в функции цен для размера на ВБ'
                                            f'\nSeller_id: {seller_id}')

        elif res.status_code == 429:
            await asyncio.sleep(60)
            await send_new_size_prices_to_wb(session, seller_id, products_for_size_price_update)

        elif res.status_code == 401:
            await unauthorised_price_api_identified(session=session,
                                                    seller_id=seller_id,
                                                    wb_api=active_api)
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления цен на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_wb_club_discounts_to_wb (session, seller_id, products_for_wb_club_discount_update):
    try:
        active_api = await get_prices_api_for_seller_id(session=session,
                                                        seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = []
        for product in products_for_wb_club_discount_update:
            params.append(product)

        # print(params)
        data = {"data": params}
        res=requests.post(send_new_wb_club_discounts_url, headers=headers, json=data)
        # print(res.status_code)
        # print(res.text)
        if res.status_code == 200:
            result = res.json()
            upload_id = result['data']['id']
            if upload_id:
                await asyncio.sleep(1)
                upload_id_status_checked = False
                while not upload_id_status_checked:
                    upload_id_status = await check_price_update_upload_id_status(session=session,
                                                                                 seller_id=seller_id,
                                                                                 upload_id=upload_id)
                    # === ДОБАВЬ ВОТ ЭТИ ДВЕ СТРОЧКИ ===
                    if upload_id_status is False or upload_id_status is None:
                        return False  # Прерываем цикл, так как произошел сбой
                    # ====================================

                    if int(upload_id_status) == 3:
                        return True
                    elif int(upload_id_status) == 4 or int(upload_id_status) == 5 or int(upload_id_status) == 6:
                        return False
                    elif int(upload_id_status) != 3 and int(upload_id_status) != 4 and int(upload_id_status) != 5 and int(upload_id_status) != 6:
                        await asyncio.sleep(10)
            else:
                await send_message_to_admin(f'Ошибка в функции цен для размера на ВБ'
                                            f'\nSeller_id: {seller_id}')

        elif res.status_code == 429:
            await asyncio.sleep(60)
            await send_new_wb_club_discounts_to_wb(session=session,
                                                   seller_id=seller_id,
                                                   products_for_wb_club_discount_update=products_for_wb_club_discount_update)

        elif res.status_code == 401:
            await unauthorised_price_api_identified(session=session,
                                                    seller_id=seller_id,
                                                    wb_api=active_api)
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления цен на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def get_prices_api_for_seller_id(session, seller_id):
    api = await session.scalar(select(PriceApiKeys.price_wb_api).where(PriceApiKeys.seller_id==seller_id))
    if not api:
        return False
    else:
        return api

@log_and_notify_admin
async def check_price_update_upload_id_status(session, seller_id, upload_id):
    try:
        active_api = await get_prices_api_for_seller_id(session=session,
                                                        seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = {'uploadID': upload_id}
        res = requests.get(check_price_update_upload_id_status_url, headers=headers, params=params)
        # print(res.status_code)
        # print(res.text)
        if res.status_code == 200:
            result = res.json()
            upload_id_status = result.get('data', {}).get('status')
            if upload_id_status is not None:
                await asyncio.sleep(1)
                # print(upload_id_status)
                return upload_id_status
            else:
                await send_message_to_admin(f'Ошибка при проверке статуса загрузки цен')
                return False  # Возвращаем False, чтобы код не падал на None

        elif res.status_code == 429:
            await asyncio.sleep(60)
            return await check_price_update_upload_id_status(session=session,
                                                             seller_id=seller_id,
                                                             upload_id=upload_id)

        elif res.status_code == 401:
            await unauthorised_price_api_identified(session=session,
                                                    seller_id=seller_id,
                                                    wb_api=active_api)
            return False
        return False  # Резервный выход

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False  # Возвращаем False вместо None при падении

@log_and_notify_admin
async def get_detailed_status_price_update_upload_id(session, seller_id, upload_id):
    try:
        get_detailed_status_price_update_upload_id_url = 'https://discounts-prices-api.wildberries.ru/api/v2/history/goods/task'
        active_api = await get_prices_api_for_seller_id(session=session,
                                                        seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = {'limit':10,'uploadID': upload_id}
        res = requests.get(get_detailed_status_price_update_upload_id_url, headers=headers, params=params)
        print(res.status_code)
        print(res.text)
        if res.status_code == 200:
            result = res.json()
            upload_id_status = result['data']['status']
            if upload_id_status:
                await asyncio.sleep(1)
                # print(upload_id_status)
                return upload_id_status
            else:
                await send_message_to_admin(f'Ошибка при проверке статуса загрузки цен')

        elif res.status_code == 429:
            await asyncio.sleep(60)
            await check_price_update_upload_id_status(session=session,
                                                      seller_id=seller_id,
                                                      upload_id=upload_id)

        elif res.status_code == 401:
            await unauthorised_price_api_identified(seller_id=seller_id, wb_api=active_api)
            return False

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)