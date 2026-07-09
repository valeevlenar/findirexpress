from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

builder = InlineKeyboardBuilder()

cost_of_sales_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Скачать шаблон с себестоимостью товаров',callback_data='send_cost_of_goods_template_to_user')],
    [InlineKeyboardButton(text='Загрузить шаблон с себестоимостью товаров',callback_data='get_cost_of_goods_template_from_user')],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
        resize_keyboard=True,
        input_field_placeholder='Выберите пункт меню')

get_cost_template_from_user_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Загрузить шаблон с себестоимостью товаров',callback_data='get_cost_of_goods_template_from_user')],
    [InlineKeyboardButton(text='↩️ Загружу позже',callback_data='back_to_main_menu')]],
        resize_keyboard=True,
        input_field_placeholder='Выберите пункт меню')

want_to_recalc_pl_for_last_week = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Пересчитать результаты за прошедшую неделю по новой себестоимости',
                          callback_data='recalc_last_week_with_new_costs_of_goods')],
    [InlineKeyboardButton(text='Не пересчитывать результаты за прошедшую неделю',
                          callback_data='do_not_recalc_last_week_with_new_costs_of_goods')]],
        resize_keyboard=True,
        input_field_placeholder='Выберите пункт меню')