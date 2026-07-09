from datetime import timedelta, datetime
from sqlalchemy import select, func
import logging
import asyncio
from threading import Lock

from app.admin.admin_message import send_message_to_admin
from app.database.classes.sales import Sales
from app.get_data.get_missing_info import repair_missing_goods_info
from app.get_data.get_sales_data import get_and_check_sales_report
from app.get_data.get_stocks import get_and_check_stocks_data
from app.get_data.marketing import get_prepare_marketing_costs_for_seller, allocate_marketing_costs_to_sku, \
    check_marketing_costs_allocation
from app.get_data.orders import get_orders_by_seller
from app.get_data.orders_nm import get_orders_by_nm_by_seller
from app.get_data.paid_acceptance import get_paid_acceptance_data_by_seller
from app.get_data.storage import get_storage_costs_by_seller
from app.locks import per_seller_lock
from app.reports.monthly_finreport import get_monthly_pl
from app.reports.weekly_finreport import get_weekly_pl
from app.database.models import Seller, Storage_costs, Paid_acceptance, async_session
from app.database.classes.stocks import Stock
from app.database.requests import check_cost, set_pl_results, set_cost_to_stock
from app.database.sales_report_compilation import sales_report_compilation
from app.database.support_functions import check_company_status, update_weekly_report_sent_date, \
    get_chat_id_by_seller_id, \
    check_three_barcodes, update_weekly_pl_calculation_date, \
    update_monthly_report_sent_date, get_seller_inn_by_seller_id, block_seller
from app.database.dates_functions import get_latest_weekly_report_sent_date, get_latest_pl_calculation_date, \
    get_latest_available_info_date, get_latest_monthly_report_sent_date
from app.dates import start_for_downloading_data_func, end_of_Reporting_Week_func, end_of_Reporting_Month_func, \
    start_of_Reporting_Month_func, start_of_Reporting_Week_func, end_of_Prior_Month_func, start_of_Prior_Month_func, \
    today_str_func, end_of_Prior_Week_func, start_of_Prior_Week_func
from app.wrappers import with_session, log_and_notify_admin
from app.semaphore import semaphore

class Counters:
    def __init__(self):
        self._lock = Lock()
        self.common_counter = 0
        self.already_sent_counter = 0
        self.download_counter = 0
        self.bad_api_counter = 0
        self.no_data_counter = 0
        self.no_stocks_counter = 0
        self.sales_upload_counter = 0
        self.unauthorised_api_counter = 0
        self.unknown_reply_counter = 0
        self.blocked_counter = 0
        self.error_in_support_get_data = 0
        self.report_sent_counter = 0
        self.check_cost_failed_counter = 0
        self.monthly_report_counter = 0

    def reset(self):
        # Сбрасываем только счетчики, не затрагивая _lock
        self.common_counter = 0
        self.already_sent_counter = 0
        self.download_counter = 0
        self.bad_api_counter = 0
        self.no_data_counter = 0
        self.no_stocks_counter = 0
        self.sales_upload_counter = 0
        self.unauthorised_api_counter = 0
        self.unknown_reply_counter = 0
        self.blocked_counter = 0
        self.error_in_support_get_data = 0
        self.report_sent_counter = 0
        self.check_cost_failed_counter = 0
        self.monthly_report_counter = 0

    def increment(self, name):
        with self._lock:
            setattr(self, name, getattr(self, name) + 1)

counter = Counters()


# Основная функция по отправке отчетов:
async def main_regular_reporting_function():
    try:
        async with async_session() as session:
            active_sellers = await session.scalar(select(func.count(Seller.id)).
                                                  where(Seller.status == 'Active',
                                                        Seller.service_status == True))
            counter.reset()

            # Получаем список селлеров для выгрузки, подготовки отчетов и рассылки
            companies = await session.execute(select(Seller.id).
                                              where(Seller.status == 'Active',
                                                    Seller.service_status == True))
            companies = companies.mappings().all()

        # Создаем список корутин с каскадным запуском (staggering)
        tasks = []
        for i, seller in enumerate(companies):
            # Каждому селлеру даем задержку старта на 10 секунд больше, чем предыдущему.
            delay = i * 10
            tasks.append(run_with_semaphore(seller_id=int(seller['id']), delay=delay))

        await asyncio.gather(*tasks)

        await send_report_summary(active_sellers)
    except Exception as e:
        await send_message_to_admin(f'Ошибка в основной отчетной функции!')
        await log_error(f'Ошибка в основной отчетной функции!', e)
    finally:
        await session.close()


