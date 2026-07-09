import logging

from sqlalchemy import select

from app.admin.admin_message import send_message_to_admin
from app.database.models import Subscriptions, Transactions
from app.dates import end_of_yesterday_func
from app.wrappers import with_session


@with_session
async def subscriptions_revenue_recognition(session):
    try:
        end_of_yesterday = await end_of_yesterday_func()
        active_subscriptions = await session.execute(select(Subscriptions.id,
                                                            Subscriptions.subscription_type,
                                                            Subscriptions.status,
                                                            Subscriptions.amount,
                                                            Subscriptions.duration,
                                                            Subscriptions.start_date,
                                                            Subscriptions.end_date,
                                                            Subscriptions.discount_amount,
                                                            Subscriptions.net_amount,
                                                            Subscriptions.seller_id).
                                                 where(Subscriptions.status == 'active',
                                                       Subscriptions.subscription_type!='trial',
                                                       Subscriptions.subscription_type!= 'promo',
                                                       Subscriptions.start_date<=end_of_yesterday,
                                                       Subscriptions.end_date>end_of_yesterday))
        active_subscriptions = active_subscriptions.mappings().all()
        for subscription in active_subscriptions:
            seller_id = subscription.seller_id
            subscription_duration_days = (subscription.end_date - subscription.start_date).days
            daily_gross_revenue = subscription.amount/subscription_duration_days
            daily_promocodes = subscription.discount_amount/subscription_duration_days
            daily_net_revenue = subscription.net_amount/subscription_duration_days
            async with session.begin_nested():
                gross_revenue = Transactions(seller_id=seller_id,
                                           amount = daily_gross_revenue,
                                           transaction_type = 'debit',
                                           transaction_stream = 'revenue',
                                           created_at = end_of_yesterday
                                           )
                session.add(gross_revenue)

                promocodes = Transactions(seller_id=seller_id,
                                           amount=daily_promocodes,
                                           transaction_type='credit',
                                           transaction_stream='promocodes',
                                           created_at=end_of_yesterday
                                           )
                session.add(promocodes)

                net_revenue = Transactions(seller_id=seller_id,
                                           amount=daily_net_revenue,
                                           transaction_type='debit',
                                           transaction_stream='net_revenue',
                                           created_at=end_of_yesterday
                                           )
                session.add(net_revenue)

            await session.commit()

    except Exception as e:
        await send_message_to_admin(text=f'Ошибка при расчете выручки'
                                         f'{e}')
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e, )
