import os
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, Boolean, ForeignKey, Integer, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from dotenv import load_dotenv

load_dotenv()


engine = create_async_engine(url=os.getenv('DBURL'),
                             echo=False,
                        # 1. pool_pre_ping заставляет SQLAlchemy делать легкий "пинг" БД перед запросом.
                            # Если соединение мертвое, оно автоматически переподключится.
                            pool_pre_ping=True,
                             pool_size=50,       # Увеличено до 20
                            max_overflow=20,    # Увеличено до 20
                            pool_timeout=60.0,  # Увеличено до 60 секунд
                            pool_recycle=1800)

async_session = async_sessionmaker(engine)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[BigInteger] = mapped_column(BigInteger, unique=True)
    tg_username: Mapped[Optional[str]] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str] = mapped_column(String(120))
    offer_approve: Mapped[bool] = mapped_column(Boolean())
    date_created: Mapped[datetime] = mapped_column(DateTime)

class Seller(Base):
    __tablename__ = 'sellers'
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_title: Mapped[str] = mapped_column(String(120))
    seller_inn: Mapped[str] = mapped_column(String(120))
    seller_type: Mapped[str] = mapped_column(String(120))
    tax_base: Mapped[str] = mapped_column(String(120))
    tax_rate: Mapped[float] = mapped_column(Float)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    user_tg_id: Mapped[BigInteger] = mapped_column(ForeignKey('users.tg_id'))
    e_mail: Mapped[str] = mapped_column(String(120))
    offer_signed: Mapped[bool] = mapped_column(Boolean())
    balance: Mapped[float] = mapped_column(Float)
    first_cost_set: Mapped[bool] = mapped_column(Boolean())
    first_reports_sent: Mapped[bool] = mapped_column(Boolean())
    date_created: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(120))
    date_updated: Mapped[datetime] = mapped_column(DateTime)
    service_status: Mapped[bool] = mapped_column(Boolean())
    date_updated_ss: Mapped[datetime] = mapped_column(DateTime)
    last_pl_calculated_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_weekly_pl_sent_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_monthly_pl_sent_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    price_control: Mapped[Optional[bool]] = mapped_column(Boolean())
    price_control_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class PriceApiKeys(Base):
    __tablename__ = 'priceapikeys'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    price_wb_api: Mapped[str] = mapped_column(String(1200),unique=True)
    api_date_created: Mapped[Optional[datetime]] = mapped_column(DateTime)
    api_status: Mapped[str] = mapped_column(String(120))

class ApiKeys(Base):
    __tablename__ = 'apikeys'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    wb_api: Mapped[str] = mapped_column(String(1200),unique=True)
    api_date_created: Mapped[Optional[datetime]] = mapped_column(DateTime)
    api_status: Mapped[str] = mapped_column(String(120))

