from datetime import datetime

from sqlalchemy import select
import config
from app.database.models import async_session, Support_tickets
from app.support.support_bot import support_bot
from app.wrappers import with_session


# Добавление нового тикета в базу
@with_session
async def new_support_ticket_registration(session, data):
    last_ticket_number = await session.scalar(select(Support_tickets.ticket_id).
                                        order_by(Support_tickets.ticket_id.desc()))
    if not last_ticket_number:
        new_ticket_number: int = 1
    else:
        new_ticket_number: int = int(last_ticket_number)+1
    async with session.begin_nested():
        session.add(Support_tickets(ticket_id=new_ticket_number,
                                    tg_id=data['tg_id'],
                                    company_name=data['company_name'],
                                    ticket_type='standard',
                                    description=data['description'],
                                    created_at=datetime.now(),
                                    status='new',
                                    tg_username = data['tg_username']
                                    ))
    await session.commit()
    await new_support_ticket_notification(data, new_ticket_number)
    return new_ticket_number

# Уведомление о поступлении нового тикета
async def new_support_ticket_notification(data, ticket_number):
    await support_bot.send_message(chat_id=config.ADMIN_ID,
                                   text=f'Новый запрос в службу поддержки!'
                                        f'\nНомер запроса: {ticket_number}'
                                        f'\ntg_id: {data['tg_id']}'
                                        f'\ntg_username: @{data['tg_username']}'
                                        f'\nКомпания: {data['company_name']}'
                                        f'\nВопрос: {data['description']}'
                                   )