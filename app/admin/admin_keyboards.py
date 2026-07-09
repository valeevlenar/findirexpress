from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

import config


# Админская клавиатура
def admin_kb(tg_id: int):
    kb_list = [
        [KeyboardButton(text='Статус системы')],
        [KeyboardButton(text='Отчет по выгрузке остатков')],
        [KeyboardButton(text="Компании и подписки")],
        [KeyboardButton(text="Промокоды")],
        [KeyboardButton(text="Реферальная программа")],
        [KeyboardButton(text="Рассылки")]
    ]

    if tg_id == config.ADMIN_ID:
        kb_list.append([KeyboardButton(text="⚙️ Tech admin menu")])
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, input_field_placeholder='Выберите пункт меню')
    return keyboard


tech_admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Запустить основную отчетную функцию', callback_data="start_main_function")],
    [InlineKeyboardButton(text='Пересчитать PL за 3 месяца', callback_data="recalculate_PL_for_3_months")],
    [InlineKeyboardButton(text='Перезапустить основную функцию по seller_id', callback_data="main_reporting_function_by_seller_id")],
    [InlineKeyboardButton(text='Удалить все данные по seller_id', callback_data="delete_seller_id_data")],
    [InlineKeyboardButton(text='Получить недельный отчет по селлеру', callback_data="get_weekly_report_by_seller")],
    [InlineKeyboardButton(text='Пересчитать PL с самого начала по селлеру',callback_data="recalculate_PL_for_3_months_by_seller")],
    [InlineKeyboardButton(text='Пересчитать PL с самого начала по всем селлерам',callback_data="recalculate_PL_for_3_months_all_sellers")],
    [InlineKeyboardButton(text='Пересчитать PL по селлеру с даты',callback_data="recalculate_PL_by_seller_from_date")],
    [InlineKeyboardButton(text='Скачать недельный отчет ВБ по селлеру',callback_data="get_weekly_wb_fin_report_by_seller")],
    [InlineKeyboardButton(text='Скачать БД',callback_data="save_sales_db")],
    [InlineKeyboardButton(text='Сохранить остатки в эксель',callback_data="save_stocks_to_excel")],
    [InlineKeyboardButton(text='Заполнить себестоимость в таблице Stock',callback_data="set_cost_for_stock")],
    [InlineKeyboardButton(text='Восстановить названия в goods_cost',callback_data="restore_goods_costs_names")],
    [InlineKeyboardButton(text='Отправить ответ',callback_data="send_support_reply")],
    [InlineKeyboardButton(text='Проверить расходы на хранение по селлеру',callback_data="check_storage_costs_allocation")],
    [InlineKeyboardButton(text='Проверить аллокацию маркетинга по селлеру',callback_data="check_marketing_allocation")],
    [InlineKeyboardButton(text='Найти ошибки в аллокации маркетинга по advert_id по селлеру',callback_data="check_marketing_allocation_by_advert_id")],
    [InlineKeyboardButton(text='Проверить акты приемки по селлеру',callback_data="check_paid_acceptance")],
    [InlineKeyboardButton(text='Temp function (заполнить бренд)', callback_data="temp_functions")],
    [InlineKeyboardButton(text='Test functions', callback_data="test_functions")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

companies_and_subscriptions = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Дать промо подписку', callback_data="promo_subscription")],
    [InlineKeyboardButton(text='Заблокировать компанию', callback_data="block_company")],
    [InlineKeyboardButton(text='Проверить подписки', callback_data="check_subscriptions")],
    [InlineKeyboardButton(text='Проверить сроки подписок', callback_data="check_subscriptions_dates")],
    [InlineKeyboardButton(text='Проверить статусы оплаты', callback_data="check_invoices_status")],
    [InlineKeyboardButton(text='Назад в Главное меню', callback_data="back_to_main_menu")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

admin_approve = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Подтвердить', callback_data="approve")],
    [InlineKeyboardButton(text='Отменить', callback_data="cancel")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

cancel = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Отменить', callback_data="cancel")]
    ], resize_keyboard=True)

promocodes_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Действующие промокоды', callback_data="active_promocodes")],
    [InlineKeyboardButton(text='Создать промокод', callback_data="create_promocode")],
    [InlineKeyboardButton(text='Удалить промокод', callback_data="delete_promocode")],
    [InlineKeyboardButton(text='Назад в Главное меню', callback_data="back_to_main_menu")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

promocodes_types = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Скидка в виде %', callback_data="percentage")],
    [InlineKeyboardButton(text='Скидка в виде суммы', callback_data="amount")],
    [InlineKeyboardButton(text='Отменить', callback_data="cancel")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')

referral_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Отчет по реферальной программе', callback_data="referrals_report")],
    [InlineKeyboardButton(text='Создать новый канал', callback_data="create_referral_channel")],
    [InlineKeyboardButton(text='Назад в Главное меню', callback_data="back_to_main_menu")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')


sending_messages_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Разослать сообщение всем пользователям', callback_data="send_message_to_all_users")],
    [InlineKeyboardButton(text='Назад в Главное меню', callback_data="back_to_main_menu")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')