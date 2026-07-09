import io
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import pandas as pd
import logging

from app.admin.admin_message import send_message_to_admin
from app.app_logic import run_with_semaphore
from app.checks import check_user_status, check_user_companies, check_active_subscription, \
    check_user_access_to_cost_for_user_tg_id
from app.database.requests import get_cost_template, set_new_cost_of_items, check_cost
from app.database.support_functions import delete_one_messages, \
    get_company_name_by_seller_id, check_first_cost_set_status, update_first_cost_template_status_true
from app.main_bot.cost_of_sales_keyboards import cost_of_sales_menu, get_cost_template_from_user_menu, \
    want_to_recalc_pl_for_last_week
from app.main_bot.handlers import register_company_text, register_user_text, no_active_subscription_text
from app.main_bot.keyboards import create_companies_keyboard
from app.main_bot.states import Send_cost_template_to_user, Get_cost_template_from_user
import app.main_bot.keyboards as kb
from app.managers.managers_functions import check_manager_companies
from app.reports.reporting_functions import recalculate_results_for_last_week
from app.wrappers import with_session

cost_of_sales_router = Router()

# Себестоимость товаров
@cost_of_sales_router.message(F.text == '📦 Себестоимость товаров')
async def cost_of_sales (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id) or await check_manager_companies(tg_id=message.from_user.id):
            try:
                await message.answer("Выберите пункт меню",
                                     reply_markup=cost_of_sales_menu)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))


