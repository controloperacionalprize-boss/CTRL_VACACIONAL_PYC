"""Mapa de casos GTH: goce 30, Art. 8, adelanto, modificar período, fechas, año."""
from datetime import date, timedelta

import pytest

from app.domain.calendar import (
    apply_consecutive_span,
    art8_fraccion_ok,
    clear_dates_for_week,
    derecho_vigente,
    key_daily,
    move_vacation_period,
    reject_if_art8_invalido,
    vacation_periods,
)
from app.domain.plan import group_periods, validate_plan

_HOY = date(2026, 8, 21)
_YEAR = 2026


def _span(daily, targets, start, days, today=_HOY):
    return apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", start, days, _YEAR, today=today
    )


# --- Art. 8 (D.S. 002-2019-TR): días CORRIDOS, no lun–vie sueltos ---

def test_art8_matriz_permitida_y_rechazada():
    assert art8_fraccion_ok([30])
    assert art8_fraccion_ok([15])
    assert art8_fraccion_ok([15, 1, 14])
    assert art8_fraccion_ok([7, 8])
    assert art8_fraccion_ok([8, 7, 2])
    assert art8_fraccion_ok([10, 7])
    assert not art8_fraccion_ok([7, 7])
    assert not art8_fraccion_ok([6, 8])
    assert not art8_fraccion_ok([5, 5, 5])
    assert not art8_fraccion_ok([1, 1, 1])


def test_lun_vie_de_tres_semanas_no_son_15_corridos():
    daily: set[str] = set()
    for start in (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21)):
        for i in range(5):
            daily.add(key_daily("1", start + timedelta(days=i)))
    sizes = [p["dias"] for p in vacation_periods(daily, "1", _YEAR, today=_HOY)]
    assert sizes == [5, 5, 5]
    with pytest.raises(ValueError, match="Art. 8"):
        reject_if_art8_invalido(daily, "1", _YEAR)


def test_goce_30_un_tramo():
    daily, targets = set(), {}
    fechas, _ = _span(daily, targets, date(2026, 9, 1), 30)
    assert (fechas[0], fechas[-1]) == (date(2026, 9, 1), date(2026, 9, 30))
    periods = vacation_periods(daily, "1", _YEAR, today=_HOY)
    assert len(periods) == 1 and periods[0]["dias"] == 30
    reject_if_art8_invalido(daily, "1", _YEAR)


def test_fraccion_15_mas_resto_y_7_8():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 15)
    _span(daily, targets, date(2026, 10, 1), 7)
    _span(daily, targets, date(2026, 11, 1), 8)
    sizes = sorted(p["dias"] for p in vacation_periods(daily, "1", _YEAR, today=_HOY))
    assert sizes == [7, 8, 15]


def test_primer_tramo_corto_ok_segundo_corto_no():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 5)
    with pytest.raises(ValueError, match="Art. 8"):
        _span(daily, targets, date(2026, 10, 1), 5)


# --- Adelanto (2.5 días por mes completo, tope 30 al cumplir el año) ---

def test_adelanto_tope_segun_meses():
    ingreso = date(2026, 1, 1)
    assert derecho_vigente(ingreso, date(2026, 1, 31)) == 0
    assert derecho_vigente(ingreso, date(2026, 2, 1)) == 2
    assert derecho_vigente(ingreso, date(2026, 8, 21)) == 17
    assert derecho_vigente(ingreso, date(2027, 1, 1)) == 30


# --- Modificar período ---

def test_mover_solo_programado_sin_duplicar():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 7)
    _span(daily, targets, date(2026, 10, 15), 8)
    move_vacation_period(
        daily, targets, "1", "ADMINISTRATIVO", _YEAR,
        old_start=date(2026, 9, 1), new_start=date(2026, 12, 1), today=_HOY,
    )
    periods = vacation_periods(daily, "1", _YEAR, today=_HOY)
    assert sum(p["dias"] for p in periods) == 15
    assert {p["inicio"] for p in periods} == {date(2026, 10, 15), date(2026, 12, 1)}


def test_no_mover_en_curso_ni_gozado():
    daily, targets = set(), {}
    apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", date(2026, 8, 21), 7, _YEAR, today=_HOY
    )
    with pytest.raises(ValueError, match="ya comenzó"):
        move_vacation_period(
            daily, targets, "1", "ADMINISTRATIVO", _YEAR,
            old_start=date(2026, 8, 21), new_start=date(2026, 9, 1), today=_HOY,
        )


def test_mover_no_puede_solaparse():
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 9, 1), 7)
    _span(daily, targets, date(2026, 10, 15), 8)
    with pytest.raises(ValueError, match="cruzan"):
        move_vacation_period(
            daily, targets, "1", "ADMINISTRATIVO", _YEAR,
            old_start=date(2026, 10, 15), new_start=date(2026, 9, 3), today=_HOY,
        )


# --- Fechas / año / semana en curso ---

def test_tramo_que_se_sale_del_anio_iso():
    daily, targets = set(), {}
    with pytest.raises(ValueError, match="no caben"):
        _span(daily, targets, date(2026, 12, 20), 30)


def test_no_borra_dias_ya_pasados_de_la_semana():
    daily: set[str] = set()
    for d in (date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 21)):
        daily.add(key_daily("1", d))
    clear_dates_for_week(daily, "1", 2026, 34, today=_HOY, keep_past=True)
    assert key_daily("1", date(2026, 8, 17)) in daily
    assert key_daily("1", date(2026, 8, 18)) in daily
    assert key_daily("1", date(2026, 8, 21)) not in daily


def test_validate_plan_marca_art8_y_saldo():
    emp = [{
        "dni": "1",
        "nombre": "Ana",
        "tipo_personal": "ADMINISTRATIVO",
        "fecha_ingreso": "2026-01-01",
        "jefatura": "X",
        "gerencia": "G",
        "area": "A",
    }]
    daily = {key_daily("1", date(2026, 9, 1) + timedelta(days=i)) for i in range(5)}
    daily |= {key_daily("1", date(2026, 10, 1) + timedelta(days=i)) for i in range(5)}
    errors, _w, groups = validate_plan(emp, {}, daily, 2026, today=_HOY)
    codes = {g["code"] for g in groups}
    assert "art8" in codes
    assert any("Art. 8" in e for e in errors)


def test_excel_periodos_usan_dias_corridos():
    emp = [{
        "dni": "1",
        "nombre": "Ana",
        "tipo_personal": "ADMINISTRATIVO",
        "jefatura": "X",
        "gerencia": "G",
        "area": "A",
    }]
    daily = set()
    for start in (date(2026, 9, 7), date(2026, 9, 14)):
        for i in range(5):
            daily.add(key_daily("1", start + timedelta(days=i)))
    rows = group_periods(emp, daily, 2026)
    assert [r["dias"] for r in rows] == [5, 5]
