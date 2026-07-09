from sqlalchemy import select
import sqlalchemy

from app.admin.admin_message import send_message_to_admin
from app.database.classes.sales import Sales
from app.database.classes.stocks import Stock
from app.database.models import Goods_cost
from app.wrappers import with_session


@with_session
async def get_brand_to_goods_cost(session):
    barcodes = await session.execute(select(Goods_cost.id,
                                            Goods_cost.barcode,
                                            Goods_cost.brand).
                                     where(Goods_cost.brand == None))

    barcodes = barcodes.mappings().all()
    empty_brand_names = len(barcodes)
    names_from_stock = 0
    names_from_sales = 0

    for item in barcodes:
        barcode = item['barcode']
        goods_cost_id = item['id']
        barcode_brand = await session.scalar(select(Stock.brand).
                                             where(Stock.barcode == barcode,
                                                   Stock.brand !=None))
        if barcode_brand:
            async with session.begin_nested():
                query = sqlalchemy.update(Goods_cost).where(Goods_cost.id == goods_cost_id).values(brand=barcode_brand)
                await session.execute(query)

            await session.commit()
            names_from_stock +=1
        else:
            barcode_brand = await session.scalar(select(Sales.brand_name).
                                             where(Sales.barcode == barcode,
                                                   Sales.brand_name != None))
            if barcode_brand:
                async with session.begin_nested():
                    query = sqlalchemy.update(Goods_cost).where(Goods_cost.id == goods_cost_id).values(
                        brand=barcode_brand)
                    await session.execute(query)

                await session.commit()
                names_from_sales += 1

    remaind_empty = empty_brand_names - names_from_stock - names_from_sales
    await send_message_to_admin(f'empty_brand_names: {empty_brand_names}'
                                f'\nnames_from_stock: {names_from_stock}'
                                f'\nnames_from_sales: {names_from_sales},'
                                f'\nremaind_empty: {remaind_empty}')


@with_session
async def make_brand_name_upper_case(session):
    barcodes = await session.execute(select(Goods_cost.id,
                                            Goods_cost.barcode,
                                            Goods_cost.brand).
                                     where(Goods_cost.brand != None))

    barcodes = barcodes.mappings().all()
    all_brand_names = len(barcodes)
    names_corrected = 0
    names_not_corrected = 0

    for item in barcodes:
        barcode = item['barcode']
        goods_cost_id = item['id']
        brand_name = item['brand']

        new_brand_name = str(brand_name).upper()

        if new_brand_name:
            async with session.begin_nested():
                query = sqlalchemy.update(Goods_cost).where(Goods_cost.id == goods_cost_id).values(brand=new_brand_name)
                await session.execute(query)

            await session.commit()
            names_corrected +=1
        else:
            names_not_corrected +=1

    remaind = all_brand_names - names_corrected - names_not_corrected
    await send_message_to_admin(f'empty_brand_names: {all_brand_names}'
                                f'\nnames_from_stock: {names_corrected}'
                                f'\nnames_not_corrected: {names_not_corrected},'
                                f'\nremaind_empty: {remaind}')
