from datetime import datetime

import sqlalchemy
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from app.admin.admin_message import send_message_to_admin
from app.database.models import Promocodes, PromocodeUsage
from app.wrappers import with_session, log_and_notify_admin


@with_session
async def create_new_promocode(session, promocode_data):
    async with session.begin_nested():
        promocode = Promocodes(code_title = promocode_data['code_title'].lower(),
                               promo_type = promocode_data['promo_type'],
                               discount_percentage = promocode_data['discount_percentage'],
                               discount_amount = promocode_data['discount_amount'],
                               is_active = True,
                               max_usage_number = promocode_data['max_usage_number'],
                               expires_at = datetime.strptime(promocode_data['expires_at'],'%d.%m.%Y'),
                               created_at = datetime.now(),
                               updated_at = datetime.now(),
                               max_budget = promocode_data['max_budget'])
        session.add(promocode)
    await session.commit()

@with_session
async def get_promocode_title_by_promocode_id(session, promocode_id):
    code_title = session.scalar(select(Promocodes.code_title).where(Promocodes.id == promocode_id))
    return code_title

@with_session
async def delete_promocode (session, promocode_id):
    async with session.begin_nested():
        query = (sqlalchemy.update(Promocodes).
                 where(Promocodes.id == promocode_id).
                 values(is_active=False,
                        updated_at=datetime.now()))
        await session.execute(query)
    await session.commit()

# Получить список активных промокодов:
@log_and_notify_admin
async def get_promocodes_list(session):
    result = await session.execute(select(Promocodes.id,
                                          Promocodes.code_title,
                                          Promocodes.promo_type,
                                          Promocodes.discount_percentage,
                                          Promocodes.discount_amount,
                                          Promocodes.max_usage_number,
                                          Promocodes.expires_at,
                                          Promocodes.max_budget).
                                   where(Promocodes.is_active == True))
    active_promocodes = result.mappings().all()
    #pd.DataFrame(result).to_dict('records')
    return active_promocodes

@with_session
async def get_promocodes_list_str (session):
    active_promocodes = await get_promocodes_list(session=session)
    promocodes_list_str = ""
    i = 1
    for promocode in active_promocodes:
        promocode_str = await get_promocode_data_str(session=session,
                                                     promocode_id=promocode.id)
        promocodes_list_str += (f'{str(i)}. {promocode_str}')
        i += 1
    return promocodes_list_str

@with_session
async def get_promocode_data_str(session, promocode_id):
    promocode = await session.execute(select(Promocodes.id,
                                          Promocodes.code_title,
                                          Promocodes.promo_type,
                                          Promocodes.discount_percentage,
                                          Promocodes.discount_amount,
                                          Promocodes.max_usage_number,
                                          Promocodes.expires_at,
                                          Promocodes.max_budget).
                                   where(Promocodes.id == promocode_id))
    promocode = promocode.mappings().first()
    promocode_discount = 0
    if promocode.promo_type == 'percentage':
        promocode_discount = f'{promocode.discount_percentage*100}%'
    elif promocode.promo_type == 'amount':
        discount_amount = '{:,.0f}'.format(promocode.discount_amount).replace(',', ' ')
        promocode_discount = f'{discount_amount} руб.'
    promocode_usage_number = await session.scalar(select(func.count(PromocodeUsage.id)).
                                              where(PromocodeUsage.promocode_id == promocode_id))
    promocode_used_budget = await session.scalar(select(func.sum(PromocodeUsage.discount_amount_used)).
                                              where(PromocodeUsage.promocode_id == promocode_id))
    if promocode_used_budget is None:
        promocode_used_budget = 0
    else:
        pass
    if promocode.max_budget is None:
        promocode_max_budget_str = '0'
    else:
        promocode_max_budget_str = '{:,.0f}'.format(promocode.max_budget).replace(',', ' ')
    promocode_used_budget_str: str = '{:,.0f}'.format(promocode_used_budget).replace(',', ' ')
    promocode_str = (f'{promocode.code_title} ({promocode_discount} | '
                            f'{promocode_usage_number}/{promocode.max_usage_number} | '
                            f'{promocode_used_budget_str}/{promocode_max_budget_str} '
                            f'до {datetime.strftime(promocode.expires_at,'%d.%m.%Y')})\n')
    return promocode_str

@with_session
async def check_promocodes_dates_and_usage(session):
    result = await session.execute(select(Promocodes.id).
                                   where(Promocodes.is_active == True))
    active_promocodes = result.mappings().all()
    for promocode in active_promocodes:
        await check_promocode_dates_and_usage(session=session,
                                              promocode_id=promocode.id)

