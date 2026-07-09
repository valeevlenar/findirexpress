from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

import config

# Клавиатура

def support_kb(tg_id: int):
    kb_list = [
        [KeyboardButton(text='⛑ Отправить вопрос ⛑')]]

    if tg_id == config.ADMIN_ID:
        kb_list.append([KeyboardButton(text="⛑ Support menu ⛑")])
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, input_field_placeholder='Выберите пункт меню')
    return keyboard

cancel_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Отменить', callback_data="cancel")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')


support_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='ЧТо-то', callback_data="potom")]
    ], resize_keyboard=True, input_field_placeholder='Выберите пункт меню')
