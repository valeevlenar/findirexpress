from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.database.models import async_session


@asynccontextmanager
async def db_session():
    """Унифицированное управление сессиями БД"""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()