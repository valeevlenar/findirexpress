import asyncio
import io
from datetime import datetime
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
import pandas as pd
from openpyxl.reader.excel import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from sqlalchemy import select
import logging
from app.admin.admin_message import send_message_to_admin
from app.database.models import async_session, Products_price, Seller
from app.database.support_functions import get_chat_id_by_seller_id, get_seller_inn_by_seller_id, \
    get_company_name_by_seller_id
from app.prices.price_db_requests import new_product_price, set_new_prices_in_db
from app.prices.price_get_data import get_goods_in_sale
from app.main_bot.main_bot import bot
from app.prices.prices_wb_requests import send_new_prices_and_discounts_to_wb, send_new_size_prices_to_wb, \
    send_new_wb_club_discounts_to_wb

from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

from app.wrappers import with_session, log_and_notify_admin


class Price_counters():
    def __init__(self,
                 sellers_counter,
                 common_counter,
                 price_ok_counter,
                 new_product_counter,
                 price_update_at_seller,
                 price_update_at_wb,
                 price_templates_to_sellers):

        self.sellers_counter = sellers_counter
        self.common_counter = common_counter
        self.price_ok_counter = price_ok_counter
        self.new_product_counter = new_product_counter
        self.price_update_at_seller = price_update_at_seller
        self.price_update_at_wb = price_update_at_wb
        self.price_templates_to_sellers = price_templates_to_sellers

price_counter = Price_counters(0,0,0,0,0,0,0)

@with_session
async def create_price_template_to_seller_on_demand(session, seller_id):
    try:
        status, goods_in_sale = await get_goods_in_sale(session, seller_id)
        if status == 'done':
            products_for_price_check = await get_products_for_price_check(session=session,
                                                                          seller_id=seller_id,
                                                                          goods_in_sale=goods_in_sale)
            price_template = await create_price_template_for_seller(session=session,
                                                                    seller_id=seller_id,
                                                                    products_for_price_check=products_for_price_check)
            return status, price_template
        else:
            status = 'false'
            price_template = None
            return status, price_template
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e,)

@with_session
async def main_prices_check_function(session):
    try:
        price_counter.sellers_counter = 0
        price_counter.common_counter = 0
        price_counter.price_ok_counter = 0
        price_counter.new_product_counter = 0
        price_counter.price_update_at_seller = 0
        price_counter.price_update_at_wb = 0
        price_counter.price_templates_to_sellers = 0
        #Получаем список селлеров для проверки цены
        sellers_for_price_check = await session.execute(select(Seller.id).
                                                 where(Seller.price_control == True,
                                                       Seller.status=='Active',
                                                       Seller.service_status==True))
        sellers_for_price_check = sellers_for_price_check.mappings().all()

        # Создаем список корутин
        tasks = [main_prices_check_function_for_seller(seller_id=int(seller['id'])) for seller in sellers_for_price_check]

        # Запускаем все корутины параллельно
        await asyncio.gather(*tasks)

        await send_message_to_admin(f'Проверка цен завершена:'
                                    f'\n\nКол-во селлеров: {price_counter.sellers_counter}'
                                    f'\nКол-во проверенных товаров: {price_counter.common_counter} шт.'
                                    f'\nТоваров с корректной ценой: {price_counter.price_ok_counter} шт.'
                                    f'\nНовых товаров: {price_counter.new_product_counter} шт.'
                                    f'\nЗапрошена цена у селлера: {price_counter.price_update_at_seller} шт.'
                                    f'\nОбновлена цена на ВБ: {price_counter.price_update_at_wb} шт.'
                                    f'\nОтправлено шаблонов цен селлерам: {price_counter.price_templates_to_sellers} шт.')
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции проверка цены'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e, )

