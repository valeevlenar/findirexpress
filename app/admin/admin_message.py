from aiogram.enums import ParseMode

import config
from app.admin.admin_bot import admin_bot
from app.admin.admin_keyboards import admin_kb

# Отправка сообщения админу
async def send_message_to_admin(text):
    chat_id = config.ADMIN_ID
    await admin_bot.send_message(chat_id=chat_id, text=text, parse_mode=None, reply_markup=admin_kb(chat_id))