@log_and_notify_admin
async def run_with_semaphore(seller_id, delay=0):
    # Спим заданное время, чтобы не ломиться в API всем табуном
    if delay > 0:
        await asyncio.sleep(delay)

    # Ограничиваем количество одновременных вызовов с помощью семафора
    async with semaphore:
        await main_reporting_function_for_seller_id(seller_id=seller_id)

@with_session
@per_seller_lock(seller_id_param="seller_id", timeout=3600)
async def main_reporting_function_for_seller_id(session, seller_id):
    try:
        counter.increment('common_counter')
        # Проверяем выгружены ли остатки, если не выгружены, то выгружаем, если не выгружаются, то ничего не выполняем.
        if await check_stocks_data(seller_id=seller_id):
            logging.info(f'Seller_id: {seller_id}. Проверили остатки товаров: Ок')
            if await get_support_data(seller_id=seller_id):
                # pass
                logging.info(f'Seller_id: {seller_id}. Выгрузили support_data')
                # return True
                downloading, reporting, latest_weekly_report_sent_date = await get_latest_reporting_dates(session=session, seller_id=seller_id)
                logging.info(f'Seller_id: {seller_id}, downloading: {downloading}, reporting: {reporting}, '
                             f''f'latest_weekly_report_sent_date: {latest_weekly_report_sent_date}')
                # print(seller_id, downloading,reporting,latest_weekly_report_sent_date)
                if downloading == True:
                    reporting = await download_fin_report(session=session, seller_id=seller_id)
                    # === ДОБАВЛЕНО ===
                    logging.info(
                        f'Seller_id: {seller_id}. Запускаем восстановление отсутствующих данных о товарах (Контент API).')
                    await repair_missing_goods_info(session=session, seller_id=seller_id)
                    # =================
                    print(seller_id,'выгрузили выручку')
                # 3. СЧИТАЕМ PL и ОТПРАВЛЯЕМ ОТЧЕТЫ
                if reporting == True:
                    # print(seller_id, 'готовим отчеты')
                    await process_reporting(session=session, seller_id=seller_id)
                    # print(seller_id, 'отправили отчеты')
                else:
                    pass
            else:
                counter.increment('error_in_support_get_data')
        else:
            counter.increment('no_stocks_counter')
        # Запись ошибки в лог
    except Exception as e:
        await send_message_to_admin(f'Ошибка в основной отчетной функции!'
                                    f'Seller_id: {seller_id}'
                                    f'\nОшибка: '
                                    f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)


@with_session
async def get_support_data(session, seller_id):
    
    logging.info(f'Seller_id: {seller_id} - выгружаем заказы')
    if await get_orders_by_seller(seller_id=seller_id):
        logging.info(f'Seller_id: {seller_id} - выгрузили заказы')
        # return True
        #print(seller_id,'выгружаем заказы по номенклатуре')
        logging.info(f'Seller_id: {seller_id} - выгружаем заказы по номенклатуре')
        if await get_orders_by_nm_by_seller(seller_id=seller_id):
            # return True

            # print(seller_id,'выгружаем хранение')
            logging.info(f'Seller_id: {seller_id} - выгружаем хранение')
            if await get_storage_costs_by_seller(session=session, seller_id=seller_id):

                logging.info(f'Seller_id: {seller_id} - выгружаем платную приемку')
                # print(seller_id,'выгружаем платную приемку')
                if await get_paid_acceptance_data_by_seller(session=session, seller_id=seller_id):
                    # print(seller_id,'выгружаем маркетинг')
                    logging.info(f'Seller_id: {seller_id} - выгружаем маркетинг')
                    if await get_prepare_marketing_costs_for_seller(session=session, seller_id=seller_id):
                        # print(seller_id,'закончили маркетинг')
                        logging.info(f'Seller_id: {seller_id} - закончили маркетинг, закончили вспомогательные выгрузки')
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False
    else:
        return False

