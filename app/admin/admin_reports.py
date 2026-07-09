from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy import select, func
import logging

from app.admin.admin_message import send_message_to_admin
from app.admin.promo_admin_functions import check_promocodes_dates_and_usage, get_promocodes_list_str
from app.database.models import async_session, Seller, Reports, Support_tickets, Invoices, Subscriptions, \
    Transactions
from app.database.classes.stocks import Stock
from app.dates import today_str_func, start_of_yesterday_func, end_of_yesterday_func, start_of_today_func
from app.wrappers import with_session


# Отчет admin-status
async def admin_system_status_daily():
    async with async_session() as session:
        try:
            system_status = await system_status_prep('daily')
            await send_message_to_admin(system_status)
        except Exception as e:
            # Запись ошибки в лог
            await send_message_to_admin(text=f'Ошибка при отправке admin_отчета!'
                                             f'\nОшибка: {e}')
            logging.error("An error occurred: %s", str(e))

# Отчет по загрузке остатков Stock
async def admin_stocks_download_status():
    async with async_session() as session:
        active_companies = await session.scalar(select(func.count(Seller.id)).
                                                 where(Seller.status=='Active',
                                                       Seller.service_status==True))
        today_str = await today_str_func()
        stock_companies = await session.scalar(select(func.count()).
                                               select_from(select(Stock.seller_id).
                                                           where(Stock.date_in_stock_str == today_str).
                                                           group_by(Stock.seller_id).subquery()))
        stock_rows = await session.scalar(select(func.count(Stock.id)).
                                               where(Stock.date_in_stock_str == today_str))
        download_report = (f'Отчет по загрузке остатков за {today_str}:'
                         f'\nВсего активных компаний: {active_companies}'
                        f'\nЗагружено остатков по компаниям: {stock_companies}'
                         f'\nЗагружено строк: {stock_rows}')
        await send_message_to_admin(download_report)

