"""Casos detectados en la auditoría del 15/09/2026."""
from datetime import date, timedelta

from app.doc_service import pendientes_por_dni
from app.domain.calendar import apply_consecutive_span, key_daily, move_vacation_period, vacation_periods
from app.domain.plan import validate_plan

HOY = date(2026, 9, 14)
APTO = {"dni": "1", "nombre": "Ana", "fecha_ingreso": "2020-01-15", "tipo_personal": "ADM",
        "jefatura": "X", "gerencia": "G", "area": "A"}
NUEVO = {**APTO, "dni": "2", "nombre": "Beto", "fecha_ingreso": "2026-03-01"}


def _dias(dni: str, inicio: date, n: int) -> set[str]:
    return {key_daily(dni, inicio + timedelta(days=i)) for i in range(n)}


def test_documentos_no_emite_plan_recepcionado_que_quedo_incompleto():
    """Si Personas y Cultura recorta días de un plan ya recepcionado, no sale un convenio parcial."""
    daily = _dias("1", date(2026, 10, 5), 7) | _dias("1", date(2026, 11, 2), 8) | _dias("1", date(2026, 12, 1), 10)
    items, _dates, motivo = pendientes_por_dni([APTO], daily, {}, 2026, HOY)["1"]
    assert items == []
    assert "Faltan 5 día(s)" in motivo


def test_documentos_emite_cuando_el_plan_esta_completo():
    daily = _dias("1", date(2026, 10, 5), 7) | _dias("1", date(2026, 11, 2), 8) | _dias("1", date(2026, 12, 1), 15)
    items, _dates, motivo = pendientes_por_dni([APTO], daily, {}, 2026, HOY)["1"]
    assert motivo == ""
    assert items and items[0]["tipo"] == "fraccionamiento"


def test_adelanto_corto_se_puede_mover():
    daily, targets = set(), {}
    apply_consecutive_span(daily, targets, "2", "ADM", date(2026, 10, 5), 5, 2026, today=HOY, validar_art8=False)
    nuevas, _d, _old = move_vacation_period(
        daily, targets, "2", "ADM", 2026, date(2026, 10, 5), date(2026, 10, 19), today=HOY, validar_art8=False
    )
    assert nuevas[0] == date(2026, 10, 19)
    assert [p["dias"] for p in vacation_periods(daily, "2", 2026, HOY)] == [5]


def test_validar_plan_no_marca_art8_en_adelanto():
    daily = _dias("2", date(2026, 10, 5), 5)
    _errors, _w, groups = validate_plan([NUEVO], {}, daily, 2026, today=HOY)
    assert "art8" not in {g["code"] for g in groups}
