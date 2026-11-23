from datetime import timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.marking.views import PAGE_SIZE, get_code_history, get_profile, list_codes

MENU_LABEL = "Честный знак"
MOSCOW_TIME = timezone(timedelta(hours=3))
marking_router = Router(name="marking")

EVENT_LABELS = {
    "issued": "Выпущен",
    "received": "Получен",
    "applied": "Нанесён",
    "introduced": "Введён в оборот",
    "transfer_reserved": "Зарезервирован для передачи",
    "transfer_sent": "УПД отправлен",
    "transfer_signed": "УПД подписан",
    "transfer_confirmed": "Передача подтверждена",
    "transfer_rejected": "Передача отклонена",
    "transfer_cancelled": "Передача отменена",
    "correction": "Исправление",
}
SOURCE_LABELS = {"findirexpress": "FindirExpress", "suz": "СУЗ", "gismt": "ГИС МТ", "edo": "ЭДО"}
ENVIRONMENT_LABELS = {"test": "тестовый", "production": "рабочий"}
MAX_ID = 2**63 - 1
MAX_PAGE = 999_999_999


class MarkingPage(CallbackData, prefix="mark"):
    issuer: int
    code: int = 0
    page: int = 0


def _button(label, issuer, code=0, page=0):
    return InlineKeyboardButton(text=label, callback_data=MarkingPage(issuer=issuer, code=code, page=page).pack())


def _date(value):
    return value.astimezone(MOSCOW_TIME).strftime("%d.%m.%Y %H:%M МСК")


def _profile_screen(profile, recipients):
    lines = ["Честный знак", profile["name"], f'ИНН {profile["inn"]}', "", "Получатели маркированного товара"]
    lines.extend(f'{row["name"]} · ИНН {row["inn"]}' for row in recipients)
    if not recipients:
        lines.append("Получатели ещё не настроены.")
    return "\n".join(lines), InlineKeyboardMarkup(
        inline_keyboard=[[_button("История кодов", profile["id"])]],
    )


def _pagination(issuer, code, page, has_more):
    buttons = []
    if page > 0:
        buttons.append(_button("← Назад", issuer, code=code, page=page - 1))
    if has_more:
        buttons.append(_button("Далее →", issuer, code=code, page=page + 1))
    return [buttons] if buttons else []


@marking_router.message(Command("marking"))
@marking_router.message(F.text == MENU_LABEL)
async def open_marking(message: Message, state: FSMContext):
    profile, recipients = await get_profile(message.from_user.id)
    if profile is None:
        await message.answer("Профиль маркировки для вашей учётной записи ещё не настроен.")
        return
    await state.clear()
    text, keyboard = _profile_screen(profile, recipients)
    await message.answer(text, reply_markup=keyboard, parse_mode=None)


@marking_router.callback_query(MarkingPage.filter())
async def show_marking_page(callback: CallbackQuery, callback_data: MarkingPage):
    issuer, code_id, page = callback_data.issuer, callback_data.code, callback_data.page
    if (not isinstance(callback.message, Message) or not 0 < issuer <= MAX_ID
            or not -1 <= code_id <= MAX_ID or not 0 <= page <= MAX_PAGE):
        await callback.answer("Эта страница недоступна.")
        return

    if code_id > 0:
        screen = await _history_screen(callback.from_user.id, issuer, code_id, page)
    else:
        profile, recipients = await get_profile(callback.from_user.id, issuer)
        if profile is None:
            screen = None
        elif code_id == -1:
            screen = _profile_screen(profile, recipients)
        else:
            screen = await _codes_screen(callback.from_user.id, issuer, page)

    if screen is None:
        await callback.answer("Эта страница недоступна.")
        return
    text, keyboard = screen
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


async def _codes_screen(tg_id, issuer, page):
    codes = await list_codes(tg_id, issuer, page)
    lines = ["История кодов маркировки", f"Страница {page + 1}"]
    if not codes:
        lines.append("На этой странице пока нет кодов.")
    buttons = []
    for code in codes[:PAGE_SIZE]:
        environment = ENVIRONMENT_LABELS[code["environment"]]
        lines.append(f'№ {code["id"]} · {environment} · {_date(code["received_at"])}\n'
                     f'GTIN {code["gtin"]} · владелец {code["owner_name"][:120]}')
        buttons.append([_button(f'№ {code["id"]} · …{code["serial_tail"]}', issuer, code["id"])])
    buttons.extend(_pagination(issuer, 0, page, len(codes) > PAGE_SIZE))
    buttons.append([_button("Профиль", issuer, code=-1)])
    return "\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


async def _history_screen(tg_id, issuer, code_id, page):
    code, events = await get_code_history(tg_id, issuer, code_id, page)
    if code is None:
        return None
    lines = [
        f'Код № {code_id} · {ENVIRONMENT_LABELS[code["environment"]]} контур',
        f'GTIN {code["gtin"]} · серийный номер …{code["serial_tail"]}',
        f'Подтверждённый владелец: {code["owner_name"][:120]}',
        f'Получен: {_date(code["received_at"])}',
    ]
    if code["issued_at"]:
        lines.append(f'Выпущен: {_date(code["issued_at"])}')
    lines.extend(("", f"События · страница {page + 1}"))
    if not events:
        lines.append("На этой странице пока нет событий.")
    for event in events[:PAGE_SIZE]:
        time = _date(event["occurred_at"]) if event["occurred_at"] else f'записано {_date(event["recorded_at"])}'
        lines.append(f'{EVENT_LABELS[event["event_type"]]} · {time} · {SOURCE_LABELS[event["source"]]}')
        if event["actor_name"]:
            lines.append(f'Пользователь: {event["actor_name"][:65]}')
        if event["recipient_name"]:
            lines.append(f'Получатель: {event["recipient_name"][:90]}')
        if event["edo_document_id"]:
            lines.append(f'УПД в ЭДО: {event["edo_document_id"][:65]}')
        if event["gismt_document_id"]:
            lines.append(f'Документ ГИС МТ: {event["gismt_document_id"][:65]}')
    buttons = _pagination(issuer, code_id, page, len(events) > PAGE_SIZE)
    buttons.append([_button("К списку кодов", issuer)])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)
