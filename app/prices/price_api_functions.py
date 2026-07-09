from datetime import timedelta, datetime
import logging
import sqlalchemy
from sqlalchemy import select

from app.admin.admin_message import send_message_to_admin
from app.database.models import async_session, Seller, PriceApiKeys
from app.database.support_functions import get_chat_id_by_seller_id, get_company_name_by_seller_id
from app.main_bot.main_bot import bot
from app.wrappers import with_session, log_and_notify_admin


@with_session
async def check_price_api_exist(session, seller_id):
    active_price_api = await session.scalar(select(PriceApiKeys.id).
                                      where(PriceApiKeys.seller_id==seller_id,
                                            PriceApiKeys.api_status =='active'))
    if not active_price_api:
        return False
    else:
        return True

@with_session
async def check_price_api(session, api_key):
    api_key = await session.scalar(select(PriceApiKeys).where(PriceApiKeys.price_wb_api == api_key))
    if not api_key:
        return True
    else:
        return False

@log_and_notify_admin
async def unauthorised_price_api_identified(session, seller_id, wb_api):
    async with session.begin_nested():
        query = (sqlalchemy.update(PriceApiKeys).
                 where(PriceApiKeys.seller_id == seller_id,
                       PriceApiKeys.price_wb_api==wb_api).
                 values(api_status='unauthorised'))
        await session.execute(query)
    await session.commit()
    await unauthorised_price_api_notification(session=session, seller_id=seller_id)

@with_session
async def new_price_api_key_upload(session, seller_id, new_api_key):
    try:
        prior_api = await session.scalar(select(PriceApiKeys.price_wb_api).
                                         where(PriceApiKeys.seller_id == seller_id,
                                               PriceApiKeys.api_status=='active'))
        if not prior_api:
            pass
        else:
            async with session.begin_nested():
                query = (sqlalchemy.update(PriceApiKeys).
                         where(PriceApiKeys.seller_id == seller_id,
                               PriceApiKeys.price_wb_api == prior_api).
                         values(api_status='unauthorised'))
                await session.execute(query)
            await session.commit()

        async with session.begin_nested():
            session.add(PriceApiKeys(seller_id=seller_id,
                                     price_wb_api=new_api_key,
                                     api_date_created=datetime.now(),
                                     api_status='active'))
        await session.commit()
    except Exception as e:
        await send_message_to_admin(text=f'Ошибка при загрузке нового API в категории "Цены"'
                                         f'\nSeller_id = {seller_id}'
                                         f'\n{e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

# Проверка апи кода по дате истечения срока годности:
@with_session
async def daily_check_price_api(session):
    # Получаем список селлеров для проверки API:
    companies_for_price_api_check = await session.execute(select(Seller.id).
                                                          where(Seller.status == 'Active',
                                                                Seller.service_status == True,
                                                                Seller.price_control == True))
    companies_for_price_api_check = companies_for_price_api_check.mappings().all()

    # Последовательно для каждого селлера
    for seller in companies_for_price_api_check:
        seller_id = seller['id']
        api_to_check = await session.execute(select(PriceApiKeys.id,
                                                     PriceApiKeys.api_date_created).
                                              where(PriceApiKeys.seller_id==seller_id,
                                                    PriceApiKeys.api_status=='active').
                                             order_by(PriceApiKeys.api_date_created.desc()))
        api_to_check = api_to_check.mappings().first()
        api_created_at = api_to_check['api_date_created']
        api_expiry_date = api_created_at+timedelta(days=180)
        today = datetime.now()
        api_days_left = (api_expiry_date-today).days
        if api_days_left<10:
            chat_id = await get_chat_id_by_seller_id(session=session,
                                                     seller_id=seller_id)
            seller_title = await get_company_name_by_seller_id(session=session,
                                                               seller_id=seller_id)
            await bot.send_message(chat_id=chat_id,
                                   text=f'❗️ Внимание ❗️ '
                                        f'\n\nСрок действия API-ключа в категории "Цены и скидки" по {seller_title} истекает '
                                        f'менее чем через {api_days_left} дней.'
                                        f'\n\nЧтобы продолжать без перебоев пользоваться '
                                        f'сервисом выгрузите новый API-ключ для категории "Цены и скидки" в личном кабинете ВБ '
                                        f'и загрузите его в разделе "Контроль цен".')
        else: pass

# Уведомление о неавторизованном API:
@log_and_notify_admin
async def unauthorised_price_api_notification (session, seller_id):
    chat_id = await get_chat_id_by_seller_id(session=session, seller_id=seller_id)
    seller_title = await get_company_name_by_seller_id(session=session, seller_id=seller_id)
    await bot.send_message(chat_id=chat_id,text=f'Ваш API-ключ по {seller_title} по категории "Цены и скидки" не авторизован, возможно истек срок действия.'
                                                    f'\n\nЧтобы продолжать пользоваться '
                                                    f'сервисом выгрузите новый API-ключ в личном кабинете ВБ '
                                            f'и загрузите его в разделе "🏦 Контроль цен".')
