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


def test_plan_15_mas_tramos_de_3_memorando_de_15_y_calendario_por_partes():
    """Caso probado en producción: 15 días y luego tramos de 3. El memorando va con los 15."""
    from app.doc_service import item_context
    from app.domain.doc_emision import calendario_documentos, documentos_pendientes
    from app.domain.documents_pdf import document_plain

    hoy = date(2026, 9, 15)
    daily = _dias("1", date(2026, 9, 21), 15)
    for inicio in (date(2026, 10, 12), date(2026, 10, 26), date(2026, 11, 9), date(2026, 11, 23), date(2026, 12, 7)):
        daily |= _dias("1", inicio, 3)
    periodos = vacation_periods(daily, "1", 2026, hoy)
    assert [p["dias"] for p in periodos] == [15, 3, 3, 3, 3, 3]
    items = documentos_pendientes(periodos=periodos, emitidos=[], today=hoy)
    assert items[0]["tramo"]["dias"] == 15
    memo = document_plain(2, item_context(APTO, items[0], year=2026, fecha_doc=hoy, programmed=[]))
    memo = memo.split("MEMORANDO DE VACACIONES")[-1]
    # Pauta de la reunión: el fraccionamiento concedido es el total, pero se otorga la salida
    # que toca ahora, con su rango real. Las otras cinco salidas van en su propio memorando.
    assert "por el periodo de 30 (treinta) días" in memo
    assert "se le otorga 15 (quince) días" in memo
    assert "del 21 de septiembre al 5 de octubre" in memo
    assert "9 de diciembre" not in memo, "el memorando no estira el rango hasta el último tramo"
    assert " | " not in memo, "el memorando no lleva tabla de periodos"
    cal = calendario_documentos(items, periodos, hoy)
    assert [c["tipo"] for c in cal] == ["fraccionamiento"] + ["memorando"] * 5
    assert cal[0]["estado"] == "por_emitir"
    assert {c["estado"] for c in cal[3:]} == {"proximo"}


def test_recepcion_directa_solo_admin_y_desde_borrador():
    import pytest

    from app.domain.workflow import (
        BORRADOR,
        ENVIADO,
        RECEPCIONADO,
        apply_recepcion_directa,
        flujo_from_row,
    )

    admin = {"rol": "ADMIN", "is_admin": True, "correo": "pyc@x.pe"}
    row = flujo_from_row(None)
    assert row["estado"] == BORRADOR
    out = apply_recepcion_directa(row, admin)
    assert out["estado"] == RECEPCIONADO
    assert out["admin_correo"] == "pyc@x.pe"
    assert out["jefe_correo"] == "" and out["gerente_correo"] == ""
    with pytest.raises(ValueError, match="Personas y Cultura"):
        apply_recepcion_directa(row, {"rol": "JEFE"})
    enviado = {**row, "estado": ENVIADO}
    with pytest.raises(ValueError, match="borrador"):
        apply_recepcion_directa(enviado, admin)


def test_jefe_no_se_asigna_a_si_mismo_con_nombre_corto_de_usuario():
    """Caso de producción: usuario JEFE "carlos coz" = maestro "COZ DE LA CRUZ CARLOS YORDANO"."""
    from app.domain.alerts import attach_jefe_nombres
    from app.org_scope import misma_persona

    assert misma_persona("carlos coz", "COZ DE LA CRUZ CARLOS YORDANO")
    assert not misma_persona("carlos", "COZ DE LA CRUZ CARLOS YORDANO"), "una sola palabra no basta"
    assert not misma_persona("ana coz", "COZ DE LA CRUZ CARLOS YORDANO")
    trabajador = {"dni": "45840854", "nombre": "COZ DE LA CRUZ CARLOS YORDANO", "area": "CONTROL OPERACIONAL", "jefatura": "CONTROL OPERACIONAL"}
    usuarios_jefe = [{"nombre_persona": "carlos coz", "area": "CONTROL OPERACIONAL"}]
    attach_jefe_nombres([trabajador], [], usuarios_jefe)
    assert trabajador["jefe_nombre"] == ""


def test_documentos_se_bajan_por_separado():
    from app.doc_service import item_context, partes_item, render_item
    from app.domain.doc_emision import documentos_pendientes
    from app.domain.documents_pdf import _blocks_parte

    hoy = date(2026, 9, 15)
    daily = _dias("1", date(2026, 9, 21), 15)
    for inicio in (date(2026, 10, 12), date(2026, 10, 26), date(2026, 11, 9), date(2026, 11, 23), date(2026, 12, 7)):
        daily |= _dias("1", inicio, 3)
    item = documentos_pendientes(periodos=vacation_periods(daily, "1", 2026, hoy), emitidos=[], today=hoy)[0]
    assert [p["id"] for p in partes_item(item)] == ["solicitud", "convenio", "memorando"]
    ctx = item_context(APTO, item, year=2026, fecha_doc=hoy, programmed=[])
    titulos = {
        parte: [b for k, b in _blocks_parte(2, ctx, parte) if k == "title"]
        for parte in ("solicitud", "convenio", "memorando")
    }
    assert titulos["solicitud"] == ["SOLICITUD FRACCIONAMIENTO DE DESCANSO VACACIONAL"]
    assert titulos["convenio"] == ["ACUERDO COMÚN DE FRACCIONAMIENTO DE DESCANSO VACACIONAL"]
    assert titulos["memorando"] == ["MEMORANDO DE VACACIONES"]
    pdf, nombre = render_item(APTO, item, year=2026, fecha_doc=hoy, programmed=[], parte="memorando")
    assert pdf.startswith(b"%PDF") and "_memorando_" in nombre
