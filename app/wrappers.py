from functools import wraps
import inspect
import logging
from app.admin.admin_message import send_message_to_admin
from app.database.asyncontext import db_session
from app.database.models import async_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

def with_session(async_func):
    @wraps(async_func)
    async def wrapper(*args, **kwargs):
        sig = inspect.signature(async_func)
        parameters = sig.parameters

        # Проверка существующей сессии
        if 'session' in parameters:
            try:
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                if isinstance(bound_args.arguments.get('session'), AsyncSession):
                    return await async_func(*args, **kwargs)
            except TypeError:
                pass

        # Создание новой сессии
        async with db_session() as session:
            try:
                # Восстановленная логика позиционирования
                if args:
                    first_arg = args[0]
                    try:
                        is_class_entity = is_orm_entity(first_arg)
                    except Exception as e:
                        logging.warning(f"Entity check error: {e}")
                        is_class_entity = False

                    if is_class_entity:
                        new_args = (first_arg, session) + args[1:]
                    else:
                        new_args = (session,) + args
                else:
                    new_args = (session,)

                return await async_func(*new_args, **kwargs)
            except Exception as e:
                await handle_error(async_func.__name__, e)
                return False

    return wrapper

async def handle_error(func_name, error):
    await send_message_to_admin(f'Ошибка в функции {func_name}: {error}')
    logging.exception("An error occurred", exc_info=error)


def is_orm_entity(obj):
    """Проверка на ORM-сущность или класс"""
    return (
        inspect.isclass(obj)
        or isinstance(obj, DeclarativeBase)
        or hasattr(obj, '_sa_instance_state')
    )

def log_and_notify_admin(async_func):
    @wraps(async_func)
    async def wrapper(*args, **kwargs):
        try:
            return await async_func(*args, **kwargs)
        except Exception as e:
            await send_message_to_admin(f'Ошибка в функции {async_func.__name__}: {e}')
            logging.exception("An error occurred: %s", exc_info=e)
            return False
    return wrapper