from datetime import date
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.calendar import (
    allowed_type,
    apply_consecutive_span,
    compute_consecutive_dates,
    reject_if_start_in_past,
    week_is_locked,
)

# Fecha fija para que los casos de agosto 2026 no choquen con "hoy" real.
_HOY = date(2026, 8, 17)


def test_todos_usan_dias_corridos():
    """Admin, operativo o desconocido: mismos 7 días corridos desde el viernes."""
    start = date(2026, 8, 21)
    for tipo in ("ADMINISTRATIVO", "OPERATIVO", "GERENCIA", "PLANTA"):
        days = compute_consecutive_dates(tipo, start, 7)
        assert days == [
            date(2026, 8, 21),
            date(2026, 8, 22),
            date(2026, 8, 23),
            date(2026, 8, 24),
            date(2026, 8, 25),
            date(2026, 8, 26),
            date(2026, 8, 27),
        ]


def test_admin_siete_dias_desde_viernes_cruza_semana():
    start = date(2026, 8, 21)
    daily, targets = set(), {}
    apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", start, 7, 2026, clear_week=34, today=_HOY
    )
    assert dict(targets) == {("1", 34): 3, ("1", 35): 4}


def test_operativo_jueves_cinco_dias_cruza_semana():
    start = date.fromisocalendar(2026, 34, 4)
    daily, targets = set(), {}
    _, deltas = apply_consecutive_span(
        daily, targets, "1", "OPERATIVO", start, 5, 2026, today=_HOY
    )
    assert dict(targets) == {("1", 34): 4, ("1", 35): 1}
    assert [(w, n) for w, _o, n in deltas] == [(34, 4), (35, 1)]


def test_desconocido_usa_calendario():
    days = compute_consecutive_dates("PLANTA", date.fromisocalendar(2026, 34, 4), 5)
    assert [d.weekday() for d in days] == [3, 4, 5, 6, 0]


def test_exclusion_por_dni_solo_habiles(monkeypatch):
    monkeypatch.setattr(
        "app.domain.calendar.DNI_SOLO_DIAS_HABILES",
        frozenset({"999"}),
    )
    assert allowed_type("OPERATIVO", "999") == "HABIL"
    assert allowed_type("ADMINISTRATIVO", "1") == "CALENDARIO"
    days = compute_consecutive_dates("ADMINISTRATIVO", date(2026, 3, 2), 10, dni="999")
    assert all(d.weekday() < 5 for d in days)
    assert len(days) == 10


def test_lock():
    assert week_is_locked(2020, 1, date(2026, 8, 19))


def test_no_programar_inicio_en_el_pasado():
    with pytest.raises(ValueError, match="solo desde hoy"):
        reject_if_start_in_past(date(2026, 8, 20), today=date(2026, 8, 21))
    reject_if_start_in_past(date(2026, 8, 21), today=date(2026, 8, 21))


def test_apply_rechaza_inicio_pasado():
    daily, targets = set(), {}
    with pytest.raises(ValueError, match="solo desde hoy"):
        apply_consecutive_span(
            daily,
            targets,
            "1",
            "ADMINISTRATIVO",
            date(2026, 8, 17),
            3,
            2026,
            today=date(2026, 8, 21),
        )