@with_session
async def main_prices_check_function_for_seller(session, seller_id):
    try:
        price_counter.sellers_counter += 1
        # Получаем товары в продаже от ВБ
        status, goods_in_sale = await get_goods_in_sale(session, seller_id)
        # print(seller_id, status, goods_in_sale)
        if status == 'done':
            products_for_price_update_from_seller = []
            products_for_price_update_at_wb = []

            # формируем список товаров для проверки:
            products_for_price_check = await get_products_for_price_check(session=session,
                                                                          seller_id=seller_id,
                                                                          goods_in_sale=goods_in_sale)

            # По каждому товару проверяем, есть ли он в базе
            for product in products_for_price_check:
                price_counter.common_counter += 1
                product_at_db = await session.execute(select(Products_price.id,
                                                            Products_price.price,
                                                            Products_price.discount,
                                                            Products_price.clubDiscount,
                                                            Products_price.price_set).
                                                     where(Products_price.seller_id == seller_id,
                                                           Products_price.nm_id == product['nmID'],
                                                           Products_price.editableSizePrice == product['editableSizePrice'],
                                                           Products_price.sizeID == product['sizeID']).
                                                     order_by(Products_price.updated_at.desc()))
                product_at_db = product_at_db.mappings().first()
                # Если товар есть в базе, то проверяем, установлена ли по нему цена
                if product_at_db:
                    if product_at_db.price_set:
                        # Если цена установлена, то проверяем цену товара
                        if product['price'] == product_at_db.price and product['discount'] == product_at_db.discount and \
                                product['clubDiscount'] == product_at_db.clubDiscount:
                            # Если цена и скидка ок, то двигаемся к следующему товару
                            price_counter.price_ok_counter += 1
                        else:
                            # Если цена не ок, то формируем список товаров для запроса с установкой новой цены.
                            products_for_price_update_at_wb.append(product)
                            price_counter.price_update_at_wb += 1
                    else:
                        # Если цена не установлена, то формируем список товаров для запроса цены у селлера:
                        products_for_price_update_from_seller.append(product)
                        price_counter.price_update_at_seller += 1
                else:
                    # если товаров нет в базе, то записываем товар в базу:
                    await new_product_price(session=session,
                                            seller_id=seller_id,
                                            product=product,
                                            price_set_bool=False)
                    price_counter.new_product_counter += 1
                    # и добавляем товар в список товаров для запроса цены у селлера:
                    products_for_price_update_from_seller.append(product)
                    price_counter.price_update_at_seller += 1

            # Если есть товары, по которым селлер не установил цену, то отправляем селлеру запрос:
            if products_for_price_update_from_seller != []:
                await send_new_products_without_price_to_seller(session=session,
                                                                seller_id=seller_id,
                                                                products_for_price_update_from_seller=products_for_price_update_from_seller)
            if products_for_price_update_at_wb != []:
                # print('мы тут')
                await send_new_prices_to_wb_main(session=session,
                                                 seller_id=seller_id,
                                                 products_for_price_update_at_wb=products_for_price_update_at_wb)
            # result = pd.DataFrame(products_for_price_check)
            # result.to_excel('товары для проверки цены.xlsx')
        else:
            await send_message_to_admin(f'Ошибка в функции проверка цены'
                                        f'\nSeller_id: {seller_id}')
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции проверка цены'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e, )

@log_and_notify_admin
async def send_new_products_without_price_to_seller(session, seller_id, products_for_price_update_from_seller):
    try:
        price_template = await create_price_template_for_seller(session=session,
                                                                seller_id=seller_id,
                                                                products_for_price_check=products_for_price_update_from_seller)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        chat_id = await get_chat_id_by_seller_id(session, seller_id)
        filename = f'{seller_title}_шаблон для заполнения цен.xlsx'
        file_in_io = io.BytesIO()
        price_template.save(file_in_io)
        file = file_in_io.getvalue()
        file_to_send = BufferedInputFile(file=file, filename=filename)
        message_text = (f'<b>У Вас есть товары с непроверенной ценой.</b>'
                        f'\nНаправляем Вам шаблон с ценами по таким товарам.'
                        f'\n\n<b>Проверьте цены в шаблоне, при необходимости поменяйте цену, '
                        f'скидку для покупателей и скидку для WB Клуба в столбцах M,N,O (выделены зеленым цветом).</b>'
                        f'\n'
                        f'\nВышлите нам обратно скорректированный шаблон, '
                        f'для этого зайдите в раздел "Контроль цен", '
                        f'выберите компанию и нажмите "Загрузить шаблон с ценами"'
                        f'\nПосле этого мы начнем контроллировать, чтобы цена на товар на ВБ всегда была такой.'
                        f'\nМы будем проверять цену товаров на площадке каждые 2 часа.')
        await bot.send_document(chat_id=chat_id, document=file_to_send, caption=message_text, parse_mode=ParseMode.HTML)
        price_counter.price_templates_to_sellers += 1
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при отправке шаблона с ценами селлеру.'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e, )

