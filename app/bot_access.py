import os
import re

from aiogram import BaseMiddleware
from aiogram.enums import ChatType


def parse_allowed_telegram_users(value):
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2 or any(re.fullmatch(r"[1-9][0-9]{0,15}", part) is None for part in parts):
        raise ValueError("ALLOWED_TELEGRAM_USER_IDS: укажите два Telegram ID через запятую")
    ids = frozenset(map(int, parts))
    if len(ids) != 2:
        raise ValueError("ALLOWED_TELEGRAM_USER_IDS: укажите два разных Telegram ID")
    return ids


def allowed_telegram_users():
    return parse_allowed_telegram_users(os.getenv("ALLOWED_TELEGRAM_USER_IDS", ""))


def is_bot_admin(user_id):
    return user_id in allowed_telegram_users()


class PrivateBotAccess(BaseMiddleware):
    def __init__(self, allowed_user_ids):
        self.allowed_user_ids = allowed_user_ids

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        if user is None or chat is None or chat.type != ChatType.PRIVATE:
            return None
        if user.id not in self.allowed_user_ids:
            return None
        return await handler(event, data)