@cost_of_sales_router.callback_query(F.data == 'send_cost_of_goods_template_to_user')
async def cost_of_sales (callback: CallbackQuery,state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.set_state(Send_cost_template_to_user.seller_id)
        companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
        await callback.message.answer("Выберите компанию, по которой хотите скачать шаблон:",
                             reply_markup=companies_list_buttons.as_markup())
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.callback_query(F.data, Send_cost_template_to_user.seller_id)
async def get_cost_file(callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_cost_for_user_tg_id(seller_id=int(callback.data),user_tg_id=int(callback.from_user.id)):
            await state.update_data(seller_id=int(callback.data))
            data = await state.get_data()
            seller_id = int(data["seller_id"])
            if await check_active_subscription(seller_id=seller_id):
                caption = f'Направляем шаблон с себестоимостью товаров'
                await get_cost_template(seller_id=seller_id, requestor_tg_id=int(callback.from_user.id), caption=caption)
                await callback.message.answer(f'Для загрузки заполненного шаблона нажмите кнопку '
                                              f'"Загрузить шаблон с себестоимостью товаров".'
                                              f'\n\nЭто можно сделать позже, '
                                              f'для этого зайдите в раздел "Себестоимость товаров" '
                                              f'главного меню и нажмите кнопку "Загрузить шаблон с себестоимостью товаров"',
                                              reply_markup=get_cost_template_from_user_menu)
            else:
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'У Вас нет доступа к себестоимости товаров по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
        await state.clear()
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.callback_query(F.data =='get_cost_of_goods_template_from_user')
async def get_cost_file(callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.set_state(Get_cost_template_from_user.seller_id)
        companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
        await callback.message.answer("Выберите компанию, по которой загружаете шаблон:",
                             reply_markup=companies_list_buttons.as_markup())
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.message(F.text == 'Загрузить шаблон с себестоимостью')
async def select_company (message: Message,state:FSMContext):
    await delete_one_messages(message)
    try:
        await state.set_state(Get_cost_template_from_user.seller_id)
        companies_list_buttons = await create_companies_keyboard(tg_id=message.from_user.id)
        await message.answer("Выберите компанию, по которой загружаете шаблон:",
                             reply_markup=companies_list_buttons.as_markup())
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.callback_query(F.data, Get_cost_template_from_user.seller_id)
async def get_cost_file (callback: CallbackQuery,state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_cost_for_user_tg_id(seller_id=int(callback.data),
                                                          user_tg_id=int(callback.from_user.id)):
            await state.update_data(seller_id=int(callback.data))
            await state.update_data(requestor_tg_id=int(callback.from_user.id))

            if await check_active_subscription(seller_id=int(callback.data)):
                await state.set_state(Get_cost_template_from_user.cost_file)
                await callback.message.answer("Отправьте заполненный шаблон с себестоимостью ответным сообщением.", reply_markup=kb.cost_file_cancel_send)
            else:
                await state.clear()
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'У Вас нет доступа к себестоимости товаров по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.message(F.document, Get_cost_template_from_user.cost_file)
async def save_cost_file(message:Message, state:FSMContext):
    try:
        await delete_one_messages(message)
        cost_file_id = message.document.file_id
        template_downloaded = False
        seller_id=""
        cost_file_in_io=io.BytesIO()
        cost_file = await message.document.bot.download(cost_file_id,cost_file_in_io)
        df = pd.read_excel(cost_file)
        cost_new = df.to_dict('records')
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        requestor_tg_id = int(data['requestor_tg_id'])
        try:
            result = await set_new_cost_of_items(seller_id=seller_id, costs_new=cost_new, requestor_tg_id = requestor_tg_id)
            if result:
                await message.answer("Шаблон с себестоимостью товаров загружен!", reply_markup=kb.main_kb(message.from_user.id))
                logging.info(f'Seller_id: {seller_id}. Новый шаблон с себестоимостью успешно загружен')
                template_downloaded = True
                # Если шаблон загружен нормально то отправляем в приложение сигнал, что загружен новый шаблон и запускаем следующую функцию:
                if template_downloaded:
                    await new_cost_template_downloaded(bot=message.bot, seller_id=seller_id, state=state)
        except ValueError as e:
            await message.answer(f'В шаблоне имеются ошибки: {str(e)}.'
                                 f'\nПожалуйста, отправьте корректный заполненный шаблон с себестоимостью.',
                                 reply_markup=kb.cost_file_cancel_send)
            logging.info(f'Seller_id: {seller_id}. Шаблон с себестоимостью не загружен - в шаблоне есть ошибки')
            await send_message_to_admin(f"Seller_id: {seller_id}. Ошибка валидации шаблона с себестоимостью: {str(e)}")
            logging.error(f"Validation error: {str(e)}")
            return
    except:
        try:
            await message.delete()
        except Exception as e:
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
        await message.answer("Пожалуйста, отправьте корректный заполненный шаблон с себестоимостью.",reply_markup=kb.cost_file_cancel_send)
        await state.set_state(Get_cost_template_from_user.cost_file)


# Загружен новый шаблон с себестоимостью, проверяем первая загрузка или нет:
@with_session
async def new_cost_template_downloaded(session, bot, seller_id: int, state):
    if await check_cost(session=session, seller_id=seller_id):
        if await check_first_cost_set_status(session=session, seller_id=seller_id):
            # Здесь делаем действия, если шаблон не первый
            # Спрашиваем, хочет ли П пересчитать результаты за прошлую неделю?
            data = await state.get_data()
            chat_id = data['requestor_tg_id']
            await bot.send_message(chat_id=chat_id, text=f'Хотите пересчитать финансовые результаты '
                                                         f'за прошедшую неделю по новой себестоимости?',
                                   reply_markup=want_to_recalc_pl_for_last_week)
        else:
            # Здесь действия при первой загрузке шаблона:
            # Обновляем статус, что первый шаблон загружен
            await state.clear()
            await update_first_cost_template_status_true(session=session, seller_id=seller_id)
            # здесь запускаем продолжение первого расчета PL и отправку отчетов:
            await run_with_semaphore(seller_id=seller_id)
    else:pass

@cost_of_sales_router.message(F.text, Get_cost_template_from_user.cost_file)
async def save_cost_file(message:Message, state:FSMContext):
    await delete_one_messages(message)
    await message.answer("Пожалуйста, отправьте заполненный шаблон с себестоимостью.", reply_markup=kb.cost_file_cancel_send)
    await state.set_state(Get_cost_template_from_user.cost_file)

@cost_of_sales_router.callback_query(F.data == 'recalc_last_week_with_new_costs_of_goods')
async def recalc (callback: CallbackQuery,state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    seller_id = int(data['seller_id'])
    try:
        await state.clear()
        await callback.message.answer("В скором времени мы пришлем Вам обновленный отчет за прошедшую неделю",
                             reply_markup=kb.main_kb(callback.from_user.id))
        await recalculate_results_for_last_week(seller_id=seller_id,recalc_bool=True)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@cost_of_sales_router.callback_query(F.data == 'do_not_recalc_last_week_with_new_costs_of_goods')
async def not_recalc (callback: CallbackQuery,state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    seller_id = int(data['seller_id'])
    try:
        await state.clear()
        await recalculate_results_for_last_week(seller_id=seller_id,recalc_bool=False)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)