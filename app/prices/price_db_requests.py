import logging
from datetime import datetime
import sqlalchemy
from app.database.models import Products_price, async_session, Seller
from app.wrappers import with_session, log_and_notify_admin


@log_and_notify_admin
async def new_product_price(session, seller_id, product, price_set_bool):
    async with session.begin_nested():
        product_to_db = Products_price(seller_id = seller_id,
                                       nm_id = product['nm_id'],
                                       vendorCode = product['vendorCode'],
                                       sizeID = product['sizeID'],
                                       price = product['price'],
                                       discountedPrice = product['discountedPrice'],
                                       clubDiscountedPrice = product['clubDiscountedPrice'],
                                       techSizeName = product['techSizeName'],
                                       currencyCode = product['currencyCode'],
                                       discount = product['discount'],
                                       clubDiscount = product['clubDiscount'],
                                       editableSizePrice = product['editableSizePrice'],
                                       price_set = price_set_bool,
                                       updated_at = datetime.now())
        session.add(product_to_db)
    await session.commit()

@with_session
async def set_new_prices_in_db(session, seller_id, products_with_id):
    try:
        for product in products_with_id:
            async with session.begin_nested():
                query = (sqlalchemy.update(Products_price).
                         where(Products_price.id == product['id'],
                               Products_price.seller_id==seller_id).
                         values(price= int(product['Цена (установленная селлером)']),
                                discount=int(product['Скидка, % (установленная селлером)']),
                                clubDiscount=int(product['Скидка для клуба ВБ, % (установленная селлером)']),
                                price_set=True,
                                updated_at=datetime.now()))
                await session.execute(query)
            await session.commit()
        return True
    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e, )
        return False

@with_session
async def enable_price_control_function (session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.update(Seller).where(Seller.id == seller_id).values(price_control=True,
                                                                               price_control_updated_at=datetime.now())
        await session.execute(query)
    await session.commit()

@with_session
async def disable_price_control_function (session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.update(Seller).where(Seller.id == seller_id).values(price_control=False,
                                                                               price_control_updated_at=datetime.now())
        await session.execute(query)
    await session.commit()
