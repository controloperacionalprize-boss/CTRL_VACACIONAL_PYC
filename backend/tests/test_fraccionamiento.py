from datetime import date

import pytest

from app.domain.calendar import (
    apply_consecutive_span,
    art8_fraccion_ok,
    move_vacation_period,
    vacation_periods,
)


_HOY = date(2026, 8, 21)
_YEAR = 2026


def _span(daily, targets, start, days):
    return apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", start, days, _YEAR, today=_HOY
    )


def test_art8_un_tramo_siempre_ok():
    assert art8_fraccion_ok([])
    assert art8_fraccion_ok([30])
    assert art8_fraccion_ok([7])
    assert art8_fraccion_ok([10])


def test_art8_quince_mas_resto():
    assert art8_fraccion_ok([15, 1, 1, 13])
    assert art8_fraccion_ok([16, 14])


def test_art8_siete_y_ocho():
    assert art8_fraccion_ok([7, 8])
    assert art8_fraccion_ok([8, 7, 1, 14])
    assert art8_fraccion_ok([10, 7])  # 10 cuenta como ≥8


def test_art8_rechaza_sin_bloque_minimo():
    assert not art8_fraccion_ok([5, 5])
    assert not art8_fraccion_ok([7, 7])
    assert not art8_fraccion_ok([6, 8])
    assert not art8_fraccion_ok([1, 1, 1])


def test_goce_completo_30():
    daily, targets = set(), {}
    fechas, _ = _span(daily, targets, date(2026, 9, 1), 30)
    assert fechas[0] == date(2026, 9, 1)
    assert fechas[-1] == date(2026, 9, 30)
    periods = vacation_periods(daily, "1", _YEAR, today=_HOY)
    assert len(periods) == 1
    assert periods[0]["dias"] == 30


def test_fraccion_7_8_15():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 7)
    _span(daily, targets, date(2026, 10, 15), 8)
    _span(daily, targets, date(2026, 12, 1), 15)
    sizes = [p["dias"] for p in vacation_periods(daily, "1", _YEAR, today=_HOY)]
    assert sorted(sizes) == [7, 8, 15]


def test_rechaza_fraccion_5_y_5():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 5)
    with pytest.raises(ValueError, match="Art. 8"):
        _span(daily, targets, date(2026, 10, 15), 5)


def test_rechaza_solape():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 7)
    with pytest.raises(ValueError, match="cruzan"):
        _span(daily, targets, date(2026, 9, 3), 8)


def test_modificar_periodo_futuro_no_duplica_dias():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 7)
    _span(daily, targets, date(2026, 10, 15), 8)
    nuevas, _, old = move_vacation_period(
        daily,
        targets,
        "1",
        "ADMINISTRATIVO",
        _YEAR,
        old_start=date(2026, 10, 15),
        new_start=date(2026, 11, 1),
        today=_HOY,
    )
    assert old["dias"] == 8
    assert nuevas[0] == date(2026, 11, 1)
    periods = vacation_periods(daily, "1", _YEAR, today=_HOY)
    assert sum(p["dias"] for p in periods) == 15
    assert {p["inicio"] for p in periods} == {date(2026, 9, 1), date(2026, 11, 1)}


def test_no_modificar_periodo_ya_iniciado():
    daily, targets = set(), {}
    apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", date(2026, 8, 21), 7, _YEAR, today=_HOY
    )
    with pytest.raises(ValueError, match="ya comenzó"):
        move_vacation_period(
            daily,
            targets,
            "1",
            "ADMINISTRATIVO",
            _YEAR,
            old_start=date(2026, 8, 21),
            new_start=date(2026, 9, 1),
            today=_HOY,
        )
