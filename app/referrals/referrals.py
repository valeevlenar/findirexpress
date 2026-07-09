import uuid
import logging
from datetime import datetime
from sqlalchemy import select
import config
from app.admin.admin_message import send_message_to_admin
from app.database.models import async_session, ReferralChannels, Referrals, User
from app.database.support_functions import get_user_by_tg_id
from app.wrappers import with_session, log_and_notify_admin


async def generate_referral_code():
    str(uuid.uuid4())

@with_session
async def create_referral_channel_for_user(session, user_tg_id,username):
    try:
        referral_link = await check_referral_channel_for_user_exist(session=session,
                                                                    user_tg_id=user_tg_id)
        user_id = await get_user_by_tg_id(session=session, tg_id=user_tg_id)
        if not referral_link:
            referral_link = f'{config.main_bot_url_link}?start={user_tg_id}'
            async with session.begin_nested():
                referral_channel = ReferralChannels(channel_type = 'user',
                                                    channel_name = username,
                                                    channel_tg_id = user_tg_id,
                                                    channel_user_id = user_id,
                                                    channel_contacts_data = str(user_tg_id),
                                                    referral_code = str(user_tg_id),
                                                    referral_link = referral_link,
                                                    channel_reward_type = 'bonus subscription',
                                                    channel_reward_conditions = '1 m bonus subscription',
                                                    channel_reward_percent = None,
                                                    channel_reward_amount = None,
                                                    created_at = datetime.now())
                session.add(referral_channel)
            await session.commit()
            return referral_link
        else:
            return referral_link
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при создании реферальной ссылки для юзера'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def check_referral_channel_for_user_exist (session, user_tg_id):
    try:
        referral_link = await session.scalar(select(ReferralChannels.referral_link).where(ReferralChannels.channel_tg_id == user_tg_id))
        if not referral_link:
            return False
        else:
            return referral_link
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при проверке канала'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def track_referral_entrance(session, referral_code, user_tg_id):
    channel_id = await session.scalar(select(ReferralChannels.id).where(ReferralChannels.referral_code==referral_code))
    user_registered = await session.scalar(select(User.id).where(User.tg_id==user_tg_id))
    user_in_referrals = await session.scalar(select(Referrals.id).where(Referrals.user_tg_id==user_tg_id))
    if channel_id and not user_in_referrals and not user_registered:
        async with session.begin_nested():
            new_referral_entrance = Referrals(user_tg_id = user_tg_id,
                                              channel_id = channel_id,
                                              created_at = datetime.now())
            session.add(new_referral_entrance)
        await session.commit()