class Testbase(Base):
    __tablename__ = 'testbase'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    test_field: Mapped[str] = mapped_column(String(1200))
    date_created: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Testbase2(Base):
    __tablename__ = 'testbase2'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    test_field: Mapped[str] = mapped_column(String(1200))
    date_created: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Orders(Base):
    __tablename__ = 'orders'

    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'order_date',
            'barcode',
            name='uq_orders_seller_date_barcode'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    order_date: Mapped[datetime] = mapped_column(DateTime)
    supplier_article: Mapped[str] = mapped_column(String(120))
    nmid: Mapped[int] = mapped_column(Integer)
    barcode: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(120))
    brand: Mapped[str] = mapped_column(String(120))
    techsize: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    total_sum: Mapped[Optional[float]] = mapped_column(Float)
    totalprice: Mapped[Optional[float]] = mapped_column(Float)
    discountpercent: Mapped[Optional[int]] = mapped_column(Integer)
    spp: Mapped[Optional[float]] = mapped_column(Float)
    finishedprice: Mapped[Optional[float]] = mapped_column(Float)
    pricewithdisc: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class Orders_nm(Base):
    __tablename__ = 'orders_nm'

    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'order_date',
            'nm_id',
            name='orders_nm_unique_constraint'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    order_date: Mapped[datetime] = mapped_column(DateTime)
    supplier_article: Mapped[str] = mapped_column(String(120))
    subject_name: Mapped[str] = mapped_column(String(120))
    nm_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    total_sum: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class Goods_cost(Base):
    __tablename__ = 'goods_cost'

    __table_args__ = (
        UniqueConstraint('seller_id', 'barcode', name='uix_seller_barcode'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    seller_inn: Mapped[str] = mapped_column(String(120))
    barcode: Mapped[str] = mapped_column(String(120), unique=True)
    subject_name: Mapped[str] = mapped_column(String(120))
    nm_id: Mapped[int]=mapped_column(Integer)
    sa_name: Mapped[str] = mapped_column(String(120))
    ts_name: Mapped[str] = mapped_column(String(120))
    cost: Mapped[float] = mapped_column(Float)
    brand: Mapped[Optional[str]] = mapped_column(String(120))

class Products_price(Base):
    __tablename__ = 'products_price'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    nm_id: Mapped[int]=mapped_column(Integer)
    vendorCode: Mapped[str] = mapped_column(String(120))
    sizeID: Mapped[Optional[int]]=mapped_column(Integer)
    price: Mapped[int]=mapped_column(Integer)
    discountedPrice: Mapped[float] = mapped_column(Float)
    clubDiscountedPrice: Mapped[float] = mapped_column(Float)
    techSizeName: Mapped[Optional[str]] = mapped_column(String(120))
    currencyCode: Mapped[str] = mapped_column(String(120))
    discount: Mapped[int]=mapped_column(Integer)
    clubDiscount: Mapped[int]=mapped_column(Integer)
    editableSizePrice: Mapped[bool] = mapped_column(Boolean())
    price_set: Mapped[bool] = mapped_column(Boolean())
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class DataDates(Base):
    __tablename__ = 'data_dates'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    last_storage_date_checked: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_supplies_date_checked: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_paid_acceptance_date_checked: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Storage_costs(Base):
    __tablename__ = 'storage_costs'

    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'cost_date',
            'warehouse',
            'chrtid',
            'barcode',
            'nmid',
            'warehouseprice',
            'barcodescount',
            name='storage_unique_constraint'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey('sellers.id'))
    cost_date: Mapped[datetime] = mapped_column(DateTime)
    warehouse: Mapped[str] = mapped_column(String(120))
    chrtid: Mapped[int] = mapped_column(Integer)
    size: Mapped[str] = mapped_column(String(120))
    barcode: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(120))
    brand: Mapped[str] = mapped_column(String(120))
    vendor_code: Mapped[str] = mapped_column(String(120))
    nmid: Mapped[int] = mapped_column(Integer)
    warehouseprice: Mapped[float] = mapped_column(Float)
    barcodescount: Mapped[int] = mapped_column(Integer)
    loyaltyDiscount: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class Supplies(Base):
    __tablename__ = 'supplies'

    __table_args__ = (
        UniqueConstraint('seller_id',
                         'incomeid',
                         'barcode',
                         'nmid',
                         name='supplies_unique_constraint'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    incomeid: Mapped[int]=mapped_column(Integer)
    number: Mapped[Optional[str]] = mapped_column(String(120))
    date: Mapped[datetime] = mapped_column(DateTime)
    lastchangedate: Mapped[datetime] = mapped_column(DateTime)
    supplierarticle: Mapped[str] = mapped_column(String(120))
    techsize: Mapped[str] = mapped_column(String(120))
    barcode: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int]=mapped_column(Integer)
    dateclose: Mapped[datetime] = mapped_column(DateTime)
    warehousename: Mapped[str] = mapped_column(String(120))
    nmid: Mapped[int]=mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(120))
    supply_cost_per_item: Mapped[Optional[float]] = mapped_column(Float)
    total_supply_costs: Mapped[Optional[float]] = mapped_column(Float)
    transaction_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cost_calculated: Mapped[bool] = mapped_column(Boolean())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Paid_acceptance(Base):
    __tablename__ = 'paid_acceptance'

    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'count',
            'incomeid',
            'nmid',
            'shkcreatedate',
            'total',
            name='paid_acceptance_unique_constraint'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    count: Mapped[int]=mapped_column(Integer)
    gicreatedate: Mapped[datetime] = mapped_column(DateTime)
    incomeid: Mapped[int]=mapped_column(Integer)
    nmid: Mapped[int]=mapped_column(Integer)
    shkcreatedate: Mapped[datetime] = mapped_column(DateTime)
    subjectname: Mapped[str] = mapped_column(String(120))
    total: Mapped[Optional[float]] = mapped_column(Float)
    is_distributed: Mapped[bool] = mapped_column(Boolean())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Marketing_costs_by_SKU(Base):
    __tablename__ = 'marketing_costs_by_sku'

    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'wb_cost_id',
            'type',
            'advert_id',
            'cost_date',
            'nmid',
            'barcode',
            'review_id',
            name='marketing_by_sku_unique_constraint'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    wb_cost_id: Mapped[Optional[int]]=mapped_column(Integer)
    type: Mapped[Optional[str]] = mapped_column(String(120))
    advert_id: Mapped[int]=mapped_column(Integer)
    cost_date: Mapped[datetime] = mapped_column(DateTime)
    nmid: Mapped[int] = mapped_column(Integer)
    barcode: Mapped[Optional[str]] = mapped_column(String(120))
    cost_sum: Mapped[Optional[float]] = mapped_column(Float)
    tax_costs: Mapped[Optional[float]] = mapped_column(Float)
    net_profit: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_id: Mapped[Optional[str]] = mapped_column(String(120))

