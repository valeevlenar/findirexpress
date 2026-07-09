import logging

from app.admin.admin_message import send_message_to_admin
from app.database.models import Paid_acceptance, Supplies, Marketing_costs_wb, Marketing_costs_by_SKU
from app.dates import start_for_downloading_data_func, end_of_Reporting_Week_func
from app.get_data.paid_acceptance import allocate_acceptance_costs_for_seller
from app.wrappers import with_session
from sqlalchemy import select, func
import sqlalchemy


@with_session
async def get_wrong_paid_acceptance_items(session, seller_id):
    logging.info(f'Начали проверку актов приемки по селлеру {seller_id}')
    paid_acceptance_items = await session.execute(select(Paid_acceptance.incomeid,
                                                         func.sum(Paid_acceptance.total).label('total')).
                                                  where(Paid_acceptance.seller_id==seller_id).
                                                  group_by(Paid_acceptance.incomeid)) or 0.0
    paid_acceptance_items_dict = paid_acceptance_items.mappings().all()

    wrong_allocation_items = []
    no_incomeid_in_supply = []
    # print(paid_acceptance_items_dict)
    # paid_acceptance_items_dict.append({'incomeid': 254699,'total':100})

    for item in paid_acceptance_items_dict:
        income_id = item['incomeid']
        income_id_amount = item['total']
        allocated_items = await session.execute(select(Supplies.incomeid,
                                                        func.sum(Supplies.total_supply_costs).label('total_supply_costs')).
                                                 where(Supplies.seller_id==seller_id,
                                                       Supplies.incomeid == income_id).
                                                group_by(Supplies.incomeid))
        allocated_item = allocated_items.mappings().first()
        # print(allocated_item)
        if allocated_item:

            amount_allocated = allocated_item['total_supply_costs']
            diff = income_id_amount - amount_allocated

            if diff >=5:
                wrong_income_id = {
                    'seller_id': seller_id,
                    'income_id': income_id,
                    'amount_per_income_id': income_id_amount,
                    'allocated_amount': amount_allocated,
                    'diff': diff
                }
                await send_message_to_admin(f'Выявили некорректное распределение платной приемки:'
                                            f'Seller_id:{seller_id}'
                                            f'\n{wrong_income_id}')
                wrong_allocation_items.append(wrong_income_id)
        else:
            no_incomeid_in_supply.append({'seller_id':seller_id,
                                          'incomeid_in_paid_acceptance': income_id,
                                          'incomeid_total':income_id_amount})

    # print(wrong_allocation)
    logging.info(f'Неправильное распределение по актам приемки: {wrong_allocation_items}.')
    logging.info(f'Нет актов платной приемки в поставках: {no_incomeid_in_supply}.')


async def reallocate_paid_acceptance(session,seller_id,wrong_allocation_items):
    try:
        for item in wrong_allocation_items:
            income_id = item['income_id']

            income_id_in_supplies = await session.scalar(select(Supplies.id).
                                                         where(Supplies.seller_id==seller_id,
                                                               Supplies.incomeid==income_id,
                                                               Supplies.barcode != None,
                                                               Supplies.quantity >= 0))
            if income_id_in_supplies:
                async with session.begin_nested():
                    query = (sqlalchemy.update(Paid_acceptance).
                             where(Paid_acceptance.incomeid == income_id,
                                   Paid_acceptance.seller_id == seller_id).
                             values(is_distributed=False))
                    await session.execute(query)
                await session.commit()
            else:
                await send_message_to_admin(f'Акта платной приемки нет в поставках:'
                                            f'\nSeller_id: {seller_id}'
                                            f'\nIncome_id: {income_id}')
        await allocate_acceptance_costs_for_seller(session=session,seller_id=seller_id)

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при попытке перераспределить платную приемку.')
        logging.exception("An error occurred: %s", exc_info=e)

