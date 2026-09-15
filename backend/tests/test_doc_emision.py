"""Qué documento emite Personas y Cultura en cada momento (reunión 11/09/2026)."""
from datetime import date, datetime

from app.domain.doc_emision import (
    POR_EMITIR,
    PROXIMO,
    TIPO_FRACCIONAMIENTO,
    TIPO_MEMORANDO,
    TIPO_MODIFICACION,
    documentos_pendientes,
    emitir_desde,
    filas_a_registrar,
    fin_de_ventana,
    item_desde_fila,
    legacy_filas,
    tramo_json,
)
from app.domain.documents import build_context
from app.domain.documents_pdf import document_plain

HOY = date(2026, 9, 11)


def _t(ini: date, fin: date) -> dict:
    return {"inicio": ini, "fin": fin, "dias": (fin - ini).days + 1}


# Ejemplo de la reunión: 7 + 8 + cinco tramos de 3 días = 30.
PLAN_REUNION = [
    _t(date(2026, 9, 14), date(2026, 9, 20)),
    _t(date(2026, 9, 28), date(2026, 10, 5)),
    _t(date(2026, 10, 19), date(2026, 10, 21)),
    _t(date(2026, 11, 2), date(2026, 11, 4)),
    _t(date(2026, 11, 16), date(2026, 11, 18)),
    _t(date(2026, 12, 2), date(2026, 12, 4)),
    _t(date(2026, 12, 16), date(2026, 12, 18)),
]


def _registrar(item: dict, emitido_at: datetime, start_id: int = 1) -> list[dict]:
    filas = []
    for i, fila in enumerate(filas_a_registrar(item)):
        filas.append({**fila, "id": start_id + i, "emitido_at": emitido_at})
    return filas


def test_ventana_es_el_mes_siguiente():
    assert fin_de_ventana(date(2026, 9, 11)) == date(2026, 10, 31)
    assert fin_de_ventana(date(2026, 12, 3)) == date(2027, 1, 31)
    assert emitir_desde(date(2026, 12, 16)) == date(2026, 11, 1)
    assert emitir_desde(date(2027, 1, 5)) == date(2026, 12, 1)


def test_suma_del_plan_de_la_reunion_es_30():
    assert sum(p["dias"] for p in PLAN_REUNION) == 30


def test_primer_pedido_convenio_con_memorando_del_primer_tramo_no_del_ultimo():
    items = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)
    assert len(items) == 1, "sin convenio no sale ningún memorando suelto"
    pkg = items[0]
    assert pkg["tipo"] == TIPO_FRACCIONAMIENTO
    assert pkg["tramo"]["inicio"] == date(2026, 9, 14)
    assert pkg["tramo"]["fin"] == date(2026, 9, 20)
    assert len(pkg["periodos"]) == 7


def test_pdf_del_convenio_usa_el_tramo_de_septiembre():
    pkg = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)[0]
    tramo = pkg["tramo"]
    ctx = build_context(
        {"dni": "1", "nombre": "CARLOS COZ", "empresa": "AQUANQA", "fecha_ingreso": date(2020, 1, 1)},
        today=HOY,
        year=2026,
        inicio=tramo["inicio"],
        fin=tramo["fin"],
        dias=tramo["dias"],
        periodos=pkg["periodos"],
        memorando=True,
    )
    text = document_plain(2, ctx)
    memorando = text.split("MEMORANDO DE VACACIONES")[-1]
    assert "de 30 (treinta) días" in memorando
    assert "se le otorga 7 (siete) días" in memorando
    assert "del 14 al 20 de septiembre" in memorando
    assert "diciembre" not in memorando
    assert "14/09/2026" in text
    assert "Sexto periodo" in text
    assert "Séptimo periodo" in text
    assert "Periodo 6" not in text


