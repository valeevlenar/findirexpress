from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Router, F
import config
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from app.support.support_keyboards import support_kb, support_menu

support_router = Router()
builder = InlineKeyboardBuilder()



@support_router.message(CommandStart())
async def start (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('⛑ Привет, хозяин! ⛑'
                         '\nВыбери пункт меню...', reply_markup=support_kb(message.from_user.id))
    else:
        await message.answer('⛑ Добро пожаловать в службу поддержки ФиндирЭкспресс! ⛑'
                             '\nНажмите кнопку "Отправить запрос", '
                             'введите свои контактные данные '
                             'и напишите свой вопрос.',
                             reply_markup=support_kb(message.from_user.id))

@support_router.callback_query(F.data == 'cancel')
async def cancel (callback: CallbackQuery, state:FSMContext):
    await state.clear()
    await callback.message.answer('Операция отменена.', reply_markup=support_kb(callback.message.from_user.id))


@support_router.message(F.text == '⛑ Support menu ⛑')
async def start (message: Message):
    if message.from_user.id == config.ADMIN_ID:
        await message.answer('Выбери пункт меню', reply_markup=support_menu)
    else:
        await message.answer('⛑ Вам сюда нельзя ⛑')


