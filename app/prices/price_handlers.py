import io
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
import pandas as pd
import logging

from app.checks import check_user_status, check_user_companies, check_active_subscription, \
    check_user_access_to_price_control_for_user_tg_id
from app.database.support_functions import delete_one_messages, get_price_control_by_seller_id, \
    get_company_name_by_seller_id
from app.main_bot.handlers import register_company_text, register_user_text, no_active_subscription_text
from app.main_bot.keyboards import create_companies_keyboard, create_price_control_keyboard, approve_keyboard, \
    price_template_cancel_send, price_template_approve
from app.main_bot.states import Price_control
import app.main_bot.keyboards as kb
from app.managers.managers_functions import check_manager_companies
from app.prices.price_api_functions import check_price_api_exist, check_price_api, new_price_api_key_upload
from app.prices.price_control_functions import create_price_template_to_seller_on_demand, \
    get_price_template_from_seller, main_prices_check_function_for_seller
from app.prices.price_db_requests import set_new_prices_in_db, enable_price_control_function, \
    disable_price_control_function

price_control_router = Router()

# Контроль цен
@price_control_router.message(F.text == '🏦 Контроль цен')
async def price_control_main (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id) or await check_manager_companies(tg_id=message.from_user.id):
            try:
                companies_list_buttons = await create_companies_keyboard(tg_id=message.from_user.id)
                await state.set_state(Price_control.company_name)
                await message.answer("Выберите компанию, по которой хотите использовать функцию:",
                                              reply_markup=companies_list_buttons.as_markup())
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))

