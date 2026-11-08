from datetime import date

import pytest

from app.core.calendar import easter_sunday, holiday_name
from app.core.clock import get_now
from app.services.store import get_opening_status, get_store_info


def status(moment):
    return get_opening_status(moment)


def test_open_on_weekday_morning():
    s = status("2026-11-09T10:00")  # segunda-feira
    assert s.is_open and s.weekday == "segunda-feira"
    assert "18:00" in s.message


def test_closing_time_is_exclusive():
    assert status("2026-11-09T17:59").is_open
    s = status("2026-11-09T18:00")
    assert not s.is_open
    assert "amanhã às 09:00" in s.message


def test_before_opening():
    s = status("2026-11-10T08:30")
    assert not s.is_open and "hoje às 09:00" in s.message


def test_saturday_closes_at_one_pm():
    assert status("2026-11-14T12:59").is_open
    s = status("2026-11-14T13:00")
    assert not s.is_open
    assert "segunda-feira (16/11) às 09:00" in s.message


def test_sunday_is_closed():
    s = status("2026-11-08T11:00")
    assert not s.is_open and s.todays_hours is None
    assert "domingo" in s.message.lower()
    assert "amanhã às 09:00" in s.message


@pytest.mark.parametrize(
    "moment, holiday",
    [
        ("2026-09-07T10:00", "Independência do Brasil"),
        ("2026-04-03T10:00", "Sexta-feira Santa"),
        ("2026-11-20T10:00", "Consciência Negra"),
        ("2026-08-26T10:00", "Aniversário de Campo Grande"),
    ],
)
def test_holidays_close_the_store(moment, holiday):
    s = status(moment)
    assert not s.is_open and s.holiday == holiday
    assert "feriado" in s.message


def test_next_opening_skips_holiday():
    s = status("2026-09-06T12:00")  # domingo; segunda 07/09 é feriado
    assert "terça-feira (08/09) às 09:00" in s.message


def test_easter_dates():
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2027) == date(2027, 3, 28)
    assert holiday_name(date(2026, 4, 3)) == "Sexta-feira Santa"
    assert holiday_name(date(2026, 4, 4)) is None


def test_store_info_matches_manual():
    info = get_store_info()
    assert info.address.startswith("Rua 14 de Maio, 3200")
    assert info.email == "contato@emporiodamusica.com.br"
    assert [h["horario"] for h in info.opening_hours] == ["09:00 às 18:00", "09:00 às 13:00", "Fechado"]
    assert "exclusivamente" in info.scope_note


def test_clock_uses_campo_grande_timezone():
    assert get_now("2026-11-09T10:00:00").isoformat().endswith("-04:00")
    assert get_now("2026-11-09T14:00:00+00:00").hour == 10


def test_clock_default_is_aware(monkeypatch):
    monkeypatch.delenv("NOW_OVERRIDE", raising=False)
    assert get_now().tzinfo is not None