@log_and_notify_admin
async def get_latest_reporting_dates(session, seller_id):
    try:
        logging.info(f'Seller_id: {seller_id} - считаем даты')
        downloading = True
        reporting = True
        # Берем начальные даты для функции:
        date_to = await end_of_Reporting_Week_func()
        start_for_downloading_data = await start_for_downloading_data_func()
        # 1. ОПРЕДЕЛЯЕМ КАКИЕ ОТЧЕТЫ ОТПРАВЛЯЛИСЬ
        # проверяем, отправлялся ли отчет за отчетную неделю:
        latest_weekly_report_sent_date = await get_latest_weekly_report_sent_date(session=session, seller_id=seller_id)

        # 1.1.если вообще не было отчетов, то:
        if not latest_weekly_report_sent_date:
            # берем самую раннюю дату для начала выгрузки
            latest_weekly_report_sent_date = start_for_downloading_data - timedelta(microseconds=1)
        # 1.3. ЕСЛИ ОТЧЕТ УЖЕ ОТПРАВЛЯЛСЯ, ТО НИЧЕГО НЕ ДЕЛАЕМ
        elif latest_weekly_report_sent_date == date_to:
            counter.increment('already_sent_counter')
            downloading = False
            reporting = False
        # 1.2. если не было отчета за последнюю неделю, то:
        elif latest_weekly_report_sent_date < date_to:
            # print(seller_id, 'мы тут')
            # print(seller_id, latest_weekly_report_sent_date)
            pass
        elif latest_weekly_report_sent_date > date_to:
            await send_message_to_admin(f"Ошибка даты для seller_id={seller_id}: latest_weekly_report_sent_date > date_to")
            downloading = False
            reporting = False
        else:
            await send_message_to_admin(f'Ошибка в latest_weekly_report_sent_date в основной отчетной функции!')
            downloading = False
            reporting = False
        # print(seller_id,latest_weekly_report_sent_date)
        # print(seller_id, downloading, reporting, latest_weekly_report_sent_date)
        logging.info(f'Seller_id: {seller_id}, downloading: {downloading}, reporting: {reporting}, latest_weekly_report_sent_date: {latest_weekly_report_sent_date}')
        return downloading, reporting, latest_weekly_report_sent_date
    except Exception as e:
        await log_error(f'Ошибка в определении дат для отчетов:'
                        f'\nSeller_id: {seller_id}'
                        f'\nОшибка: {e}', e)