def test_despues_del_convenio_solo_memorandos_por_tramo():
    pkg = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)[0]
    emitidos = _registrar(pkg, datetime(2026, 9, 11, 10, 0))
    items = documentos_pendientes(periodos=PLAN_REUNION, emitidos=emitidos, today=HOY)
    assert {i["tipo"] for i in items} == {TIPO_MEMORANDO}
    por_inicio = {i["tramo"]["inicio"]: i["estado"] for i in items}
    assert date(2026, 9, 14) not in por_inicio, "el primer memorando ya salió con el convenio"
    assert por_inicio[date(2026, 9, 28)] == POR_EMITIR
    assert por_inicio[date(2026, 10, 19)] == POR_EMITIR
    assert por_inicio[date(2026, 12, 16)] == PROXIMO


def test_en_noviembre_toca_el_memorando_de_diciembre():
    pkg = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)[0]
    emitidos = _registrar(pkg, datetime(2026, 9, 11, 10, 0))
    items = documentos_pendientes(periodos=PLAN_REUNION, emitidos=emitidos, today=date(2026, 11, 20))
    diciembre = [i for i in items if i["tramo"]["inicio"].month == 12]
    assert diciembre and all(i["estado"] == POR_EMITIR for i in diciembre)
    assert not any(i["tramo"]["fin"] < date(2026, 11, 20) for i in items), "lo gozado no se emite"


def test_si_el_primer_tramo_esta_lejos_el_convenio_sale_sin_memorando():
    plan = [_t(date(2026, 12, 1), date(2026, 12, 15)), _t(date(2027, 1, 4), date(2027, 1, 18))]
    items = documentos_pendientes(periodos=plan, emitidos=[], today=HOY)
    assert len(items) == 1
    assert items[0]["tipo"] == TIPO_FRACCIONAMIENTO
    assert items[0]["tramo"] is None


def test_mover_un_tramo_despues_del_convenio_pide_modificacion():
    pkg = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)[0]
    emitidos = _registrar(pkg, datetime(2026, 9, 11, 10, 0))
    movido = [*PLAN_REUNION[:2], _t(date(2026, 10, 21), date(2026, 10, 23)), *PLAN_REUNION[3:]]
    items = documentos_pendientes(periodos=movido, emitidos=emitidos, today=date(2026, 9, 15))
    mod = [i for i in items if i["tipo"] == TIPO_MODIFICACION]
    assert len(mod) == 1
    assert mod[0]["tramo"]["inicio"] == date(2026, 10, 21), "el memorando nuevo va con la modificación"
    assert {p["inicio"] for p in mod[0]["periodos_anteriores"]} >= {date(2026, 10, 19)}
    assert mod[0]["fecha_convenio"] == date(2026, 9, 11)
    memos = {i["tramo"]["inicio"] for i in items if i["tipo"] == TIPO_MEMORANDO}
    assert date(2026, 9, 28) in memos, "los tramos sin cambio siguen con su memorando"
    assert date(2026, 10, 21) not in memos


def test_goce_de_30_seguidos_solo_memorando():
    plan = [_t(date(2026, 10, 1), date(2026, 10, 30))]
    items = documentos_pendientes(periodos=plan, emitidos=[], today=HOY)
    assert [i["tipo"] for i in items] == [TIPO_MEMORANDO]


def test_reimpresion_conserva_lo_emitido():
    pkg = documentos_pendientes(periodos=PLAN_REUNION, emitidos=[], today=HOY)[0]
    fila = _registrar(pkg, datetime(2026, 9, 11, 10, 0))[0]
    fila["periodos"] = [tramo_json(p) for p in pkg["periodos"]]
    item = item_desde_fila(fila)
    assert item["tipo"] == TIPO_FRACCIONAMIENTO
    assert item["tramo"]["inicio"] == date(2026, 9, 14)
    assert len(item["periodos"]) == 7


def test_migracion_legacy_arma_convenio_y_primer_memorando():
    fechas = [date(2026, 9, d) for d in range(14, 21)] + [date(2026, 10, d) for d in range(1, 9)]
    filas = legacy_filas(2, "|".join(d.isoformat() for d in fechas))
    assert [f["tipo"] for f in filas] == [TIPO_FRACCIONAMIENTO, TIPO_MEMORANDO]
    assert filas[1]["tramo_inicio"] == date(2026, 9, 14)
    assert legacy_filas(2, "") == []
