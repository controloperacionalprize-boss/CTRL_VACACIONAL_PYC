from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.calendar import apply_consecutive_span, compute_consecutive_dates, week_is_locked


def test_consecutive_habil():
    days = compute_consecutive_dates("ADMINISTRATIVO", date(2026, 3, 2), 10)
    assert all(d.weekday() < 5 for d in days)
    assert len(days) == 10


def test_consecutive_operativo():
    days = compute_consecutive_dates("OPERATIVO", date(2026, 1, 12), 7)
    assert len(days) == 7


def test_operativo_jueves_cinco_dias_cruza_semana():
    start = date.fromisocalendar(2026, 34, 4)
    daily, targets = set(), {}
    _, deltas = apply_consecutive_span(daily, targets, "1", "OPERATIVO", start, 5, 2026)
    assert dict(targets) == {("1", 34): 4, ("1", 35): 1}
    assert [(w, n) for w, _o, n in deltas] == [(34, 4), (35, 1)]


def test_desconocido_usa_calendario():
    days = compute_consecutive_dates("PLANTA", date.fromisocalendar(2026, 34, 4), 5)
    assert [d.weekday() for d in days] == [3, 4, 5, 6, 0]


def test_lock():
    assert week_is_locked(2020, 1, date(2026, 8, 19))
