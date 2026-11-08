"""Feriados que fecham a loja (manual, seção 2: 'Domingo e Feriados: Fechado').

Lista simplificada: feriados nacionais, o estadual de MS e o municipal de
Campo Grande. Pontos facultativos (Carnaval, Corpus Christi) não entram.
"""
from __future__ import annotations

from datetime import date, timedelta

_FIXED = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 11): "Criação do Estado de Mato Grosso do Sul",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Consciência Negra",
    (12, 25): "Natal",
    (8, 26): "Aniversário de Campo Grande",
}


def easter_sunday(year: int) -> date:
    """Algoritmo de Meeus/Jones/Butcher (calendário gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def holiday_name(day: date) -> str | None:
    name = _FIXED.get((day.month, day.day))
    if name:
        return name
    if day == easter_sunday(day.year) - timedelta(days=2):
        return "Sexta-feira Santa"
    return None
