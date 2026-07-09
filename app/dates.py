import asyncio
from datetime import datetime
from datetime import timedelta
from time import strftime
import pytz


today_date=datetime.now()
async def today_str_func():
    today_str=datetime.strftime(datetime.now(),'%Y-%m-%d')
    return today_str

async def today_weekday_func():
    today_weekday=datetime.isoweekday(datetime.now())
    return today_weekday

async def start_of_yesterday_func():
    start_of_yesterday = (datetime.now()-timedelta(days=1)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_yesterday

async def end_of_yesterday_func():
    start_of_yesterday = await start_of_yesterday_func()
    end_of_yesterday = start_of_yesterday.replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_yesterday

async def yesterday_str_func():
    end_of_yesterday = await end_of_yesterday_func()
    yesterday_str = datetime.strftime(end_of_yesterday,'%Y-%m-%d')
    return yesterday_str

async def start_of_today_func():
    start_of_today = datetime.now().replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_today

# async def start_of_today_str():
#     start_of_today = await start_of_today_func()
#     start_of_today_str = datetime.strftime(start_of_today,'%Y-%m-%d')
#     return start_of_today_str

async def start_of_Reporting_Week_func():
    today_weekday = await today_weekday_func()
    start_of_Reporting_Week=(datetime.now()-timedelta(days=today_weekday+6)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_Reporting_Week

# async def start_of_Reporting_Week_str():
#     start_of_Reporting_Week = await start_of_Reporting_Week_func()
#     start_of_Reporting_Week_str=datetime.strftime(start_of_Reporting_Week,'%Y-%m-%d')
#     return start_of_Reporting_Week_str

async def end_of_Reporting_Week_func():
    today_weekday = await today_weekday_func()
    end_of_Reporting_Week=(datetime.now()-timedelta(days=today_weekday)).replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_Reporting_Week

# async def end_of_Reporting_Week_str():
#     end_of_Reporting_Week = await end_of_Reporting_Week_func()
#     end_of_Reporting_Week_str=datetime.strftime(end_of_Reporting_Week,'%Y-%m-%d')
#     return end_of_Reporting_Week_str

async def start_of_Prior_Week_func():
    today_weekday = await today_weekday_func()
    start_of_Prior_Week=(datetime.now()-timedelta(days=today_weekday+13)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_Prior_Week

# async def start_of_Prior_Week_str():
#     start_of_Prior_Week = await start_of_Prior_Week_func()
#     start_of_Prior_Week_str=datetime.strftime(start_of_Prior_Week,'%Y-%m-%d')
#     return start_of_Prior_Week_str

async def end_of_Prior_Week_func():
    today_weekday = await today_weekday_func()
    end_of_Prior_Week=(datetime.now()-timedelta(days=today_weekday+7)).replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_Prior_Week

# async def end_of_Prior_Week_str():
#     end_of_Prior_Week = await end_of_Prior_Week_func()
#     end_of_Prior_Week_str=datetime.strftime(end_of_Prior_Week,'%Y-%m-%d')
#     return end_of_Prior_Week_str

# async def start_of_Current_Month():
#     start_of_Current_Month=datetime.now().replace(day=1,hour=00,minute=00,second=00,microsecond=00)
#     return start_of_Current_Month

# async def start_of_Current_Month_str():
#     start_of_Current_Month = await start_of_Current_Month_func()
#     start_of_Current_Month_str=datetime.strftime(start_of_Current_Month,'%Y-%m-%d')
#     return start_of_Current_Month_str

async def end_of_Reporting_Month_func():
    end_of_Reporting_Month=(datetime.now().replace(day=1)-timedelta(days=1)).replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_Reporting_Month

# async def end_of_Reporting_Month_str():
#     end_of_Reporting_Month = await end_of_Reporting_Month_func()
#     end_of_Reporting_Month_str=datetime.strftime(end_of_Reporting_Month,'%Y-%m-%d')
#     return end_of_Reporting_Month_str

async def start_of_Reporting_Month_func():
    end_of_Reporting_Month = await end_of_Reporting_Month_func()
    start_of_Reporting_Month=(datetime.now().replace(day=1)-timedelta(days=end_of_Reporting_Month.day)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_Reporting_Month

# async def start_of_Reporting_Month_str():
#     start_of_Reporting_Month = await start_of_Reporting_Month_func()
#     start_of_Reporting_Month_str=datetime.strftime(start_of_Reporting_Month,'%Y-%m-%d')
#     return start_of_Reporting_Month_str

async def end_of_Prior_Month_func():
    start_of_Reporting_Month = await start_of_Reporting_Month_func()
    end_of_Prior_Month=(start_of_Reporting_Month-timedelta(days=1)).replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_Prior_Month

# async def end_of_Prior_Month_str():
#     end_of_Prior_Month = await end_of_Prior_Month_func()
#     end_of_Prior_Month_str=datetime.strftime(end_of_Prior_Month,'%Y-%m-%d')
#     return end_of_Prior_Month_str

async def start_of_Prior_Month_func():
    end_of_Prior_Month = await end_of_Prior_Month_func()
    start_of_Prior_Month=(end_of_Prior_Month.replace(day=1)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_Prior_Month

# async def start_of_Prior_Month_str():
#     start_of_Prior_Month = await start_of_Prior_Month_func()
#     start_of_Prior_Month_str=datetime.strftime(start_of_Prior_Month,'%Y-%m-%d')
#     return start_of_Prior_Month_str

async def end_of_PriorMinusOne_Month_func():
    start_of_Prior_Month = await start_of_Prior_Month_func()
    end_of_PriorMinusOne_Month=(start_of_Prior_Month-timedelta(days=1)).replace(hour=23,minute=59,second=59,microsecond=999999)
    return end_of_PriorMinusOne_Month

# async def end_of_PriorMinusOne_Month_str():
#     end_of_PriorMinusOne_Month = await end_of_PriorMinusOne_Month_func()
#     end_of_PriorMinusOne_Month_str=datetime.strftime(end_of_PriorMinusOne_Month,'%Y-%m-%d')
#     return end_of_PriorMinusOne_Month_str

async def start_of_PriorMinusOne_Month_func():
    end_of_PriorMinusOne_Month = await end_of_PriorMinusOne_Month_func()
    start_of_PriorMinusOne_Month=(end_of_PriorMinusOne_Month.replace(day=1)).replace(hour=00,minute=00,second=00,microsecond=00)
    return start_of_PriorMinusOne_Month

# async def start_of_PriorMinusOne_Month_str():
#     start_of_PriorMinusOne_Month = await start_of_PriorMinusOne_Month_func()
#     start_of_PriorMinusOne_Month_str=datetime.strftime(start_of_PriorMinusOne_Month,'%Y-%m-%d')
#     return start_of_PriorMinusOne_Month_str

async def start_for_downloading_data_func():
    # Получаем начало предыдущего месяца
    start_of_Prior_Month = await start_of_Prior_Month_func()
    # Вычисляем понедельник для начала предыдущего месяца и еще минус 1 неделя
    start_for_downloading_data = start_of_Prior_Month - timedelta(days=(datetime.isoweekday(start_of_Prior_Month) - 1)) - timedelta(days=7)
    # Получаем начало текущего квартала
    start_of_current_quarter = await start_of_current_quarter_func()

    # Вычисляем понедельник недели для начала квартала и еще минус 1 неделя
    start_of_current_quarter_week_start = start_of_current_quarter - timedelta(days=(datetime.isoweekday(start_of_current_quarter) - 1))- timedelta(days=7)

    # Если начало предыдущего месяца (понедельник) > начало квартала, берем понедельник недели квартала
    if start_for_downloading_data > start_of_current_quarter:
        start_for_downloading_data = start_of_current_quarter_week_start

    return start_for_downloading_data.replace(hour=00, minute=00, second=00, microsecond=000000)

async def start_of_current_quarter_func():
    # Определяем номер квартала
    quarter = (datetime.now().month - 1) // 3 + 1
    # Определяем месяц начала квартала
    month_start = (quarter - 1) * 3 + 1
    # Возвращаем дату начала квартала
    return datetime(datetime.now().year, month_start, 1).replace(hour=00,minute=00,second=00,microsecond=00)

def start_of_quarter_func(date):
    # Определяем номер квартала
    quarter = (date.month - 1) // 3 + 1
    # Определяем месяц начала квартала
    month_start = (quarter - 1) * 3 + 1
    # Возвращаем дату начала квартала
    return datetime(date.year, month_start, 1).replace(hour=00,minute=00,second=00,microsecond=00)

async def start_of_reporting_quarter(date):
    # Определяем номер квартала
    quarter = (date.month - 1) // 3 + 1
    # Определяем месяц начала квартала
    month_start = (quarter - 1) * 3 + 1
    # Возвращаем дату начала квартала
    return datetime(date.year, month_start, 1).replace(hour=00,minute=00,second=00,microsecond=00)

async def get_end_of_prior_week_for_ar(date):
    days = datetime.isoweekday(date)
    end_of_prior_week_for_ar = (date-timedelta(days=days)).replace(hour=23,minute=59,second=59,microsecond=999999)
    start_of_prior_week_for_ar = (end_of_prior_week_for_ar - timedelta(days=6)).replace(hour=00, minute=00, second=00,
                                                                                        microsecond=000000)
    return start_of_prior_week_for_ar, end_of_prior_week_for_ar

async def get_end_of_month(date):
    # Получаем первый день следующего месяца
    next_month = date.replace(day=28) + timedelta(days=4)  # Переходим на следующий месяц
    first_day_next_month = next_month.replace(day=1)

    # Вычитаем один день, чтобы получить последний день текущего месяца
    end_of_month = (first_day_next_month - timedelta(days=1)).replace(hour=23,minute=59,second=59,microsecond=999999)

    return end_of_month


async def main():
    date = await start_for_downloading_data_func() + timedelta(hours=2)
    date_from_utc = date.isoformat()
    print(date)
    print(date_from_utc)

if __name__== "__main__":
    asyncio.run(main())