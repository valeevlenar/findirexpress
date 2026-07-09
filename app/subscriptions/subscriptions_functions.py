from datetime import timedelta, datetime
from datetime import datetime as dt
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
import sqlalchemy.orm

from app.database.models import Subscriptions, Seller
from app.database.support_functions import get_chat_id_by_seller_id, get_company_name_by_seller_id

from app.payments.invoices import create_new_invoice
from app.promocodes.promocodes_functions import get_discount_amount_for_promocode, promocode_usage
from app.subscriptions.subscription_types import get_subscription_price_by_subscription_type, SubscriptionTypes, trial, \
    promo
from app.main_bot.main_bot import bot
from app.wrappers import log_and_notify_admin, with_session


# Деактивируем старые подписки со статусом pending_payment
@log_and_notify_admin
async def deactivate_pending_subscription(session, seller_id):
    pending_subscriptions = await session.execute(select(Subscriptions.id).
                                            where(Subscriptions.seller_id == seller_id,
                                                  Subscriptions.status=='payment_waiting'))
    for item in pending_subscriptions:
        async with session.begin_nested():
            query = sqlalchemy.update(Subscriptions).where(Subscriptions.id == item[0]).values(status='canceled',updated_at=datetime.now())
            await session.execute(query)
        await session.commit()

# Создаем новую подписку
@with_session
async def new_subscription_with_invoice(session, seller_id, subscription_type, date_start, promocode_id, requestor_tg_id):
    await deactivate_pending_subscription(session, seller_id)
    gross_price = await get_subscription_price_by_subscription_type(subscription_type)
    if promocode_id is None:
        discount_amount = 0
        subscription_net_price = gross_price
    else:
        discount_amount, subscription_net_price = await get_discount_amount_for_promocode(session=session,
                                                                                          subscription_type=subscription_type,
                                                                                          promocode_id=promocode_id)
    duration = 0
    for item in SubscriptionTypes.items:
        if item.subscription_type == subscription_type:
            duration = item.duration
    date_end = date_start + relativedelta(months=+duration)
    async with session.begin_nested():
        subscription = Subscriptions(seller_id=seller_id,
                                     subscription_type = subscription_type,
                                     amount = gross_price,
                                     duration = duration,
                                     start_date = date_start,
                                     end_date = date_end,
                                     status = 'payment_waiting',
                                     created_at = dt.now(),
                                     promocode_id = promocode_id,
                                     discount_amount = discount_amount,
                                     net_amount = subscription_net_price,
                                     updated_at = dt.now()
                                     )
        session.add(subscription)
        await session.flush()
        subscription_id = subscription.id
    await session.commit()

    # print (subscription_id)
    await create_new_invoice(session=session,
                             seller_id=seller_id,
                             subscription_id=subscription_id,
                             requestor_tg_id=requestor_tg_id,
                             subscription_duration=duration)
    if promocode_id is not None:
        await promocode_usage(session=session,
                              promocode_id=promocode_id,
                              subscription_id=subscription_id,
                              seller_id=seller_id,
                              discount_amount_used=discount_amount)

# Создаем новую подписку
@with_session
async def new_trial_subscription (session, seller_id):
    date_start = dt.now()
    date_end = date_start + timedelta(days=7)
    async with session.begin_nested():
        subscription = Subscriptions(seller_id=seller_id,
                                     subscription_type = trial.subscription_type,
                                     amount = trial.price,
                                     duration = 0,
                                     start_date = date_start,
                                     end_date = date_end,
                                     status = 'active',
                                     created_at = dt.now(),
                                     discount_amount = 0,
                                     net_amount = trial.price,
                                     updated_at = dt.now()
                                     )
        session.add(subscription)
    await session.commit()

# Проверяем сроки подписок
@with_session
async def check_subscriptions_dates(session):
    active_subscriptions = await session.execute(select(Subscriptions.id,
                                                        Subscriptions.seller_id,
                                                  Subscriptions.end_date).
                                           where(Subscriptions.status=='active'))
    active_subscriptions=active_subscriptions.mappings().all()
    for subscription in active_subscriptions:
        if subscription['end_date'] < dt.now():
            async with session.begin_nested():
                query = (sqlalchemy.update(Subscriptions).
                         where(Subscriptions.id == subscription['id']).
                         values(status='expired',
                                updated_at=dt.now()))
                await session.execute(query)
            await session.commit()

            seller_id = subscription['seller_id']
            active_subscription = await session.scalar(select(Subscriptions.id).
                                                 where(Subscriptions.seller_id == seller_id,
                                                       Subscriptions.status == 'active'))
            if not active_subscription:
                async with session.begin_nested():
                    query2 = (sqlalchemy.update(Seller).
                         where(Seller.id == seller_id).
                         values(service_status=False,
                                date_updated_ss=dt.now()))
                    await session.execute(query2)
                await session.commit()
            else:
                pass

