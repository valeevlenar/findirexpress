import asyncio
from functools import wraps
import logging
from app.admin.admin_message import send_message_to_admin
import inspect


def per_seller_lock(seller_id_param: str = "seller_id", timeout: int = 600):
    def decorator(func):
        locks = {}
        manager_lock = asyncio.Lock()

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Получаем информацию о параметрах функции
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Извлекаем seller_id
            if seller_id_param not in bound_args.arguments:
                raise ValueError(f"Параметр {seller_id_param} не найден в {func.__name__}")

            seller_id = bound_args.arguments[seller_id_param]

            # Управление блокировками
            async with manager_lock:
                if seller_id not in locks:
                    locks[seller_id] = asyncio.Lock()
                lock = locks[seller_id]

            try:
                await asyncio.wait_for(lock.acquire(), timeout=timeout)
                return await func(*args, **kwargs)
            except asyncio.TimeoutError:
                logging.error(f"Timeout для seller_id {seller_id}")
                await send_message_to_admin(f"⚠️ Таймаут блокировки seller_id {seller_id}")
                return None
            finally:
                if lock.locked():
                    lock.release()
                async with manager_lock:
                    if seller_id in locks and not locks[seller_id].locked():
                        del locks[seller_id]

        return wrapper

    return decorator