import logging
import asyncio
import io
from datetime import timedelta, datetime
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
import pandas as pd
import app.main_bot.keyboards as kb
import app.database.requests as rq
import config
from app.admin.admin_message import send_message_to_admin
from app.admin.promo_admin_functions import check_promocode_dates_and_usage, check_promocode_budget
from app.app_logic import run_with_semaphore
from app.reports.reporting_functions import recalculate_results_for_last_week
from app.checks import check_user, check_company, check_api, check_user_companies, check_user_status, \
    check_active_subscription, check_active_promocode, check_user_access_to_api_for_user_tg_id, \
    check_user_access_to_cost_for_user_tg_id
from app.database.api_functions import new_api_key_upload
from app.database.requests import check_cost, get_cost_template, set_new_cost_of_items, \
    set_company
from app.database.support_functions import delete_company_from_database, \
    check_first_cost_set_status, \
    update_first_cost_template_status_true, delete_one_messages, delete_two_messages, \
    get_company_name_by_seller_id
from app.main_bot.keyboards import create_companies_keyboard, cancel_operation, \
    create_subscription_keyboard, faq_menu
from app.main_bot.main_handler_functions import create_my_companies_str, create_my_subscriptions_str
from app.main_bot.states import Register_user, Register_company, Send_cost_template_to_user, \
    Get_cost_template_from_user, Delete_company, New_api_key, Support_ticket, New_subscription, \
    Register_manager_user
from app.managers.managers_functions import process_managers_invite_token, \
    check_manager_access_exist_for_manager_user_tg_id, check_manager_companies
from app.promocodes.promocodes_functions import get_discount_amount_for_promocode
from app.referrals.referrals import create_referral_channel_for_user, track_referral_entrance
from app.subscriptions.subscription_types import get_subscription_name_by_subscription_type, \
    get_subscription_price_by_subscription_type
from app.subscriptions.subscriptions_functions import new_subscription_with_invoice, new_trial_subscription
from app.support.support_bot_functions import new_support_ticket_registration
from app.wrappers import log_and_notify_admin, with_session

router = Router()

register_user_text=(f'Вы еще не зарегистрированы. '
                            f'\nДля работы с сервисом зайдите в раздел "Профиль" и нажмите "Зарегистрироваться".'
                            f'\nПосле регистрации в качестве пользователя нужно добавить компанию. '
                    f'Для этого в разделе "Профиль" выберите пункт "Добавить компанию".')
register_company_text=(f'Вы еще не добавили ни одну компанию. '
                               f'\nДля работы с сервисом зайдите в раздел "Профиль" и выберите пункт "Добавить компанию".')
no_active_subscription_text=(f'У компании отсутвует действующая подписка.'
                             f'\n\nДля работы с сервисом зайдите в раздел "Подписка на сервис" и оформите новую подписку.')

