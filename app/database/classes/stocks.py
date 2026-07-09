
from datetime import datetime, timedelta

from sqlalchemy import select, Float, ForeignKey, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base
from app.dates import today_str_func
from app.wrappers import with_session, log_and_notify_admin


class Stock(Base):
    __tablename__ = 'stock'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    seller_inn: Mapped[str] = mapped_column(String(120))
    date_in_stock: Mapped[datetime] = mapped_column(DateTime)
    date_in_stock_str: Mapped[str] = mapped_column(String(120))
    warehouse_name: Mapped[str] = mapped_column(String(120))
    supplier_article: Mapped[str] = mapped_column(String(120))
    nmid: Mapped[int]=mapped_column(Integer)
    barcode: Mapped[str] = mapped_column(ForeignKey('goods_cost.barcode'))
    quantity: Mapped[int]=mapped_column(Integer)
    inwaytoclient: Mapped[int]=mapped_column(Integer)
    inwayfromclient: Mapped[int]=mapped_column(Integer)
    quantityfull: Mapped[int]=mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(120))
    brand: Mapped[str] = mapped_column(String(120))
    techsize: Mapped[str] = mapped_column(String(120))
    price: Mapped[float] = mapped_column(Float)
    discount: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    total_at_sell_price: Mapped[float] = mapped_column(Float)
    cost_per_item: Mapped[float] = mapped_column(Float)
    total_at_cost: Mapped[float] = mapped_column(Float)

    @classmethod
    @with_session
    async def check_stock_data_today(cls, session, seller_id):
        # Проверяем, что за сегодня выгружены Stocks:

        today_str = await today_str_func()
        stock = await session.scalar(select(cls.id).
                                     where(cls.seller_id == seller_id,
                                           cls.date_in_stock_str == today_str))
        if not stock:
            return False
        else:
            return True

    @classmethod
    @with_session
    async def get_stock_data_at_date_end_or_current(cls, session, seller_id, date_to):
        # Берем на 1 день позже, так как остатки выгружаются в 00.02
        stocks_quantity = None
        new_date = date_to
        date_str = datetime.strftime(new_date, '%Y-%m-%d')
        while not stocks_quantity and new_date<=datetime.now():
            new_date = new_date + timedelta(days=1)
            date_str = datetime.strftime(new_date,'%Y-%m-%d')
            # print(date_str)
            stocks_quantity = await session.scalar(select(func.sum(cls.quantityfull)).
                                                   where(cls.seller_id == seller_id,
                                                         cls.date_in_stock_str == date_str))
        if not stocks_quantity:
            stocks_quantity = 0.0

        stocks_total_at_cost = await session.scalar(select(func.sum(cls.total_at_cost)).
                                                    where(cls.seller_id == seller_id,
                                                          cls.date_in_stock_str == date_str)) or 0.0

        stocks_total_at_sell_price = await session.scalar(select(func.sum(cls.total_at_sell_price)).
                                                          where(cls.seller_id == seller_id,
                                                                cls.date_in_stock_str == date_str)) or 0.0

        stocks_data = {'stocks_quantity': stocks_quantity,
                       'stocks_total_at_cost': stocks_total_at_cost,
                       'stocks_total_at_sell_price': stocks_total_at_sell_price,
                       'new_date':new_date}

        # print(stocks_data)

        return stocks_data

    @classmethod
    @log_and_notify_admin
    async def get_stock_data_at_date_end(cls, session, seller_id, date_to):
        # Берем на 1 день позже, так как остатки выгружаются в 00.02
        date_plus_one = date_to + timedelta(days=1)
        date_str = datetime.strftime(date_plus_one, '%Y-%m-%d')
        stocks_quantity = await session.scalar(select(func.sum(cls.quantityfull)).
                                               where(cls.seller_id == seller_id,
                                                     cls.date_in_stock_str == date_str)) or 0.0

        stocks_total_at_cost = await session.scalar(select(func.sum(cls.total_at_cost)).
                                               where(cls.seller_id == seller_id,
                                                     cls.date_in_stock_str == date_str)) or 0.0

        stocks_total_at_sell_price = await session.scalar(select(func.sum(cls.total_at_sell_price)).
                                               where(cls.seller_id == seller_id,
                                                     cls.date_in_stock_str == date_str)) or 0.0

        stocks_data = {'stocks_quantity': stocks_quantity,
                       'stocks_total_at_cost': stocks_total_at_cost,
                       'stocks_total_at_sell_price': stocks_total_at_sell_price}
        return stocks_data

    @classmethod
    @with_session
    async def get_average_stocks_at_cost_or_current(cls, session, seller_id, date_from, date_to):
        # Берем на 1 день позже, так как остатки выгружаются в 00.02
        date_from_for_stock = date_from
        date_to_for_stock = date_to
        average_stocks_reporting_period_query = (select(Stock.date_in_stock_str,
                               func.sum(Stock.total_at_cost).label('total_stocks')).
                                              where(Stock.seller_id == seller_id,
                                                    Stock.date_in_stock >= date_from_for_stock,
                                                    Stock.date_in_stock <= (date_to_for_stock + timedelta(days=1))).
                                              group_by(Stock.date_in_stock_str).subquery())
        average_stocks_reporting_period = await session.scalar(select(func.avg(average_stocks_reporting_period_query.c.total_stocks)))

        if not average_stocks_reporting_period:

            stocks = await Stock.get_stock_data_at_date_end_or_current(seller_id=seller_id, date_to=date_to)
            average_stocks_reporting_period = stocks['stocks_total_at_cost']

        return average_stocks_reporting_period

    @classmethod
    @with_session
    async def get_average_stocks_count_or_current(cls, session, seller_id, date_from, date_to):
        # Берем на 1 день позже, так как остатки выгружаются в 00.02
        date_from_for_stock = date_from
        date_to_for_stock = date_to
        average_stocks_count_reporting_period_query = (select(Stock.date_in_stock_str,
                                                              func.sum(Stock.quantityfull).label('total_stocks')).
                                              where(Stock.seller_id == seller_id,
                                                    Stock.date_in_stock >= date_from_for_stock,
                                                    Stock.date_in_stock <= (date_to_for_stock + timedelta(days=1))).
                                              group_by(Stock.date_in_stock_str).subquery())
        average_stocks_count_reporting_period = await session.scalar(select(func.avg(average_stocks_count_reporting_period_query.c.total_stocks)))

        if not average_stocks_count_reporting_period:

            stocks = await Stock.get_stock_data_at_date_end_or_current(seller_id=seller_id, date_to=date_to)
            average_stocks_count_reporting_period = stocks['stocks_quantity']

        return float(average_stocks_count_reporting_period)

    @classmethod
    @log_and_notify_admin
    async def get_stock_change(cls,session, seller_id, date_from, date_to):
        stock_change = 0
        # Берем на 1 день позже, так как остатки выгружаются в 00.02
        date_to_plus_one = date_to + timedelta(days=1)
        date_to_str = datetime.strftime(date_to_plus_one, '%Y-%m-%d')
        stocks_total_at_cost_date_to = await session.scalar(select(func.sum(cls.total_at_cost)).
                                                    where(cls.seller_id == seller_id,
                                                          cls.date_in_stock_str == date_to_str)) or 0.0

        date_from_plus_one = date_from + timedelta(days=1)
        date_from_str = datetime.strftime(date_from_plus_one, '%Y-%m-%d')
        stocks_total_at_cost_date_from = await session.scalar(select(func.sum(cls.total_at_cost)).
                                                    where(cls.seller_id == seller_id,
                                                          cls.date_in_stock_str == date_from_str)) or 0.0
        if stocks_total_at_cost_date_from > 0 and stocks_total_at_cost_date_to > 0:
            stock_change = stocks_total_at_cost_date_to - stocks_total_at_cost_date_from

        return stock_change

