import logging
from app.admin.admin_message import send_message_to_admin
from app.database.models import ApiKeys, Subscriptions, Promocodes, Managers
from app.database.classes.stocks import Stock
from app.database.models import User, Seller
from sqlalchemy import select

from app.dates import today_str_func
from app.wrappers import with_session, log_and_notify_admin


@with_session
async def check_user(session, tg_id):
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if not user:
        return True
    else:
        return False

@with_session
async def check_company(session, seller_inn):
    company = await session.scalar(select(Seller).
                                   where(Seller.seller_inn == seller_inn))
    if not company:
        return True
    else:
        return False

@with_session
async def check_api(session, api_key):
    api_key = await session.scalar(select(ApiKeys).where(ApiKeys.wb_api == api_key))
    if not api_key:
        return True
    else:
        return False

# Проверяем есть ли у пользователя копании:
@with_session
async def check_user_companies(session, tg_id):
    company = await session.scalar(select(Seller).where(Seller.user_tg_id == tg_id,
                                                             Seller.status!='Deleted',
                                                             Seller.status!='Blocked'))
    if not company:
        return False
    else:
        return True

# Проверяем есть ли у компании действующая подписка:
@with_session
async def check_active_subscription(session, seller_id):
    subscription = await session.scalar(select(Subscriptions.id).
                                        where(Subscriptions.seller_id == seller_id,
                                                             Subscriptions.status =='active'))
    if not subscription:
        return False
    else:
        return True

# Проверяем статусы пользователя при нажатии кнопок:
@with_session
async def check_user_status(session, tg_id):
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if not user:
        return False
    else: return True

# Проверяем загружены ли сегодняшние Stocks по селлеру:
@log_and_notify_admin
async def check_seller_stocks_downloaded_today(session, seller_id):
    today_str = await today_str_func()
    stocks = await session.scalar(select(Stock.id).
                                  where(Stock.seller_id == seller_id,
                                        Stock.date_in_stock_str==today_str))
    if not stocks:
        return False
    else: return True

# Проверяем, есть ли такой промокод:
@with_session
async def check_active_promocode(session, promocode_title):
    active_promocode_id = await session.scalar(select(Promocodes.id).
                                               where(Promocodes.code_title == promocode_title,
                                                     Promocodes.is_active == True))
    if not active_promocode_id:
        return False

    else:
        return active_promocode_id

# Проверяем доступ user_tg_id к компании
@log_and_notify_admin
async def check_user_access_to_seller_id_by_user_tg_id(session, seller_id, user_tg_id):
    try:
        owner_access = await session.scalar(select(Seller.id).
                                            where(Seller.user_tg_id == user_tg_id,
                                                  Seller.status != 'Blocked',
                                                  Seller.status != 'Deleted'))
        manager_access = await session.scalar(select(Managers.seller_id).
                                              outerjoin(User, User.id == Managers.user_id).
                                              outerjoin(Seller, Seller.id == Managers.seller_id).
                                          where(User.tg_id == user_tg_id,
                                                Managers.access_is_active == True,
                                                Seller.status != 'Blocked',
                                                Seller.status != 'Deleted'))
        if owner_access or manager_access:
            return True
        else:
            return False

    except Exception as e:
            await send_message_to_admin(f'Ошибка в проверке доступа к компании для user_tg_id'
                                        f'\nSeller_id: {seller_id}'
                                        f'\nUser_tg_id: {user_tg_id}'
                                        f'\nОшибка: {e}')
            # Запись ошибки в лог
            logging.exception("An error occurred: %s", exc_info=e)
            return False

@with_session
async def check_user_access_to_api_for_user_tg_id(session, seller_id, user_tg_id):
    try:
        owner_access = await session.scalar(select(Seller.id).
                                            where(Seller.user_tg_id == user_tg_id,
                                                  Seller.id == seller_id,
                                                  Seller.status != 'Blocked',
                                                  Seller.status != 'Deleted'))
        manager_access = await session.scalar(select(Managers.api_access).
                                              outerjoin(User, User.id == Managers.user_id).
                                              outerjoin(Seller, Seller.id == Managers.seller_id).
                                      where(User.tg_id == user_tg_id,
                                            Managers.seller_id == seller_id,
                                            Managers.api_access == True,
                                            Managers.access_is_active == True,
                                            Seller.status != 'Blocked',
                                            Seller.status != 'Deleted'))
        if owner_access or manager_access:
            return True
        else:
            return False

    except Exception as e:
        await send_message_to_admin(f'Ошибка в проверке доступа к апи для user_tg_id'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nUser_tg_id: {user_tg_id}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def check_user_access_to_cost_for_user_tg_id(session, seller_id, user_tg_id):
    try:
        owner_access = await session.scalar(select(Seller.id).
                                            where(Seller.user_tg_id == user_tg_id,
                                                  Seller.id == seller_id,
                                                  Seller.status != 'Blocked',
                                                  Seller.status != 'Deleted'))
        manager_access = await session.scalar(select(Managers.cost_access).
                                              outerjoin(User, User.id == Managers.user_id).
                                              outerjoin(Seller, Seller.id == Managers.seller_id).
                                      where(User.tg_id == user_tg_id,
                                            Managers.seller_id == seller_id,
                                            Managers.cost_access == True,
                                            Managers.access_is_active == True,
                                            Seller.status != 'Blocked',
                                            Seller.status != 'Deleted'))

        if owner_access or manager_access:
            return True
        else:
            return False

    except Exception as e:
        await send_message_to_admin(f'Ошибка в проверке доступа к себестоимости для user_tg_id'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nUser_tg_id: {user_tg_id}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def check_user_access_to_price_control_for_user_tg_id(session, seller_id, user_tg_id):
    try:
        owner_access = await session.scalar(select(Seller.id).
                                            where(Seller.user_tg_id == user_tg_id,
                                                  Seller.id == seller_id,
                                                  Seller.status != 'Blocked',
                                                  Seller.status != 'Deleted'))
        manager_access = await session.scalar(select(Managers.price_control_access).
                                              outerjoin(User, User.id == Managers.user_id).
                                              outerjoin(Seller, Seller.id == Managers.seller_id).
                                      where(User.tg_id == user_tg_id,
                                            Managers.seller_id == seller_id,
                                            Managers.price_control_access == True,
                                            Managers.access_is_active == True,
                                            Seller.status != 'Blocked',
                                            Seller.status != 'Deleted'))

        if owner_access or manager_access:
            return True
        else:
            return False

    except Exception as e:
        await send_message_to_admin(f'Ошибка в проверке доступа к себестоимости для user_tg_id'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nUser_tg_id: {user_tg_id}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False

@with_session
async def check_user_access_to_managers_for_user_tg_id(session, seller_id, user_tg_id):
    try:
        owner_access = await session.scalar(select(Seller.id).
                                            where(Seller.user_tg_id == user_tg_id,
                                                  Seller.id == seller_id,
                                                  Seller.status != 'Blocked',
                                                  Seller.status != 'Deleted'))
        if owner_access:
            return True
        else:
            return False

    except Exception as e:
        await send_message_to_admin(f'Ошибка в проверке доступа к себестоимости для user_tg_id'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nUser_tg_id: {user_tg_id}'
                                    f'\nОшибка: {e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        return False
