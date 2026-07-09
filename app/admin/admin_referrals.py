from datetime import datetime
import logging
from sqlalchemy import select

import config
from app.admin.admin_message import send_message_to_admin

from app.database.models import async_session, ReferralChannels
from app.wrappers import with_session


@with_session
async def create_referral_channel(session, channel_name, channel_contacts_data, channel_reward_conditions):
    try:
        channel_id = await check_referral_channel_exist(session=session, channel_name=channel_name)
        if not channel_id:
            referral_link = f'{config.main_bot_url_link}?start={channel_name}'
            referral_channel = ReferralChannels(channel_type = 'channel',
                                                channel_name = channel_name,
                                                channel_tg_id = None,
                                                channel_user_id = None,
                                                channel_contacts_data = channel_contacts_data,
                                                referral_code = channel_name,
                                                referral_link = referral_link,
                                                channel_reward_type = 'custom',
                                                channel_reward_conditions = channel_reward_conditions,
                                                channel_reward_percent = None,
                                                channel_reward_amount = None,
                                                created_at = datetime.now())
            session.add(referral_channel)
            await session.commit()
            return referral_link
        else:
            return False
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при создании нового канала'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def check_referral_channel_exist (session, channel_name):
    try:
        channel_id = await session.scalar(select(ReferralChannels.id).where(ReferralChannels.channel_name == channel_name))
        if not channel_id:
            return False
        else:
            return channel_id
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при проверке канала'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)