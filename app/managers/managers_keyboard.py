from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Managers
from app.managers.managers_functions import get_managers_list
from app.wrappers import with_session
from sqlalchemy import select

managers_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Мои менеджеры', callback_data="my_managers")],
    [InlineKeyboardButton(text='Добавить менеджера', callback_data="add_manager")],
    [InlineKeyboardButton(text='Настройки доступа менеджера', callback_data="manager_access_settings")],
    [InlineKeyboardButton(text='Удалить менеджера', callback_data="delete_manager")],
    [InlineKeyboardButton(text='↩️ Назад в Главное меню',callback_data='back_to_main_menu')]],
    resize_keyboard=True)

managers_cancel = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel')]],
                            resize_keyboard=True)

managers_approve = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ Подтвердить',callback_data='approve_managers')],
    [InlineKeyboardButton(text='↩️ Отменить',callback_data='cancel_managers')]],
                            resize_keyboard=True)

async def create_managers_keyboard(seller_id):
    managers_list_buttons = InlineKeyboardBuilder()
    managers_list = await get_managers_list(seller_id = seller_id)
    for manager in managers_list:
        managers_list_buttons.button(text=manager['username'],callback_data=str(manager['manager_id']), resize_keyboard=True)
    managers_list_buttons.button(text='↩️ Отменить', callback_data='cancel',resize_keyboard=True)
    managers_list_buttons.adjust(1,1)
    return managers_list_buttons

@with_session
async def create_managers_access_settings_keyboard(session, manager_id, access_settings):
    manager_access_setting_buttons = InlineKeyboardBuilder()
    if not manager_id:
        access_settings_buttons_dict = access_settings
    else:
        access_settings_buttons_dict = await session.execute(select(Managers.api_access,
                                                                    Managers.cost_access,
                                                                    Managers.price_control_access).
                                                             where(Managers.id == manager_id))
        access_settings_buttons_dict = access_settings_buttons_dict.mappings().first()
    if access_settings_buttons_dict['api_access']:
        manager_access_setting_buttons.button(text=f'Выключить доступ к обновлению api',
                                              callback_data=f'api_access_switch', resize_keyboard=True)
    else:
        manager_access_setting_buttons.button(text=f'Включить доступ к обновлению api',
                                              callback_data=f'api_access_switch', resize_keyboard=True)
    if access_settings_buttons_dict['cost_access']:
        manager_access_setting_buttons.button(text=f'Выключить доступ к обновлению себестоимости',
                                              callback_data=f'cost_access_switch', resize_keyboard=True)
    else:
        manager_access_setting_buttons.button(text=f'Включить доступ к обновлению себестоимости',
                                              callback_data=f'cost_access_switch', resize_keyboard=True)
    if access_settings_buttons_dict['price_control_access']:
        manager_access_setting_buttons.button(text=f'Выключить доступ к функции "Контроль цен"',
                                              callback_data=f'price_control_access_switch', resize_keyboard=True)
    else:
        manager_access_setting_buttons.button(text=f'Включить доступ к функции "Контроль цен"',
                                              callback_data=f'price_control_access_switch', resize_keyboard=True)
    manager_access_setting_buttons.button(text='✅ Сохранить настройки', callback_data='save_access_settings', resize_keyboard=True)
    manager_access_setting_buttons.button(text='↩️ Отменить', callback_data='cancel',resize_keyboard=True)
    manager_access_setting_buttons.adjust(1,1)
    return manager_access_setting_buttons