# Проверяем текущую подписку
@with_session
async def check_subscriptions_status(session):
    active_sellers = await session.execute(select(Seller.id).where(Seller.status=='Active'))
    active_sellers = active_sellers.mappings().all()
    for seller in active_sellers:
        seller_id = seller['id']
        chat_id = await get_chat_id_by_seller_id(session, seller_id)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        subscription = await session.execute(select(Subscriptions.status,
                                                    Subscriptions.subscription_type,
                                                    Subscriptions.end_date,
                                                   Subscriptions.created_at).
                                             where(Subscriptions.seller_id==seller_id).order_by(Subscriptions.created_at.desc()))
        subscription = subscription.mappings().first()
        end_date = datetime.strftime(subscription['end_date'],'%Y-%m-%d')
        subscription_days_left = (subscription['end_date'] - dt.now()).days
        # print (seller_id, subscription_days_left, subscription['status'])
        if subscription['status']=='active' and subscription['subscription_type']=='trial':
            if subscription_days_left == 5 or subscription_days_left == 2:
                await bot.send_message(chat_id=chat_id,text=f'У {seller_title} действует пробная подписка на сервис.'
                                                                f'\nПодписка действует до {end_date}'
                                                                f'\n\nЧтобы продолжить пользоваться сервисом после этого '
                                                                f'срока оформите подписку в разделе "Подписка на сервис"')
        elif subscription['status']=='active' and subscription['subscription_type']=='promo':
            if subscription_days_left == 5 or subscription_days_left == 2:
                await bot.send_message(chat_id=chat_id,text=f'У {seller_title} заканчивается промо-подписка на сервис.'
                                                                f'\nПодписка действует до {end_date}'
                                                                f'\n\nЧтобы продолжить пользоваться сервисом после этого '
                                                                f'срока оформите подписку в разделе "Подписка на сервис"')
        elif subscription['status']=='active'and subscription['subscription_type']!='trial' and subscription['subscription_type']!='promo':
            if subscription_days_left==5:
                subscription_type = subscription['subscription_type']
                await bot.send_message(chat_id=chat_id,text=f'До окончания подписки на сервис по {seller_title} '
                                                            f'осталось {subscription_days_left} дней.'
                                                            f'\n\nНаправляем Вам счет на оплату для пролонгации подписки.'
                                                            f'\nНовая подписка будет активирована после оплаты счета. '
                                                            f'Срок новой подписки будет добавлен к текущей.'
                                                            f'\n\nЕсли Вы хотите выбрать другой вариант подписки, '
                                                            f'то зайдите в раздел "Подписка на сервис" и выберите подходящий вариант.')
                await new_subscription_with_invoice(session=session,
                                                    seller_id=seller_id,
                                                    subscription_type=subscription_type,
                                                    date_start=dt.now(),
                                                    promocode_id=None,
                                                    requestor_tg_id=None)
        elif subscription['status']=='payment_waiting':
            active_subscription = await session.scalar(select(Subscriptions.id).
                                                 where(Subscriptions.seller_id==seller_id,
                                                       Subscriptions.status=='active'))
            if not active_subscription:
                await bot.send_message(chat_id=chat_id, text=f'У {seller_title} закончилась подписка.'
                                                             f'\nКомпания больше не обслуживается.'
                                                             f'\n\n Чтобы продолжить пользоваться '
                                                             f'сервисом оплатите ранее направленный счет,'
                                                             f' либо оформите новую подписку в разделе "Подписка на сервис"')
        elif subscription['status']=='canceled':
            pass
        elif subscription['status'] == 'expired' and subscription['subscription_type'] == 'trial':
            if subscription_days_left==-1:
                await bot.send_message(chat_id=chat_id, text=f'Срок пробной подписки на сервис по {seller_title} истек.'
                                                         f'\n\nЧтобы продолжить пользоваться сервисом '
                                                                f'оформите подписку в разделе "Подписка на сервис"')




# Создаем новую промо подписку
@with_session
async def new_promo_subscription (session, data):
    date_start = dt.now()
    seller_inn = data['seller_inn']
    seller_id = await session.scalar(select(Seller.id).where(Seller.seller_inn==seller_inn,Seller.status=='Active'))
    if not seller_id:
        raise ValueError("Seller not found or inactive")
    duration = int(data ['duration'])
    date_end = date_start + relativedelta(months=+duration)
    async with session.begin_nested():
        subscription = Subscriptions(seller_id=seller_id,
                                     subscription_type = promo.subscription_type,
                                     amount = promo.price,
                                     duration = duration,
                                     start_date = date_start,
                                     end_date = date_end,
                                     status = 'active',
                                     created_at = dt.now(),
                                     discount_amount=0,
                                     net_amount=promo.price,
                                     updated_at=dt.now()
                                     )
        session.add(subscription)
        query = sqlalchemy.update(Seller).where(Seller.id == seller_id).values(service_status = True, date_updated_ss = datetime.now())
        await session.execute(query)
    await session.commit()