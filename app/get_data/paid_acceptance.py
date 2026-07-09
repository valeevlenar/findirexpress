from datetime import datetime
import sqlalchemy
from sqlalchemy import select, func
import logging
from app.admin.admin_message import send_message_to_admin

from app.database.models import Supplies, Paid_acceptance
from app.dates import start_for_downloading_data_func, end_of_Reporting_Week_func
from app.get_data.get_paid_acceptance import get_paid_acceptance_costs_by_seller
from app.get_data.get_supplies import get_supplies_by_seller_id

CHUNK_SIZE = 1000  # Размер пакета для bulk-операций

def chunker(sequence, chunk_size):
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]

async def get_paid_acceptance_data_by_seller(session, seller_id):

    try:
        logging.info(f'Seller_id: {seller_id}. Выгружаем поставки.')
        if not await get_supplies_by_seller_id(session, seller_id):
            await send_message_to_admin(f'Ошибка в выгрузке поставок.:'
                                        f'\nseller_id: {seller_id}')
            return False

        logging.info(f'Seller_id: {seller_id}. Выгружаем расходы по платной приемке.')
        if not await get_paid_acceptance_costs_by_seller(session, seller_id):
            await send_message_to_admin(f'Ошибка в выгрузке расходов по платной приемке.:'
                                        f'\nseller_id: {seller_id}')
            return False

        logging.info(f'Seller_id: {seller_id}. Аллоцируем расходы по платной приемке.')
        if await allocate_acceptance_costs_for_seller(session, seller_id):
            logging.info(f'Seller_id: {seller_id}. Проверяем аллокацию расходов по платной приемке.')
            await check_paid_acceptance_costs(session, seller_id)
            logging.info(f'Seller_id: {seller_id}. Закончили расходы по платной приемке.')
            return True
        else:
            await send_message_to_admin(f'Ошибка в аллокации платной приемки по селлеру:'
                                        f'\nseller_id: {seller_id}')

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в выгрузке платной приемки по селлеру:'
                                    f'\nseller_id: {seller_id}')
        logging.exception("An error occurred: %s", exc_info=e)


async def allocate_acceptance_costs_for_seller (session, seller_id):
    try:
        paid_acceptance_costs = await session.execute(select(Paid_acceptance.id,
                                                             Paid_acceptance.count,
                                                             Paid_acceptance.incomeid,
                                                             Paid_acceptance.nmid,
                                                             Paid_acceptance.shkcreatedate,
                                                             Paid_acceptance.total).
                                                      where(Paid_acceptance.seller_id == seller_id,
                                                            Paid_acceptance.is_distributed==False))
        paid_acceptance_costs = paid_acceptance_costs.mappings().all()
        if not paid_acceptance_costs:
            return True

        # print(len(paid_acceptance_costs))

        for paid_acceptance in paid_acceptance_costs:

            items_to_allocate_costs = await session.execute(select(Supplies.id,
                                                                   Supplies.barcode,
                                                                   Supplies.nmid,
                                                                   Supplies.quantity,
                                                                   Supplies.supply_cost_per_item,
                                                                   Supplies.total_supply_costs).
                                                           where(Supplies.seller_id == seller_id,
                                                                 Supplies.incomeid == paid_acceptance.incomeid,
                                                                 Supplies.nmid == paid_acceptance.nmid))
            if items_to_allocate_costs:
                items_to_allocate_costs = items_to_allocate_costs.mappings().all()

                total_items_to_allocate_costs = 0
                for item in items_to_allocate_costs:
                    total_items_to_allocate_costs += item['quantity']

                if total_items_to_allocate_costs == 0:
                    await send_message_to_admin(f'Seller_id: {seller_id}. Ошибка: есть платная приемка, есть акта приемки, но количество 0: income_id:{paid_acceptance.incomeid}')
                else:
                    cost_per_item = paid_acceptance.total / total_items_to_allocate_costs

                    for item in items_to_allocate_costs:
                        total_supply_costs = item['total_supply_costs'] + cost_per_item * item ['quantity']
                        supply_cost_per_item = total_supply_costs / item ['quantity']

                        await update_supply_costs_in_db(session=session,
                                                        seller_id=seller_id,
                                                        supplies_id=item['id'],
                                                        supply_cost_per_item = supply_cost_per_item,
                                                        total_supply_costs = total_supply_costs)

                        await update_paid_acceptance_in_db(session=session,
                                                           seller_id=seller_id,
                                                           paid_acceptance_id=paid_acceptance['id'])
            else:
                await send_message_to_admin(f'Seller_id: {seller_id}. Ошибка: есть платная приемка, но нет акта приемки: income_id:{paid_acceptance.incomeid}')



            # if await check_paid_acceptance_costs(session, seller_id, paid_acceptance.incomeid):
            #     return True


        else:
            pass
        logging.info(f'Seller_id: {seller_id}. Распределили расходы по платной приемке.')
        return True
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в распределении платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

async def update_supply_costs_in_db (session, seller_id, supplies_id, supply_cost_per_item, total_supply_costs):
    try:
        async with session.begin_nested():
            supplies_query = (sqlalchemy.update(Supplies).
                              where(Supplies.id == supplies_id).
                              values(supply_cost_per_item = supply_cost_per_item,
                                     total_supply_costs = total_supply_costs,
                                     cost_calculated = True,
                                     updated_at = datetime.now()))
            await session.execute(supplies_query)
        await session.commit()
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в распределении платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

async def update_paid_acceptance_in_db (session, seller_id, paid_acceptance_id):
    try:
        async with session.begin_nested():
            paid_acceptance_query = (sqlalchemy.update(Paid_acceptance).
                                     where(Paid_acceptance.id == paid_acceptance_id).
                                     values(is_distributed = True,
                                            updated_at = datetime.now()))
            await session.execute(paid_acceptance_query)
        await session.commit()
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в распределении платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)

async def check_paid_acceptance_costs(session, seller_id):
    try:
        start_date = await start_for_downloading_data_func()
        end_date = await end_of_Reporting_Week_func()
        total_paid_acceptance_costs_per_income_id = await session.scalar(select(func.sum(Paid_acceptance.total)).
                                                                         where(Paid_acceptance.seller_id == seller_id,
                                                                               Paid_acceptance.shkcreatedate >= start_date,
                                                                               Paid_acceptance.shkcreatedate <= end_date)) or 0.0
        total_allocated_costs_per_income_id = await session.scalar(select(func.sum(Supplies.total_supply_costs)).
                                                                   where(Supplies.seller_id == seller_id,
                                                                         Supplies.transaction_date >= start_date,
                                                                         Supplies.transaction_date <= end_date)) or 0.0

        # print('total_paid_acceptance_costs_per_income_id', total_paid_acceptance_costs_per_income_id)
        # print('total_allocated_costs_per_income_id', total_allocated_costs_per_income_id)

        diff = total_paid_acceptance_costs_per_income_id - total_allocated_costs_per_income_id

        if abs(diff) <= 10:
            logging.info(f'Seller_id: {seller_id}. Аллокация расходов по платной приемке-Ок')
            return True
        else:
            await send_message_to_admin(f'Ошибка в проверке распределении платной приемки по актам:'
                                    f'\nSeller_id: {seller_id}'
                                        f'\ntotal_paid_acceptance_costs_per_income_id: {total_paid_acceptance_costs_per_income_id}'
                                        f'\ntotal_allocated_costs_per_income_id: {total_allocated_costs_per_income_id}'
                                        f'\nЗапускаем проверку по актам')

            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в проверке распределении платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)