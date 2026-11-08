"""Informações da loja e horário de funcionamento (manual, seções 1 e 2)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.calendar import holiday_name
from app.core.clock import get_now
from app.core.rules import OPENING_HOURS, SOLD_CATEGORIES_NOTE, STORE_INFO
from app.services.schemas import OpeningStatus, StoreInfo

WEEKDAYS_PT = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


def _hours_text(hours: tuple | None) -> str | None:
    if hours is None:
        return None
    return f"{hours[0]:%H:%M} às {hours[1]:%H:%M}"


def get_store_info() -> StoreInfo:
    return StoreInfo(
        name=STORE_INFO["name"],
        tagline=STORE_INFO["tagline"],
        address=STORE_INFO["address"],
        phone=STORE_INFO["phone"],
        whatsapp=STORE_INFO["whatsapp"],
        email=STORE_INFO["email"],
        founded=STORE_INFO["founded"],
        opening_hours=[
            {"dias": "Segunda a sexta-feira", "horario": _hours_text(OPENING_HOURS[0]) or ""},
            {"dias": "Sábado", "horario": _hours_text(OPENING_HOURS[5]) or ""},
            {"dias": "Domingo e feriados", "horario": "Fechado"},
        ],
        scope_note=SOLD_CATEGORIES_NOTE,
    )


def _next_opening(now: datetime) -> datetime | None:
    for offset in range(0, 15):
        day = now.date() + timedelta(days=offset)
        hours = OPENING_HOURS[day.weekday()]
        if holiday_name(day) or hours is None:
            continue
        start = datetime.combine(day, hours[0], tzinfo=now.tzinfo)
        if start > now:
            return start
    return None


def _describe_day(target: datetime, now: datetime) -> str:
    if target.date() == now.date():
        label = "hoje"
    elif target.date() == now.date() + timedelta(days=1):
        label = "amanhã"
    else:
        label = f"{WEEKDAYS_PT[target.weekday()]} ({target:%d/%m})"
    return f"{label} às {target:%H:%M}"


def get_opening_status(now: datetime | str | None = None) -> OpeningStatus:
    moment = get_now(now)
    today = moment.date()
    holiday = holiday_name(today)
    hours = None if holiday else OPENING_HOURS[today.weekday()]
    is_open = bool(hours and hours[0] <= moment.time() < hours[1])
    nxt = None if is_open else _next_opening(moment)

    if is_open:
        message = f"Estamos abertos agora e fechamos hoje às {hours[1]:%H:%M}."
    else:
        if holiday:
            reason = f"Hoje é feriado ({holiday}) e a loja fica fechada."
        elif hours is None:
            reason = "Aos domingos a loja fica fechada."
        else:
            reason = f"Hoje atendemos das {_hours_text(hours)} e estamos fora do expediente."
        message = reason + (f" Voltamos {_describe_day(nxt, moment)}." if nxt else "")

    return OpeningStatus(
        now=moment.isoformat(timespec="minutes"),
        is_open=is_open,
        weekday=WEEKDAYS_PT[today.weekday()],
        todays_hours=_hours_text(hours),
        holiday=holiday,
        next_opening=nxt.isoformat(timespec="minutes") if nxt else None,
        message=message,
    )
