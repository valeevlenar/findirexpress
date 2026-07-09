from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from app.database.support_functions import get_companies_list, get_price_control_by_seller_id
from app.managers.managers_functions import create_companies_list_for_manager_user_tg_id
from app.prices.price_api_functions import check_price_api_exist
from app.subscriptions.subscription_types import SubscriptionTypes
from app.wrappers import with_session

builder = InlineKeyboardBuilder()


def main_kb(tg_id: int):
    kb_list = [
        [KeyboardButton(text='💼 О сервисе')],
        [KeyboardButton(text='👨🏼‍💼 Профиль')],
        [KeyboardButton(text='🧮 Посмотреть примеры отчетов')],
        [KeyboardButton(text='💵 Тарифы')],
        [KeyboardButton(text='💰 Подписка на сервис')],
        [KeyboardButton(text='📦 Себестоимость товаров')],
        [KeyboardButton(text='🗄 Отчеты')],
        [KeyboardButton(text='👨‍💼 Менеджеры')],
        [KeyboardButton(text='🏦 Контроль цен')],
        [KeyboardButton(text='🌟 Реферальная программа')],
        [KeyboardButton(text='🔑 API')],
        [KeyboardButton(text='🔗 FAQ и другая информация')],
        [KeyboardButton(text='💬 Написать в поддержку')]]
    if tg_id == config.ADMIN_ID:
        kb_list.append([KeyboardButton(text="⚙️ Admin menu")])
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, input_field_placeholder='Выберите пункт меню')
    return keyboard

admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Пусто', callback_data="empty")],
    [InlineKeyboardButton(text='Пусто',callback_data="empty")],
    [InlineKeyboardButton(text='Пусто', callback_data="empty")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

profile_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='👨🏼‍💼 Зарегистрироваться',callback_data='add_user')],
    [InlineKeyboardButton(text='Добавить компанию',callback_data='add_company')],
    [InlineKeyboardButton(text='Мои компании',callback_data='my_companies')],
    [InlineKeyboardButton(text='Удалить компанию',callback_data='delete_company')],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
                            resize_keyboard=True,
                            input_field_placeholder='Выберите пункт меню')

registration_approve = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='approve_registration')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

user_registration_approve = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='user_approve_registration')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

cost_file_cancel_send = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

tax_regime = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='УСНО (доходы) - 6%',callback_data='usn_6')],
    [InlineKeyboardButton(text='УСНО (доходы) по льготной ставке (для отдельных регионов)',callback_data='usn_lgot')],
    [InlineKeyboardButton(text='УСНО (доходы минус расходы)',callback_data='usn_income_less_exp')],
    #[InlineKeyboardButton(text='Общая система налогообложения (платите НДС)',callback_data='osn_withVAT')],
    #[InlineKeyboardButton(text='Общая система налогообложения (освобождение от НДС)',callback_data='osn_lessVAT')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

cancel_operation = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

company_deletion = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Удалить',callback_data="delete")],
    [InlineKeyboardButton(text='↩️ Отменить удаление',callback_data="cancel")]],resize_keyboard=True)

reports_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Выслать отчет за неделю',callback_data='send_weekly_report')],
    [InlineKeyboardButton(text='Выслать отчет за месяц',callback_data='send_monthly_report')],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
                            resize_keyboard=True,
                            input_field_placeholder='Выберите пункт меню')

new_api = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Загрузить новый ключ API', callback_data="new_api_key")],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
    resize_keyboard=True)

balance_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Мои текущие подписки', callback_data='balance_and_subscriptions')],
    [InlineKeyboardButton(text='Оформить/продлить подписку', callback_data='get_new_subscription')],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
    resize_keyboard=True)



faq_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Перейти на сайт', url='https://xn--d1achbkprgcida1a5k.xn--p1ai/instruktsiya/')],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
    resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