@with_session
async def check_promocode_dates_and_usage(session, promocode_id):
    result = await session.execute(select(Promocodes.id,
                                      Promocodes.code_title,
                                      Promocodes.promo_type,
                                      Promocodes.discount_percentage,
                                      Promocodes.discount_amount,
                                      Promocodes.max_usage_number,
                                      Promocodes.expires_at,
                                      Promocodes.max_budget).
                                      where(Promocodes.id == promocode_id))
    promocode = result.mappings().first()
    promocode_usage_number = await session.scalar(select(func.count(PromocodeUsage.id)).
                                                  where(PromocodeUsage.promocode_id == promocode.id))
    promocode_used_budget = await session.scalar(select(func.sum(PromocodeUsage.discount_amount_used)).
                                                 where(PromocodeUsage.promocode_id == promocode.id))
    if promocode.expires_at < datetime.now():
        promocode_data_str = await get_promocode_data_str(session=session,
                                                          promocode_id=promocode.id)
        async with session.begin_nested():
            query = (sqlalchemy.update(Promocodes).
                 where(Promocodes.id == promocode.id).
                 values(is_active=False,
                        updated_at=datetime.now()))
            await session.execute(query)
        await session.commit()
        await send_message_to_admin(f'<b>Промокод удален в связи с истечением срока:</b>'
                                    f'\n{promocode_data_str}')
        return False
    elif promocode.max_usage_number <= promocode_usage_number:
        promocode_data_str = await get_promocode_data_str(session=session,
                                                          promocode_id=promocode.id)
        async with session.begin_nested():
            query = (sqlalchemy.update(Promocodes).
                     where(Promocodes.id == promocode.id).
                     values(is_active=False,
                            updated_at=datetime.now()))
            await session.execute(query)
        await session.commit()
        await send_message_to_admin(f'<b>Промокод удален в связи с окончанием количества промокодов:</b>'
                                    f'\n{promocode_data_str}')
        return False
    elif promocode.max_budget!=0:
        if not await check_promocode_budget(session=session,
                                            promocode_id=promocode_id,
                                            discount_amount=0):
            return False
        else:
            return True
    else:
        return True

@with_session
async def check_promocode_budget (session, promocode_id, discount_amount):
    promocode_max_budget = await session.scalar(select(Promocodes.max_budget).
                                                 where(Promocodes.id == promocode_id))
    if promocode_max_budget is None:
        promocode_max_budget = 0
    promocode_used_budget = await session.scalar(select(func.sum(PromocodeUsage.discount_amount_used)).
                                                 where(PromocodeUsage.promocode_id == promocode_id))
    if promocode_used_budget is None:
        promocode_used_budget =0
    if promocode_max_budget == 0:
        return True
    elif promocode_max_budget >= (promocode_used_budget+discount_amount):
        return True
    else:
        promocode_data_str = await get_promocode_data_str(session=session, promocode_id=promocode_id)
        async with session.begin_nested():
            query = (sqlalchemy.update(Promocodes).
                     where(Promocodes.id == promocode_id).
                     values(is_active=False,
                            updated_at=datetime.now()))
            await session.execute(query)
        await session.commit()
        await send_message_to_admin(f'<b>Промокод удален в связи с окончанием бюджета:</b>'
                                    f'\n{promocode_data_str}')
        return False

@with_session
async def create_active_promocodes_keyboard(session):
    promocodes_list_buttons = InlineKeyboardBuilder()
    active_promocodes = await get_promocodes_list(session=session)
    i = 1
    for promocode in active_promocodes:
        promocode_discount=0
        if promocode.promo_type == 'percentage':
            promocode_discount = f'{promocode.discount_percentage * 100}%'
        elif promocode.promo_type == 'amount':
            discount_amount = '{:,.0f}'.format(promocode.discount_amount).replace(',', ' ')
            promocode_discount = f'{discount_amount} руб.'
        promocode_usage_number = await session.scalar(select(func.count(PromocodeUsage.id)).
                                                      where(PromocodeUsage.promocode_id == promocode.id))
        promocode_used_budget = await session.scalar(select(func.sum(PromocodeUsage.discount_amount_used)).
                                                     where(PromocodeUsage.promocode_id == promocode.id))
        if promocode_used_budget is None:
            promocode_used_budget = 0
        else:
            pass
        if promocode.max_budget is None:
            promocode_max_budget_str = '0'
        else:
            promocode_max_budget_str = '{:,.0f}'.format(promocode.max_budget).replace(',', ' ')
        promocode_used_budget_str: str = '{:,.0f}'.format(promocode_used_budget).replace(',', ' ')
        active_promocode_button_str = (f'{str(i)}. {promocode.code_title} ({promocode_discount} | '
                                f'{promocode_usage_number}/{promocode.max_usage_number} | '
                                f'{promocode_used_budget_str}/{promocode_max_budget_str} '
                                f'до {datetime.strftime(promocode.expires_at, '%d.%m.%Y')})\n')
        i += 1
        promocodes_list_buttons.button(text=active_promocode_button_str,callback_data=str(promocode.id), resize_keyboard=True)
    promocodes_list_buttons.button(text='Отменить', callback_data='cancel',resize_keyboard=True)
    promocodes_list_buttons.adjust(1,1)
    return promocodes_list_buttons