class Marketing_campaigns_stats(Base):
    __tablename__ = 'marketing_campaigns_stats'
    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'advert_id',
            'date',
            'app_type',
            'nmid',
            'costs',
            name='marketing_stats_unique_constraint'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    advert_id: Mapped[int]=mapped_column(Integer)
    date: Mapped[Optional[str]] = mapped_column(String(120))
    cost_date: Mapped[datetime] = mapped_column(DateTime)
    app_type: Mapped[int]=mapped_column(Integer)
    nmid: Mapped[int]=mapped_column(Integer)
    views: Mapped[int]=mapped_column(Integer)
    clicks: Mapped[int]=mapped_column(Integer)
    costs: Mapped[Optional[float]] = mapped_column(Float)
    adds_to_cart: Mapped[int]=mapped_column(Integer)
    orders: Mapped[int]=mapped_column(Integer)
    quantity: Mapped[int]=mapped_column(Integer)
    orders_sum: Mapped[Optional[float]] = mapped_column(Float)
    optional: Mapped[Optional[str]] = mapped_column(String(120))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Marketing_costs_wb(Base):
    __tablename__ = 'marketing_costs_wb'
    __table_args__ = (
        UniqueConstraint(
            'seller_id',
            'cost_date',
            'updtime',
            'paymenttype',
            'updnum',
            'updsum',
            'advertid',
            name='marketing_costs_unique_constraint'
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    cost_date: Mapped[datetime] = mapped_column(DateTime)
    updtime: Mapped[str] = mapped_column(String(120))
    campname: Mapped[str] = mapped_column(String(120))
    paymenttype: Mapped[str] = mapped_column(String(120))
    updnum: Mapped[Optional[int]] = mapped_column(Integer)
    updsum: Mapped[int] = mapped_column(Integer)
    advertid: Mapped[int] = mapped_column(Integer)
    adverttype: Mapped[Optional[int]] = mapped_column(Integer)
    advertstatus: Mapped[Optional[int]] = mapped_column(Integer)
    cost_allocated: Mapped[bool] = mapped_column(Boolean())
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class Transactions(Base):
    __tablename__ = 'transactions'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    amount: Mapped[float] = mapped_column(Float)
    transaction_type: Mapped[str] = mapped_column(String(120))
    transaction_stream: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)

class ClosingDocuments(Base):
    __tablename__ = 'closing_documents'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    amount: Mapped[float] = mapped_column(Float)
    date_start: Mapped[datetime] = mapped_column(DateTime)
    date_end: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(120))
    tochka_doc_id: Mapped[str] = mapped_column(String(120))
    file_name: Mapped[str] = mapped_column(String(120))

class Reports(Base):
    __tablename__ = 'reports'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    seller_inn: Mapped[str] = mapped_column(String(120))
    report_type: Mapped[str] = mapped_column(String(120))
    report_creation_type: Mapped[str] = mapped_column(String(120))
    report_date_to: Mapped[datetime] = mapped_column(DateTime)
    report_status: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