@with_session
async def create_companies_keyboard(session, tg_id):
    companies_list_buttons = InlineKeyboardBuilder()
    companies_list = await get_companies_list(session=session, tg_id=tg_id)
    for company in companies_list:
        companies_list_buttons.button(text=company['seller_title'],callback_data=str(company['seller_id']), resize_keyboard=True)
    manager_companies = await create_companies_list_for_manager_user_tg_id(session, tg_id)
    # print(manager_companies)
    if manager_companies:
        for manager_company in manager_companies:
            companies_list_buttons.button(text=manager_company['seller_title'], callback_data=str(manager_company['seller_id']),
                                      resize_keyboard=True)
    companies_list_buttons.button(text='↩️ Отменить', callback_data='cancel',resize_keyboard=True)
    companies_list_buttons.adjust(1,1)
    return companies_list_buttons

async def create_subscription_keyboard():
    subscription_list_buttons = InlineKeyboardBuilder()
    subscriptions = SubscriptionTypes.items
    for item in subscriptions:
        if item.subscription_type != 'trial' and item.subscription_type!='promo':
            subscription_list_buttons.button(text=f'{item.subscription_name}: {item.price} руб.',
                                             callback_data=item.subscription_type, resize_keyboard=True)
    subscription_list_buttons.button(text='↩️ Отменить', callback_data='cancel',resize_keyboard=True)
    subscription_list_buttons.adjust(1,1)
    return subscription_list_buttons

is_promocode = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Да, есть промокод',callback_data='promocode_true')],
    [InlineKeyboardButton(text='Продолжить без промокода',callback_data='promocode_false')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
        resize_keyboard=True)

continue_without_promocode = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Продолжить без промокода',callback_data='promocode_false')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
        resize_keyboard=True)

approve_subscription = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='approve_subscription')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='back_to_main_menu')]],
        resize_keyboard=True)

approve_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='approve')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='back_to_main_menu')]],
        resize_keyboard=True)

@with_session
async def create_price_control_keyboard(session, seller_id):
    price_control = await get_price_control_by_seller_id(session=session, seller_id=seller_id)
    price_control_buttons = InlineKeyboardBuilder()
    price_api_exist = await check_price_api_exist(session, seller_id)
    if price_control:
        if price_api_exist:
            price_control_buttons.button(text=f'Скачать шаблон с ценами', callback_data='price_control_get_price_template',
                                         resize_keyboard=True)
            price_control_buttons.button(text=f'Загрузить шаблон с ценами', callback_data='price_control_upload_price_template',
                                         resize_keyboard=True)
            price_control_buttons.button(text=f'Загрузить новый api-ключ по категории "Цены и скидки"', callback_data='price_control_new_api',resize_keyboard=True)
            price_control_buttons.button(text=f'Выключить функцию контроля цен', callback_data='price_control_disable', resize_keyboard=True)
        else:
            price_control_buttons.button(text=f'Загрузить api-ключ по категории "Цены и скидки"',
                                         callback_data='price_control_new_api', resize_keyboard=True)
            price_control_buttons.button(text=f'Выключить функцию контроля цен',
                                         callback_data='price_control_disable', resize_keyboard=True)
    else:
        price_control_buttons.button(text=f'Включить контроль цен', callback_data='price_control_enable',
                                     resize_keyboard=True)
    price_control_buttons.button(text='↩️ Назад в главное меню', callback_data='back_to_main_menu', resize_keyboard=True)
    price_control_buttons.adjust(1,1)
    return price_control_buttons

price_new_api = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔑 Загрузить новый ключ API', callback_data="price_control_new_api_key_upload")],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='back_to_main_menu')]],
    resize_keyboard=True)

price_template_cancel_send = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

price_template_approve = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='approve_price_template')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel_price_template')]],
                            resize_keyboard=True)

referral_program = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔗 Получить реферальную ссылку',callback_data='get_referral_link')],
    [InlineKeyboardButton(text='↩️ Назад в главное меню',callback_data='back_to_main_menu')]],
                            resize_keyboard=True)