# Общий отчет по системе
async def system_status_prep(report_type):
    async with async_session() as session:
        if report_type == 'daily':
            start_of_yesterday = await start_of_yesterday_func()
            date_from = start_of_yesterday
            end_of_yesterday = await end_of_yesterday_func()
            date_to = end_of_yesterday
        elif report_type == 'now':
            start_of_today = await start_of_today_func()
            date_from = start_of_today
            date_to = datetime.now()
        start_of_month = date_from.replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        start_of_prior_month = (start_of_month - timedelta(days=1)).replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        date_to_prior_month = start_of_prior_month + timedelta(days=datetime.now().day)
        total_companies = await session.scalar(select(func.count(Seller.id)))
        active_companies = await session.scalar(select(func.count(Seller.id)).
                                                 where(Seller.status=='Active',
                                                       Seller.service_status==True))
        new_companies = await session.scalar(select(func.count(Seller.id)).
                                                where(Seller.status == 'Active',
                                                      Seller.service_status == True,
                                                      Seller.date_created>=date_from,
                                                      Seller.date_created<=date_to))
        blocked_companies = await session.scalar(select(func.count(Seller.id)).
                                                where(Seller.status == 'Blocked'))
        deleted_companies = await session.scalar(select(func.count(Seller.id)).
                                                 where(Seller.status == 'Deleted'))
        monthly_reports_sent = await session.scalar(select(func.count(Reports.id)).
                                                 where(Reports.report_type == 'monthly',
                                                       Reports.report_status=='sent',
                                                       Reports.created_at>=date_from,
                                                       Reports.created_at<=date_to))
        monthly_reports_sent_auto = await session.scalar(select(func.count(Reports.id)).
                                                    where(Reports.report_type == 'monthly',
                                                          Reports.report_status == 'sent',
                                                          Reports.report_creation_type == 'auto',
                                                          Reports.created_at >= date_from,
                                                          Reports.created_at<=date_to))
        monthly_reports_sent_on_demand = await session.scalar(select(func.count(Reports.id)).
                                                         where(Reports.report_type == 'monthly',
                                                               Reports.report_status == 'sent',
                                                               Reports.report_creation_type == 'on_demand',
                                                               Reports.created_at >= date_from,
                                                               Reports.created_at <= date_to))
        weekly_reports_sent = await session.scalar(select(func.count(Reports.id)).
                                                 where(Reports.report_type == 'weekly',
                                                       Reports.report_status=='sent',
                                                       Reports.created_at>=date_from,
                                                       Reports.created_at<=date_to))
        weekly_reports_sent_auto = await session.scalar(select(func.count(Reports.id)).
                                                 where(Reports.report_type == 'weekly',
                                                       Reports.report_status=='sent',
                                                       Reports.report_creation_type == 'auto',
                                                       Reports.created_at>=date_from,
                                                       Reports.created_at<=date_to))
        weekly_reports_sent_on_demand = await session.scalar(select(func.count(Reports.id)).
                                                 where(Reports.report_type == 'weekly',
                                                       Reports.report_status=='sent',
                                                       Reports.report_creation_type == 'on_demand',
                                                       Reports.created_at>=date_from,
                                                       Reports.created_at<=date_to))
        new_support_requests = await session.scalar(select(func.count(Support_tickets.id)).
                                                 where(Support_tickets.created_at>=date_from,
                                                       Support_tickets.created_at<=date_to))
        replied_support_requests = await session.scalar(select(func.count(Support_tickets.id)).
                                                 where(Support_tickets.replied_at>=date_from,
                                                       Support_tickets.replied_at<=date_to,
                                                        Support_tickets.status == 'replied'))
        without_reply_support_requests = await session.scalar(select(func.count(Support_tickets.id)).
                                                        where(Support_tickets.status == 'new'))
        invoices_issued = await session.scalar(select(func.count(Invoices.id)).
                                                        where(Invoices.status != 'canceled',
                                                              Invoices.created_at>=date_from,
                                                              Invoices.created_at<=date_to))
        invoices_issued_amount = await session.scalar(select(func.sum(Invoices.amount)).
                                                        where(Invoices.status != 'canceled',
                                                              Invoices.created_at>=date_from,
                                                              Invoices.created_at<=date_to))
        if not invoices_issued_amount:
            invoices_issued_amount = 0
        invoices_paid = await session.scalar(select(func.count(Invoices.id)).
                                                        where(Invoices.status == 'payment_paid',
                                                              Invoices.paid_at>=date_from,
                                                              Invoices.paid_at<=date_to))
        invoices_paid_amount = await session.scalar(select(func.sum(Invoices.amount)).
                                                        where(Invoices.status == 'payment_paid',
                                                              Invoices.paid_at>=date_from,
                                                              Invoices.paid_at<=date_to))
        if not invoices_paid_amount:
            invoices_paid_amount = 0
        invoices_paid_monthly = await session.scalar(select(func.count(Invoices.id)).
                                             where(Invoices.status == 'payment_paid',
                                                   Invoices.paid_at >= start_of_month,
                                                   Invoices.paid_at <= date_to))
        invoices_paid_monthly_amount = await session.scalar(select(func.sum(Invoices.amount)).
                                                    where(Invoices.status == 'payment_paid',
                                                          Invoices.paid_at >= start_of_month,
                                                          Invoices.paid_at <= date_to))
        if not invoices_paid_monthly_amount:
            invoices_paid_monthly_amount = 0
        subscriptions_issued = await session.scalar(select(func.count(Subscriptions.id)).
                                               where(Subscriptions.status != 'canceled',
                                                     Subscriptions.subscription_type!='promo',
                                                     Subscriptions.created_at >= date_from,
                                                     Subscriptions.created_at <= date_to))
        subscriptions_issued_amount = await session.scalar(select(func.sum(Subscriptions.amount)).
                                                      where(Subscriptions.status != 'canceled',
                                                            Subscriptions.created_at >= date_from,
                                                            Subscriptions.created_at <= date_to))
        if not subscriptions_issued_amount:
            subscriptions_issued_amount = 0
        subscriptions_billable = await session.scalar(select(func.count(Subscriptions.id)).
                                               where(Subscriptions.status == 'active',
                                                     Subscriptions.subscription_type!='promo',
                                                     Subscriptions.subscription_type != 'trial'))
        subscriptions_free = await session.scalar(select(func.count(Subscriptions.id)).
                                               where(Subscriptions.status == 'active',
                                                     or_(Subscriptions.subscription_type=='promo',Subscriptions.subscription_type == 'trial')))
        revenue_daily = await session.scalar(select(func.sum(Transactions.amount)).
                                                      where(Transactions.transaction_type == 'debit',
                                                            Transactions.transaction_stream=='revenue',
                                                            Transactions.created_at >= date_from,
                                                            Transactions.created_at <= date_to))
        if not revenue_daily:
            revenue_daily = 0
        revenue_monthly = await session.scalar(select(func.sum(Transactions.amount)).
                                                      where(Transactions.transaction_type == 'debit',
                                                            Transactions.transaction_stream=='revenue',
                                                            Transactions.created_at >= start_of_month,
                                                            Transactions.created_at <= date_to))
        if not revenue_monthly:
            revenue_monthly = 0
        revenue_prior_month = await session.scalar(select(func.sum(Transactions.amount)).
                                                      where(Transactions.transaction_type == 'debit',
                                                            Transactions.transaction_stream=='revenue',
                                                            Transactions.created_at >= start_of_prior_month,
                                                            Transactions.created_at <= date_to_prior_month))
        if not revenue_prior_month:
            revenue_prior_month = 0
        total_invoices_paid = await session.scalar(select(func.sum(Invoices.amount)).
                                                            where(Invoices.status == 'payment_paid'))
        if not total_invoices_paid:
            total_invoices_paid = 0
        total_revenue_recognised = await session.scalar(select(func.sum(Transactions.amount)).
                                                      where(Transactions.transaction_type == 'debit',
                                                            Transactions.transaction_stream=='revenue'))
        if not total_revenue_recognised:
            total_revenue_recognised = 0
        prepayments = total_invoices_paid - total_revenue_recognised
        prepayments_str = '{:,.0f}'.format(prepayments).replace(',', ' ')
        invoices_issued_amount_str = '{:,.0f}'.format(invoices_issued_amount).replace(',', ' ')
        revenue_daily_str = '{:,.0f}'.format(revenue_daily).replace(',', ' ')
        revenue_monthly_str = '{:,.0f}'.format(revenue_monthly).replace(',',' ')
        invoices_paid_amount_str = '{:,.0f}'.format(invoices_paid_amount).replace(',',' ')
        subscriptions_issued_amount_str = '{:,.0f}'.format(subscriptions_issued_amount).replace(',',' ')
        invoices_paid_monthly_amount_str = '{:,.0f}'.format(invoices_paid_monthly_amount).replace(',',' ')

        if not revenue_monthly:
            monthly_growth_str = f'+0'
            monthly_growth_percent = f'+0%'
        else:
            if not revenue_prior_month:
                monthly_growth_str = f'+{revenue_monthly_str}'
                monthly_growth_percent = f'+100%'
            else:
                monthly_growth = (revenue_monthly - revenue_prior_month)
                monthly_growth_percent = f'{(monthly_growth / revenue_prior_month):.0%}'
                if monthly_growth > 0:
                    monthly_growth_str = f'+{monthly_growth:,.0f}'.replace(',',' ')
                else:
                    monthly_growth_str = f'{monthly_growth:,.0f}'.replace(',',' ')
        system_status = (f'<b>ФиндирЭкспресс</b>'
                         f'\n\n<b>Статус системы за {date_to.strftime('%Y-%m-%d')}:</b>'
                         f'\nВсего компаний: {total_companies}'
                         f'\nАктивных компаний: {active_companies}'
                         f'\nНовых компаний: {new_companies}'
                         f'\nЗаблокировано/удалено: {blocked_companies+deleted_companies}'
                         f'\n'
                         f'\n<b>Выручка:</b>'
                         f'\nВыручка за день: {revenue_daily_str} руб.'
                         f'\nВыручка за месяц (накопительно): {revenue_monthly_str} руб.'
                         f'\nВыручка за месяц (vs PM): {monthly_growth_str} руб. /  {monthly_growth_percent}'
                         f'\nВыставлено счетов: {invoices_issued} шт. / {invoices_issued_amount_str} руб.'
                         f'\nОплачено счетов: {invoices_paid} шт. / {invoices_paid_amount_str} руб.'
                         f'\nОплачено счетов за месяц: {invoices_paid_monthly} шт. / {invoices_paid_monthly_amount_str} руб.'
                         f'\nАвансы по подпискам: {prepayments_str} руб.'
                         f'\n'
                         f'\n<b>Подписки:</b>'
                         f'\nОформлено/продлено подписок: {subscriptions_issued} шт. / {subscriptions_issued_amount_str} руб.'
                         f'\nВсего действующих платных подписок: {subscriptions_billable} шт.'
                         f'\nВсего подписок с промокодами:  шт./%'
                         f'\nВсего действующих бесплатных подписок: {subscriptions_free} шт.'
                         f'\n'
                         f'\n<b>Отчеты</b>'
                         f'\nОтправлено месячных отчетов: {monthly_reports_sent}'
                         f'\n - автоматически: {monthly_reports_sent_auto}'
                         f'\n - по требованию: {monthly_reports_sent_on_demand}'
                         f'\nОтправлено недельных отчетов: {weekly_reports_sent}'
                         f'\n - автоматически: {weekly_reports_sent_auto}'
                         f'\n - по требованию: {weekly_reports_sent_on_demand}'
                         f'\n'
                         f'\n<b>Поддержка</b>'
                         f'\nНовых вопросов: {new_support_requests}'
                         f'\nОтвечено: {replied_support_requests}'
                         f'\nОсталось без ответа: {without_reply_support_requests}')
        return system_status


# Отчет по промокодам
@with_session
async def daily_promocodes_check_admin_report(session):
    await check_promocodes_dates_and_usage(session=session)
    report = await get_promocodes_list_str(session=session)
    await send_message_to_admin(f'<b>Промокоды проверены!</b>'
                                f'\nАктивные промокоды:'
                                f'\n{report}')