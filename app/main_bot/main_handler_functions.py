import logging
from app.admin.admin_message import send_message_to_admin
from app.database.support_functions import get_companies_list, get_active_subscription_type_and_end_date_by_seller_id
from app.managers.managers_functions import create_companies_list_for_manager_user_tg_id, get_manager_companies_list
from app.wrappers import with_session

@with_session
async def create_my_companies_str(session, user_tg_id):
    try:
        companies_list = await get_companies_list(session, user_tg_id)
        companies_list_str = f'Ваши компании:\n'
        if companies_list:
            i = 1
            for company in companies_list:
                companies_list_str += f'{str(i)}. {company['seller_title']}\n'
                i += 1
        else:
            companies_list_str += f'У Вас нет своих компаний.\n'

        manager_companies = await create_companies_list_for_manager_user_tg_id(session, user_tg_id)
        if manager_companies:
            m = 1
            companies_list_str += f'\nКомпании, в которых вы менеджер:\n'
            for manager_company in manager_companies:
                companies_list_str += f'{str(m)}. {manager_company['seller_title']}\n'
                m += 1
        return companies_list_str

    except Exception as e:
        await send_message_to_admin(f'Ошибка в подготовке списка моих компаний'
                            f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def create_my_subscriptions_str(session, user_tg_id):
    try:
        companies_list = await get_companies_list(session, user_tg_id)
        manager_companies_list = await get_manager_companies_list(session, user_tg_id)
        companies_balance_str = ""
        manager_companies_balance_str = ""
        message_text = ''
        i = 1
        if companies_list:
            for company in companies_list:
                seller_id = company['seller_id']
                active_subscription_name, subscription_date_end_str = await get_active_subscription_type_and_end_date_by_seller_id(session=session,
                                                                                                                                   seller_id=seller_id)
                if not active_subscription_name:
                    active_subscription_name = 'Нет действующей подписки'
                    subscription_date_end_str = '-'
                else:
                    pass
                companies_balance_str += (f'<b>{str(i)}. {company['seller_title']}:</b>'
                                          f'\nподписка: {active_subscription_name}'
                                          f'\nподписка действует до: {subscription_date_end_str}\n\n')
                i += 1
            message_text += (f'<b>Действующие подписки по Вашим компаниям:\n</b>'
                            f'\n{companies_balance_str}')
        if manager_companies_list:
            for company in manager_companies_list:
                seller_id = company['seller_id']
                active_subscription_name, subscription_date_end_str = await get_active_subscription_type_and_end_date_by_seller_id(session=session,
                                                                                                                                   seller_id=seller_id)
                if not active_subscription_name:
                    active_subscription_name = 'Нет действующей подписки'
                    subscription_date_end_str = '-'
                else:
                    pass
                manager_companies_balance_str += (f'<b>{str(i)}. {company['seller_title']}:</b>'
                                          f'\nподписка: {active_subscription_name}'
                                          f'\nподписка действует до: {subscription_date_end_str}\n\n')
                i += 1
            message_text += (f'<b>Действующие подписки по компаниям в которых Вы менеджер:\n</b>'
                            f'\n{manager_companies_balance_str}')

        return message_text

    except Exception as e:
        await send_message_to_admin(f'Ошибка в подготовке списка подписок'
                            f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False