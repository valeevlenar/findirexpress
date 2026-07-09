from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, Float, ForeignKey, DateTime, Integer, String, func, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base
from app.dates import start_of_quarter_func
from app.wrappers import with_session


class Sales(Base):
    __tablename__ = 'sales'
    # ДОБАВЛЕНО: Уникальный индекс для rrd_id, чтобы работал ON CONFLICT в коде
    __table_args__ = (
        Index('idx_sales_rrd_id', 'rrd_id', unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    seller_inn: Mapped[str] = mapped_column(String(120))
    rrd_id: Mapped[BigInteger] = mapped_column(BigInteger)
    realizationreport_id: Mapped[int] = mapped_column(Integer)
    date_from: Mapped[str] = mapped_column(String(120))
    date_to: Mapped[str] = mapped_column(String(120))
    create_dt: Mapped[str] = mapped_column(String(120))
    subject_name: Mapped[str] = mapped_column(String(120))
    nm_id: Mapped[int] = mapped_column(Integer)
    brand_name: Mapped[str] = mapped_column(String(120))
    sa_name: Mapped[str] = mapped_column(String(120))
    ts_name: Mapped[str] = mapped_column(String(120))
    barcode: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    retail_price: Mapped[float] = mapped_column(Float)
    retail_amount: Mapped[float] = mapped_column(Float)
    sale_percent: Mapped[int] = mapped_column(Integer)
    commission_percent: Mapped[float] = mapped_column(Float)
    office_name: Mapped[str] = mapped_column(String(120))
    supplier_oper_name: Mapped[str] = mapped_column(String(120))
    order_dt: Mapped[str] = mapped_column(String(120))
    sale_dt: Mapped[str] = mapped_column(String(120))
    rr_dt: Mapped[str] = mapped_column(String(120))
    transaction_date: Mapped[datetime] = mapped_column(DateTime)
    retail_price_withdisc_rub: Mapped[float] = mapped_column(Float)
    delivery_amount: Mapped[int] = mapped_column(Integer)
    return_amount: Mapped[int] = mapped_column(Integer)
    delivery_rub: Mapped[float] = mapped_column(Float)
    product_discount_for_report: Mapped[float] = mapped_column(Float)
    supplier_promo: Mapped[float] = mapped_column(Float)
    rid: Mapped[int] = mapped_column(Integer)
    ppvz_spp_prc: Mapped[float] = mapped_column(Float)
    ppvz_kvw_prc_base: Mapped[float] = mapped_column(Float)
    ppvz_kvw_prc: Mapped[float] = mapped_column(Float)
    sup_rating_prc_up: Mapped[float] = mapped_column(Float)
    is_kgvp_v2: Mapped[float] = mapped_column(Float)
    ppvz_sales_commission: Mapped[float] = mapped_column(Float)
    ppvz_for_pay: Mapped[float] = mapped_column(Float)
    ppvz_reward: Mapped[float] = mapped_column(Float)
    acquiring_fee: Mapped[float] = mapped_column(Float)
    ppvz_vw: Mapped[float] = mapped_column(Float)
    ppvz_vw_nds: Mapped[float] = mapped_column(Float)
    ppvz_office_name: Mapped[str] = mapped_column(String(500))
    bonus_type_name: Mapped[Optional[str]] = mapped_column(String(250))
    site_country: Mapped[str] = mapped_column(String(120))
    penalty: Mapped[float] = mapped_column(Float)
    additional_payment: Mapped[float] = mapped_column(Float)
    rebill_logistic_cost: Mapped[float] = mapped_column(Float)
    storage_fee: Mapped[float] = mapped_column(Float)
    deduction: Mapped[float] = mapped_column(Float)
    acceptance: Mapped[float] = mapped_column(Float)
    goods_quantity: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[float] = mapped_column(Float)
    full_comission: Mapped[float] = mapped_column(Float)
    other_deductions: Mapped[float] = mapped_column(Float)
    for_withdraw:Mapped[float] = mapped_column(Float)
    cost_of_sales: Mapped[float] = mapped_column(Float)
    tax_base_amount: Mapped[float] = mapped_column(Float)
    tax_costs: Mapped[float] = mapped_column(Float)
    net_profit: Mapped[float] = mapped_column(Float)
    revenue_before_spp: Mapped[Optional[float]] = mapped_column(Float)
    commission_before_spp: Mapped[Optional[float]] = mapped_column(Float)
    spp_amount: Mapped[Optional[float]] = mapped_column(Float)
    doc_type_name: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


    @classmethod
    @with_session
    async def get_sales_count(cls, session, seller_id, date_from, date_to):
        sales_count = await session.scalar(select(func.sum(cls.goods_quantity)).
                                                 where(cls.seller_id == seller_id,
                                                       cls.transaction_date.between(date_from, date_to))) or 0.0

        return sales_count

    @classmethod
    @with_session
    async def get_sales_sum(cls, session, seller_id, date_from, date_to):
        sales_gross_sum = await session.scalar(select(func.sum(cls.revenue)).
                                               where(cls.seller_id == seller_id,
                                                     cls.transaction_date.between(date_from, date_to))) or 0.0

        sales_sum = sales_gross_sum
        return sales_sum

    @classmethod
    @with_session
    async def get_tax_payable(cls, session, seller_id, date_from, date_to):
        start_of_quarter = start_of_quarter_func(date_to)
        tax_payable = await session.scalar(select(func.coalesce(func.sum(Sales.tax_costs), 0.0))
                                                   .where(Sales.seller_id == seller_id,
                                                          Sales.transaction_date.between(start_of_quarter, date_to)))

        return tax_payable

    @classmethod
    @with_session
    async def get_accumulated_profit(cls, session, seller_id, date_to):
        accumulated_profit = await session.scalar(select(func.coalesce(func.sum(Sales.net_profit), 0.0))
                                           .where(Sales.seller_id == seller_id,
                                                  Sales.transaction_date <= date_to))

        return accumulated_profit

    @classmethod
    @with_session
    async def get_earliest_data_date(cls, session, seller_id):
        earliest_data_date = await session.scalar(select(cls.transaction_date).
                                                  where(cls.seller_id == seller_id).
                                                  order_by(cls.transaction_date.asc()))
        return earliest_data_date

    @classmethod
    @with_session
    async def get_reporting_week_accounts_receivable(cls, session, seller_id, date_to: datetime):
        date_from = date_to.replace(hour=00, minute=00, second=00, microsecond=000000) - timedelta(days=13)

        accounts_receivable = await session.scalar(select(func.coalesce(func.sum(Sales.for_withdraw), 0.0))
                                                   .where(Sales.seller_id == seller_id,
                                                          Sales.transaction_date.between(date_from, date_to)))
        # print(date_from, date_to, accounts_receivable)

        return accounts_receivable

    @classmethod
    @with_session
    async def get_reporting_month_accounts_receivable(cls, session, seller_id, date_to: datetime):
        date_from = date_to.replace(hour=00, minute=00, second=00, microsecond=000000) - timedelta(days=13)

        accounts_receivable = await session.scalar(select(func.coalesce(func.sum(Sales.for_withdraw), 0.0))
                                                   .where(Sales.seller_id == seller_id,
                                                          Sales.transaction_date.between(date_from, date_to)))
        # print(date_from, date_to, accounts_receivable)

        return accounts_receivable

    @classmethod
    @with_session
    async def get_reporting_week_cash_inflow(cls, session, seller_id, date_to: datetime):
        date_to = date_to - timedelta(days=14)
        date_from = date_to.replace(hour=00, minute=00, second=00, microsecond=000000) - timedelta(days=6)

        cash_inflow = await session.scalar(select(func.coalesce(func.sum(Sales.for_withdraw), 0.0))
                                                   .where(Sales.seller_id == seller_id,
                                                          Sales.transaction_date.between(date_from, date_to)))
        # print('cashflow', date_from, date_to, cash_inflow)

        return cash_inflow

