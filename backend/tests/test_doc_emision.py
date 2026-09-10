from datetime import date

from app.domain.doc_emision import (
    EMITIDO,
    POR_EMITIR,
    POR_REEMITIR,
    emision_estado,
    item_documento,
    plan_hash,
    escenario_de_plan,
)


def test_plan_hash_ordena_fechas():
    assert plan_hash([date(2026, 1, 3), date(2026, 1, 1)]) == "2026-01-01|2026-01-03"


def test_emision_estado_tres_casos():
    h = "2026-01-01"
    assert emision_estado(None, h) == POR_EMITIR
    assert emision_estado("", h) == POR_EMITIR
    assert emision_estado(h, h) == EMITIDO
    assert emision_estado(h, "2026-01-01|2026-01-02") == POR_REEMITIR


def test_escenario_memorando_vs_fraccion_vs_adelanto():
    assert escenario_de_plan(es_adelanto=False, period_sizes=[30])["escenario"] == 1
    assert escenario_de_plan(es_adelanto=False, period_sizes=[15, 15])["escenario"] == 2
    assert escenario_de_plan(es_adelanto=True, period_sizes=[10])["escenario"] == 4


def test_item_documento_por_reemitir():
    emp = {
        "dni": "10000001",
        "nombre": "María Pérez",
        "area": "T.I.",
        "jefatura": "T.I.",
        "jefe_nombre": "Huaman Rodriguez",
        "fecha_ingreso": "2018-01-01",
    }
    periodos = [{"inicio": date(2026, 10, 1), "fin": date(2026, 10, 30), "dias": 30}]
    dates = [date(2026, 10, d) for d in range(1, 31)]
    row = item_documento(
        emp,
        periodos=periodos,
        dates=dates,
        today=date(2026, 9, 10),
        emision={"plan_hash": "otro", "descargas": 1, "descargado_nombre": "Luis"},
        recepcionado_at="2026-09-09T10:00:00",
    )
    assert row is not None
    assert row["estado_emision"] == POR_REEMITIR
    assert row["escenario"] == 1
    assert row["jefe_nombre"] == "Huaman Rodriguez"
    assert row["descargas"] == 1


def test_item_sin_dias_no_entra():
    emp = {"dni": "1", "nombre": "X", "fecha_ingreso": "2018-01-01"}
    assert item_documento(
        emp,
        periodos=[],
        dates=[],
        today=date(2026, 9, 10),
        emision=None,
        recepcionado_at=None,
    ) is None
