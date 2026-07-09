import logging
import io
from aiogram import Bot
from aiogram.types import BufferedInputFile
from openpyxl import Workbook

from app.admin.admin_message import send_message_to_admin
from app.database.support_functions import get_chat_id_by_seller_id
from app.managers.managers_functions import get_managers_chat_ids_with_cost_access_by_seller_id
from app.wrappers import log_and_notify_admin, with_session


# Фукнкция принимает эксель в формате wb openpyxl, находит чат с пользователем и отправляет ему файл.
@log_and_notify_admin
async def send_file_to_user(session, bot: Bot, seller_id, file: Workbook, filename,requestor_tg_id, caption):
    try:
        file_in_io = io.BytesIO()
        file.save(file_in_io)
        file_to_send = file_in_io.getvalue()

        if not requestor_tg_id:
            owner_chat_id = await get_chat_id_by_seller_id(session=session, seller_id=seller_id)
            await bot.send_document(chat_id=owner_chat_id, document=BufferedInputFile(file_to_send, filename), caption=caption)
            manager_chat_ids = await get_managers_chat_ids_with_cost_access_by_seller_id(session=session, seller_id=seller_id)
            if manager_chat_ids:
                for chat_id in manager_chat_ids:
                    await bot.send_document(chat_id=chat_id, document=BufferedInputFile(file_to_send, filename), caption=caption)
        else:
            await bot.send_document(chat_id=requestor_tg_id, document=BufferedInputFile(file_to_send, filename), caption=caption)

        return True
    except Exception as e:
        # Запись ошибки в лог
        logging.info(f'Seller_id: {seller_id}. Ошибка при отправке шаблона с себестоимостью')
        await send_message_to_admin(f'Seller_id: {seller_id}. Ошибка при отправке шаблона с себестоимостью')
        logging.exception("An error occurred: %s", exc_info=e)



