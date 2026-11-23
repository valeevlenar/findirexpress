import logging
import os
import asyncio
from aiogram import Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.admin.admin_bot import admin_bot
from app.admin.admin_handlers import admin_router
from app.main_bot.handlers import router
from app.database.models import async_main
from aiogram.fsm.storage.memory import MemoryStorage

from app.prices.price_handlers import price_control_router
from app.managers.managers_handlers import managers_router
from app.reports.report_handlers import report_router
from app.scheduler import scheduler
from app.main_bot.main_bot import bot
from app.support.support_bot import support_bot
from app.support.support_handlers import support_router
from app.main_bot.cost_of_sales_handlers import cost_of_sales_router
from app.logger import setup_logging
from app.bot_access import PrivateBotAccess, allowed_telegram_users
from app.marking.handlers import marking_router
from config import ADMIN_ID


def build_dispatchers():
    allowed_users = allowed_telegram_users()
    if ADMIN_ID not in allowed_users:
        raise ValueError("ADMIN_ID должен входить в ALLOWED_TELEGRAM_USER_IDS")
    bot_access = PrivateBotAccess(allowed_users)

    dp = Dispatcher(bot=bot, storage=MemoryStorage())
    dp.include_routers(marking_router, router, price_control_router, managers_router, report_router, cost_of_sales_router)

    admin_dp = Dispatcher(bot=admin_bot, storage=MemoryStorage())
    admin_dp.include_router(admin_router)

    support_dp = Dispatcher(bot=support_bot, storage=MemoryStorage())
    support_dp.include_router(support_router)

    for dispatcher in (dp, admin_dp, support_dp):
        dispatcher.update.outer_middleware(bot_access)
    return dp, admin_dp, support_dp


async def main():
    setup_logging()
    dp, admin_dp, support_dp = build_dispatchers()
    # 1. Получаем прокси из .env вместо жесткого хардкода
    proxy_url = os.getenv("PROXY_URL")

    # 2. Подменяем сессии у ботов ТОЛЬКО если прокси указан в .env
    if proxy_url:
        logging.info("Запуск ботов через прокси")
        bot.session = AiohttpSession(proxy=proxy_url)
        admin_bot.session = AiohttpSession(proxy=proxy_url)
        support_bot.session = AiohttpSession(proxy=proxy_url)
    else:
        logging.info("Запуск ботов напрямую (без прокси через локальный VPN)")

    await async_main()

    scheduler.start()  # Запускаем планировщик

    try:
        await bot.delete_webhook()
        await admin_bot.delete_webhook()
        await support_bot.delete_webhook()
        await asyncio.gather(
            dp.start_polling(bot),
            admin_dp.start_polling(admin_bot),
            support_dp.start_polling(support_bot)
        )
    except Exception:
        logging.exception("Сбой запуска или работы Telegram-ботов")
        raise
    finally:
        await bot.session.close()
        await admin_bot.session.close()
        await support_bot.session.close()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
