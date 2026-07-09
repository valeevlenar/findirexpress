from aiogram.fsm.state import StatesGroup, State


class Register_user(StatesGroup):
    user_name = State()
    user_phone_number = State()

class Register_manager_user(StatesGroup):
    user_name = State()
    user_phone_number = State()
    token = State()
    approve = State()


class Register_company(StatesGroup):
    company_name = State()
    inn = State()
    e_mail = State()
    wb_api = State()
    tax_base = State()
    tax_rate = State()
    tax_system_str = State()
    tax_object = State()
    tax_rate_str = State()


class Send_cost_template_to_user(StatesGroup):
    seller_id = State()
    cost_file = State()


class Get_cost_template_from_user(StatesGroup):
    seller_id = State()
    cost_file = State()
    requestor_tg_id = State()


class Delete_company(StatesGroup):
    select_company = State()
    user_tg_id = State()
    seller_id = State()
    delete_company_confirmation = State()


class Reports_on_demand(StatesGroup):
    select_company = State()
    user_tg_id = State()
    seller_id = State()
    report_type = State()
    select_period = State()


class New_api_key(StatesGroup):
    select_company = State()
    user_tg_id = State()
    seller_id = State()
    new_api_await = State()


class Support_ticket (StatesGroup):
    company_name = State()
    tg_id = State()
    tg_username = State()
    description = State()


class New_subscription (StatesGroup):
    company_name = State()
    seller_id = State()
    subscription_type = State()
    subscription_name = State()
    is_promocode = State()
    promocode = State ()
    promocode_id = State ()
    approve = State()

class Price_control (StatesGroup):
    company_name = State()
    seller_id = State()
    price_control_menu = State()
    price_template = State()
    enable = State()
    disable = State()
    approve_enable = State()
    approve_disable = State()
    new_api_await = State()
    price_template_upload = State()
    price_template_approve = State()
    price_template_product_list = State()