@log_and_notify_admin
async def download_fin_report(session, seller_id):
    try:
        logging.info(f'Seller_id: {seller_id}. Выгружаем выручку.')
        downloading = True
        reporting = True
        date_to = await end_of_Reporting_Week_func()
        # 2. ПРОВЕРЯЕМ, НУЖНО ЛИ ВЫГРУЖАТЬ ДАННЫЕ:
        # 2.1. Берем даты для выгрузки продаж:
        # Берем последнюю дату, на которую есть информация, если нет данных, то берем самую раннюю
        available_sales_info_date = await get_latest_available_info_date(session=session, seller_id=seller_id)
        # 3. проверяем, есть ли данные на дату отчета:
        if available_sales_info_date == date_to:
            # если есть, то не выгружаем
            downloading = False
        # 4.1. берем дату для выгрузки
        date_from_for_downloading = available_sales_info_date + timedelta(microseconds=1)
        logging.info(f'Seller_id: {seller_id}. Выгружаем выручку. downloading: {downloading},date_from_for_downloading: {date_from_for_downloading},date_to: {date_to}')
        # print(f'Скачиваем выручку',seller_id,downloading,date_from_for_downloading,date_to)
        # 4.2. Выгружаем и проверяем продажи за неделю:
        if downloading == True:
            downloading_status = False
            downloading_counter = 0
            while downloading_status != True and downloading_counter < 15:
                logging.info(f'Seller_id: {seller_id}. Выгружаем выручку. Downloading status: {downloading_status},'
                             f'downloading_counter: {downloading_counter}')
                status, sales_report = await get_and_check_sales_report(session=session,
                                                                        seller_id=seller_id,
                                                                        date_to=date_to,
                                                                        date_from=date_from_for_downloading)
                if status == 'unauthorised_api':
                    counter.increment('bad_api_counter')
                    reporting = False
                    downloading_status = True
                elif status == 'new_unauthorised_api':
                    counter.increment('unauthorised_api_counter')
                    reporting = False
                    downloading_status = True
                elif status == 'unknown':
                    await send_message_to_admin(f'Неизвестный ответ от ВБ в регулярной загрузке продаж!'
                                                f'\nSeller_id: {seller_id}'
                                                f'\nSeller_inn: {await get_seller_inn_by_seller_id(session=session,seller_id=seller_id)}'
                                                f'\ntg_id: {await get_chat_id_by_seller_id(session=session, seller_id=seller_id)}'
                                                f'\nОтвет ВБ: '
                                                f'{sales_report}')
                    reporting = False
                    downloading_status = True
                    counter.increment('unknown_reply_counter')
                elif status == 'no_data':
                    counter.increment('no_data_counter')
                    reporting = False
                    downloading_status = True
                elif status == 'Done':
                    counter.increment('download_counter')
                    # проверяем баркоды
                    logging.info(f'Seller_id: {seller_id}. Выгрузили выручку: {len(sales_report)} строк. Проверяем баркоды.')
                    check_barcodes = await check_three_barcodes(session, sales_report, seller_id)
                    if check_barcodes:
                        # Загружаем продажи в базу
                        logging.info(f'Seller_id: {seller_id}. Баркоды Ок. Загружаем выручку в базу.')
                        if await sales_report_compilation(session=session, seller_id=seller_id, sales_report=sales_report):
                            counter.increment('sales_upload_counter')

                            downloading_status = True
                        else:
                            reporting = False
                            downloading_status = True
                    # Блокируем компанию, если уже есть такие баркоды:
                    else:
                        await block_seller(session=session, seller_id=seller_id)
                        counter.increment('blocked_counter')
                        await send_message_to_admin(f'Seller_id: {seller_id}. Селлер заблокирован после проверки баркодов.')
                        logging.info(f'Seller_id: {seller_id}. Селлер заблокирован после проверки баркодов.')
                        reporting = False
                        downloading_status = True
                elif status == 'not_complete':
                    # проверяем баркоды
                    logging.info(f'Seller_id: {seller_id}. Статус загрузки выручки: {status}.')
                    check_barcodes = await check_three_barcodes(session, sales_report, seller_id)
                    if check_barcodes:
                        logging.info(f'Seller_id: {seller_id}. Баркоды Ок. Загружаем выручку в базу.')
                        # Загружаем продажи в базу
                        if await sales_report_compilation(session=session, seller_id=seller_id, sales_report=sales_report):
                            logging.info(f'Seller_id: {seller_id}. Загрузили выручку в базу.')
                            latest_downloaded_date = await get_latest_available_info_date(session=session, seller_id=seller_id)
                            if latest_downloaded_date >= date_to:
                                downloading_status = True
                                logging.info(f'Seller_id: {seller_id}. Выручка загружена по {latest_downloaded_date}.')
                            else:
                                date_from_for_downloading = latest_downloaded_date + timedelta(microseconds=1)
                                downloading_counter += 1
                                logging.info(f'Seller_id: {seller_id}. Выручка загружена по {latest_downloaded_date}. Ждем 60, выгружаем дальше с {date_from_for_downloading}')
                                await asyncio.sleep(60)
                        else:
                            reporting = False
                            downloading_status = True
                    # Блокируем компанию, если уже есть такие баркоды:
                    else:
                        await block_seller(session=session, seller_id=seller_id)
                        counter.increment('blocked_counter')
                        await send_message_to_admin(f'Seller_id: {seller_id}. Селлер заблокирован после проверки баркодов.')
                        logging.info(f'Seller_id: {seller_id}. Селлер заблокирован после проверки баркодов.')
                        reporting = False
                        downloading_status = True
                else:
                    await send_message_to_admin(f'Ошибка в latest_weekly_report_sent_date в основной отчетной функции!')
                    reporting = False
        return reporting

    except Exception as e:
        await log_error(f'Ошибка в выгрузке фин.отчета:'
                        f'\nSeller_id: {seller_id}'
                        f'\nОшибка: {e}', e)

