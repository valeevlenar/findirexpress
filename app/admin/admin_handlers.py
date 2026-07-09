# -*- coding: utf-8 -*-
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Router, F
import config
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from aiogram.enums import ParseMode
import logging
import sqlalchemy
from datetime import datetime, timedelta

from app.admin.admin_message import send_message_to_admin
from app.admin.restore_goods_cost import restore_goods_cost_names
from app.admin.temp_functions import get_brand_to_goods_cost, make_brand_name_upper_case
from app.database.check_allocation_functions import get_wrong_paid_acceptance_items, \
    get_wrong_marketing_allocation_items
from app.database.classes.goods_cost_template import Goods_cost_template
from app.database.dates_functions import get_latest_weekly_report_sent_date
from app.get_data.get_marketing_stats import get_marketing_stats_from_wb
from app.get_data.get_paid_acceptance import get_paid_acceptance_costs_by_seller
from app.get_data.get_sales_data import get_and_check_sales_report
from app.main_bot.main_bot import bot

from app.admin.admin_functions import admin_recalculate_pl_results_for_three_months, \
    admin_recalculate_pl_results_for_three_months_for_seller_id, send_message_to_all_users, \
    admin_recalculate_pl_results_for_seller_id_from_date
from app.admin.admin_keyboards import admin_kb, tech_admin_menu, companies_and_subscriptions, cancel, \
    promocodes_kb, promocodes_types, admin_approve, referral_kb, sending_messages_kb

from app.admin.admin_referrals import check_referral_channel_exist, create_referral_channel
from app.admin.admin_reports import system_status_prep, admin_stocks_download_status
from app.admin.promo_admin_functions import create_new_promocode, get_promocodes_list_str, delete_promocode, \
    get_promocode_data_str, create_active_promocodes_keyboard
from app.app_logic import main_regular_reporting_function, run_with_semaphore, check_storage_costs_allocation
from app.data_clerance.deletion_in_db import delete_data_by_seller_id
from app.database.models import async_session, Seller, Marketing_costs_wb
from app.database.requests import set_cost_to_stock, check_cost
from app.database.support_functions import delete_one_messages, block_seller, get_company_name_by_seller_id
from app.dates import start_for_downloading_data_func, end_of_Reporting_Week_func, start_of_Reporting_Week_func, \
    start_of_Prior_Week_func, end_of_Prior_Week_func
from app.get_data.marketing import allocate_marketing_costs_to_sku, check_marketing_costs_allocation
from app.payments.invoices import check_invoices_status
from app.reports.weekly_finreport import get_weekly_pl
from app.reports.reporting_functions import get_db_to_excel, save_stocks_to_excel
from app.subscriptions.subscriptions_functions import check_subscriptions_dates, \
    check_subscriptions_status, new_promo_subscription
from app.wrappers import with_session

admin_router = Router()
builder = InlineKeyboardBuilder()

class Block_company(StatesGroup):
    tg_id = State()
    seller_id = State()

class Promo_Subscription(StatesGroup):
    seller_inn = State()
    seller_id = State()
    duration = State()
    approve = State()

class PromocodeCreation(StatesGroup):
    code_title = State()
    promo_type = State()
    discount_percentage = State()
    discount_amount = State()
    max_usage_number = State()
    max_budget = State()
    expires_at = State()
    approve = State()

class PromocodeDeletion(StatesGroup):
    promocode = State()
    promocode_id = State()
    approve = State()

class ReferralChannelCreation(StatesGroup):
    channel_name = State()
    channel_contacts_data = State()
    channel_reward_conditions = State()
    approve = State()

class Delete_seller_id_data(StatesGroup):
    seller_id = State()

class Main_reporting_function_by_seller_id(StatesGroup):
    seller_id = State()

class Get_weekly_report_by_seller(StatesGroup):
    seller_id = State()
    date_from = State()
    date_to = State()

class Recalculate_PL_for_3_months_by_seller(StatesGroup):
    seller_id = State()

class Check_paid_acceptance_by_seller(StatesGroup):
    seller_id = State()

class Check_marketing_allocation_by_seller(StatesGroup):
    seller_id = State()

class Check_marketing_allocation_by_seller_by_advert_id(StatesGroup):
    seller_id = State()

class Check_storage_allocation_by_seller(StatesGroup):
    seller_id = State()

class Recalculate_PL_by_seller_from_date(StatesGroup):
    seller_id = State()
    date_from = State()

class Get_weekly_wb_fin_report_by_seller(StatesGroup):
    seller_id = State()

class Send_message_to_users(StatesGroup):
    message_text = State()
    message_photo = State()

class Add_doctype(StatesGroup):
    seller_id = State()

