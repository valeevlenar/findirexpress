from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import logging

from app.admin.admin_message import send_message_to_admin
from app.checks import check_user_status, check_user_companies, check_active_subscription, \
    check_user_access_to_managers_for_user_tg_id
from app.database.support_functions import delete_one_messages, get_company_name_by_seller_id, get_user_by_tg_id
from app.main_bot.handlers import register_company_text, register_user_text, no_active_subscription_text
from app.main_bot.keyboards import create_companies_keyboard
import app.main_bot.keyboards as kb
from app.managers.managers_functions import generate_managers_invite_link, create_my_managers_list, get_managers_list, \
    get_manager_name_by_manager_id, delete_manager_from_db, get_access_settings_for_manager_id, \
    update_access_settings_for_manager_id
from app.managers.managers_keyboard import managers_main_keyboard, create_managers_keyboard, managers_approve, \
    create_managers_access_settings_keyboard
from app.managers.managers_states import Managers_addition, Managers_deletion, Managers_change_access_settings

managers_router = Router()

# Контроль цен
@managers_router.message(F.text == '👨‍💼 Менеджеры')
async def managers_main (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id):
            try:
                await message.answer("Выберите пункт меню:",
                                              reply_markup=managers_main_keyboard)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))

@managers_router.callback_query(F.data == 'add_manager')
async def managers_main (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.clear()
    if await check_user_status(tg_id=callback.from_user.id):
        if await check_user_companies(tg_id=callback.from_user.id):
            try:
                companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
                await state.set_state(Managers_addition.access_settings)
                await callback.message.answer("Выберите компанию, по которой хотите добавить менеджера:",
                                              reply_markup=companies_list_buttons.as_markup())
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await callback.message.answer(register_company_text, reply_markup=kb.main_kb(callback.message.from_user.id))
    else:await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.message.from_user.id))

@managers_router.callback_query(F.data, Managers_addition.access_settings)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_managers_for_user_tg_id(seller_id=int(callback.data),
                                                              user_tg_id=int(callback.from_user.id)):
            await state.update_data(seller_id = callback.data)
            access_settings = {'api_access': False,
                               'cost_access': False,
                               'price_control_access': False}
            await state.update_data(access_settings=access_settings)
            if await check_active_subscription(seller_id=int(callback.data)):
                await state.set_state(Managers_addition.access_settings_update)
                message_text = (f'Настройка роли менеджера!'
                                f'\nПо умолчанию все менеджеры получают доступ к отчетам и подпискам.'
                                f'\nВы можете отдельно по каждому менеджеру настроить доступ к обновлению себестоимости, '
                                f'api-ключей, и доступ к функции "Контроль цен".'
                                f'\n'
                                f'\nВыберите соответствующие настройки ниже и затем нажмите кнопку "Сохранить настройки"')
                manager_access_setting_buttons = await create_managers_access_settings_keyboard(manager_id=None,
                                                                                                access_settings=access_settings)
                await callback.message.answer(text=message_text, reply_markup=manager_access_setting_buttons.as_markup(),
                                              parse_mode=ParseMode.HTML)

            else:
                await state.clear()
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'Вы не можете добавлять менеджеров по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data=='save_access_settings', Managers_addition.access_settings_update)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        user_id = int(await get_user_by_tg_id(tg_id=callback.from_user.id))
        # print("user_id", user_id)
        data = await state.get_data()
        access_settings = data['access_settings']
        seller_id = int(data['seller_id'])
        invite_link = await generate_managers_invite_link(seller_id=seller_id,
                                                          user_id=user_id,
                                                          access_settings=access_settings)
        await state.clear()
        message_text = (f'Направляем Вам ссылку для добавления менеджера, '
                        f'перешлите ее менеджеру, которому хотите дать доступ к сервису.'
                        f'\n'
                        f'\n{invite_link}'
                        f'\n'
                        f'\nСсылка действует только 24 часа.'
                        f'\nМы пришлем Вам уведомление, когда менеджер пройдет по ссылке и получит доступ.')
        await callback.message.answer(text=message_text, reply_markup=managers_main_keyboard,
                                      parse_mode=ParseMode.HTML)

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data, Managers_addition.access_settings_update)
async def managers_main(callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        access_settings = data['access_settings']
        # print(access_settings)
        if callback.data == 'api_access_switch':
            if access_settings['api_access']:
                access_settings['api_access'] = False
            else:
                access_settings['api_access'] = True

        elif callback.data == 'cost_access_switch':
            if access_settings['cost_access']:
                access_settings['cost_access'] = False
            else:
                access_settings['cost_access'] = True

        elif callback.data == 'price_control_access_switch':
            if access_settings['price_control_access']:
                access_settings['price_control_access'] = False
            else:
                access_settings['price_control_access'] = True
        await state.update_data(access_settings=access_settings)
        await state.set_state(Managers_addition.access_settings_update)
        message_text = (f'Настройка роли менеджера!'
                        f'\nПо умолчанию все менеджеры получают доступ к отчетам и подпискам.'
                        f'\nВы можете отдельно по каждому менеджеру настроить доступ к обновлению себестоимости, '
                        f'api-ключей, и доступ к функции "Контроль цен".'
                        f'\n'
                        f'\nВыберите соответствующие настройки ниже и затем нажмите кнопку "Сохранить настройки"')
        manager_access_setting_buttons = await create_managers_access_settings_keyboard(manager_id=None,
                                                                                        access_settings=access_settings)
        await callback.message.answer(text=message_text, reply_markup=manager_access_setting_buttons.as_markup(),
                                      parse_mode=ParseMode.HTML)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data == 'my_managers')