@log_and_notify_admin
async def process_reporting(session, seller_id):
    try:
        # Проверяем статус селлера перед дальнейшим расчетом:
        logging.info(f'Seller_id: {seller_id}. Начали отчетную функцию.')
        if await check_company_status(session=session, seller_id=seller_id):
            logging.info(f'Seller_id: {seller_id}. Проверили селлера и подписку: Ок.')
            reporting = True
            date_to = await end_of_Reporting_Week_func()
            end_of_Prior_Week = await end_of_Prior_Week_func()
            latest_weekly_report_sent_date = await get_latest_weekly_report_sent_date(session=session, seller_id=seller_id)
            logging.info(f'Seller_id: {seller_id}. Начали аллокацию маркетинговых расходов.')
            await allocate_marketing_costs_to_sku(session=session, seller_id=seller_id)
            logging.info(f'Seller_id: {seller_id}. Закончили аллокацию маркетинговых расходов.')
            logging.info(f'Seller_id: {seller_id}. Проверяем аллокацию маркетинговых расходов.')
            await check_marketing_costs_allocation(session=session, seller_id=seller_id)
            logging.info(f'Seller_id: {seller_id}. Проверяем детализацию расходов на хранение.')
            await check_storage_costs_allocation(session=session, seller_id=seller_id)
            logging.info(f'Seller_id: {seller_id}. Проверяем детализацию расходов по платной приемке.')
            await check_paid_acceptance_costs_detalisation(session=session, seller_id=seller_id)

            # Считаем даты для PL
            latest_pl_calculation_date: datetime = await get_latest_pl_calculation_date(session=session, seller_id=seller_id)
            available_sales_info_date = await get_latest_available_info_date(session=session, seller_id=seller_id)
            logging.info(f'Seller_id: {seller_id}. Даты для обработки: '
                         f'end_of_reporting_week: {date_to},'
                         f'last_sent_date: {latest_weekly_report_sent_date},'
                         f'availables_sales_date: {available_sales_info_date}.')
            # Если PL ни разу не считался, то считаем с самого начала
            if not latest_pl_calculation_date:
                date_from_for_pl = await start_for_downloading_data_func()
            # Если PL считался, то считаем с последнего расчета
            else:
                date_from_for_pl = latest_pl_calculation_date + timedelta(microseconds=1)

            # Проверяем себестоимость и если 0, то отправляем пользователю шаблон для заполнения:
            if await check_cost(session=session, seller_id=seller_id):
                logging.info(f'Seller_id: {seller_id}. Проверили себестоимость товаров: Ок')
                # Проверяем, появились ли данные на конец отчетной недели:

                date_from_for_report = await start_of_Reporting_Week_func()
                # если появились, то отправляем отчет за последнюю неделю
                if available_sales_info_date == date_to:
                    pass
                # если данные есть только на конец предыдущей недели и отчет за предыдущую неделю не отправлялся, то отправляем за предыдущую неделю:
                elif available_sales_info_date == end_of_Prior_Week and latest_weekly_report_sent_date != end_of_Prior_Week:
                    date_to = end_of_Prior_Week
                    date_from_for_report = await start_of_Prior_Week_func()
                # если что-то непонятное:
                else:
                    await send_message_to_admin(f'Ошибка в датах подготовки отчетов!')
                    reporting = False
                if reporting == True:
                    logging.info(f'Seller_id: {seller_id}. Готовим недельный отчет_date_from_for_pl={date_from_for_pl}_date_from_for_report={date_from_for_report}_date_to={date_to}')
                    weekly_status = await weekly_reports_calculation_and_send(session=session,
                                                                              seller_id=seller_id,
                                                                              date_from_for_pl=date_from_for_pl,
                                                                              date_from_for_report=date_from_for_report,
                                                                              date_to=date_to)
                    logging.info(f'Seller_id: {seller_id}. Статус недельного отчета: {weekly_status}')

                    if weekly_status:
                        counter.increment('report_sent_counter')
                    logging.info(f'Seller_id: {seller_id}. Готовим месячный отчет')
                    monthly_status = await monthly_report_calculation_and_send(session=session, seller_id=seller_id)
                    logging.info(f'Seller_id: {seller_id}. Статус месячного отчета: {monthly_status}')
                    if monthly_status:
                        counter.increment('monthly_report_counter')
                else:
                    pass
            else:
                logging.info(f'Seller_id: {seller_id}. Проверили себестоимость товаров: отправили шаблон')
                counter.increment('check_cost_failed_counter')
        else:
            logging.info(f'Seller_id: {seller_id}. Проверили селлера и подписку: False.')
    except Exception as e:
        await log_error(f'Ошибка в расчете PL и отправке отчетов:'
                        f'\nSeller_id: {seller_id}'
                        f'\nОшибка: {e}', e)

