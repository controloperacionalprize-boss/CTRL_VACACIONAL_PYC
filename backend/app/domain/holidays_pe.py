from __future__ import annotations

from datetime import date, timedelta

# (mes, día) fijos. Semana Santa se calcula aparte.
_FIXED = (
    (1, 1),
    (5, 1),
    (6, 29),
    (7, 28),
    (7, 29),
    (8, 30),
    (10, 8),
    (11, 1),
    (12, 8),
    (12, 9),
    (12, 25),
)


def _easter_sunday(year: int) -> date:
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


def peru_holidays(year: int) -> set[date]:
    easter = _easter_sunday(year)
    return {date(year, m, d) for m, d in _FIXED} | {
        easter - timedelta(days=3),
        easter - timedelta(days=2),
    }