async def balance_and_subscriptions(callback:CallbackQuery):
    await delete_one_messages(callback.message)
    try:
        my_managers_str = await create_my_managers_list(user_tg_id=int(callback.from_user.id))
        await callback.message.answer(f'Ваши менеджеры по компаниям:'
                                      f'\n{my_managers_str}',
                                      reply_markup=managers_main_keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        await send_message_to_admin(f'Ошибка при создании списка менеджеров'
                                    f'\nUser_tg_id: {callback.from_user.id}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data == 'delete_manager')
async def managers_deletion (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.clear()
    if await check_user_status(tg_id=callback.from_user.id):
        if await check_user_companies(tg_id=callback.from_user.id):
            try:
                companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
                await state.set_state(Managers_deletion.company_name)
                await callback.message.answer("Выберите компанию, по которой хотите удалить менеджера:",
                                              reply_markup=companies_list_buttons.as_markup())
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await callback.message.answer(register_company_text, reply_markup=kb.main_kb(callback.message.from_user.id))
    else:await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.message.from_user.id))

@managers_router.callback_query(F.data, Managers_deletion.company_name)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_managers_for_user_tg_id(seller_id=int(callback.data),
                                                              user_tg_id=int(callback.from_user.id)):
            seller_id = int(callback.data)
            await state.update_data(seller_id = seller_id)
            if await check_active_subscription(seller_id=seller_id):
                managers_list_buttons = await create_managers_keyboard(seller_id)
                managers_list = await get_managers_list(seller_id=seller_id)
                if managers_list:
                    await state.set_state(Managers_deletion.manager_id)
                    await callback.message.answer("Выберите менеджера, которого хотите удалить:",
                                                  reply_markup=managers_list_buttons.as_markup())
                else:
                    await state.clear()
                    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
                    await callback.message.answer(f'У Вас нет назначенных менеджеров в компании {seller_title}.',
                                                  reply_markup=managers_main_keyboard)
            else:
                await state.clear()
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'Вы не можете удалять менеджеров по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data, Managers_deletion.manager_id)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.update_data(manager_id = int(callback.data))
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        manager_id = int(callback.data)
        manager_user_name = await get_manager_name_by_manager_id(manager_id = manager_id)
        await state.set_state(Managers_deletion.approve_manager_deletion)
        await callback.message.answer(f'Подтвердите удаление менеджера:'
                                      f'\nКомпания: {seller_title}'
                                      f'\nМенеджер: {manager_user_name}',
                                      reply_markup=managers_approve)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data, Managers_deletion.approve_manager_deletion)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        manager_id = int(data['manager_id'])
        manager_user_name = await get_manager_name_by_manager_id(manager_id=manager_id)
        if await delete_manager_from_db(manager_id=manager_id):
            await state.clear()
            await callback.message.answer(f'{manager_user_name} удален из списка менеджеров компании {seller_title}.',
                                          reply_markup=managers_main_keyboard)

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data == 'manager_access_settings')
async def managers_main (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.clear()
    if await check_user_status(tg_id=callback.from_user.id):
        if await check_user_companies(tg_id=callback.from_user.id):
            try:
                companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
                await state.set_state(Managers_change_access_settings.seller_id)
                await callback.message.answer("Выберите компанию, по которой хотите изменить настройки доступа менеджера:",
                                              reply_markup=companies_list_buttons.as_markup())
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await callback.message.answer(register_company_text, reply_markup=kb.main_kb(callback.message.from_user.id))
    else:await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.message.from_user.id))