@with_session
async def get_price_template_from_seller(session, seller_id, products):
    try:
        # Получаем шаблон от селлера
        seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
        product_check = True
        price_check = True
        products_for_review = ''
        products_with_id = []
        product_for_review_counter =1
        # Берем отдельно каждый товар:
        for product in products:
            nm_id = int(product['Артикул ВБ'])
            editableSizePrice = bool(product['Возможность устанавливать цену для размера'])
            vendorCode = str(product['Артикул продавца'])
            if str(product['Код размера']) == 'nan':
                sizeID = None
            else:
                sizeID = int(product['Код размера'])
            if str(product['Размер'])=='nan':
                size = None
            else:
                size = str(product['Размер'])
            price = int(product['Цена (установленная селлером)'])
            discount = int(product['Скидка, % (установленная селлером)'])
            clubDiscount = int(product['Скидка для клуба ВБ, % (установленная селлером)'])
            product_inn = str(product['ИНН продавца'])
            new_discounted_price = float(product['Цена (установленная селлером) со скидкой'])
            new_club_discounted_price = float(product['Цена (установленная селлером) со скидкой для клуба ВБ'])
            # Проверяем список товаров на ошибки
            # print(nm_id, price, discount, clubDiscount, product_inn)
            if nm_id != "" and price>0 and discount>=0 and clubDiscount>=0 and product_inn == seller_inn:
                # Если ошибок нет, то ищем товар в базе
                product_in_db = await session.execute(select(Products_price.id,
                                                             Products_price.price,
                                                             Products_price.discount,
                                                             Products_price.clubDiscount).
                                                  where(Products_price.nm_id == nm_id,
                                                        Products_price.editableSizePrice == editableSizePrice,
                                                        Products_price.sizeID == sizeID,
                                                        Products_price.seller_id == seller_id).
                                                      order_by(Products_price.updated_at.desc()))
                product_in_db = product_in_db.mappings().first()
                # print(product_in_db)
                # Если такого товара нет в бд, то выдаем ошибку
                if not product_in_db:
                    product_check = False
                # Если товар есть:
                else:
                    # Берем старые и новые цены и считаем изменение
                    current_discounted_price_in_db = product_in_db['price']*(100-product_in_db['discount'])/100
                    current_club_discounted_price_in_db = product_in_db['price']*((100-product_in_db['discount'])/100)*(100-product_in_db['clubDiscount'])/100
                    try:
                        new_discounted_price_change = (new_discounted_price - current_discounted_price_in_db)/current_discounted_price_in_db
                    except:
                        new_discounted_price_change = 1
                    try:
                        # print(product_in_db, current_club_discounted_price_in_db, new_club_discounted_price)
                        new_club_discounted_price_change = (new_club_discounted_price - current_club_discounted_price_in_db)/current_club_discounted_price_in_db
                    except:
                        new_club_discounted_price_change = 1
                    # Проверяем цену:
                    if abs(new_discounted_price_change) >= 0.25 or abs(new_club_discounted_price_change)>=0.25:
                        # Если цена не ок, то выдаем ошибку по цене, и формируем список таких товаров селлеру
                        price_check = False
                        product_for_review_str = (f'\n{product_for_review_counter}. Артикул ВБ:{nm_id}'
                                                  f'\nАртикул продавца:{vendorCode}'
                                                 f'\nРазмер: {size}'
                                                 f'\nНовая цена после скидки:{new_discounted_price}'
                                                 f'\nНовая цена после скидки клуба ВБ:{new_club_discounted_price}')
                        product_for_review_counter+=1
                        products_for_review+=product_for_review_str
                    else:
                        # если цены ок, то ничего не делаем
                        pass
                    # Добавляем id товара к списку товаров для дальнейшего поиска.
                    product_id = {'id': product_in_db['id']}
                    product_with_id_merged = {**product_id, **product}
                    products_with_id.append(product_with_id_merged)
            else:
                # print('почему то')
                product_check = False
        # Если все товары есть в базе и цена ок, то обновляем цены в базе:
        if product_check == True and price_check == True:
            await set_new_prices_in_db(session=session,
                                       seller_id=seller_id,
                                       products_with_id=products_with_id)

        return product_check, price_check, products_for_review, products_with_id
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e, )