@log_and_notify_admin
async def check_stocks_data(seller_id):
    # Проверяем, что за сегодня выгружены Stocks:
    today_str = await today_str_func()
    async with async_session() as session:
        stock = await session.scalar(select(Stock.id).
                                  where(Stock.seller_id == seller_id,
                                        Stock.date_in_stock_str == today_str))
    if not stock:
        if await get_and_check_stocks_data(seller_id=seller_id):
            return True
        else:
            return False
    else:
        logging.info(f'Seller_id: {seller_id}. Проверили остатки товаров: Ок')
        return True

@log_and_notify_admin
@per_seller_lock(seller_id_param="seller_id", timeout=600)
async def weekly_reports_calculation_and_send (session, seller_id, date_from_for_pl, date_from_for_report, date_to):
    try:
        status = False
        # Проверяем, что компания все еще активная и не заблокирована, и что себестоимость в базе ок:
        if await check_company_status(session=session, seller_id=seller_id) and await check_cost(session=session, seller_id=seller_id):
            # считаем PL в таблице Sales и остатки по с\с в таблице Stock:
            await set_pl_results(session=session, seller_id=seller_id, date_start= date_from_for_pl)
            await set_cost_to_stock(session=session, seller_id=seller_id, date_start= date_from_for_pl)
            await update_weekly_pl_calculation_date(session=session,
                                                    seller_id=seller_id,
                                                    date_to=date_to)
            # формируем и отправляем первый месячный PL
            # формируем и отправляем первый недельный PL:
            await get_weekly_pl(session=session,
                                seller_id=seller_id,
                                report_creation_type='auto',
                                date_from=date_from_for_report,
                                date_to=date_to,
                                requestor_chat_id=None)

            # обновляем в базе дату отправки отчета
            await update_weekly_report_sent_date(session=session,
                                                 seller_id=seller_id,
                                                 date_to=date_to)
            status = True
        else: pass
        return status
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при регулярном расчете результатов и отправке отчетов!'
                                    f'\nSeller_id: {seller_id}'
                                    f'\nSeller_inn: {await get_seller_inn_by_seller_id(session=session, seller_id=seller_id)}'
                                    f'\ntg_id: {await get_chat_id_by_seller_id(session, seller_id)}'
                                    f'\nОшибка: '
                                    f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def monthly_report_calculation_and_send(session, seller_id):
    latest_monthly_report_sent_date = await get_latest_monthly_report_sent_date(session=session, seller_id=seller_id)
    latest_pl_calculation_date = await get_latest_pl_calculation_date(session=session, seller_id=seller_id)
    end_of_Reporting_Month = await end_of_Reporting_Month_func()
    date_to = end_of_Reporting_Month
    start_of_Reporting_Month = await start_of_Reporting_Month_func()
    date_from = start_of_Reporting_Month
    end_of_Prior_Month = await end_of_Prior_Month_func()
    status = False
    # Если ни разу не отправляли отчет
    if not latest_monthly_report_sent_date:
        # проверяем, есть ли расчитанный PL
        # если нет, то ничего не делаем
        if not latest_pl_calculation_date:
            pass
        # если есть посчитанный PL
        else:
            # если PL посчитан за отчетный месяц, то отправляем за отчетный месяц
            if latest_pl_calculation_date>=end_of_Reporting_Month:
                date_to = end_of_Reporting_Month
                date_from = start_of_Reporting_Month
            # если PL посчитан за предыдущий месяц, то отправляем за предыдущий месяц
            elif latest_pl_calculation_date>=end_of_Prior_Month:
                date_to = end_of_Prior_Month
                start_of_Prior_Month = await start_of_Prior_Month_func()
                date_from = start_of_Prior_Month
            await get_monthly_pl(session=session,
                                 seller_id=seller_id,
                                 report_creation_type='auto',
                                 date_from=date_from,
                                 date_to=date_to,
                                 requestor_chat_id=None)
            status = True
            await update_monthly_report_sent_date(session=session,
                                                  seller_id=seller_id,
                                                  date_to=date_to)
    # Если уже отправляли отчет за отчетный месяц, то ничего не делаем
    elif latest_monthly_report_sent_date == end_of_Reporting_Month:
        pass
    # Если отправляли отчет за предыдущий месяц, то
    elif latest_pl_calculation_date >= end_of_Reporting_Month:
        date_to = end_of_Reporting_Month
        date_from = start_of_Reporting_Month
        await get_monthly_pl(session=session,
                             seller_id=seller_id,
                             report_creation_type='auto',
                             date_from=date_from,
                             date_to=date_to,
                             requestor_chat_id=None)
        status = True
        await update_monthly_report_sent_date(session=session,
                                              seller_id=seller_id,
                                              date_to=date_to)
        # Если нет, то ничего не делаем
    else:
        pass
    return status

