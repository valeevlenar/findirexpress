from datetime import datetime, timedelta

from app.database.models import async_session, Storage_costs, Orders, Supplies, Paid_acceptance, Marketing_costs_wb, \
    Marketing_campaigns_stats, Marketing_costs_by_SKU, Seller, Orders_nm
from app.database.classes.sales import Sales
from app.dates import end_of_Reporting_Week_func, start_of_Reporting_Week_func
from sqlalchemy import delete
import sqlalchemy

from app.wrappers import with_session


@with_session
async def delete_storage_costs(session):
    end_of_Reporting_Week = await end_of_Reporting_Week_func()
    async with session.begin_nested():
        query = sqlalchemy.delete(Storage_costs).where(Storage_costs.cost_date >= end_of_Reporting_Week)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_data_by_seller_id(session, seller_id):
    await delete_orders_by_seller_id(session, seller_id)
    await delete_orders_nm_by_seller_id(session, seller_id)
    await delete_storage_by_seller_id(session, seller_id)
    await delete_supplies_by_seller_id(session, seller_id)
    await delete_paid_acceptance_by_seller_id(session, seller_id)
    await delete_marketing_costs_by_seller_id(session, seller_id)
    await delete_marketing_stats_by_seller_id(session, seller_id)
    await delete_marketing_allocation_by_seller_id(session, seller_id)
    await delete_sales_by_seller_id(session, seller_id)
    await update_sellers_table_for_seller_id(session, seller_id)

@with_session
async def delete_orders_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Orders).where(Orders.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_orders_nm_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Orders_nm).where(Orders_nm.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_storage_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Storage_costs).where(Storage_costs.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_supplies_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Supplies).where(Supplies.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_paid_acceptance_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Paid_acceptance).where(Paid_acceptance.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_marketing_costs_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_costs_wb).where(Marketing_costs_wb.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_marketing_stats_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_campaigns_stats).where(Marketing_campaigns_stats.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_marketing_allocation_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_costs_by_SKU).where(Marketing_costs_by_SKU.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def delete_sales_by_seller_id(session, seller_id):
    async with session.begin_nested():
        query = sqlalchemy.delete(Sales).where(Sales.seller_id == seller_id)
        await session.execute(query)
    await session.commit()

@with_session
async def update_sellers_table_for_seller_id(session, seller_id):
    async with session.begin_nested():
        query = (sqlalchemy.update(Seller).
                 where(Seller.id == seller_id).
                 values(last_pl_calculated_date=None,
                        last_weekly_pl_sent_date=None,
                        last_monthly_pl_sent_date=None))
        await session.execute(query)
    await session.commit()

@with_session
async def delete_data_for_reporting_week(session):
    date_from = await start_of_Reporting_Week_func()

    #Удаляем заказы
    async with session.begin_nested():
        query = sqlalchemy.delete(Orders).where(Orders.order_date >= date_from)
        await session.execute(query)
    await session.commit()

    #Удаляем заказы nm
    async with session.begin_nested():
        query = sqlalchemy.delete(Orders_nm).where(Orders_nm.order_date >= date_from)
        await session.execute(query)
    await session.commit()

    #Удаляем расходы на хранение
    async with session.begin_nested():
        query = sqlalchemy.delete(Storage_costs).where(Storage_costs.cost_date >= date_from)
        await session.execute(query)
    await session.commit()

    # Удаляем поставки
    async with session.begin_nested():
        query = sqlalchemy.delete(Supplies).where(Supplies.transaction_date >= date_from)
        await session.execute(query)
    await session.commit()

    # Удаляем платную приемку
    async with session.begin_nested():
        query = sqlalchemy.delete(Paid_acceptance).where(Paid_acceptance.shkcreatedate >= date_from)
        await session.execute(query)
    await session.commit()

    # Удаляем маркетинговые расходы
    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_costs_wb).where(Marketing_costs_wb.cost_date >= date_from)
        await session.execute(query)
    await session.commit()

    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_campaigns_stats).where(Marketing_campaigns_stats.cost_date >= date_from)
        await session.execute(query)
    await session.commit()

    async with session.begin_nested():
        query = sqlalchemy.delete(Marketing_costs_by_SKU).where(Marketing_costs_by_SKU.cost_date >= date_from)
        await session.execute(query)
    await session.commit()

    # Удаляем продажи
    date_to = await end_of_Reporting_Week_func()
    date_to_str = datetime.strftime(date_to,'%Y-%m-%d')
    async with session.begin_nested():
        query = sqlalchemy.delete(Sales).where(Sales.date_to >= date_to_str)
        await session.execute(query)
    await session.commit()

    #Обновляем статусы в таблицу sellers
    # query = (sqlalchemy.update(Seller).
    #          where(Seller.last_weekly_pl_sent_date != None).
    #          values(last_pl_calculated_date=None,
    #                 last_weekly_pl_sent_date=(date_to - timedelta(days=7))))
    # await session.execute(query)
    # await session.commit()