@log_and_notify_admin
async def get_products_for_price_check(session, seller_id, goods_in_sale):
    products_for_price_check = []
    for product in goods_in_sale:
        nmID = product['nmID']
        vendorCode = product['vendorCode']
        editableSizePrice = product['editableSizePrice']
        currencyCode = product['currencyIsoCode4217']
        discount = product['discount']
        clubDiscount = product['clubDiscount']
        product_dict = {'nmID': product['nmID'],
                        'vendorCode': product['vendorCode'],
                        'editableSizePrice': product['editableSizePrice'],
                        'currencyCode': product['currencyIsoCode4217'],
                        'discount': product['discount'],
                        'clubDiscount': product['clubDiscount']}
        if editableSizePrice:  # убрать not потом
            sizes = product['sizes']
            for size in sizes:
                size = {'sizeID': size['sizeID'],
                        'price': size['price'],
                        'discountedPrice': size['discountedPrice'],
                        'clubDiscountedPrice': size['clubDiscountedPrice'],
                        'techSizeName': size['techSizeName'],
                        'price_set_bool': False,
                        'price_set_by_seller': size['price'],
                        'discount_set_by_seller': product['discount'],
                        'clubDiscount_set_by_seller': product['clubDiscount']}
                product_merged = {**product_dict, **size}
                products_for_price_check.append(product_merged)
        else:
            size = {'sizeID': None,
                    'price': product['sizes'][0]['price'],
                    'discountedPrice': product['sizes'][0]['discountedPrice'],
                    'clubDiscountedPrice': product['sizes'][0]['clubDiscountedPrice'],
                    'techSizeName': None,
                    'price_set_bool': False,
                    'price_set_by_seller': product['sizes'][0]['price'],
                    'discount_set_by_seller': product['discount'],
                    'clubDiscount_set_by_seller': product['clubDiscount']}
            product_merged = {**product_dict, **size}
            products_for_price_check.append(product_merged)
    for product in products_for_price_check:
        product_in_db = await session.execute(select(Products_price.price,
                                                    Products_price.discount,
                                                    Products_price.clubDiscount,
                                                    Products_price.price_set).
                                             where(Products_price.seller_id==seller_id,
                                                   Products_price.nm_id ==product['nmID'],
                                                   Products_price.editableSizePrice==product['editableSizePrice'],
                                                   Products_price.sizeID==product['sizeID']).
                                              order_by(Products_price.updated_at.desc()))
        product_in_db = product_in_db.mappings().first()
        if not product_in_db:
            # Здесь надо создать запись в базу
            async with session.begin_nested():
                product_to_db = Products_price(seller_id = seller_id,
                                               nm_id = product['nmID'],
                                               vendorCode = product['vendorCode'],
                                               sizeID = product['sizeID'],
                                               price = product['price'],
                                               discountedPrice = product['discountedPrice'],
                                               clubDiscountedPrice = product['clubDiscountedPrice'],
                                               techSizeName = product['techSizeName'],
                                               currencyCode = product['currencyCode'],
                                               discount = product['discount'],
                                               clubDiscount = product['clubDiscount'],
                                               editableSizePrice = product['editableSizePrice'],
                                               price_set = False,
                                               updated_at = datetime.now())
                session.add(product_to_db)
            await session.commit()
        else:
            product['price_set_bool'] = product_in_db['price_set']
            product['price_set_by_seller'] = product_in_db['price']
            product['discount_set_by_seller'] = product_in_db['discount']
            product['clubDiscount_set_by_seller'] = product_in_db['clubDiscount']

    return products_for_price_check