class Subscriptions(Base):
    __tablename__ = 'subscriptions'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    subscription_type: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    duration: Mapped[int]=mapped_column(Integer)
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    promocode_id: Mapped[Optional[int]]=mapped_column(Integer)
    discount_amount: Mapped[float] = mapped_column(Float)
    net_amount: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Promocodes(Base):
    __tablename__ = 'promocodes'

    id: Mapped[int] = mapped_column(primary_key=True)
    code_title: Mapped[str] = mapped_column(String(120))
    promo_type: Mapped[str] = mapped_column(String(120))
    discount_percentage: Mapped[Optional[float]] = mapped_column(Float)
    discount_amount: Mapped[Optional[float]] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean())
    max_usage_number: Mapped[int]=mapped_column(Integer)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    max_budget: Mapped[Optional[float]] = mapped_column(Float)

class PromocodeUsage(Base):
    __tablename__ = 'promocode_usage'

    id: Mapped[int] = mapped_column(primary_key=True)
    promocode_id: Mapped[int] = mapped_column(ForeignKey('promocodes.id'))
    subscription_id: Mapped[int] = mapped_column(ForeignKey('subscriptions.id'))
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    discount_amount_used: Mapped[Optional[float]] = mapped_column(Float)
    date_used: Mapped[datetime] = mapped_column(DateTime)

class Invoices(Base):
    __tablename__ = 'invoices'

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(120))
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    amount: Mapped[float] = mapped_column(Float)
    subscription_id: Mapped[int] = mapped_column(ForeignKey('subscriptions.id'))
    status: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    tochka_invoice_id: Mapped[str] = mapped_column(String(120))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    file_name: Mapped[str] = mapped_column(String(120))

class ReferralChannels(Base):
    __tablename__ = 'referral_channels'

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(120))
    channel_name: Mapped[Optional[str]] = mapped_column(String(120), unique=True)
    channel_tg_id: Mapped[Optional[BigInteger]] = mapped_column(BigInteger)
    channel_user_id: Mapped[Optional[int]] = mapped_column(Integer)
    channel_contacts_data: Mapped[Optional[str]] = mapped_column(String(255))
    referral_code: Mapped[str] = mapped_column(String(120))
    referral_link: Mapped[str] = mapped_column(String(255))
    channel_reward_type: Mapped[Optional[str]] = mapped_column(String(120))
    channel_reward_conditions: Mapped[Optional[str]] = mapped_column(String(120))
    channel_reward_percent: Mapped[Optional[str]] = mapped_column(String(120))
    channel_reward_amount: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class Referrals(Base):
    __tablename__ = 'referrals'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_tg_id: Mapped[Optional[BigInteger]] = mapped_column(BigInteger)
    channel_id: Mapped[str] = mapped_column(ForeignKey('referral_channels.id'))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# class Referral_rewards(Base):
#     __tablename__ = 'referrals'
#
#     id: Mapped[int] = mapped_column(primary_key=True)
#     channel_name: Mapped[str] = mapped_column(String(120))
#     channel_contacts_data: Mapped[str] = mapped_column(String(255))

class Managers(Base):
    __tablename__ = 'managers'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    access_is_active: Mapped[bool] = mapped_column(Boolean())
    role: Mapped[Optional[str]] = mapped_column(String(120))
    api_access: Mapped[bool] = mapped_column(Boolean())
    cost_access: Mapped[bool] = mapped_column(Boolean())
    price_control_access: Mapped[bool] = mapped_column(Boolean())
    updated_at: Mapped[datetime] = mapped_column(DateTime)

class Managers_tokens(Base):
    __tablename__ = 'managers_tokens'

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(120))
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    api_access: Mapped[bool] = mapped_column(Boolean())
    cost_access: Mapped[bool] = mapped_column(Boolean())
    price_control_access: Mapped[bool] = mapped_column(Boolean())
    is_used: Mapped[bool] = mapped_column(Boolean())

class Support_tickets(Base):
    __tablename__ = 'support_tickets'

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int]=mapped_column(Integer)
    tg_id: Mapped[BigInteger] = mapped_column(BigInteger)
    company_name: Mapped[str] = mapped_column(String(120))
    ticket_type: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(120))
    reply: Mapped[Optional[str]] = mapped_column(String(500))
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    tg_username: Mapped[Optional[str]] = mapped_column(String(120))

async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


