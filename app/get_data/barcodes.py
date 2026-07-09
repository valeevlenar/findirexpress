from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import Goods_cost
from app.wrappers import with_session


@with_session
async def get_existing_barcodes(session, seller_id):
    """Получаем все штрих-коды продавца одним запросом"""
    result = await session.execute(
        select(Goods_cost.barcode).where(Goods_cost.seller_id == seller_id)
    )
    return {row[0] for row in result.scalars()}


@with_session
async def add_new_barcode(session, seller_id, seller_inn, stock_item):
    """Добавляет новый штрих-код с проверкой на race condition"""
    new_barcode = Goods_cost(
        seller_id=seller_id,
        seller_inn=seller_inn,
        barcode=stock_item['barcode'],
        subject_name=stock_item['subject'],
        nm_id=stock_item['nmId'],
        sa_name=stock_item['supplierArticle'].lower(),
        ts_name=stock_item['techSize'],
        cost=0
    )
    session.add(new_barcode)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Штрих-код уже добавлен в параллельной задаче
        pass