@log_and_notify_admin
async def create_price_template_for_seller (session, seller_id, products_for_price_check):
    seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
    df = pd.DataFrame(products_for_price_check)
    df.head()
    path = 'app/templates/Шаблон для заполнения цен.xlsx'
    price_template = load_workbook(path)
    ws = price_template["Шаблон цен"]
    df.insert(0, 'ИНН продавца', seller_inn)
    df.insert(1, 'Артикул ВБ',df.pop('nmID'))
    df.insert(2, 'Артикул продавца', df.pop('vendorCode'))
    df.insert(3, 'Возможность устанавливать цену для размера', df.pop('editableSizePrice'))
    df.insert(4, 'Код размера', df.pop('sizeID'))
    df.insert(5, 'Размер', df.pop('techSizeName'))
    df.insert(6, 'Валюта', df.pop('currencyCode'))
    df.insert(7, 'Цена (на ВБ)', df.pop('price'))
    df.insert(8, 'Скидка, % (на ВБ)', df.pop('discount'))
    df.insert(9, 'Скидка для клуба ВБ, % (на ВБ)', df.pop('clubDiscount'))
    df.insert(10, 'Текущая цена со скидкой', df.pop('discountedPrice'))
    df.insert(11, 'Текущая цена со скидкой для клуба ВБ', df.pop('clubDiscountedPrice'))
    df.insert(12, 'Селлер зафиксировал цену в сервисе?', df.pop('price_set_bool'))
    df.insert(13, 'Цена (установленная селлером)', df.pop('price_set_by_seller'))
    df.insert(14, 'Скидка, % (установленная селлером)', df.pop('discount_set_by_seller'))
    df.insert(15, 'Скидка для клуба ВБ, % (установленная селлером)', df.pop('clubDiscount_set_by_seller'))
    df.insert(16, 'Цена (установленная селлером) со скидкой',0)
    df.insert(17, 'Цена (установленная селлером) со скидкой для клуба ВБ', 0)

    for r in dataframe_to_rows(df, header=True, index=False):
        ws.append(r)
        ws.title = 'Шаблон цен'
    max_row = ws.max_row+1
    for row_num in range(2, max_row):
        new_price_with_discount = '=N{}*(100-O{})/100'
        formatted_new_price_with_discount = new_price_with_discount.format(row_num, row_num)
        ws['Q{}'.format(row_num)] = formatted_new_price_with_discount
        new_price_with_discount_wb_club = '=Q{}*(100-P{})/100'
        formatted_new_price_with_discount_wb_club = new_price_with_discount_wb_club.format(row_num, row_num)
        ws['R{}'.format(row_num)] = formatted_new_price_with_discount_wb_club

    # меняем ширину столбцов
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 11
    ws.column_dimensions['C'].width = 26
    ws.column_dimensions['E'].width = 11
    number_columns = ['D','H','I','J', 'K', 'L', 'M','N','O','P','Q','R']
    for col in number_columns:
        ws.column_dimensions[col].width = 11

    # Раскрашиваем столбцы:
    thin_color = Side(border_style="thin", color="BFBFBF")
    lightgreenFill = PatternFill(start_color='C6E0B4',
                                 end_color='C6E0B4',
                                 fill_type='solid')
    lightorangeFill = PatternFill(start_color='FDE9D9',
                                  end_color='FDE9D9',
                                  fill_type='solid')
    lightgreyFill = PatternFill(start_color='D9D9D9',
                                 end_color='D9D9D9',
                                 fill_type='solid')
    ft_normal = Font(name='Calibri', size=10, bold=False)
    light_grey_columns = ['H','I','J','K','L']
    for col in light_grey_columns:
        for cell in ws[col]:
            cell.font = ft_normal
            cell.fill = lightgreyFill
            cell.border = Border(left=thin_color,
                                 right=thin_color,
                                 bottom=thin_color,
                                 top=thin_color)

    light_green_columns = ['N','O','P']
    for col in light_green_columns:
        for cell in ws[col]:
            cell.font = ft_normal
            cell.fill = lightgreenFill
            cell.border = Border(left=thin_color,
                                 right=thin_color,
                                 bottom=thin_color,
                                 top=thin_color)

    orange_columns = ['Q','R']
    for col in orange_columns:
        for cell in ws[col]:
            cell.font = ft_normal
            cell.fill = lightorangeFill
            cell.border = Border(left=thin_color,
                                 right=thin_color,
                                 bottom=thin_color,
                                 top=thin_color)
    normal_columns = ['A','B','C','D','E','F','G','M']
    for col in normal_columns:
        for cell in ws[col]:
            cell.font = ft_normal

    # Форматируем шапку:
    ft = Font(name='Calibri', size=10, bold=True)
    thin = Side(border_style="thin", color="000000")
    for row in ws["A1:R1"]:
        for cell in row:
            cell.font = ft
            cell.border = Border(bottom=thin,
                                 left=thin_color,
                                 right=thin_color,
                                 top=thin_color)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrapText=True)

    # Меняем высоту первой строки:
    ws.row_dimensions[1].height = 76
    return price_template