@router.message(Command('start'))
async def start (message: Message, command: CommandObject, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    try:
        token = command.args
        if token and token.startswith('invite_'):
            invite_token = token.split('_')[1]
            user_tg_id = int(message.from_user.id)

            seller_id, token_process_result = await process_managers_invite_token(user_tg_id=user_tg_id,
                                                                                  invite_token=invite_token)
            if token_process_result == 'owner':
                await message.answer(f'Вы не можете сами воспользоваться этой ссылкой.'
                                     f'\nВыберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))

            elif token_process_result == 'already_access_granted':
                seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
                await message.answer(f'Вы уже являетесь менеджером компании {seller_title}.'
                               f'\nВыберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))

            elif token_process_result == 'access_granted':
                seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
                await message.answer(f'Привет! Вы стали менеджером компании {seller_title}!'
                               f'\nВыберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))

            elif token_process_result == 'no_user':
                await state.update_data(token = str(invite_token))
                await state.set_state(Register_manager_user.user_name)
                await message.answer(f'Привет! Для добавления в качестве менеджера Вам необходимо зарегистрироваться как пользователь.'
                                     f'\nВведите Ваше ФИО в формате "Иванов Иван Иванович"...',
                                     reply_markup=kb.main_kb(message.from_user.id))
            elif token_process_result == 'invalid_token':
                await message.answer(
                    f'Привет! Ссылка недействительна или истек срок ее действия.',
                    reply_markup=kb.main_kb(message.from_user.id))
        elif token:
            await track_referral_entrance(referral_code=token,user_tg_id=message.from_user.id)
            await message.answer('Привет! Добро пожаловать в наш сервис! '
                                 'Выберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))
        else:
            await message.answer('Привет! Добро пожаловать в наш сервис! '
                                 'Выберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Невозможно отследить реферальный код'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


@router.message(F.text, Register_manager_user.user_name)
async def register_user_name(message:Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(user_name=message.text)
    await state.set_state(Register_manager_user.user_phone_number)
    await message.answer('Введите Ваш номер телефона в формате "+79876543210"...')

@router.message(F.text, Register_manager_user.user_phone_number)
async def register_user_phone_number (message:Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(user_phone_number=message.text)
    data = await state.get_data()
    await state.set_state(Register_manager_user.approve)
    await message.answer(f'Ваше ФИО: {data["user_name"]}'
                         f'\nВаш номер телефона: {data["user_phone_number"]}'
                         f'\nВаш телеграмм: @{message.from_user.username}'
                         f'\nНажимая "Подтвердить" Вы подтверждаете '
                         f'корректность данных и соглашаетесь с условиями '
                         f'публичной оферты, размещенной на сайте =>'
                         f'\n "https://финдирэкспресс.рф/agreement"',reply_markup=kb.user_registration_approve)

@router.callback_query(F.data == 'user_approve_registration', Register_manager_user.approve)
async def user_approve_registration (callback: CallbackQuery, state:FSMContext):
    try:
        await delete_one_messages(callback.message)
        data = await state.get_data()
        await rq.set_user(data=data,
                          tg_id=callback.from_user.id,
                          username=callback.from_user.username)
        seller_id, token_process_result = await process_managers_invite_token(invite_token=data['token'],
                                                                              user_tg_id=int(callback.from_user.id))
        await state.clear()
        if token_process_result == 'access_granted':
            seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
            await callback.message.answer(f'Поздравляем! Вы зарегистрированы как пользователь!'
                                          f'\nВы стали менеджером компании {seller_title}!'
                                          f'\nВыберите пункт меню...', reply_markup=kb.main_kb(callback.message.from_user.id))
        else:
            await send_message_to_admin(f'Что-то пошло не так при добавлении нового пользователя - менеджера')
    except Exception as e:
        await send_message_to_admin(f'Что-то пошло не так при добавлении нового пользователя - менеджера'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@router.callback_query(F.data == 'back_to_main_menu')
async def back_to_main_menu (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.clear()
    await callback.message.answer(f'Главное меню:', reply_markup=kb.main_kb(callback.from_user.id))

@router.callback_query(F.data == 'cancel')
async def back_to_main_menu (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.clear()
    await callback.message.answer(f'Операция отменена.\nГлавное меню:', reply_markup=kb.main_kb(callback.from_user.id))

@router.message(F.text == '⚙️ Admin menu')
async def admin_menu (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("У вас нет прав доступа к этому разделу меню!", reply_markup=kb.main_kb(message.from_user.id))
    elif message.from_user.id == config.ADMIN_ID:
        await message.answer("Выберите пункт меню:", reply_markup=kb.admin_menu)


@router.message(F.text == '🧮 Посмотреть примеры отчетов')
async def examples (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    path1 = config.templates_path + 'ООО_Пример_еженедельный_отчет.xlsx'
    file_to_send = FSInputFile(filename='ООО_Пример_еженедельный_отчет.xlsx', path=path1)
    await message.answer_document(document=file_to_send)
    path2 = config.templates_path + 'ООО_Пример_месячный отчет.xlsx'
    file_to_send = FSInputFile(filename='ООО_Пример_месячный отчет.xlsx',path=path2)
    await message.answer_document(document=file_to_send)
    await message.answer(text=f'Ознакомьтесь с примерами отчетов в прилагаемых файлах.'
                              f'\n\n🔝 Такие отчеты вы будете получать за каждую неделю и за каждый месяц.'
                              f'\n🔼 Зарегистрируйтесь и получите бесплатную подписку на 7 дней и первый комплект отчетов бесплатно!',
                         reply_markup=kb.main_kb(message.from_user.id))

@router.message(F.text == '💵 Тарифы')
async def examples (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    path = config.templates_path + 'tariffs.jpg'
    photo = FSInputFile(filename='photo', path=path)
    await message.answer_photo(photo)
    await message.answer(text=f'У нас единый тариф, который включает в себя абсолютно все функции. '
                              f'\nНе зависит от количества СКЮ и количества операций за месяц. '
                              f'\nРазличия только в сроках подписки. '
                              f'На более длинные подписки цена меньше.'
                              f''
                              f'\n\nСервис также автоматически следит за сроками подписки '
                              f'и заблаговременно уведомит вас, когда нужно будет продлить подписку.'
                              ,
                         reply_markup=kb.main_kb(message.from_user.id))

@router.message(F.text == '🌟 Реферальная программа')
async def referral_program (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        await message.answer(text=f'Для участия в реферальной программе создайте собственную реферальную ссылку.'
                                  f'\n\nОтправляйте эту ссылку друзьям, знакомым и коллегам!'
                                  f'\nЗа каждого нового клиента и Вы, и тот, кого Вы приведете получите бонус:'
                                  f'\n1 месяц бесплатной подписки! (для 1 компании)'
                                  ,
                             reply_markup=kb.referral_program)
    else:
        await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))

@router.callback_query(F.data == 'get_referral_link')
async def referral_program (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    try:
        user_tg_id = callback.from_user.id
        username = callback.from_user.username
        referral_link = await create_referral_channel_for_user(user_tg_id=user_tg_id,
                                                               username=username)
        await callback.message.answer(text=f'Ваша реферальная ссылка: '
                                           f'\n{referral_link}')
        await callback.message.answer(text=f'Отправляйте эту ссылку друзьям, знакомым и коллегам!'
                              f'\n\nЗа каждого нового клиента и Вы, и тот, кого Вы приведете получите бонус:'
                                           f'\n1 месяц бесплатной подписки! (для 1 компании)'
                              ,
                         reply_markup=kb.main_kb(callback.message.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при создании реферальной ссылки для юзера.'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@router.message(F.text == '👨🏼‍💼 Профиль')
async def main_menu (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    await message.answer("Выберите пункт меню:", reply_markup=kb.profile_menu)

@router.callback_query(F.data == 'my_companies')
async def my_companies (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    if await check_user_status(tg_id=callback.from_user.id):
        if await check_user_companies(tg_id=callback.from_user.id) or await check_manager_access_exist_for_manager_user_tg_id(user_tg_id=callback.from_user.id):
            try:
                my_companies_str = await create_my_companies_str(callback.from_user.id)
                await callback.message.answer(text=my_companies_str,
                                              reply_markup=kb.main_kb(callback.from_user.id))
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await callback.message.answer(register_company_text, reply_markup=kb.main_kb(callback.from_user.id))
    else:await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.from_user.id))

@router.callback_query(F.data == 'delete_company')
async def delete_company (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if await check_user_status(tg_id=callback.from_user.id):
        if await check_user_companies(tg_id=callback.from_user.id) or await check_manager_companies(tg_id=callback.from_user.id):
            try:
                if await check_user_companies(tg_id=callback.from_user.id):
                    companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
                    if companies_list_buttons:
                        await state.set_state(Delete_company.select_company)
                        await callback.message.answer("Выберите компанию, которую хотите удалить:",reply_markup=companies_list_buttons.as_markup())
                else:
                    await state.clear()
                    await callback.message.answer("У Вас нет компаний, которые Вы можете удалить.",
                                                  reply_markup=kb.main_kb(callback.from_user.id))
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await callback.message.answer(register_company_text, reply_markup=kb.main_kb(callback.from_user.id))
    else:await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.from_user.id))

@router.callback_query(F.data, Delete_company.select_company)
async def delete_company_confirmation (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(user_tg_id=callback.from_user.id)
    await state.update_data(seller_id=int(callback.data))
    await state.set_state(Delete_company.delete_company_confirmation)
    company_name = await get_company_name_by_seller_id(seller_id=int(callback.data))
    await callback.message.answer(f'Подтвердите удаление компании {company_name}', reply_markup=kb.company_deletion)

@router.callback_query(F.data == 'delete', Delete_company.delete_company_confirmation)
async def delete_company (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data=await state.get_data()
        print(data["seller_id"])
        company_name = await get_company_name_by_seller_id(seller_id=int(data["seller_id"]))
        await delete_company_from_database(tg_id=data["user_tg_id"],seller_id=int(data["seller_id"]))
        await state.clear()
        await callback.message.answer(f'Компания {company_name} удалена и больше не обслуживается', reply_markup=kb.main_kb(callback.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@router.callback_query(F.data == 'add_user')
async def add_user (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if await check_user(tg_id=callback.from_user.id):
        await state.set_state(Register_user.user_name)
        await callback.message.answer('Привет! Мы очень рады, что Вы решили воспользоваться нашим сервисом! '
                         'Для того, чтобы начать получать отчеты мы зарегистрируем Вас как пользователя и добавим данные по Вашей Компании. '
                         '\nВведите Ваше ФИО в формате "Иванов Иван Иванович"...')
    else: await callback.message.answer('Вы уже зарегистрированы. Выберите пункт меню...', reply_markup=kb.main_kb(callback.from_user.id))

@router.message(Register_user.user_name)
async def register_user_name(message:Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(user_name=message.text)
    await state.set_state(Register_user.user_phone_number)
    await message.answer('Введите Ваш номер телефона в формате "+79876543210"...')

@router.message(Register_user.user_phone_number)
async def register_user_phone_number (message:Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(user_phone_number=message.text)
    data = await state.get_data()
    await message.answer(f'Ваше ФИО: {data["user_name"]}'
                         f'\nВаш номер телефона: {data["user_phone_number"]}'
                         f'\nВаш телеграмм: @{message.from_user.username}'
                         f'\nНажимая "Подтвердить" Вы подтверждаете '
                         f'корректность данных и соглашаетесь с условиями '
                         f'публичной оферты, размещенной на сайте =>'
                         f'\n "https://финдирэкспресс.рф/agreement"',reply_markup=kb.user_registration_approve)

@router.callback_query(F.data == 'user_approve_registration')
async def user_approve_registration (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    await rq.set_user(data=data,
                      tg_id=callback.from_user.id,
                      username=callback.from_user.username)
    await state.clear()
    await callback.message.answer('Поздравляем! Вы зарегистрированы как пользователь! '
                                      'Зайдите в "Главное меню " и нажмите "Добавить компанию" ')

@router.message(Command('help'))
async def cmd_help (message: Message):
    await delete_one_messages(message)
    await message.answer("У тебя все получится!!!")

@router.message(F.text == '🔑 API')
async def main_menu (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id) or await check_manager_companies(tg_id=message.from_user.id):
            try:
                companies_list_buttons = await create_companies_keyboard(tg_id=message.from_user.id)
                await state.set_state(New_api_key.select_company)
                await message.answer("Выберите компанию, по которой хотите загрузить новый API ключ:",reply_markup=companies_list_buttons.as_markup())
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))

@router.callback_query(F.data, New_api_key.select_company)
async def new_api_key(callback: CallbackQuery, state: FSMContext):
        await delete_one_messages(callback.message)
        if await check_user_access_to_api_for_user_tg_id(seller_id=int(callback.data),user_tg_id=int(callback.from_user.id)):
            await state.update_data(seller_id=int(callback.data))
            await state.set_state(New_api_key.new_api_await)
            path = config.templates_path + 'Как выгрузить API.pdf'
            file_to_send = FSInputFile(filename='Как выгрузить API.pdf', path=path)
            await callback.message.answer_document(document=file_to_send,
                                                   caption=f'Выгрузите новый ключ API из кабинета WB.'
                                                           f'\nКак это сделать смотрите в прилагаемой инструкции =>'
                                                           f'\nПосле получения нового ключа нажмите кнопку "Загрузить новый ключ API".',
                                                   reply_markup=kb.new_api)
        else:
            seller_title = await get_company_name_by_seller_id(seller_id=int(callback.data))
            await state.clear()
            await callback.message.answer(text=f'У Вас нет доступа к api по {seller_title}.',
                                          reply_markup=kb.main_kb(callback.from_user.id))

@router.callback_query(F.data == 'new_api_key')
async def new_api_key (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(New_api_key.new_api_await)
    await callback.message.answer('Отправьте новый ключ API ответным сообщением.',reply_markup=kb.cancel_operation, show_alert=False)

@router.message(F.text, New_api_key.new_api_await)
async def new_api_key (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(new_api_await=message.text)
    data = await state.get_data()
    new_api_key_str = data["new_api_await"]
    seller_id = int(data["seller_id"])
    if await check_api(api_key=new_api_key_str):
        await new_api_key_upload(seller_id=seller_id, new_api_key=new_api_key_str)
        await state.clear()
        await message.answer('Новый API ключ загружен.', reply_markup=kb.main_kb(message.from_user.id),
                             show_alert=False)
    else:
        await state.clear()
        await message.answer('Данный API-ключ уже используется. Скачайте новый API-ключ и повторите операцию',
                         reply_markup=kb.main_kb(message.from_user.id))



@router.callback_query(F.data == 'add_company')
async def add_company (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if await check_user_status(tg_id=callback.from_user.id):
        await state.set_state(Register_company.company_name)
        await callback.message.answer('Введите название юр. лица/ИП в формате ООО "Продажник" '
                                      'или ИП Иванов Петр Сергеевич',reply_markup=kb.cancel_operation, show_alert=False)
    else:
        await callback.message.answer(register_user_text, reply_markup=kb.main_kb(callback.from_user.id))

@router.message(F.text, Register_company.company_name)
async def register_company_name(message:Message, state:FSMContext):
    await delete_two_messages(message)
    await state.update_data(company_name=message.text)
    await state.set_state(Register_company.inn)
    await message.answer('Введите ИНН юр. лица/ИП', reply_markup=kb.cancel_operation)

@router.message(F.text, Register_company.inn)
async def register_inn(message:Message, state:FSMContext):
    await delete_two_messages(message)
    if await check_company(seller_inn=message.text):
        await state.update_data(inn=message.text)
        await state.set_state(Register_company.e_mail)
        await message.answer('Введите e-mail для связи и отправки документов',reply_markup=kb.cancel_operation)
    else:
        await state.clear()
        await message.answer('Компания c таким ИНН уже зарегистрирована. Выберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))

@router.message(F.text, Register_company.e_mail)
async def register_inn(message:Message, state:FSMContext):
    await delete_two_messages(message)
    try:
        await state.update_data(e_mail=message.text)
        await state.set_state(Register_company.tax_base)
        await message.answer('Выберите Вашу систему налогообложения:',reply_markup=kb.tax_regime)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@router.callback_query(F.data == 'usn_6', Register_company.tax_base)
async def register_tax_system (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(tax_base='income')
    await state.update_data(tax_system_str='УСНО')
    await state.update_data(tax_object='Доходы')
    await state.update_data(tax_rate=6)
    await state.update_data(tax_rate_str='6%')
    await state.set_state(Register_company.wb_api)
    path = config.templates_path + 'Как выгрузить API.pdf'
    file_to_send = FSInputFile(filename='Как выгрузить API.pdf',path=path)
    await callback.message.answer_document(document=file_to_send,
                                           caption=f'Выгрузите ключ API из кабинета WB и загрузите ключ здесь ответным сообщением.'
                                            f'\nКак это сделать смотрите в прилагаемой инструкции =>',
                                           reply_markup=kb.cancel_operation)

@router.callback_query(F.data == 'usn_lgot', Register_company.tax_base)
async def register_tax_system (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(tax_base='income')
    await state.update_data(tax_system_str='УСНО')
    await state.update_data(tax_object='Доходы')
    await state.set_state(Register_company.tax_rate)
    await callback.message.answer('Укажите льготную ставку налога в формате "1.5%" (без кавычек)', reply_markup=kb.cancel_operation)

@router.callback_query(F.data == 'usn_income_less_exp', Register_company.tax_base)
async def register_tax_system (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(tax_base='income_less_exp')
    await state.update_data(tax_system_str='УСНО')
    await state.update_data(tax_object='Доходы минус расходы')
    await state.set_state(Register_company.tax_rate)
    await callback.message.answer('Укажите ставку налога в Вашем регионе в формате "15%" (без кавычек)..', reply_markup=kb.cancel_operation)

@router.message(F.text, Register_company.tax_rate)
async def register_tax_rate (message:Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(tax_rate=message.text)
    await state.update_data(tax_rate_str=message.text)
    await state.set_state(Register_company.wb_api)
    path = config.templates_path + 'Как выгрузить API.pdf'
    file_to_send = FSInputFile(filename='Как выгрузить API.pdf',path=path)
    await message.answer_document(document=file_to_send,
                                           caption=f'Выгрузите ключ API из кабинета WB и загрузите ключ здесь ответным сообщением.'
                                            f'\nКак это сделать смотрите в прилагаемой инструкции =>',
                                           reply_markup=kb.cancel_operation)

@router.message(F.text, Register_company.wb_api)
async def register_api(message:Message, state:FSMContext):
    await delete_two_messages(message)
    if await check_api(api_key=message.text):
        await state.update_data(wb_api=message.text)
        data = await state.get_data()
        await message.answer(f'Ваша компания: {data["company_name"]}'
                             f'\nВаш ИНН: {data["inn"]}'
                             f'\nВаша система налогообложения: {data["tax_system_str"]}'
                             f'\nВаша база налогообложения: {data["tax_object"]}'
                             f'\nВаша ставка налогообложения: {data["tax_rate_str"]}'
                             ,reply_markup=kb.registration_approve)
    else:
        await state.clear()
        await message.answer('Данный api-ключ уже используется. Выберите пункт меню...', reply_markup=kb.main_kb(message.from_user.id))

@router.callback_query(F.data == 'approve_registration')
async def approve_registration (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    seller_id = await set_company(data=data,
                                  tg_id=callback.from_user.id)
    await state.clear()
    await new_trial_subscription(seller_id=seller_id)
    date_end = (datetime.now()+timedelta(days=7)).strftime('%Y-%m-%d')
    await callback.message.answer(f'<b>Поздравляем! Компания добавлена!</b>'
                                  f'\n\nБесплатная пробная подписка на сервис на 7 дней активирована.'
                                  f'\nПодписка действует до {date_end}'
                                  f'\n\nОсталось загрузить себестоимость товаров и '
                                  f'Вы будете получать автоматические отчеты!'
                                  f'\nВ скором времени мы пришлем Вам шаблон '
                                  f'для заполнения себестоимости по Вашим товарам.', reply_markup=kb.main_kb(callback.from_user.id), parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await callback.message.answer(f'Первая выгрузка всех данных с ВБ может занять до 40 минут.'
                                  f'\nМы выгружаем полную детализацию за 3 месяца по продажам, заказам, маркетингу, приемке, хранению и пр. Каждая выгрузка с ВБ содержит свои ограничения по количеству транзакций и количеству запросов в минуту. Поэтому первая большая выгрузка может занимать продолжительное время.'
                                  f'\nПоследующие выгрузки мы делаем ежедневно, поэтому вы будете оперативно получать все отчеты!',
                                  reply_markup=kb.main_kb(callback.from_user.id), parse_mode=ParseMode.HTML)
    await run_with_semaphore(seller_id=seller_id)

@router.message(F.text == '🔗 FAQ и другая информация')
async def start (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    await message.answer('Полная инструкция по работе с сервисом размещена на сайте =>https://финдирэкспресс.рф/instruktsiya/', reply_markup=faq_menu)


# Отправка запроса в службу поддержки
@router.message(F.text == '💬 Написать в поддержку')
async def start (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    await state.set_state(Support_ticket.tg_id)
    await state.update_data(tg_id=message.from_user.id)
    await state.update_data(tg_username=message.from_user.username)
    await state.set_state(Support_ticket.company_name)
    await message.answer('Введите название компании, по которой хотите отправить вопрос?', reply_markup=cancel_operation)

@router.message(F.text, Support_ticket.company_name)
async def company_name (message:Message, state:FSMContext):
    await delete_two_messages(message)
    await state.update_data(company_name=message.text)
    await state.set_state(Support_ticket.description)
    await message.answer('Напишите Ваш вопрос', reply_markup=cancel_operation)

@router.message(F.text, Support_ticket.description)
async def support_ticket_description (message:Message, state:FSMContext):
    await delete_two_messages(message)
    await state.update_data(description=message.text)
    data = await state.get_data()
    ticket_number = await new_support_ticket_registration(data=data)
    await state.clear()
    await message.answer(f'Ваш вопрос отправлен в службу поддержки!'
                         f'\n\nНомер вашего обращения: {ticket_number}'
                         f'\nКомпания: {data['company_name']}'
                         f'\nТекст вопроса: {data['description']}'
                         f'\n\nМы вернемся к Вам с ответом в ближайшее время.',reply_markup=kb.main_kb(message.from_user.id))

@router.message(F.text == '💰 Подписка на сервис')
async def balance (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id) or await check_manager_companies(tg_id=message.from_user.id):
            try:
                await message.answer(f'\nВыберите пункт меню',
                                     reply_markup=kb.balance_menu)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))

@router.callback_query(F.data == 'balance_and_subscriptions')
async def balance_and_subscriptions(callback:CallbackQuery):
    await delete_one_messages(callback.message)
    try:
        message_text = await create_my_subscriptions_str(user_tg_id=int(callback.from_user.id))
        await callback.message.answer(message_text,
                                      reply_markup=kb.main_kb(callback.from_user.id), parse_mode=ParseMode.HTML)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Отправляем список компаний для выбора
@router.callback_query(F.data == 'get_new_subscription')
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.set_state(New_subscription.company_name)
        companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
        await callback.message.answer("Выберите компанию, по которой хотите оформить/продлить подписку:",
                             reply_markup=companies_list_buttons.as_markup())
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Выбор типа подписки
@router.callback_query(F.data, New_subscription.company_name)
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.update_data(seller_id=callback.data)
        await state.set_state(New_subscription.subscription_type)
        subscription_keyboard = await create_subscription_keyboard()
        await callback.message.answer("Выберите тип подписки:",
                             reply_markup=subscription_keyboard.as_markup())
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Спрашиваем, есть ли промокод
@router.callback_query(F.data, New_subscription.subscription_type)
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.update_data(subscription_type=callback.data)
        await state.set_state(New_subscription.is_promocode)
        await callback.message.answer(f'Есть ли у Вас промокод?',
                             reply_markup=kb.is_promocode)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Если нет промокода, просим подтвердить подписку
@router.callback_query(F.data=='promocode_false')
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        subscription_name = await get_subscription_name_by_subscription_type(subscription_type=data['subscription_type'])
        price = await get_subscription_price_by_subscription_type(subscription_type=data['subscription_type'])
        company_name = await get_company_name_by_seller_id(seller_id=int(data['seller_id']))
        await state.update_data(promocode_id=None)
        await state.set_state(New_subscription.approve)
        await callback.message.answer(f'Подтвердите оформление подписки:'
                                      f'\nКомпания: {company_name}'
                                      f'\nТип подписки: {subscription_name}'
                                      f'\nСумма: {price} руб.'
                                      ,
                                      reply_markup=kb.approve_subscription)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Если есть промокод, просим ввести промокод
@router.callback_query(F.data =='promocode_true', New_subscription.is_promocode)
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.set_state(New_subscription.promocode)
        await callback.message.answer(f'Отправьте промокод ответным сообщением'
                                      ,
                                      reply_markup=kb.continue_without_promocode)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Получаем промокод, проверяем, если ок, то просим подтвердить подписку,
# если не ок, то пишем селлеру, что такого промокода нет, и предлагаем ввести новый, либо продолжить без промокода
@router.message(F.text, New_subscription.promocode)
async def new_subscription(message:Message, state:FSMContext):
    await delete_two_messages(message)
    try:
        promocode_to_check = message.text.lower()
        promocode_id = await check_active_promocode(promocode_title=promocode_to_check)
        promocode_check = True
        if promocode_id:
            if await check_promocode_dates_and_usage(promocode_id=promocode_id):
                await state.update_data(promocode_id = promocode_id)
                data = await state.get_data()
                subscription_name = await get_subscription_name_by_subscription_type(subscription_type=data['subscription_type'])
                price = await get_subscription_price_by_subscription_type(subscription_type=data['subscription_type'])
                discount_amount, subscription_net_price = await get_discount_amount_for_promocode(subscription_type = data['subscription_type'],
                                                                                                  promocode_id = promocode_id)
                company_name = await get_company_name_by_seller_id(seller_id=int(data['seller_id']))
                if await check_promocode_budget(promocode_id=promocode_id,
                                                discount_amount=discount_amount):
                    await state.set_state(New_subscription.approve)
                    await message.answer(f'Подтвердите оформление подписки:'
                                         f'\nКомпания: {company_name}'
                                         f'\nТип подписки: {subscription_name}'
                                         f'\nСумма: {price} руб.'
                                         f'\nСкидка по промокоду: {discount_amount} руб.'
                                         f'\nСумма с учетом скидки: {subscription_net_price} руб.'
                                         ,reply_markup=kb.approve_subscription)
                else:
                    promocode_check = False
            else:
                promocode_check = False
        else:
            promocode_check = False
        if not promocode_check:
            await state.update_data(promocode_id=None)
            await state.set_state(New_subscription.promocode)
            await message.answer(f'Такой промокод не существует либо закончился.'
                                 f'\nОтправьте действующий промокод ответным сообщением'
                                      ,reply_markup=kb.continue_without_promocode)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Оформляем новую подписку. Отправляем подтверждение, что подписка оформлена
@router.callback_query(F.data == 'approve_subscription', New_subscription.approve)
async def new_subscription(callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    try:
        data = await state.get_data()
        await callback.message.answer(f'<b>Подписка оформлена!</b>'
                                      f'\nНаправляем Вам счет на оплату.'
                                      f'\nПодписка будет активирована после оплаты счета.'
                                      f'\n\nПросим оплачивать счет только со счета зарегистрированной в сервисе организации/ИП.'
                                      f'\nНе оплачивайте подписку с личного счета физ.лица. '
                                      f'В случае оплаты подписки со счета физ.лица '
                                      f'мы вернем Вам деньги, но подписка не будет активирована.'
                                      f'\nДля быстрого распознавания платежа просим '
                                      f'обязательно указывать номер счета в назначении платежа!'
                                      ,reply_markup=kb.main_kb(callback.from_user.id), parse_mode=ParseMode.HTML)
        await new_subscription_with_invoice(seller_id=int(data['seller_id']),
                                            subscription_type=data['subscription_type'],
                                            date_start=datetime.now(),
                                            promocode_id = data['promocode_id'],
                                            requestor_tg_id = int(callback.from_user.id))
        await state.clear()
    except Exception as e:
        # Запись ошибки в лог
        # logging.exception("An error occurred: %s", exc_info=e)
        logging.exception("An error occurred", exc_info=True)


@router.message(F.text == '💼 О сервисе')
@log_and_notify_admin
async def about_service(message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.clear()
    path = config.templates_path + 'О сервисе.jpg'
    photo = FSInputFile(filename='photo', path=path)
    await message.answer_photo(photo=photo,
                               caption=f'FindirExpress - сервис автоматизации и анализа данных на марткетплейсах.'
                                       f'\n\nДля начала работы необходимо перейти в раздел "Профиль" и зарегистрироваться как пользователь. '
                                       f'Далее нужно добавить компанию.'
                                       f'\n\nЛюбые вопросы можно задавать в поддержку или в наш чат.'
                                       
                                       f'\n\nСсылка на наш сайт => финдирэкспресс.рф'
                                       f'\nКанал по оцифровке ВБ => @FindirExpressChannel'
                                       f'\nЧат по оцифровке ВБ => @FindirExpressCommunity'
                               , reply_markup=kb.main_kb(message.from_user.id))

