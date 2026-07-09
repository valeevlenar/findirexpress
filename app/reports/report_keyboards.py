from app.database.classes.sales import Sales
from app.database.dates_functions import get_latest_weekly_report_sent_date, get_latest_monthly_report_sent_date
from app.wrappers import with_session

# Конфигурация
ITEMS_PER_PAGE = 4
CACHE_TTL_SECONDS = 300  # 5 минут

from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from functools import lru_cache


# Сначала объявляем все вспомогательные функции
def generate_weeks(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Генерация недельных периодов (пропускаем первую неделю после start_date)"""
    periods = []

    # Находим конец первой недели после start_date
    first_week_end = start + timedelta(days=(6 - start.weekday()))
    first_week_end = first_week_end.replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    # Начинаем с конца и идем назад
    current_end = end.replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    # Корректируем до предыдущего воскресенья
    if current_end.weekday() != 6:
        current_end -= timedelta(days=current_end.weekday() + 1)

    while current_end > first_week_end:
        period_start = current_end - timedelta(days=6)
        period_start = period_start.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Не включаем периоды до start_date
        if period_start < start:
            break

        periods.append((period_start, current_end))
        current_end = period_start - timedelta(seconds=1)

    return periods

def generate_months(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:

    """Генерация месячных периодов (пропускаем первый полный месяц)"""
    periods = []

    # Находим начало следующего месяца после start_date
    next_month = start.replace(day=28) + timedelta(days=4)  # Гарантированно переходим в следующий месяц
    current_start = next_month.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    # Пропускаем первый полный месяц
    current_start = current_start.replace(day=28) + timedelta(days=4)
    current_start = current_start.replace(day=1)

    while current_start <= end:
        period_end = (current_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        period_end = min(period_end, end)

        if period_end >= current_start and period_end.month == current_start.month:
            periods.append((current_start, period_end))

        current_start = period_end + timedelta(seconds=1)

    return list(reversed(periods))

# Теперь объявляем конфигурацию
REPORT_TYPES = {
    'weekly': {
        'period_generator': generate_weeks,
        'items_per_page': 4
    },
    'monthly': {
        'period_generator': generate_months,
        'items_per_page': 4
    }
}


@lru_cache(maxsize=32)
def generate_periods(report_type: str, start_ts: float, end_ts: float, seller_id: int) -> list:
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)

    if report_type == 'weekly':
        return generate_weeks(start, end)
    return generate_months(start, end)

def format_date(dt: datetime) -> str:
    """Форматирование даты в формате 'день месяц' с русским названием месяца"""
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    current_year = datetime.now().year
    year_suffix = f" {dt.year}" if dt.year != current_year else ""
    return f"{dt.day} {months[dt.month]} {year_suffix}"


@with_session
async def generate_report_keyboard(session, page: int, report_type: str, seller_id: int) -> InlineKeyboardMarkup:
    """Обновленная функция генерации клавиатуры с индивидуальными датами"""
    # Получаем индивидуальные даты для seller_id
    start_date = await Sales.get_earliest_data_date(session=session, seller_id=seller_id)
    if not start_date:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Нет данных для отчетов", callback_data="no_data")
        ]])

    # Получаем конечную дату в зависимости от типа отчета
    if report_type == 'weekly':
        end_date = await get_latest_weekly_report_sent_date(session=session, seller_id=seller_id)
    else:
        end_date = await get_latest_monthly_report_sent_date(session=session, seller_id=seller_id)

    # Проверка корректности дат
    if not end_date or start_date > end_date:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Нет данных для отчетов", callback_data="no_data")
        ]])

    items_per_page = REPORT_TYPES[report_type]['items_per_page']

    # Генерация периодов с индивидуальными датами
    all_periods = generate_periods(
        report_type,
        start_date.timestamp(),
        end_date.timestamp(),
        seller_id
    )

    if not all_periods:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Первый отчет будет доступен со следующего периода",
                callback_data="no_reports"
            )
        ]])

    # Разбиваем на страницы
    pages = [all_periods[i:i + items_per_page]
             for i in range(0, len(all_periods), items_per_page)]

    if not pages:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Нет отчетов", callback_data="no_reports")
        ]])

    current_page = max(0, min(page, len(pages) - 1))
    total_pages = len(pages)
    current_periods = pages[current_page]

    keyboard = []

    # Кнопки периодов
    for start, end in current_periods:
        if report_type == 'weekly':
            text = f"{format_date(start)} - {format_date(end)}"
        else:
            month_name = format_month(start)
            text = f"{month_name} {start.year}"

        callback = f"period:{report_type}:{start.timestamp()}:{end.timestamp()}"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])

    # Кнопки пагинации
    pagination = []
    if current_page < len(pages) - 1:
        pagination.append(InlineKeyboardButton(
            text=f"Раньше ◀ ({current_page + 1}/{total_pages})",
            callback_data=f"page:{report_type}:{current_page + 1}"
        ))
    if current_page > 0:
        pagination.append(InlineKeyboardButton(
            text=f"▶ Позже ({current_page + 1}/{total_pages})",
            callback_data=f"page:{report_type}:{current_page - 1}"
        ))

    if pagination:
        keyboard.append(pagination)

    # Кнопка отмены
    keyboard.append([InlineKeyboardButton(text="↩️ Отменить", callback_data="cancel")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_month(dt: datetime) -> str:
    """Форматирование названия месяца"""
    months = {
        1: 'Январь', 2: 'Февраль', 3: 'Март',
        4: 'Апрель', 5: 'Май', 6: 'Июнь',
        7: 'Июль', 8: 'Август', 9: 'Сентябрь',
        10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    return months[dt.month]