# Тут делим на 4 потока: 1 - цены и скидки, 2 - скидки для размеров, 3 - цены для размеров, 4 - скидки для wb клуба
@log_and_notify_admin
async def send_new_prices_to_wb_main(session, seller_id,products_for_price_update_at_wb):
    try:
        # print (products_for_price_update_at_wb)
        products_for_price_and_discount_update = []
        products_for_size_discount_update = []
        products_for_size_price_update = []
        products_for_wb_club_discount_update = []
        status_prices_and_discounts = False
        status_size_discounts = False
        status_size_prices = False
        status_wb_club_discount = False
        for product in products_for_price_update_at_wb:
            # print(product)
            # обычные товары - цены и скидки
            if (product['editableSizePrice'] == False and
                    (product['discount_set_by_seller'] != product['discount']
                     or product['price_set_by_seller']!= product['price'])):
                product_dict = {'nmID': product['nmID'],
                                'price': product['price_set_by_seller'],
                                'discount': product['discount_set_by_seller']}
                products_for_price_and_discount_update.append(product_dict)

            # скидки для размеров
            if product['editableSizePrice'] == True and product['discount_set_by_seller']!= product['discount']:
                editable_size_product_discount_dict = {'nmID': product['nmID'],
                                                       'discount': product['discount_set_by_seller']}
                products_for_size_discount_update.append(editable_size_product_discount_dict)

            # цены для размеров
            if product['editableSizePrice'] == True and product['price_set_by_seller']!= product['price']:
                editable_size_product_price_dict = {'nmID': product['nmID'],
                                              'sizeID': product['sizeID'],
                                              'price': product['price_set_by_seller']}
                products_for_size_price_update.append(editable_size_product_price_dict)

            # скидки для ВБ клуба
            if product['clubDiscount_set_by_seller'] != product['clubDiscount']:
                club_discount_product_dict = {'nmID': product['nmID'],
                                                    'clubDiscount': product['clubDiscount_set_by_seller']}
                products_for_wb_club_discount_update.append(club_discount_product_dict)

        # print(products_for_price_and_discount_update)
        # Обрабатываем группу 1 - простые цены и скидки
        if products_for_price_and_discount_update != []:
            status_prices_and_discounts = await send_new_prices_and_discounts_to_wb_generator(session=session,
                                                                                              seller_id=seller_id,
                                                                                              products_for_price_and_discount_update=products_for_price_and_discount_update)
        else:
            status_prices_and_discounts = True

        # print(products_for_size_discount_update)
        # Обрабатываем группу 2 - скидки для размера
        if products_for_size_discount_update != []:
            status_size_discounts = await send_new_size_discounts_to_wb_generator(session=session,
                                                                                  seller_id=seller_id,
                                                                                  products_for_size_discount_update=products_for_size_discount_update)
        else:
            status_size_discounts = True

        # print(products_for_size_price_update)
        # Обрабатываем группу 3 - цены для размера
        if products_for_size_price_update != []:
            status_size_prices = await send_new_size_prices_to_wb_generator(session=session,
                                                                            seller_id=seller_id,
                                                                            products_for_size_price_update=products_for_size_price_update)
        else:
            status_size_prices = True

        # print(products_for_wb_club_discount_update)
        # Обрабатываем группу 4 - скидки для вб клуба
        if products_for_wb_club_discount_update != []:
            status_wb_club_discount = await send_new_wb_club_discounts_to_wb_generator(session=session,
                                                                                       seller_id=seller_id,
                                                                                       products_for_wb_club_discount_update=products_for_wb_club_discount_update)
        else:
            status_wb_club_discount = True

        if status_prices_and_discounts and status_size_discounts and status_size_prices and status_wb_club_discount:
            # print('status_prices_and_discounts', status_prices_and_discounts)
            # print('status_size_discounts', status_size_discounts)
            # print('status_size_prices', status_size_prices)
            # print('status_wb_club_discount', status_wb_club_discount)
            pass
        else:
            # print('status_prices_and_discounts', status_prices_and_discounts)
            # print('status_size_discounts', status_size_discounts)
            # print('status_size_prices', status_size_prices)
            # print('status_wb_club_discount', status_wb_club_discount)
            await send_message_to_admin(f'Ошибка при обновлении цен на ВБ'
                                        f'\nSeller_id: {seller_id}')

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления цен на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_prices_and_discounts_to_wb_generator(session, seller_id, products_for_price_and_discount_update):
    try:
        price_update_limit = 1
        products_for_price_and_discount_update_limited = [products_for_price_and_discount_update[i:i + price_update_limit] for i in range(0, len(products_for_price_and_discount_update), price_update_limit)]
        status = True
        # Для каждой части списка отдельно отправляем цены на апдейт:
        for products_for_price_and_discount_update_short in products_for_price_and_discount_update_limited:
            await asyncio.sleep(1)
            upload_status = await send_new_prices_and_discounts_to_wb(session=session,
                                                                      seller_id=seller_id,
                                                                      products_for_price_and_discounts_update=products_for_price_and_discount_update_short)
            if upload_status:
                pass
            else:
                status = False

        return status
    except Exception as e:
    # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления обычных цен на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_size_discounts_to_wb_generator(session, seller_id, products_for_size_discount_update):
    try:
        price_update_limit = 1000
        products_for_size_discount_update_limited = [products_for_size_discount_update[i:i + price_update_limit] for i in range(0, len(products_for_size_discount_update), price_update_limit)]
        status = True
        # Для каждой части списка отдельно отправляем цены на апдейт:
        for products_for_size_discount_update_short in products_for_size_discount_update_limited:
            await asyncio.sleep(1)
            upload_status = await send_new_prices_and_discounts_to_wb(session=session,
                                                                      seller_id=seller_id,
                                                                      products_for_price_and_discounts_update=products_for_size_discount_update_short)
            if upload_status:
                pass
            else:
                status = False
        # print('статус загрузки', status)
        return status
    except Exception as e:
    # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления скидок для размера на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_size_prices_to_wb_generator(session, seller_id, products_for_size_price_update):
    try:
        price_update_limit = 1000
        products_for_size_price_update_limited = [products_for_size_price_update[i:i + price_update_limit] for i in range(0, len(products_for_size_price_update), price_update_limit)]
        status = True
        # Для каждой части списка отдельно отправляем цены на апдейт:
        for products_for_size_price_update_short in products_for_size_price_update_limited:
            await asyncio.sleep(1)
            upload_status = await send_new_size_prices_to_wb(session=session,
                                                             seller_id=seller_id,
                                                             products_for_size_price_update=products_for_size_price_update_short)
            if upload_status:
                pass
            else:
                status = False

        return status
    except Exception as e:
    # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления цен для размера на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_new_wb_club_discounts_to_wb_generator(session, seller_id, products_for_wb_club_discount_update):
    try:
        price_update_limit = 1000
        products_for_wb_club_discount_update_limited = [products_for_wb_club_discount_update[i:i + price_update_limit] for i in range(0, len(products_for_wb_club_discount_update), price_update_limit)]
        status = True
        # print('обновляем скидку клуба')
        # Для каждой части списка отдельно отправляем цены на апдейт:
        for products_for_wb_club_discount_update_short in products_for_wb_club_discount_update_limited:
            await asyncio.sleep(1)
            upload_status = await send_new_wb_club_discounts_to_wb(session=session,
                                                                   seller_id=seller_id,
                                                                   products_for_wb_club_discount_update=products_for_wb_club_discount_update_short)
            # print(upload_status)
            if upload_status:
                pass
            else:
                status = False

        return status
    except Exception as e:
    # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в функции обновления скидок для ВБ клуба на ВБ'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)