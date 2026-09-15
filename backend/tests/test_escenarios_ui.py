"""Recorre los 4 escenarios como lo harían los botones de Plan / Documentos.

No toca la BD: simula Guardar período, Modificar y Adelanto, y mira qué fila
aparecería en la tabla de Documentos (tipo, tramo, estado).
"""
from datetime import date, datetime

from app.domain.calendar import (
    apply_consecutive_span,
    art8_fraccion_ok,
    move_vacation_period,
    reject_if_art8_invalido,
    reject_if_plan_not_completo,
    vacation_periods,
)
from app.domain.doc_emision import (
    POR_EMITIR,
    PROXIMO,
    TIPO_ADELANTO,
    TIPO_FRACCIONAMIENTO,
    TIPO_MEMORANDO,
    TIPO_MODIFICACION,
    documentos_pendientes,
    filas_a_registrar,
)

HOY = date(2026, 9, 14)
YEAR = 2026


def _span(daily, targets, start, days):
    return apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", start, days, YEAR, today=HOY
    )


def _periodos(daily):
    return vacation_periods(daily, "1", YEAR, today=HOY)


def _tipos(items):
    return [(i["tipo"], i["estado"], i["tramo"]["inicio"] if i["tramo"] else None) for i in items]


def test_boton_programar_30_corridos_tabla_documentos_solo_memorando():
    """Personas y Cultura: Programar vacaciones 01/10–30/10 → tabla Documentos: Memorando."""
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 10, 1), 30)
    periodos = _periodos(daily)
    reject_if_plan_not_completo(nombre="Ana", programados=sum(p["dias"] for p in periodos), derecho=30)
    reject_if_art8_invalido(daily, "1", YEAR)
    items = documentos_pendientes(periodos=periodos, emitidos=[], today=HOY)
    assert [p["dias"] for p in periodos] == [30]
    assert _tipos(items) == [(TIPO_MEMORANDO, POR_EMITIR, date(2026, 10, 1))]


def test_boton_programar_5_dias_no_se_guarda():
    """Jefe tabla / grilla de Personas y Cultura → Programar 5 días al inicio: Art. 8 rechaza el guardado."""
    daily, targets = set(), {}
    import pytest

    with pytest.raises(ValueError, match="Art. 8"):
        _span(daily, targets, date(2026, 10, 1), 5)
    assert vacation_periods(daily, "1", YEAR, today=HOY) == []


def test_botones_guardar_periodo_fraccion_7_8_y_libres():
    """Jefe: Guardar período 7, luego 8, luego tramos de 3. Primer PDF = convenio + memo 14-20/09."""
    daily, targets = set(), {}
    for start, days in (
        (date(2026, 9, 21), 7),
        (date(2026, 10, 5), 8),
        (date(2026, 10, 19), 3),
        (date(2026, 11, 2), 3),
        (date(2026, 11, 16), 3),
        (date(2026, 12, 1), 3),
        (date(2026, 12, 16), 3),
    ):
        _span(daily, targets, start, days)
    periodos = _periodos(daily)
    sizes = [p["dias"] for p in periodos]
    assert sum(sizes) == 30
    assert art8_fraccion_ok(sizes)
    reject_if_plan_not_completo(nombre="Ana", programados=30, derecho=30)
    items = documentos_pendientes(periodos=periodos, emitidos=[], today=HOY)
    assert len(items) == 1
    assert items[0]["tipo"] == TIPO_FRACCIONAMIENTO
    assert items[0]["tramo"]["inicio"] == date(2026, 9, 21)
    assert items[0]["tramo"]["fin"] == date(2026, 9, 27)
    assert len(items[0]["periodos"]) == 7


def test_despues_de_emitir_convenio_tabla_solo_memos_por_tramo():
    daily, targets = set(), {}
    for start, days in (
        (date(2026, 9, 21), 7),
        (date(2026, 10, 5), 8),
        (date(2026, 10, 19), 3),
        (date(2026, 11, 2), 3),
        (date(2026, 11, 16), 3),
        (date(2026, 12, 1), 3),
        (date(2026, 12, 16), 3),
    ):
        _span(daily, targets, start, days)
    periodos = _periodos(daily)
    pkg = documentos_pendientes(periodos=periodos, emitidos=[], today=HOY)[0]
    emitidos = [{**f, "id": i + 1, "emitido_at": datetime(2026, 9, 14, 10, 0)} for i, f in enumerate(filas_a_registrar(pkg))]
    items = documentos_pendientes(periodos=periodos, emitidos=emitidos, today=HOY)
    assert {i["tipo"] for i in items} == {TIPO_MEMORANDO}
    por_inicio = {i["tramo"]["inicio"]: i["estado"] for i in items}
    assert date(2026, 9, 21) not in por_inicio
    assert por_inicio[date(2026, 10, 5)] == POR_EMITIR
    assert por_inicio[date(2026, 12, 16)] == PROXIMO


def test_boton_modificar_periodo_tras_convenio_pide_modificacion():
    """Personas y Cultura/Jefe: Modificar período (mueve un tramo) → tabla Documentos: Modificación de convenio."""
    daily, targets = set(), {}
    for start, days in (
        (date(2026, 9, 21), 7),
        (date(2026, 10, 5), 8),
        (date(2026, 11, 2), 15),
    ):
        _span(daily, targets, start, days)
    periodos = _periodos(daily)
    pkg = documentos_pendientes(periodos=periodos, emitidos=[], today=HOY)[0]
    emitidos = [{**f, "id": i + 1, "emitido_at": datetime(2026, 9, 14, 10, 0)} for i, f in enumerate(filas_a_registrar(pkg))]
    move_vacation_period(
        daily, targets, "1", "ADMINISTRATIVO", YEAR,
        old_start=date(2026, 10, 5), new_start=date(2026, 10, 12), today=HOY,
    )
    movidos = _periodos(daily)
    items = documentos_pendientes(periodos=movidos, emitidos=emitidos, today=HOY)
    mods = [i for i in items if i["tipo"] == TIPO_MODIFICACION]
    assert len(mods) == 1
    assert mods[0]["tramo"]["inicio"] == date(2026, 10, 12)
    assert sum(p["dias"] for p in movidos) == 30


def test_boton_adelanto_tabla_documentos_tipo_propio():
    """Personas y Cultura: Adelanto vacacional (no cumple el año) → tabla: Adelanto, no convenio."""
    daily, targets = set(), {}
    _span(daily, targets, date(2026, 10, 1), 10)
    periodos = _periodos(daily)
    items = documentos_pendientes(periodos=periodos, emitidos=[], today=HOY, es_adelanto=True)
    assert _tipos(items) == [(TIPO_ADELANTO, POR_EMITIR, date(2026, 10, 1))]
    assert all(i["tipo"] != TIPO_FRACCIONAMIENTO for i in items)


def test_fraccion_5_el_guardar_periodo_falla_al_inicio():
    import pytest

    daily, targets = set(), {}
    with pytest.raises(ValueError, match="Art. 8"):
        _span(daily, targets, date(2026, 10, 1), 5)
