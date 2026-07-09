from aiogram.fsm.state import StatesGroup, State


class Managers_addition (StatesGroup):
    company_name = State()
    seller_id = State()
    user_id = State()
    access_settings = State()
    access_settings_update = State()
    save_settings = State()
    approve_manager = State()

class Managers_deletion (StatesGroup):
    company_name = State()
    seller_id = State()
    manager_id = State()
    approve_manager_deletion = State()

class Managers_change_access_settings (StatesGroup):
    company_name = State()
    seller_id = State()
    manager_id = State()
    user_id = State()
    access_settings = State()
    access_settings_update = State()
    save_settings = State()
    approve_manager = State()
