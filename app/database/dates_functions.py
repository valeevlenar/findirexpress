from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.models import Seller
from app.database.classes.sales import Sales
from app.dates import start_for_downloading_data_func
from app.wrappers import with_session


# берем дату последнего отправленного недельного отчета:
@with_session
async def get_latest_weekly_report_sent_date(session, seller_id):
    date = await session.scalar(select(Seller.last_weekly_pl_sent_date).
                                where(Seller.id == seller_id))
    return date

# берем дату последнего отправленного месячного отчета:
@with_session
async def get_latest_monthly_report_sent_date(session, seller_id):
    date = await session.scalar(select(Seller.last_monthly_pl_sent_date).
                                where(Seller.id == seller_id))
    return date

# берем дату последнего расчета PL:
@with_session
async def get_latest_pl_calculation_date (session, seller_id):
    latest_pl_calculation_date = await session.scalar(select(Seller.last_pl_calculated_date).
                                    where(Seller.id == seller_id))
    return latest_pl_calculation_date

# берем дату последней доступной информации:
@with_session
async def get_latest_available_info_date (session, seller_id):
    date = await session.scalar(select(Sales.date_to).
                                    where(Sales.seller_id == seller_id).
                                    order_by(Sales.transaction_date.desc()))
    if not date:
        start_for_downloading_data = await start_for_downloading_data_func()
        date = (start_for_downloading_data-timedelta(microseconds=1)).strftime('%Y-%m-%d')
    latest_available_info_date = (datetime.strptime(date, '%Y-%m-%d').
            replace(hour=23, minute=59, second=59, microsecond=999999))
    return latest_available_info_date