@price_control_router.callback_query(F.data, Price_control.company_name)
async def price_control_company(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_price_control_for_user_tg_id(seller_id=int(callback.data),
                                                                   user_tg_id=int(callback.from_user.id)):
            await state.update_data(seller_id = callback.data)
            if await check_active_subscription(seller_id=int(callback.data)):
                price_control_for_seller = await get_price_control_by_seller_id(seller_id=int(callback.data))
                price_control_buttons = await create_price_control_keyboard(seller_id=int(callback.data))
                message_text = ''
                if price_control_for_seller:
                    message_text = (f'У Вас включена функция контроля цен на товары.'
                                    f'\nМы проверяем цены на товары каждый час. '
                                    f'Если цена на ВБ отличается от установленной Вами, то мы установим Вашу цену на товары.')
                    price_api_exist = await check_price_api_exist(seller_id=int(callback.data))
                    if not price_api_exist:
                        message_text += (f'\n\nДля работы функции необходимо загрузить отдельный '
                                         f'api-ключ для раздела "Цены и скидки" в режиме редактирования.')
                    await state.set_state(Price_control.price_control_menu)

                else:
                    message_text = (f'У Вас не включена функция контроля цен на товары'
                                    f'\nНажмите кнопку "Включить контроль цен" для включения функции.'
                                    f'\nПосле включения функции Вам понадобится загрузить отдельный '
                                    f'api-ключ для раздела "Цены и скидки" в режиме редактирования. '
                                    f'Мы пришлем Вам инструкцию как это сделать.'
                                    f'\n\nМы проверяем цены на товары каждый час.'
                                    f'\nЕсли цена на ВБ отличается от установленной Вами, то мы установим Вашу цену на товары.')
                    await state.set_state(Price_control.enable)
                await callback.message.answer(text=message_text,reply_markup=price_control_buttons.as_markup(), parse_mode=ParseMode.HTML)
            else:
                await state.clear()
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'У Вас нет доступа к функции "Контроль цен" по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Включаем функцию контроля цен
@price_control_router.callback_query(F.data == 'price_control_enable', Price_control.enable)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await callback.message.answer(text=f'Подтвердите включение функции контроля цен для {seller_title}',
                                      reply_markup=approve_keyboard, parse_mode=ParseMode.HTML)
        await state.set_state(Price_control.approve_enable)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Включаем функцию контроля цен
@price_control_router.callback_query(F.data == 'approve', Price_control.approve_enable)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await enable_price_control_function(seller_id=seller_id)
        price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
        message_text = (f'Функция контроля цен по {seller_title} включена!'
                        f'\n\nМы проверяем цены на товары каждый час.'
                        f'\nЕсли цена на ВБ отличается от установленной Вами, то мы установим Вашу цену на товары.')
        price_api_exist = await check_price_api_exist(seller_id=seller_id)
        if not price_api_exist:
            message_text += (f'\n\nДля работы функции необходимо загрузить отдельный '
                             f'api-ключ для раздела "Цены и скидки" в режиме редактирования.')
        await callback.message.answer(text=message_text,
                                      reply_markup=price_control_buttons.as_markup(), parse_mode=ParseMode.HTML)
        await state.set_state(Price_control.price_control_menu)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Выключаем функцию контроля цен
@price_control_router.callback_query(F.data == 'price_control_disable', Price_control.price_control_menu)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await callback.message.answer(text=f'Подтвердите отключение функции контроля цен для {seller_title}',
                                      reply_markup=approve_keyboard, parse_mode=ParseMode.HTML)
        await state.set_state(Price_control.approve_disable)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Включаем функцию контроля цен
@price_control_router.callback_query(F.data == 'approve', Price_control.approve_disable)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await disable_price_control_function(seller_id=seller_id)
        price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
        await callback.message.answer(text=f'Функция контроля цен по {seller_title} выключена!',
                                      reply_markup=price_control_buttons.as_markup(), parse_mode=ParseMode.HTML)
        await state.set_state(Price_control.enable)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@price_control_router.callback_query(F.data=='price_control_new_api')
async def new_api_key(callback: CallbackQuery, state: FSMContext):
        await delete_one_messages(callback.message)
        path = 'app/templates/Как выгрузить API в категории Цены.pdf'
        file_to_send = FSInputFile(filename='Как выгрузить API по категории Цены.pdf', path=path)
        await callback.message.answer_document(document=file_to_send,
                                               caption=f'Выгрузите новый ключ API по категории "Цены и скидки" из кабинета WB.'
                                                       f'\nКак это сделать смотрите в прилагаемой инструкции =>'
                                                       f'\nПосле получения нового ключа нажмите кнопку "Загрузить новый ключ API".',
                                               reply_markup=kb.price_new_api)

@price_control_router.callback_query(F.data == 'price_control_new_api_key_upload')
async def new_api_key (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Price_control.new_api_await)
    await callback.message.answer('Отправьте новый ключ API ответным сообщением.',reply_markup=kb.cancel_operation, show_alert=False)

@price_control_router.message(F.text, Price_control.new_api_await)
async def new_api_key (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(new_api_await=message.text)
    data = await state.get_data()
    new_api_key_str = data["new_api_await"]
    seller_id = int(data["seller_id"])
    await state.set_state(Price_control.price_control_menu)
    if await check_price_api(api_key=new_api_key_str):
        await new_price_api_key_upload(seller_id=seller_id,
                                       new_api_key=new_api_key_str)
        price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
        await message.answer(f'Новый API по категории "Цены и скидки" загружен.'
                             f'\n\nНажмите "Скачать шаблон с ценами", чтобы скачать весь список товаров в продаже с текущими ценами.',
                             reply_markup=price_control_buttons.as_markup(),
                             show_alert=False)
    else:
        price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
        await message.answer('Данный API-ключ уже используется. Скачайте новый API-ключ и повторите операцию',
                         reply_markup=price_control_buttons.as_markup())

# Отправляем селлеру шаблон с ценами
@price_control_router.callback_query(F.data == 'price_control_get_price_template', Price_control.price_control_menu)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await callback.message.answer(text=f'В скором времени мы пришлем Вам шаблон с ценами по всем товарам.', parse_mode=ParseMode.HTML)
        filename = f'{seller_title}_шаблон для заполнения цен.xlsx'
        status, price_template = await create_price_template_to_seller_on_demand(seller_id=seller_id)

        if status == 'done':
            price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
            file_in_io = io.BytesIO()
            price_template.save(file_in_io)
            file = file_in_io.getvalue()
            file_to_send = BufferedInputFile(file=file,filename=filename)
            message_text = (f'Направляем Вам шаблон с ценами по всем Вашим товарам.'
                            f'\n\n<b>Проверьте цены в шаблоне, при необходимости поменяйте цену, '
                            f'скидку для покупателей и скидку для WB Клуба в столбцах N,O,P (выделены зеленым цветом).</b>'
                            f'\n'
                            f'\nВышлите нам обратно скорректированный шаблон. После этого мы начнем контроллировать, чтобы цена на товар на ВБ всегда была такой.'
                            f'\nМы будем проверять цену товаров на площадке каждый час.')
            await callback.message.answer_document(caption=message_text,document=file_to_send,
                                          reply_markup=price_control_buttons.as_markup(), parse_mode=ParseMode.HTML)
            await state.set_state(Price_control.price_control_menu)
        else:
            await state.set_state(Price_control.price_control_menu)
            price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
            await callback.message.answer('Проблема с выгрузкой товаров и цен. Мы уже занимаемся этим.',
                                 reply_markup=price_control_buttons.as_markup())

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Загружаем шаблон от селлера функцию контроля цен
@price_control_router.callback_query(F.data == 'price_control_upload_price_template', Price_control.price_control_menu)
async def price_control_handler(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        await state.set_state(Price_control.price_template_upload)
        await callback.message.answer("Отправьте заполненный шаблон с ценами ответным сообщением.",
                                      reply_markup=price_template_cancel_send,
                                      parse_mode=ParseMode.HTML)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@price_control_router.message(F.document, Price_control.price_template_upload)
async def save_price_template(message:Message, state:FSMContext):
    await delete_one_messages(message)
    price_template_file_id = message.document.file_id
    data = await state.get_data()
    seller_id = int(data['seller_id'])
    try:
        price_template_file_in_io=io.BytesIO()
        price_template = await message.document.bot.download(price_template_file_id,price_template_file_in_io)
        df = pd.read_excel(price_template)
        products = df.to_dict('records')
        product_check, price_check, products_for_review, products_with_id = await get_price_template_from_seller(seller_id=seller_id,
                                                                                                                 products=products)
        # print(product_check, price_check)
        if product_check and price_check:
            price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
            await message.answer(f'Шаблон с ценами товаров загружен!'
                                 f'\nМы будем проверять цену товаров на площадке каждый час.',
                                 reply_markup=price_control_buttons.as_markup())
            await main_prices_check_function_for_seller(seller_id=seller_id)
            await state.set_state(Price_control.price_control_menu)
        elif product_check and not price_check:
            await state.update_data(price_template_product_list=products_with_id)
            await message.answer(f'Цена по следующим товарам изменилась более чем на 25%!'
                                 f'\nПроверьте цены, если все корректно, то нажмите "Подтвердить":'
                                 f'\n{products_for_review}',
                                 reply_markup=price_template_approve)
            await state.set_state(Price_control.price_template_approve)
        else:
            await message.answer("Пожалуйста, отправьте корректный заполненный шаблон с ценами.",
                                 reply_markup=price_template_cancel_send)
            await state.set_state(Price_control.price_template_upload)
    except Exception as e:
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            await message.answer("Пожалуйста, отправьте корректный заполненный шаблон с ценами.",
                                 reply_markup=price_template_cancel_send)
            await state.set_state(Price_control.price_template_upload)

@price_control_router.message(F.text, Price_control.price_template_upload)
async def price_control(message:Message, state:FSMContext):
    await delete_one_messages(message)
    await message.answer("Пожалуйста, отправьте заполненный шаблон с ценами.", reply_markup=price_template_cancel_send)
    await state.set_state(Price_control.price_template_upload)

@price_control_router.callback_query(F.data=='approve_price_template', Price_control.price_template_approve)
async def save_price_template(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    seller_id = int(data['seller_id'])
    products_with_id = data['price_template_product_list']
    try:
        if await set_new_prices_in_db(seller_id=seller_id,products_with_id=products_with_id):
            price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
            await callback.message.answer(f'Шаблон с ценами товаров загружен!'
                                 f'\nМы будем проверять цену товаров на площадке каждый час.',
                                 reply_markup=price_control_buttons.as_markup())
            await main_prices_check_function_for_seller(seller_id=seller_id)
            await state.set_state(Price_control.price_control_menu)
        else:
            price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
            await callback.message.answer("При обновлении цены возникла ошибка. Мы уже работаем над этим",
                                        reply_markup=price_control_buttons.as_markup())
            await state.set_state(Price_control.price_control_menu)
    except Exception as e:
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            await state.set_state(Price_control.price_control_menu)

@price_control_router.callback_query(F.data=='cancel_price_template', Price_control.price_template_approve)
async def save_price_template(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    seller_id = int(data['seller_id'])
    await state.update_data(price_template_product_list=[])
    try:
        price_control_buttons = await create_price_control_keyboard(seller_id=seller_id)
        await callback.message.answer(f'Операция отменена.',
                             reply_markup=price_control_buttons.as_markup())
        await state.set_state(Price_control.price_control_menu)
    except Exception as e:
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            await state.set_state(Price_control.price_control_menu)