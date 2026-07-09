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


async def main():
    setup_logging()
    # 1. Получаем прокси из .env вместо жесткого хардкода
    proxy_url = os.getenv("PROXY_URL")

    # 2. Подменяем сессии у ботов ТОЛЬКО если прокси указан в .env
    if proxy_url:
        logging.info(f"Запуск ботов через прокси: {proxy_url}")
        bot.session = AiohttpSession(proxy=proxy_url)
        admin_bot.session = AiohttpSession(proxy=proxy_url)
        support_bot.session = AiohttpSession(proxy=proxy_url)
    else:
        logging.info("Запуск ботов напрямую (без прокси через локальный VPN)")

    await async_main()

    dp = Dispatcher(bot=bot, storage=MemoryStorage())
    dp.include_routers(router, price_control_router, managers_router, report_router, cost_of_sales_router)

    admin_dp = Dispatcher(bot=admin_bot, storage=MemoryStorage())
    admin_dp.include_router(admin_router)

    support_dp = Dispatcher(bot=support_bot, storage=MemoryStorage())
    support_dp.include_router(support_router)

    scheduler.start()  # Запускаем планировщик

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await admin_bot.delete_webhook(drop_pending_updates=True)
        await asyncio.gather(
            dp.start_polling(bot),
            admin_dp.start_polling(admin_bot),
            support_dp.start_polling(support_bot)
        )
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        await bot.session.close()
        await admin_bot.session.close()
        await support_bot.session.close()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())