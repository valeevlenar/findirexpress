import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.checks import check_user_status, check_user_companies, check_active_subscription
from app.database.support_functions import delete_one_messages
from app.main_bot import keyboards as kb
from app.main_bot.handlers import register_company_text, register_user_text, no_active_subscription_text
from app.main_bot.keyboards import reports_kb, create_companies_keyboard
from app.main_bot.states import Reports_on_demand
from app.managers.managers_functions import check_manager_companies
from app.reports.reporting_functions import send_report_on_demand

from app.reports.report_keyboards import generate_report_keyboard

report_router = Router()

@report_router.message(F.text == '🗄 Отчеты')
async def main_menu(message: Message, state:FSMContext):
    await delete_one_messages(message)
    await state.clear()
    if await check_user_status(tg_id=message.from_user.id):
        if await check_user_companies(tg_id=message.from_user.id) or await check_manager_companies(tg_id=message.from_user.id):
            try:
                await message.answer('Выберите тип отчета:', reply_markup=reports_kb)
            except Exception as e:
                # Запись ошибки в лог
                logging.exception("An error occurred: %s", exc_info=e)
        else: await message.answer(register_company_text, reply_markup=kb.main_kb(message.from_user.id))
    else:await message.answer(register_user_text, reply_markup=kb.main_kb(message.from_user.id))


@report_router.callback_query(F.data == 'send_weekly_report')
async def send_weekly_report (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(report_type="weekly")
    await state.set_state(Reports_on_demand.select_company)
    companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
    await callback.message.answer("Выберите компанию, по которой хотите получить отчет:",
                                  reply_markup=companies_list_buttons.as_markup())

@report_router.callback_query(F.data == 'send_monthly_report')
async def send_monthly_report (callback: CallbackQuery, state:FSMContext):
    await delete_one_messages(callback.message)
    await state.update_data(report_type="monthly")
    await state.set_state(Reports_on_demand.select_company)
    companies_list_buttons = await create_companies_keyboard(tg_id=callback.from_user.id)
    await callback.message.answer("Выберите компанию, по которой хотите получить отчет:",
                         reply_markup=companies_list_buttons.as_markup())


@report_router.callback_query(F.data, Reports_on_demand.select_company)
async def get_cost_file(callback: CallbackQuery, state: FSMContext):
    await delete_one_messages(callback.message)
    try:
        await state.update_data(seller_id=callback.data)
        data = await state.get_data()
        seller_id = int(data["seller_id"])
        if await check_active_subscription(seller_id=seller_id):
            data = await state.get_data()
            report_type = data["report_type"]
            report_keyboard = await generate_report_keyboard(page=0, report_type=report_type, seller_id=seller_id)
            await callback.message.answer("📅 Выберите период отчета:", reply_markup=report_keyboard)
            await state.set_state(Reports_on_demand.select_period)
        else:
            await state.clear()
            await callback.message.answer(no_active_subscription_text, reply_markup=kb.main_kb(callback.message.from_user.id))
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)


@report_router.callback_query(F.data.startswith("page:"), Reports_on_demand.select_period)
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обновленный обработчик пагинации"""
    data = await state.get_data()
    seller_id = int(data["seller_id"])
    _, report_type, page = callback.data.split(':')
    page = int(page)
    keyboard = await generate_report_keyboard(page, report_type, seller_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@report_router.callback_query(F.data.startswith("period:"), Reports_on_demand.select_period)
async def handle_period(callback: CallbackQuery, state: FSMContext):
    """Обновленный обработчик периода"""
    _, report_type, start_ts, end_ts = callback.data.split(':')
    start = datetime.fromtimestamp(float(start_ts)).replace(hour=00,minute=00,second=00,microsecond=00)
    end = datetime.fromtimestamp(float(end_ts)).replace(hour=23,minute=59,second=59,microsecond=999999)

    # Здесь формируем и отправляем отчет
    await callback.message.delete()
    data = await state.get_data()
    seller_id = int(data["seller_id"])
    await callback.message.answer("В скором времени мы пришлем Вам запрошенный отчет!")
    # print(start)
    # print(end)

    await send_report_on_demand(seller_id=seller_id,
                                report_type=data['report_type'],
                                requestor_tg_id=int(callback.from_user.id),
                                date_from=start,
                                date_to=end)
    await state.clear()
    await callback.answer()