@admin_router.message(CommandStart())
async def start (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('⚙️ Привет, хозяин! ⚙️ '
                         '\nВыбери пункт меню...', reply_markup=admin_kb(message.from_user.id))

# Отмена операции
@admin_router.callback_query(F.data == 'cancel')
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        await state.clear()
        await callback.message.answer('Операция отменена.', reply_markup=admin_kb(callback.message.from_user.id))
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Отмена операции
@admin_router.callback_query(F.data == 'back_to_main_menu')
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        await state.clear()
        await callback.message.answer('Операция отменена.', reply_markup=admin_kb(callback.message.from_user.id))
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

@admin_router.message(F.text == 'Статус системы')
async def system_status (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        system_status = await system_status_prep('now')
        await message.answer(system_status, parse_mode=ParseMode.HTML, reply_markup=admin_kb(message.from_user.id))
    else:
        await message.answer('У вас нет никаких прав!!!')

# Супер админское меню
@admin_router.message(F.text == '⚙️ Tech admin menu')
async def admin_menu (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('Выберите пункт меню', reply_markup=tech_admin_menu)
    else:
        await message.answer('У вас нет никаких прав!!!')

# Принудительно запускаем основную отчетную функцию
@admin_router.callback_query(F.data == 'start_main_function')
async def get_stocks (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    await main_regular_reporting_function()
    await callback.message.answer('Выполнено!')

# Пересчет PL за 3 месяца
@admin_router.callback_query(F.data == 'recalculate_PL_for_3_months')
async def recalculate_pl (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    await admin_recalculate_pl_results_for_three_months()
    await callback.message.answer('Выполнено!')

# Меню операции с компаниями
@admin_router.message(F.text == 'Компании и подписки')
async def admin_menu (message: Message):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('Выберите пункт меню', reply_markup=companies_and_subscriptions)
    else:
        await message.answer('У вас нет никаких прав!!!')

# Вручную блокируем компанию
@admin_router.callback_query(F.data == 'block_company')
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        await state.set_state(Block_company.seller_id)
        await callback.message.answer('Введите ID селлера для блокировки', reply_markup=cancel)
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Даем промо подписку
@admin_router.callback_query(F.data == 'promo_subscription')
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        await state.set_state(Promo_Subscription.seller_inn)
        await callback.message.answer('Введите ИНН селлера кому хотите дать промо-подписку', reply_markup=cancel)
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

@admin_router.message(F.text, Promo_Subscription.seller_inn)
async def admin_func (message:Message, state:FSMContext):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await state.update_data(seller_inn = message.text)
        await state.set_state(Promo_Subscription.duration)
        await message.answer('Введите срок, на который хотите дать промо-подписку', reply_markup=cancel)
    else:
        await message.answer('У вас нет никаких прав!!!')

@admin_router.message(F.text, Promo_Subscription.duration)
async def admin_func (message:Message, state:FSMContext):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await state.update_data(duration = message.text)
        data = await state.get_data()
        await state.set_state(Promo_Subscription.approve)
        await message.answer(f'Подтвердите предоставление промо-подписки:'
                             f'\nseller_inn: {data['seller_inn']}'
                             f'\nсрок: {data['duration']} мес.', reply_markup=admin_approve)
    else:
        await message.answer('У вас нет никаких прав!!!')

@admin_router.callback_query(F.data =='approve', Promo_Subscription.approve)
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        data = await state.get_data()
        await state.clear()
        await new_promo_subscription(data=data)
        await callback.message.answer(f'Промо-подписка предоставлена!'
                             f'\nseller_inn: {data['seller_inn']}'
                             f'\nсрок: {data['duration']} мес.', reply_markup=admin_kb(callback.message.from_user.id))
    else:
        await callback.answer('У вас нет никаких прав!!!')


@admin_router.message(F.text, Block_company.seller_id)
async def admin_func (message:Message, state:FSMContext):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await state.update_data(seller_id=message.text)
        data = await state.get_data()
        seller_id = int(data['seller_id'])
        await block_seller(seller_id=seller_id)
        await message.answer('Компания заблокирована', reply_markup=admin_kb(message.from_user.id))
    else:
        await message.answer('У вас нет никаких прав!!!')

# # Вручную вызываем выгрузку остатков с ВБ
# @admin_router.callback_query(F.data == 'get_stocks_data')
# async def get_stocks (callback: CallbackQuery):
#     await delete_one_messages(callback.message)
#     await daily_get_stocks_data()
#     await callback.message.answer('Остатки выгружены')

# Вызываем отчет по выгрузке остатков
@admin_router.message(F.text == 'Отчет по выгрузке остатков')
async def system_status (message: Message):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await admin_stocks_download_status()
    else:
        await message.answer('У вас нет никаких прав!!!')

# Сохранить остатки в эксель
@admin_router.callback_query(F.data == 'save_stocks_to_excel')
async def save_stocks (callback: CallbackQuery):
    if callback.from_user.id == config.ADMIN_ID:
        await callback.message.delete()
        await save_stocks_to_excel()
        await callback.message.answer('Остатки сохранены в эксель')
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Сохранить продажи в эксель
@admin_router.callback_query(F.data == 'save_sales_db')
async def save_stocks (callback: CallbackQuery):
    if callback.from_user.id == config.ADMIN_ID:
        await callback.message.delete()
        await get_db_to_excel()
        await callback.message.answer('Продажи сохранены в эксель')
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Проверяем подписки вручную
@admin_router.callback_query(F.data == 'check_subscriptions')
async def check_subscriptions (callback: CallbackQuery):
    if callback.from_user.id == config.ADMIN_ID:
        await callback.message.delete()
        await check_subscriptions_status()
        await callback.message.answer('Выполнено!')
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Проверяем подписки вручную
@admin_router.callback_query(F.data == 'check_subscriptions_dates')
async def check_subscriptions (callback: CallbackQuery):
    if callback.from_user.id == config.ADMIN_ID:
        await callback.message.delete()
        await check_subscriptions_dates()
        await callback.message.answer('Выполнено!')
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Проверяем подписки вручную
@admin_router.callback_query(F.data == 'check_invoices_status')
async def check_invoices (callback: CallbackQuery):
    if callback.from_user.id == config.ADMIN_ID:
        await callback.message.delete()
        await check_invoices_status()
        await callback.message.answer('Выполнено!')
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

# Заполнить себестоимость в таблице Stock
@admin_router.callback_query(F.data == 'set_cost_for_stock')
async def set_cost_for_stocks (callback: CallbackQuery):
    async with async_session() as session:
        if callback.from_user.id == config.ADMIN_ID:
            await callback.message.delete()
            # Получаем список селлеров для расчета
            query = select(Seller.id).where(Seller.status == 'Active', Seller.service_status == True)
            companies = await session.execute(query)
            await session.commit()
            # Последовательно для каждого селлера
            for row in companies:
                seller_id = row[0]
                # Заполняем таблицу Stock:
            start_for_downloading_data = await start_for_downloading_data_func()
            await set_cost_to_stock(seller_id=seller_id,
                                        date_start=start_for_downloading_data)
            await callback.message.answer('Таблица Stock заполнена')
        else:
            await callback.message.answer('У вас нет никаких прав!!!')

# Меню операции с компаниями
@admin_router.message(F.text == 'Промокоды')
async def promocodes (message: Message):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('Выберите пункт меню', reply_markup=promocodes_kb)
    else:
        await message.answer('У вас нет никаких прав!!!')

# создание нового промокода
@admin_router.callback_query(F.data == 'create_promocode')
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(PromocodeCreation.code_title)
    await callback.message.answer(f'Введите название промокода', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.code_title)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(code_title=message.text)
    await state.set_state(PromocodeCreation.promo_type)
    await message.answer(f'Выберите тип промокода', reply_markup=promocodes_types)

# создание нового промокода
@admin_router.callback_query(F.data, PromocodeCreation.promo_type)
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(promo_type=str(callback.data))
    if str(callback.data) == 'percentage':
        await state.update_data(discount_amount = 0)
        await state.set_state(PromocodeCreation.discount_percentage)
        await callback.message.answer(f'Укажите размер скидки в %', reply_markup=cancel)
    elif str(callback.data) == 'amount':
        await state.update_data(discount_percentage=0)
        await state.set_state(PromocodeCreation.discount_amount)
        await callback.message.answer(f'Укажите величину скидки в руб.', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.discount_percentage)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(discount_percentage = float(str(message.text).replace("%","").replace(",","."))/100)
    await state.set_state(PromocodeCreation.max_usage_number)
    await message.answer(f'Введите максимальное количество использования промо-кодов', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.discount_amount)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(discount_amount=float(message.text))
    await state.set_state(PromocodeCreation.max_usage_number)
    await message.answer(f'Введите максимальное количество использования промо-кодов', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.max_usage_number)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(max_usage_number=int(message.text))
    await state.set_state(PromocodeCreation.max_budget)
    await message.answer(f'Укажите максимальный бюджет на кампанию', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.max_budget)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(max_budget=float(message.text))
    await state.set_state(PromocodeCreation.expires_at)
    await message.answer(f'Укажите дату окончания действия промокода в формате 31.12.2024', reply_markup=cancel)

# создание нового промокода
@admin_router.message(F.text, PromocodeCreation.expires_at)
async def promocodes (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(expires_at=message.text)
    data = await state.get_data()
    await state.set_state(PromocodeCreation.approve)
    max_budget = data['max_budget']
    max_budget = '{:,.0f}'.format(max_budget).replace(',', ' ')
    await message.answer(f'Подтвердите создание промокода:'
                         f'\nНазвание: {data['code_title']}'
                         f'\nТип: {data['promo_type']}'
                         f'\nПроцент скидки: {data['discount_percentage']}'
                         f'\nСумма скидки: {data['discount_amount']} руб. '
                         f'\nКол-во использований: {data['max_usage_number']}'
                         f'\nБюджет на кампанию: {max_budget} руб.'
                         f'\nСрок действия до: {data['expires_at']}', reply_markup=admin_approve)

# создание нового промокода
@admin_router.callback_query(F.data, PromocodeCreation.approve)
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    await state.clear()
    await create_new_promocode(promocode_data=data)
    max_budget = data['max_budget']
    max_budget = '{:,.0f}'.format(max_budget).replace(',', ' ')
    await callback.message.answer(f'Промокод создан:'
                         f'\nНазвание: {data['code_title']}'
                         f'\nТип: {data['promo_type']}'
                         f'\nПроцент скидки: {data['discount_percentage']}'
                         f'\nСумма скидки: {data['discount_amount']} руб.'
                         f'\nКол-во использований: {data['max_usage_number']}'
                         f'\nБюджет на кампанию: {max_budget} руб.'
                         f'\nСрок действия до: {data['expires_at']}', reply_markup=admin_kb(callback.message.from_user.id))

# действующие промокоды
@admin_router.callback_query(F.data == 'active_promocodes')
async def active_promocodes (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    try:
        promocodes_list_str = await get_promocodes_list_str()
        await callback.message.answer(f'<b>Активные промокоды:</b>'
                                      f'\n{promocodes_list_str}',
                                      reply_markup=admin_kb(callback.message.from_user.id),
                                      parse_mode=ParseMode.HTML)
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)


# удаление промокода
@admin_router.callback_query(F.data == 'delete_promocode')
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(PromocodeDeletion.promocode)
    promocodes_list_buttons = await create_active_promocodes_keyboard()
    await callback.message.answer(f'Выберите промокод для удаления',
                                  reply_markup=promocodes_list_buttons.as_markup())

# удаление промокода
@admin_router.callback_query(F.data, PromocodeDeletion.promocode)
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(promocode_id = int(callback.data))
    promocode_data_str = await get_promocode_data_str(promocode_id=int(callback.data))
    await state.update_data(promocode = promocode_data_str)
    await state.set_state(PromocodeDeletion.approve)
    await callback.message.answer(f'Подтвердите удаление промокода:'
                                  f'\n{promocode_data_str}', reply_markup=admin_approve)

# удаление промокода
@admin_router.callback_query(F.data == 'approve', PromocodeDeletion.approve)
async def promocodes (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    await delete_promocode(promocode_id=data['promocode_id'])
    await state.clear()
    await callback.message.answer(f'Промокод удален:'
                                  f'\n{data['promocode']}', reply_markup=admin_kb(callback.message.from_user.id))

# Реферальная программа
@admin_router.message(F.text == 'Реферальная программа')
async def referral_programm (message: Message):
    await delete_one_messages(message)
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('Выберите пункт меню', reply_markup=referral_kb)
    else:
        await message.answer('У вас нет никаких прав!!!')

# Создаем канал
@admin_router.callback_query(F.data == 'create_referral_channel')
async def referral_channel (callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(ReferralChannelCreation.channel_name)
    await callback.message.answer(f'Введите название канала', reply_markup=cancel)

# Создаем канал
@admin_router.message(F.text, ReferralChannelCreation.channel_name)
async def referral_channel (message: Message, state: FSMContext):
    await delete_one_messages(message)
    channel_id = await check_referral_channel_exist(channel_name=message.text)
    if not channel_id:
        await state.update_data(channel_name = message.text)
        await state.set_state(ReferralChannelCreation.channel_contacts_data)
        await message.answer(f'Введите контактные данные канала', reply_markup=cancel)
    else:
        await state.clear()
        await message.answer(f'Такой канал уже существует', reply_markup=admin_kb(message.from_user.id))

# Создаем канал
@admin_router.message(F.text, ReferralChannelCreation.channel_contacts_data)
async def referral_channel (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.update_data(channel_contacts_data = message.text)
    await state.set_state(ReferralChannelCreation.channel_reward_conditions)
    await message.answer(f'Введите условия вознаграждения канала', reply_markup=cancel)

# Создаем канал
@admin_router.message(F.text, ReferralChannelCreation.channel_reward_conditions)
async def referral_channel (message: Message, state: FSMContext):
    await delete_one_messages(message)
    await state.update_data(channel_reward_conditions = message.text)
    data = await state.get_data()
    await state.set_state(ReferralChannelCreation.approve)
    await message.answer(f'Подтвердите создание нового реферального канала:'
                         f'\nChannel_name: {data['channel_name']}'
                         f'\nContacts_data: {data['channel_contacts_data']}'
                         f'\nRewards_conditions: {data['channel_reward_conditions']}', reply_markup=admin_approve)

# Создаем канал
@admin_router.callback_query(F.data =='approve', ReferralChannelCreation.approve)
async def referral_channel (callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    data = await state.get_data()
    channel_referral_link = await create_referral_channel(channel_name=data['channel_name'],
                                                          channel_contacts_data=data['channel_contacts_data'],
                                                          channel_reward_conditions=data['channel_reward_conditions'])
    if channel_referral_link:
        await callback.message.answer(f'Реферальный канал создан:'
                             f'\nChannel_name: {data['channel_name']}'
                             f'\nContacts_data: {data['channel_contacts_data']}'
                             f'\nRewards_conditions: {data['channel_reward_conditions']}')
        await callback.message.answer(f'Реферальная ссылка: {channel_referral_link}'
                              , reply_markup=admin_kb(callback.message.from_user.id))
        await state.clear()
    else:
        await callback.answer(f'Ошибка при создании канала.'
                              , reply_markup=admin_kb(callback.message.from_user.id))

# удаление таблиц по селлеру
@admin_router.callback_query(F.data == 'delete_seller_id_data')
async def delete_seller_id_data (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Delete_seller_id_data.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите удалить данные', reply_markup=cancel)

# удаление таблиц по селлеру
@admin_router.message(F.text, Delete_seller_id_data.seller_id)
async def delete_seller_id_data (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
    await state.clear()
    await delete_data_by_seller_id(seller_id=seller_id)
    await message.answer(f'Данные по seller_id {seller_id}, {seller_title} удалены.', reply_markup=cancel)

# удаление таблиц по селлеру
@admin_router.callback_query(F.data == 'main_reporting_function_by_seller_id')
async def main_reporting_function_by_seller_id (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Main_reporting_function_by_seller_id.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите запустить отчетную функцию', reply_markup=cancel)

# удаление таблиц по селлеру
@admin_router.message(F.text, Main_reporting_function_by_seller_id.seller_id)
async def main_reporting_function_by_seller_id (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
    await state.clear()
    await run_with_semaphore(seller_id)
    await message.answer(f'Основная отчетная функция по seller_id {seller_id}, {seller_title} выполнена.', reply_markup=cancel)



# получить недельный отчет по селлеру
@admin_router.callback_query(F.data == 'get_weekly_report_by_seller')
async def get_weekly_report_by_seller (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Get_weekly_report_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите получить недельный отчет', reply_markup=cancel)

# получить недельный отчет по селлеру
@admin_router.message(F.text, Get_weekly_report_by_seller.seller_id)
async def get_weekly_report_by_seller (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    await state.update_data(seller_id=seller_id)
    await state.set_state(Get_weekly_report_by_seller.date_from)
    await message.answer(f'Введите date_from', reply_markup=cancel)


# получить недельный отчет по селлеру
@admin_router.message(F.text, Get_weekly_report_by_seller.date_from)
async def get_weekly_report_by_seller (message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.update_data(date_from=message.text)
    await state.set_state(Get_weekly_report_by_seller.date_to)
    await message.answer(f'Введите date_to', reply_markup=cancel)


# получить недельный отчет по селлеру
@admin_router.message(F.text, Get_weekly_report_by_seller.date_to)
async def get_weekly_report_by_seller (message: Message, state:FSMContext):
    try:
        await delete_one_messages(message)
        print('тут')
        date_to = datetime.strptime(message.text, '%d.%m.%Y').replace(hour=23,minute=59,second=59,microsecond=999999)
        data = await state.get_data()
        seller_id = data['seller_id']
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        date_from = datetime.strptime(data['date_from'], '%d.%m.%Y')
        if not date_to:
            date_to = await end_of_Reporting_Week_func()
        date_from = (date_to - timedelta(days=6)).replace(hour=00, minute=00, second=00, microsecond=00)
        report_creation_type = 'admin'
        print(seller_id, date_from, date_to)
        await state.clear()
        await get_weekly_pl(seller_id = seller_id,
                            report_creation_type = report_creation_type,
                            date_from=date_from,
                            date_to=date_to,
                            requestor_chat_id=None)
        await message.answer(f'Отчет по seller_id {seller_id}, {seller_title} подготовлен.', reply_markup=cancel)
    except Exception as e:
        logging.exception(f"Unexpected error in sales_report_compilation: {str(e)}")
        await send_message_to_admin(f'Ошибка: {str(e)}')
        return False

# пересчитать PL за 3 месяца по селлеру
@admin_router.callback_query(F.data == 'recalculate_PL_for_3_months_by_seller')
async def recalculate_PL_for_3_months_by_seller (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Recalculate_PL_for_3_months_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите пересчитать PL', reply_markup=cancel)

# пересчитать PL за 3 месяца по селлеру
@admin_router.message(F.text, Recalculate_PL_for_3_months_by_seller.seller_id)
async def recalculate_PL_for_3_months_by_seller (message: Message, state:FSMContext):
    async with async_session() as session:
        await delete_one_messages(message)
        seller_id = int(message.text)
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await state.clear()
        await admin_recalculate_pl_results_for_three_months_for_seller_id(seller_id)
        query = sqlalchemy.update(Marketing_costs_wb).where(Marketing_costs_wb.seller_id == seller_id,
                                                            Marketing_costs_wb.cost_allocated == True).values(cost_allocated=False)
        await session.execute(query)
        await session.commit()
        # await temp_test_function2(seller_id=seller_id)
        await message.answer(f'PL за 3 месяца по seller_id {seller_id}, {seller_title} пересчитан.', reply_markup=cancel)


# пересчитать PL по селлеру c даты
@admin_router.callback_query(F.data == 'recalculate_PL_by_seller_from_date')
async def recalculate_PL_by_seller_from_date (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Recalculate_PL_by_seller_from_date.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите пересчитать PL', reply_markup=cancel)

# пересчитать PL по селлеру c даты
@admin_router.message(F.text, Recalculate_PL_by_seller_from_date.seller_id)
async def recalculate_PL_by_seller_from_date (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    await state.update_data(seller_id=seller_id)
    await state.set_state(Recalculate_PL_by_seller_from_date.date_from)
    await message.answer(f'Введите дату, с которой хотите пересчитать PL в формате 01.01.2025', reply_markup=cancel)

# пересчитать PL по селлеру c даты
@admin_router.message(F.text, Recalculate_PL_by_seller_from_date.date_from)
async def recalculate_PL_by_seller_from_date (message: Message, state:FSMContext):
    async with async_session() as session:
        await delete_one_messages(message)
        date_from_for_pl = datetime.strptime(message.text, '%d.%m.%Y')
        data = await state.get_data()
        seller_id = data['seller_id']
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await state.clear()
        await admin_recalculate_pl_results_for_seller_id_from_date(session, seller_id, date_from_for_pl)
        await message.answer(f'PL по seller_id {seller_id}, {seller_title} c {str(date_from_for_pl)} пересчитан.', reply_markup=cancel)


# пересчитать PL за 3 месяца по селлеру
@admin_router.callback_query(F.data == 'recalculate_PL_for_3_months_all_sellers')
async def recalculate_PL_for_3_months_all_sellers (callback: CallbackQuery):
    async with async_session() as session:
        await delete_one_messages(callback.message)
        sellers = await session.execute(select(Seller.id).where(Seller.status == 'Active'))
        sellers = sellers.mappings().all()
        for seller in sellers:
            seller_id = seller['id']
            logging.info(f'Пересчитываем PL по seller_id {seller_id}')
            await admin_recalculate_pl_results_for_three_months_for_seller_id(seller_id)
            query = sqlalchemy.update(Marketing_costs_wb).where(Marketing_costs_wb.seller_id == seller_id,
                                                                Marketing_costs_wb.cost_allocated == True).values(cost_allocated=False)
            await session.execute(query)
            await allocate_marketing_costs_to_sku(session=session, seller_id=seller_id)
            await session.commit()
            logging.info(f'Пересчитали PL по seller_id {seller_id}')

# скачать недельный фин отчет по селлеру
@admin_router.callback_query(F.data == 'get_weekly_wb_fin_report_by_seller')
async def get_weekly_wb_fin_report_by_seller (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Get_weekly_wb_fin_report_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите скачать недельный фин.отчет ВБ', reply_markup=cancel)

# скачать недельный фин отчет по селлеру
@admin_router.message(F.text, Get_weekly_wb_fin_report_by_seller.seller_id)
async def get_weekly_wb_fin_report_by_seller (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
    date_from = await start_of_Reporting_Week_func()
    date_to = await end_of_Reporting_Week_func()
    await get_and_check_sales_report(seller_id=seller_id, date_from= date_from, date_to=date_to)
    await message.answer(f'Фин. отчет ВБ по seller_id {seller_id}, {seller_title} скачан.', reply_markup=cancel)

# Рассылки
@admin_router.message(F.text == 'Рассылки')
async def system_status (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        await message.answer(text='Выберите пункт меню', parse_mode=ParseMode.HTML, reply_markup=sending_messages_kb)
    else:
        await message.answer('У вас нет никаких прав!!!')

@admin_router.callback_query(F.data == 'send_message_to_all_users')
async def admin_func (callback:CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    if callback.from_user.id == config.ADMIN_ID:
        await state.clear()
        await callback.message.answer('Введите текст сообщения', reply_markup=cancel)
        await state.set_state(Send_message_to_users.message_text)
    else:
        await callback.message.answer('У вас нет никаких прав!!!')

@admin_router.message(F.text, Send_message_to_users.message_text)
async def system_status (message: Message, state:FSMContext):
    if message.from_user.id == config.ADMIN_ID:
        message_text = message.text
        await send_message_to_all_users(message_text=message_text)
        await message.answer(text='Сообщение отправлено всем юзерам.', parse_mode=ParseMode.HTML, reply_markup=admin_kb(message.from_user.id))
    else:
        await message.answer('У вас нет никаких прав!!!')


# функция для тестов
@admin_router.callback_query(F.data == 'send_support_reply')
async def test_function (callback: CallbackQuery):
    async with (async_session() as session):
        await delete_one_messages(callback.message)
        await bot.send_message(chat_id=7620997811, text='Добрый день!'
                                                                '\nМы получили Ваш вопрос в службу поддержки Findirexpress.'
                                                                '\nНапишите мне напрямую @lenarvaleev, обсудим.')

        await callback.message.answer('Выполнено!')

# функция для тестов
@admin_router.callback_query(F.data == 'add_doctype_name')
async def add_doctype_name_for_seller (callback: CallbackQuery, state:FSMContext):
    async with (async_session() as session):
        await delete_one_messages(callback.message)
        await state.set_state(Add_doctype.seller_id)
        await callback.message.answer(f'Введите seller_id, по которому хотите загрузить doctype', reply_markup=cancel)

# @admin_router.message(F.text, Add_doctype.seller_id)
# async def add_doctype_name_for_seller (message: Message, state:FSMContext):
#     async with async_session() as session:
#         await delete_one_messages(message)
#         seller_id = int(message.text)
#         seller_title = await get_company_name_by_seller_id(seller_id)
#         await state.clear()
#         await add_doc_type_name(seller_id=seller_id)
#         await message.answer(f'Doctype по seller_id {seller_id}, {seller_title} добавлен.', reply_markup=cancel)

# Проверка распределения маркетинга по селлеру
@admin_router.callback_query(F.data == 'check_marketing_allocation')
async def check_paid_acceptance_by_seller_id (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Check_marketing_allocation_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите запустить проверку маркетинга', reply_markup=cancel)

# Проверка распределения маркетинга по селлеру
@admin_router.message(F.text, Check_marketing_allocation_by_seller.seller_id)
async def main_reporting_function_by_seller_id (message: Message, state:FSMContext):
    async with async_session() as session:
        await delete_one_messages(message)
        seller_id = int(message.text)
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await state.clear()
        await check_marketing_costs_allocation (session=session, seller_id=seller_id)
        await message.answer(f'Проверка маркетинга по seller_id {seller_id}, {seller_title} выполнена.', reply_markup=cancel)

# Найти ошибки в аллокации маркетинга по advert_id по селлеру
@admin_router.callback_query(F.data == 'check_marketing_allocation_by_advert_id')
async def check_paid_acceptance_by_seller_id (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Check_marketing_allocation_by_seller_by_advert_id.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите запустить проверку маркетинга', reply_markup=cancel)

# Найти ошибки в аллокации маркетинга по advert_id по селлеру
@admin_router.message(F.text, Check_marketing_allocation_by_seller_by_advert_id.seller_id)
async def main_reporting_function_by_seller_id (message: Message, state:FSMContext):
    async with async_session() as session:
        await delete_one_messages(message)
        seller_id = int(message.text)
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await state.clear()
        await get_wrong_marketing_allocation_items (session=session, seller_id=seller_id)
        await message.answer(f'Проверка маркетинга по seller_id {seller_id}, {seller_title} выполнена.', reply_markup=cancel)

# Проверка детализацию расходов по хранению по селлеру
@admin_router.callback_query(F.data == 'check_storage_costs_allocation')
async def check_paid_acceptance_by_seller_id (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Check_storage_allocation_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите запустить проверку хранения', reply_markup=cancel)

# Проверка детализацию расходов по хранению по селлеру
@admin_router.message(F.text, Check_storage_allocation_by_seller.seller_id)
async def main_reporting_function_by_seller_id (message: Message, state:FSMContext):
    async with async_session() as session:
        await delete_one_messages(message)
        seller_id = int(message.text)
        seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
        await state.clear()
        await check_storage_costs_allocation (session=session, seller_id=seller_id)
        await message.answer(f'Проверка хранения по seller_id {seller_id}, {seller_title} выполнена.', reply_markup=cancel)

# Проверка актов приемки по селлеру
@admin_router.callback_query(F.data == 'check_paid_acceptance')
async def check_paid_acceptance_by_seller_id (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.set_state(Check_paid_acceptance_by_seller.seller_id)
    await callback.message.answer(f'Введите seller_id, по которому хотите запустить проверку актов приемки', reply_markup=cancel)

# Проверка актов приемки по селлеру
@admin_router.message(F.text, Check_paid_acceptance_by_seller.seller_id)
async def main_reporting_function_by_seller_id (message: Message, state:FSMContext):
    await delete_one_messages(message)
    seller_id = int(message.text)
    seller_title = await get_company_name_by_seller_id(seller_id=seller_id)
    await state.clear()
    await get_wrong_paid_acceptance_items(seller_id=seller_id)
    await message.answer(f'Проверка актов приемки по seller_id {seller_id}, {seller_title} выполнена.', reply_markup=cancel)

# Восстановить названия в goods_costs
@admin_router.callback_query(F.data == 'restore_goods_costs_names')
async def test_function (callback: CallbackQuery):
    await delete_one_messages(callback.message)
    await restore_goods_cost_names()
    await callback.message.answer('Выполнено!')


# Для временных функций
@admin_router.callback_query(F.data == 'temp_functions')
async def test_function (callback: CallbackQuery):
    async with (async_session() as session):
        await delete_one_messages(callback.message)
        await get_brand_to_goods_cost()
        await make_brand_name_upper_case()

        await callback.message.answer('Выполнено!')


# функция для тестов
@admin_router.callback_query(F.data == 'test_functions')
async def test_function (callback: CallbackQuery):
    async with (async_session() as session):
        await delete_one_messages(callback.message)

        # await get_marketing_costs_from_wb(session=session, seller_id=12, date_from_str='2025-04-23', date_to_str='2025-04-23')

        # advert_id=[{'id': 24771500, 'dates': ["2025-04-18", "2025-04-19"]}]
        # response = await get_marketing_stats_from_wb(session=session, seller_id=13, advert_ids=advert_id)
        # print(response)

        #
        # # async with session.begin_nested():
        # #     query = sqlalchemy.delete(Marketing_costs_by_SKU).where(Marketing_costs_by_SKU.seller_id == seller_id)
        # #     await session.execute(query)
        # # await session.commit()
        # #
        # # async with session.begin_nested():
        # #     query = sqlalchemy.update(Marketing_costs_wb).where(Marketing_costs_wb.seller_id == seller_id,
        # #                                                         Marketing_costs_wb.cost_allocated == True).values(
        # #                                                             cost_allocated=False)
        # #     await session.execute(query)
        # # await session.commit()
        #
        # # await restore_goods_cost2()
        # result = await check_cost(session=session, seller_id=2)
        # print(result)
        date_from = await start_of_Prior_Week_func()
        date_to = await end_of_Prior_Week_func()
        await get_and_check_sales_report(seller_id=3, date_from=date_from, date_to=date_to)
        await callback.message.answer('Выполнено!')

@with_session
async def get_sellers_report_from_wb(session):
    date_from = '2024-01-01'
    date_to = '2025-04-20'
    date_from = datetime.strptime(date_from, '%Y-%m-%d').replace(hour=00, minute=00, second=00, microsecond=00)
    date_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)
    # print(date_from, date_to)
    await get_and_check_sales_report(session=session, seller_id=1,date_from=date_from, date_to=date_to)


@with_session
async def temp_test_function(session, seller_id):
    # date_from = '2025-04-14'
    # date_to = '2025-04-20'
    # rrdid = 0
    # active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
    # await get_sales_data(session, seller_id, date_from, date_to, rrdid, active_api)
    # await download_fin_report(session,seller_id)
    # await get_orders_by_seller(session,seller_id)
    # await get_orders_by_nm_by_seller(session, seller_id)
    # await get_storage_costs_by_seller(session, seller_id)
    # await get_supplies_by_seller_id(session,seller_id)
    pass