async def send_report_summary(active_sellers):
    await send_message_to_admin(text=f'<b>Отчет по подготовке отчетов:</b>'
                                    f'\n\nАктивных компаний: {active_sellers}'
                                    f'\nОбработано компаний: {counter.common_counter}'
                                    f'\nОтчеты отправлены ранее: {counter.already_sent_counter}'
                                    f'\nВыгружена выручка: {counter.download_counter}'
                                    f'\nЗагружена выручка: {counter.sales_upload_counter}'
                                    f'\nОтправлено недельных отчетов: {counter.report_sent_counter}'
                                    f'\nОтправлено месячных отчетов: {counter.monthly_report_counter}'
                                    f'\nОтправлено шаблонов с/с: {counter.check_cost_failed_counter}'
                                    f'\nНет данных: {counter.no_data_counter}'
                                    f'\nНовая ошибка api: {counter.unauthorised_api_counter}'
                                    f'\nПлохой api: {counter.bad_api_counter}'
                                     f'\nОшибка в support выгрузках: {counter.error_in_support_get_data}'
                                    f'\nНет остатков: {counter.no_stocks_counter}'
                                    f'\nЗаблокировано: {counter.blocked_counter}'
                                    f'\nНеизвестный ответ: {counter.unknown_reply_counter}')

async def log_error(message, error):
    await send_message_to_admin(f'{message}\nОшибка: {error}')
    logging.exception("An error occurred: %s", exc_info=error)