@managers_router.callback_query(F.data, Managers_change_access_settings.seller_id)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        if await check_user_access_to_managers_for_user_tg_id(seller_id=int(callback.data),
                                                              user_tg_id=int(callback.from_user.id)):
            seller_id = int(callback.data)
            await state.update_data(seller_id = seller_id)
            if await check_active_subscription(seller_id=seller_id):
                managers_list_buttons = await create_managers_keyboard(seller_id)
                managers_list = await get_managers_list(seller_id=seller_id)
                if managers_list:
                    await state.set_state(Managers_change_access_settings.manager_id)
                    await callback.message.answer("Выберите менеджера, по которому хотите изменить настройки доступа:",
                                                  reply_markup=managers_list_buttons.as_markup())
                else:
                    await state.clear()
                    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
                    await callback.message.answer(f'У Вас нет назначенных менеджеров в компании {seller_title}.',
                                                  reply_markup=managers_main_keyboard)
            else:
                await state.clear()
                await callback.message.answer(no_active_subscription_text,
                                              reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'Вы не можете менять настройки доступа менеджеров по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data, Managers_change_access_settings.manager_id)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.update_data(manager_id=int(callback.data))
        access_settings = await get_access_settings_for_manager_id(manager_id=int(callback.data))
        await state.update_data(access_settings=access_settings)
        data = await state.get_data()
        seller_id = data['seller_id']
        if await check_active_subscription(seller_id=seller_id):
            await state.set_state(Managers_change_access_settings.access_settings_update)
            message_text = (f'Настройка роли менеджера!'
                            f'\nПо умолчанию все менеджеры получают доступ к отчетам и подпискам.'
                            f'\nВы можете отдельно по каждому менеджеру настроить доступ к обновлению себестоимости, '
                            f'api-ключей, и доступ к функции "Контроль цен".'
                            f'\n'
                            f'\nВыберите соответствующие настройки ниже и затем нажмите кнопку "Сохранить настройки"')
            manager_access_setting_buttons = await create_managers_access_settings_keyboard(manager_id=int(callback.data),
                                                                                            access_settings=access_settings)
            await callback.message.answer(text=message_text, reply_markup=manager_access_setting_buttons.as_markup(),
                                          parse_mode=ParseMode.HTML)

        else:

            await state.clear()
            await callback.message.answer(no_active_subscription_text,
                                          reply_markup=kb.main_kb(callback.message.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data=='save_access_settings', Managers_change_access_settings.access_settings_update)
async def managers_main(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        access_settings: dict = dict(data['access_settings'])
        seller_id = data['seller_id']
        manager_id = data['manager_id']
        await update_access_settings_for_manager_id(seller_id=seller_id,
                                                    manager_id=manager_id,
                                                    granted_by_user_tg_id=(int(callback.from_user.id)),
                                                    access_settings=access_settings)
        await state.clear()
        message_text = f'Настройки доступа менеджера сохранены.'
        await callback.message.answer(text=message_text, reply_markup=managers_main_keyboard,
                                      parse_mode=ParseMode.HTML)

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@managers_router.callback_query(F.data, Managers_change_access_settings.access_settings_update)
async def managers_main(callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        access_settings: dict = dict(data['access_settings'])

        if callback.data == 'api_access_switch':
            if access_settings['api_access']:
                access_settings['api_access'] = False
            else:
                access_settings['api_access'] = True

        elif callback.data == 'cost_access_switch':
            if access_settings['cost_access']:
                access_settings['cost_access'] = False
            else:
                access_settings['cost_access'] = True

        elif callback.data == 'price_control_access_switch':
            if access_settings['price_control_access']:
                access_settings['price_control_access'] = False
            else:
                access_settings['price_control_access'] = True
        await state.update_data(access_settings=access_settings)
        await state.set_state(Managers_change_access_settings.access_settings_update)
        message_text = (f'Настройка роли менеджера!'
                        f'\nПо умолчанию все менеджеры получают доступ к отчетам и подпискам.'
                        f'\nВы можете отдельно по каждому менеджеру настроить доступ к обновлению себестоимости, '
                        f'api-ключей, и доступ к функции "Контроль цен".'
                        f'\n'
                        f'\nВыберите соответствующие настройки ниже и затем нажмите кнопку "Сохранить настройки"')
        manager_access_setting_buttons = await create_managers_access_settings_keyboard(manager_id=None,
                                                                                        access_settings=access_settings)
        await callback.message.answer(text=message_text, reply_markup=manager_access_setting_buttons.as_markup(),
                                      parse_mode=ParseMode.HTML)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