@with_session
async def get_wrong_marketing_allocation_items(session, seller_id):
    logging.info(f'Начали проверку аллокации маркетинга по селлеру {seller_id}')

    start_date = await start_for_downloading_data_func()
    end_date = await end_of_Reporting_Week_func()

    marketing_cost_items = await session.execute(select(Marketing_costs_wb.advertid,
                                                         func.sum(Marketing_costs_wb.updsum).label('total')).
                                                  where(Marketing_costs_wb.seller_id == seller_id,
                                                        Marketing_costs_wb.cost_date>=start_date,
                                                        Marketing_costs_wb.cost_date<=end_date,
                                                        Marketing_costs_wb.cost_allocated == True,
                                                        Marketing_costs_wb.paymenttype != 'Бонусы',
                                                        Marketing_costs_wb.paymenttype != 'Кэшбэк'
                                                        ).group_by(Marketing_costs_wb.advertid))
    marketing_cost_items = marketing_cost_items.mappings().all()
    wrong_advert_ids = []
    if marketing_cost_items:
        for item in marketing_cost_items:
            advert_id = item ['advertid']
            advert_id_cost = item ['total']

            total_allocated_marketing_costs_per_advert_id = await session.scalar(select(func.sum(Marketing_costs_by_SKU.cost_sum)).
                                                               where(Marketing_costs_by_SKU.seller_id == seller_id,
                                                                     Marketing_costs_by_SKU.type == 'wb_promotion',
                                                                     Marketing_costs_by_SKU.cost_date>=start_date,
                                                                     Marketing_costs_by_SKU.cost_date<=end_date,
                                                                     Marketing_costs_by_SKU.advert_id==advert_id)) or 0.0

            # print('total_marketing_costs', total_marketing_costs)
            # print('total_allocated_marketing_costs', total_allocated_marketing_costs)
            diff = advert_id_cost - total_allocated_marketing_costs_per_advert_id

            if abs(diff) <= 5:
                pass

            else:
                wb_cost_ids_per_advert_ids = await session.execute(select(Marketing_costs_wb.id,
                                                         func.sum(Marketing_costs_wb.updsum).label('total')).
                                                  where(Marketing_costs_wb.seller_id == seller_id,
                                                        Marketing_costs_wb.cost_date>=start_date,
                                                        Marketing_costs_wb.cost_date<=end_date,
                                                        Marketing_costs_wb.cost_allocated == True,
                                                        Marketing_costs_wb.paymenttype != 'Бонусы',
                                                        Marketing_costs_wb.paymenttype != 'Кэшбэк',
                                                        Marketing_costs_wb.advertid == advert_id).
                                                                   group_by(Marketing_costs_wb.id))
                wb_cost_ids_per_advert_ids = wb_cost_ids_per_advert_ids.mappings().all()
                if wb_cost_ids_per_advert_ids:
                    for item in wb_cost_ids_per_advert_ids:
                        wb_cost_id = item['id']
                        total_for_wb_cost_id = item['total']
                        total_allocated_marketing_costs_per_wb_cost_id = await session.scalar(select(func.sum(Marketing_costs_by_SKU.cost_sum)).
                                                                                              where(Marketing_costs_by_SKU.seller_id == seller_id,
                                                                                                    Marketing_costs_by_SKU.type == 'wb_promotion',
                                                                                                    Marketing_costs_by_SKU.cost_date >= start_date,
                                                                                                    Marketing_costs_by_SKU.cost_date <= end_date,
                                                                                                    Marketing_costs_by_SKU.wb_cost_id == wb_cost_id)) or 0.0

                        diff = total_for_wb_cost_id - total_allocated_marketing_costs_per_wb_cost_id

                        if abs(diff) <= 5:
                            pass
                        else:
                            wrong_advert_ids.append({'advert_id':advert_id,
                                                     'wb_cost_id': wb_cost_id,
                                                     'total_for_wb_cost_id': total_for_wb_cost_id,
                                                     'total_allocated_marketing_costs_per_wb_cost_id': total_allocated_marketing_costs_per_wb_cost_id,
                                                     'diff':diff
                                                     })

    if wrong_advert_ids:
        try:
            await send_message_to_admin(f'Ошибки в проверке аллокации маркетинга:'
                                f'\nSeller_id: {seller_id}'
                                    f'\n{wrong_advert_ids}')
        except:
            pass
    logging.info(f'Ошибки в проверке аллокации маркетинга: Seller_id: {seller_id}: {wrong_advert_ids}')