async def check_storage_costs_allocation(session, seller_id):
    try:
        start_date = await start_for_downloading_data_func()
        end_date = await end_of_Reporting_Week_func()
        total_storage_costs_per_fin_report = await session.scalar(select(func.sum(Sales.storage_fee)).
                                                                         where(Sales.seller_id == seller_id,
                                                                               Sales.transaction_date >= start_date,
                                                                               Sales.transaction_date <= end_date)) or 0.0
        total_allocated_storage_costs = await session.scalar(select(func.sum(Storage_costs.warehouseprice)).
                                                                   where(Storage_costs.seller_id == seller_id,
                                                                         Storage_costs.cost_date >= start_date,
                                                                         Storage_costs.cost_date <= end_date)) or 0.0

        # print('total_storage_costs', total_storage_costs)
        # print('total_allocated_storage_costs', total_allocated_storage_costs)

        diff = total_storage_costs_per_fin_report - total_allocated_storage_costs
        # print(diff)

        if abs(diff) <= 50:
            logging.info(f'Seller_id: {seller_id}. Расходы на хранение-Ок')
            logging.info(f'Seller_id: {seller_id}. total_storage_costs_per_fin_report: {total_storage_costs_per_fin_report}, total_allocated_storage_costs: {total_allocated_storage_costs}')
            return True
        else:
            await send_message_to_admin(f'Ошибка в проверке расходов на хранение:'
                                    f'\nSeller_id: {seller_id}'
                                        f'\ntotal_storage_costs_per_fin_report: {total_storage_costs_per_fin_report}'
                                        f'\ntotal_allocated_storage_costs: {total_allocated_storage_costs}')
            logging.info(f'Seller_id: {seller_id}. Расходы на хранение-не ок')
            logging.info(f'Seller_id: {seller_id}. total_storage_costs_per_fin_report: {total_storage_costs_per_fin_report}, total_allocated_storage_costs: {total_allocated_storage_costs}')
            return False

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в проверке расходов на хранение:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)


async def check_paid_acceptance_costs_detalisation(session, seller_id):
    try:
        start_date = await start_for_downloading_data_func()
        end_date = await end_of_Reporting_Week_func()
        total_paid_acceptance_costs_per_income_id = await session.scalar(select(func.sum(Paid_acceptance.total)).
                                                                         where(Paid_acceptance.seller_id == seller_id,
                                                                               Paid_acceptance.shkcreatedate>=start_date,
                                                                               Paid_acceptance.shkcreatedate<=end_date)) or 0.0
        total_allocated_costs_per_fin_report = await session.scalar(select(func.sum(Sales.acceptance)).
                                                                   where(Sales.seller_id == seller_id,
                                                                         Sales.transaction_date >= start_date,
                                                                         Sales.transaction_date <= end_date)) or 0.0

        # print('total_paid_acceptance_costs_per_income_id', total_paid_acceptance_costs_per_income_id)
        # print('total_allocated_costs_per_fin_report', total_allocated_costs_per_fin_report)

        diff = total_paid_acceptance_costs_per_income_id - total_allocated_costs_per_fin_report

        if abs(diff) <= 150:
            logging.info(f'Seller_id: {seller_id}. Детализация расходов по платной приемке-Ок')
            return True
        else:
            await send_message_to_admin(f'Ошибка в детализации платной приемки по актам:'
                                        f'\nSeller_id: {seller_id}'
                                        f'\ntotal_paid_acceptance_costs_per_income_id: {total_paid_acceptance_costs_per_income_id}'
                                        f'\ntotal_allocated_costs_per_fin_report: {total_allocated_costs_per_fin_report}')
            logging.info(f'Seller_id: {seller_id}. Детализация расходов по платной приемке-не ок. total_paid_acceptance_costs_per_income_id: {total_paid_acceptance_costs_per_income_id}, '
                         f'total_allocated_costs_per_fin_report: {total_allocated_costs_per_fin_report}')
            return True

    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка в детализации платной приемки по актам:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)