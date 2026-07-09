from datetime import datetime
from sqlalchemy import select

from app.database.models import async_session, PromocodeUsage, Promocodes
from app.subscriptions.subscription_types import get_subscription_price_by_subscription_type
from app.wrappers import log_and_notify_admin, with_session


@log_and_notify_admin
async def promocode_usage(session, promocode_id, subscription_id, seller_id, discount_amount_used):
    async with session.begin_nested():
        promocode_usage = PromocodeUsage(promocode_id = promocode_id,
                                         subscription_id = subscription_id,
                                         seller_id = seller_id,
                                         discount_amount_used = discount_amount_used,
                                         date_used = datetime.now())
        session.add(promocode_usage)
    await session.commit()

@with_session
async def get_discount_amount_for_promocode (session, subscription_type, promocode_id):
    subscription_gross_price = await get_subscription_price_by_subscription_type(subscription_type)
    promocode_type = await session.scalar(select(Promocodes.promo_type).
                                          where(Promocodes.id==promocode_id))
    if promocode_type == 'percentage':
        discount_percent = await session.scalar(select(Promocodes.discount_percentage).
                                          where(Promocodes.id==promocode_id))
        discount_amount = subscription_gross_price * discount_percent
    elif promocode_type == 'amount':
        discount_amount = await session.scalar(select(Promocodes.discount_amount).
                                                where(Promocodes.id == promocode_id))
    subscription_net_price = subscription_gross_price - discount_amount
    return discount_amount, subscription_net_price




