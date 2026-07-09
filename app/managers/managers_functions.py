import uuid
import logging
from datetime import datetime, timedelta
import config
import sqlalchemy
from sqlalchemy import select
from app.admin.admin_message import send_message_to_admin
from app.database.models import Managers_tokens, Managers, User, Seller
from app.database.support_functions import get_user_by_tg_id, get_company_name_by_seller_id, \
    get_chat_id_by_user_id, get_user_name_by_user_id
from app.main_bot.main_bot import bot
from app.wrappers import log_and_notify_admin, with_session


@with_session
async def generate_managers_invite_link(session, seller_id, user_id, access_settings):
    try:
        token = str(await generate_invite_token())
        invite_link = f'{config.main_bot_url_link}?start=invite_{token}'
        async with session.begin_nested():
            manager_token = Managers_tokens(token = token,
                                            seller_id = seller_id,
                                            created_by_user_id = user_id,
                                            expires_at = (datetime.now()+timedelta(days=1)),
                                            api_access = access_settings['api_access'],
                                            cost_access = access_settings['cost_access'],
                                            price_control_access = access_settings['price_control_access'],
                                            is_used = False)
            session.add(manager_token)
        await session.commit()
        return invite_link
    except Exception as e:
            await send_message_to_admin(f'Ошибка в создании пригласительного токена'
                                        f'\nSeller_id: {seller_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@log_and_notify_admin
async def generate_invite_token():
    token = uuid.uuid4()
    return token

@with_session
async def process_managers_invite_token(session, invite_token, user_tg_id):
    try:
        token_checked = await check_invite_token(session, invite_token)
        if token_checked:
            user_id = await get_user_by_tg_id(session, user_tg_id)
            seller_id = await session.scalar(select(Managers_tokens.seller_id).
                                             where(Managers_tokens.token == invite_token))
            process_managers_invite_token_result = None
            if not user_id:
                process_managers_invite_token_result = 'no_user'
            else:
                granted_by_user_id = await session.scalar(select(Managers_tokens.created_by_user_id).
                                                          where(Managers_tokens.token == invite_token))
                if granted_by_user_id == user_id:
                    process_managers_invite_token_result = 'owner'
                else:
                    if await check_manager_access_for_seller_id_by_user_id(session=session, seller_id=seller_id,user_id=user_id):
                        process_managers_invite_token_result = 'already_access_granted'
                    else:
                        access_settings = await session.execute(select(Managers_tokens.api_access,
                                                                       Managers_tokens.cost_access,
                                                                       Managers_tokens.price_control_access).
                                                                where(Managers_tokens.token == invite_token))
                        access_settings = access_settings.mappings().first()

                        if await add_new_manager_by_invite(session=session,
                                                           invite_token=invite_token,
                                                           user_id=user_id,
                                                           seller_id=seller_id,
                                                           granted_by_user_id=granted_by_user_id,
                                                           access_settings=access_settings):
                            await update_invite_token_used(session=session,
                                                           invite_token=invite_token)
                            await notify_invite_user_new_manager_registered(session, seller_id, granted_by_user_id, user_id)
                            process_managers_invite_token_result = 'access_granted'
                        else:
                            pass
            return seller_id, process_managers_invite_token_result
        else:
            seller_id = None
            process_managers_invite_token_result = 'invalid_token'
            # print('status', process_managers_invite_token_result)
            return seller_id, process_managers_invite_token_result
    except Exception as e:
        await send_message_to_admin(f'Ошибка в обработке пригласительного токена'
                                    f'\ntoken: {invite_token}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@log_and_notify_admin
async def add_new_manager_by_invite(session, invite_token, user_id, seller_id, granted_by_user_id, access_settings):
    try:
        async with session.begin_nested():
            manager_to_add = Managers(user_id = user_id,
                                      seller_id = seller_id,
                                      granted_by_user_id = granted_by_user_id,
                                      created_at = datetime.now(),
                                      access_is_active = True,
                                      role = None,
                                      api_access = access_settings['api_access'],
                                      cost_access = access_settings['cost_access'],
                                      price_control_access = access_settings['price_control_access'],
                                      updated_at = datetime.now())
            session.add(manager_to_add)
        await session.commit()
        return True

    except Exception as e:
        await send_message_to_admin(f'Ошибка в добавлении менеджера в базу'
                                    f'\ntoken: {invite_token}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@log_and_notify_admin
async def check_invite_token(session, invite_token):
    try:
        token_to_check_id = await session.scalar(select(Managers_tokens.id).
                                           where(Managers_tokens.token == invite_token,
                                                 Managers_tokens.expires_at>=datetime.now(),
                                                 Managers_tokens.is_used == False))
        if not token_to_check_id:
            return False
        else:
            return True
    except Exception as e:
            await send_message_to_admin(f'Ошибка в проверке пригласительного токена'
                                        f'\ntoken: {invite_token}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@log_and_notify_admin
async def update_invite_token_used(session, invite_token):
    try:
        async with session.begin_nested():
            query = sqlalchemy.update(Managers_tokens).where(Managers_tokens.token == invite_token).values(is_used=True)
            await session.execute(query)
        await session.commit()

    except Exception as e:
        await send_message_to_admin(f'Ошибка в update пригласительного токена'
                                    f'\ntoken: {invite_token}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def get_invite_token_created_by_tg_id(session, invite_token):
    try:
        created_by_user_id = await session.scalar(select(Managers_tokens.created_by_user_id).
                                           where(Managers_tokens.token == invite_token,
                                                 Managers_tokens.expires_at>=datetime.now(),
                                                 Managers_tokens.is_used == False))

        tg_id_created_by = await session.scalar(select(User.tg_id).where(User.id == created_by_user_id))
        return tg_id_created_by
    except Exception as e:
            await send_message_to_admin(f'Ошибка в проверке пригласительного токена'
                                        f'\ntoken: {invite_token}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@log_and_notify_admin
async def check_manager_access_for_seller_id_by_user_id(session, seller_id, user_id):
    try:
        access = await session.scalar(select(Managers.id).where(Managers.seller_id == seller_id,
                                                                Managers.user_id == user_id,
                                                                Managers.access_is_active == True))
        if not access:
            return False
        else:
            return True
    except Exception as e:
            await send_message_to_admin(f'Ошибка в проверке доступа менеджера'
                                        f'\nSeller_id: {seller_id}'
                                        f'\nUser_id: {user_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@with_session
async def check_manager_access_for_seller_id_by_user_tg_id(session, seller_id, user_tg_id):
    try:
        access = await session.scalar(select(Managers.id).
                                      outerjoin(User, User.id == Managers.user_id).
                                      where(Managers.seller_id == seller_id,
                                            Managers.access_is_active == True,
                                            User.tg_id == user_tg_id))
        if not access:
            return False
        else:
            return True
    except Exception as e:
            await send_message_to_admin(f'Ошибка в проверке доступа менеджера'
                                        f'\nSeller_id: {seller_id}'
                                        f'\nUser_tg_id: {user_tg_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@log_and_notify_admin
async def notify_invite_user_new_manager_registered(session, seller_id, granted_by_user_id, user_id):
    try:
        chat_id = await get_chat_id_by_user_id(session, granted_by_user_id)
        seller_title = await get_company_name_by_seller_id(session=session,
                                                           seller_id=seller_id)
        user_name = await get_user_name_by_user_id(session=session, user_id=user_id)
        message_text = f'Пользователь {user_name} добавлен в качестве менеджера компании {seller_title}!'
        await bot.send_message(chat_id=chat_id,text=message_text)

    except Exception as e:
            await send_message_to_admin(f'Ошибка в отправке уведомления об использовании токена'
                                        f'\nseller_id: {seller_id}'
                                        f'\ngranted_by_user_id: {granted_by_user_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@with_session
async def create_my_managers_list(session, user_tg_id):
    try:
        user_id = await get_user_by_tg_id(session, user_tg_id)
        companies_with_managers = await session.execute(select(Managers.seller_id).
                                                        join(Seller, Seller.id == Managers.seller_id).
                                                        where(Managers.granted_by_user_id == user_id,
                                                              Managers.access_is_active==True,
                                                              Seller.status != 'Deleted',
                                                              Seller.status != 'Blocked').
                                                        group_by(Managers.seller_id).
                                                        order_by(Managers.seller_id.asc()))
        companies_with_managers = companies_with_managers.mappings().all()

        if companies_with_managers:
            my_managers_str = ""
            company_counter = 1
            for company in companies_with_managers:
                seller_title = await get_company_name_by_seller_id(session=session,
                                                                   seller_id=company['seller_id'])
                company_str = f'\n{company_counter}. {seller_title}:'
                my_managers_str += company_str
                managers = await session.execute(select(Managers.user_id).
                                             where(Managers.granted_by_user_id == user_id,
                                                   Managers.seller_id == company['seller_id'],
                                                   Managers.access_is_active==True))
                managers = managers.mappings().all()
                manager_counter = 1
                for manager in managers:
                    user_name = await session.scalar(select(User.username).
                                                     where(User.id == manager['user_id']))
                    manager_str = f'\n  {manager_counter}. {user_name}'
                    my_managers_str += manager_str
                    manager_counter += 1
                my_managers_str += f'\n'
                company_counter +=1

        else:
            my_managers_str = f'У Вас нет назначенных менеджеров.'

        return my_managers_str

    except Exception as e:
            await send_message_to_admin(f'Ошибка в подготовке списка менеджеров'
                                        f'\nuser_tg_id: {user_tg_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@with_session
async def get_managers_list (session, seller_id):
    try:
        managers = await session.execute(select(User.username, Managers.id.label('manager_id')).
                                         outerjoin(Managers, Managers.user_id == User.id).
                                         where(Managers.seller_id == seller_id,
                                               Managers.access_is_active==True))
        managers = managers.mappings().all()
        return managers

    except Exception as e:
        await send_message_to_admin(f'Ошибка в подготовке списка менеджеров'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def get_manager_name_by_manager_id(session, manager_id):
    try:
        manager_user_name = await session.scalar(select(User.username).
                                         outerjoin(Managers, Managers.user_id == User.id).
                                         where(Managers.id == manager_id))

        return manager_user_name

    except Exception as e:
        await send_message_to_admin(f'Ошибка в получении имени менеджера'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def delete_manager_from_db(session, manager_id):
    try:
        async with session.begin_nested():
            query = sqlalchemy.update(Managers).where(Managers.id == manager_id,
                                                      Managers.access_is_active == True).values(access_is_active=False)
            await session.execute(query)
        await session.commit()

        return True

    except Exception as e:
        await send_message_to_admin(f'Ошибка при удалении менеджера'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@log_and_notify_admin
async def create_companies_list_for_manager_user_tg_id(session, user_tg_id):
    try:
        companies = await session.execute(select(Seller.id.label('seller_id'), Seller.seller_title).
                                          outerjoin(Managers, Managers.seller_id == Seller.id).
                                          outerjoin(User, User.id == Managers.user_id).
                                          where(User.tg_id == user_tg_id,
                                            Managers.access_is_active == True))
        companies = companies.mappings().all()
        return companies

    except Exception as e:
            await send_message_to_admin(f'Ошибка в подготовке списка компаний для user_tg_id'
                                        f'\nUser_tg_id: {user_tg_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@with_session
async def check_manager_access_exist_for_manager_user_tg_id(session, user_tg_id):
    try:
        company = await session.scalar(select(Managers.seller_id).
                                          outerjoin(User, User.id == Managers.user_id).
                                          where(User.tg_id == user_tg_id,
                                            Managers.access_is_active == True))
        if company:
            return True
        else:
            return False

    except Exception as e:
            await send_message_to_admin(f'Ошибка в подготовке списка компания для user_tg_id'
                                        f'\nUser_tg_id: {user_tg_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

# Получить список компаний по юзеру:
@log_and_notify_admin
async def get_manager_companies_list(session, tg_id):
    result = await session.execute(select(Seller.seller_title,
                                          Seller.id.label('seller_id')).
                                   join(Managers,Managers.seller_id == Seller.id).
                                   join(User, User.id == Managers.user_id).
                                   where(User.tg_id == tg_id,
                                         Managers.access_is_active == True,
                                         Seller.status !='Deleted',
                                         Seller.status !='Blocked'))
    companies_list = result.mappings().all()
    return companies_list

# Проверяем есть ли у пользователя копании:
@with_session
async def check_manager_companies(session, tg_id):
    manager_company = await session.scalar(select(Managers.seller_id).
                                           join(Seller, Seller.id == Managers.seller_id).
                                           join(User, User.id == Managers.user_id).
                                           where(User.tg_id == tg_id,
                                                 Managers.access_is_active == True,
                                                 Seller.status!='Deleted',
                                                 Seller.status!='Blocked'))
    if not manager_company:
        return False
    else:
        return True

# Получить chat_id по selle_id из базы:
@log_and_notify_admin
async def get_managers_chat_ids_by_seller_id(session, seller_id):
    chat_ids_list = await session.execute(select(User.tg_id).
                                     join(Managers,Managers.user_id == User.id).
                                     where(Managers.seller_id == seller_id,
                                           Managers.access_is_active == True).
                                     group_by(User.tg_id))
    chat_ids_list = chat_ids_list.mappings().all()
    chat_ids = []
    for item in chat_ids_list:
        chat_ids.append(int(item['tg_id']))
    return chat_ids

@log_and_notify_admin
async def get_managers_chat_ids_with_cost_access_by_seller_id(session, seller_id):
    chat_ids_list = await session.execute(select(User.tg_id).
                                     join(Managers,Managers.user_id == User.id).
                                     where(Managers.seller_id == seller_id,
                                           Managers.cost_access == True,
                                           Managers.access_is_active == True).
                                     group_by(User.tg_id))
    chat_ids_list = chat_ids_list.mappings().all()
    chat_ids = []
    for item in chat_ids_list:
        chat_ids.append(int(item['tg_id']))
    return chat_ids

@with_session
async def get_access_settings_for_manager_id(session, manager_id):
    access_settings = await session.execute(select(Managers.api_access,
                                                   Managers.cost_access,
                                                   Managers.price_control_access).
                                            where(Managers.id == manager_id))
    access_settings = access_settings.mappings().first()
    # print(access_settings)
    return access_settings

@with_session
async def update_access_settings_for_manager_id(session, seller_id, manager_id, granted_by_user_tg_id, access_settings):
    try:
        granted_by_user_id = await get_user_by_tg_id(session, granted_by_user_tg_id)
        async with session.begin_nested():
            query = (sqlalchemy.update(Managers).
                     where(Managers.id == manager_id,
                           Managers.seller_id == seller_id,
                           Managers.granted_by_user_id == granted_by_user_id).
                     values(api_access = access_settings['api_access'],
                            cost_access = access_settings['cost_access'],
                            price_control_access = access_settings['price_control_access']))
            await session.execute(query)
        await session.commit()
        return True
    except:
        return False
