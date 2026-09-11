"""
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook
import pandas as pd

from .export import _style_workbook
from .workflow import BORRADOR

TIPO_RECORD = "record_vence"
TIPO_MES = "mes_siguiente"
TIPO_SIN_PROGRAMAR = "sin_programar"
TIPO_PENDIENTES = "pendientes_flujo"


def flujo_estado_label(estado: str | None, rol: str) -> str:
    """Espejo de flujoEstadoLabel en el frontend: la etiqueta cambia según quién mira."""
    estado = estado or BORRADOR
    rol = (rol or "").upper()
    if estado == "ENVIADO":
        if rol == "GERENTE":
            return "Por validar"
        if rol == "ADMIN":
            return "Pendiente de gerente"
        return "Enviado al gerente"
    if estado == "VALIDADO":
        if rol == "ADMIN":
            return "Por recepcionar"
        if rol == "GERENTE":
            return "Validado"
        return "Validado por el gerente"
    if estado == "RECEPCIONADO":
        return "Recepcionado"
    if estado == "OBSERVADO":
        return "Observado"
    return "Borrador"


def _base_cols(p: dict) -> dict:
    return {
        "DNI": p.get("dni") or "",
        "NOMBRE": p.get("nombre") or "",
        "AREA": p.get("area") or "",
        "JEFATURA": p.get("jefatura") or "",
        "JEFE": p.get("jefe_nombre") or p.get("jefatura") or "",
        "GERENCIA": p.get("gerencia") or p.get("division") or "",
    }


def _row_for(p: dict, tipo: str, rol: str) -> dict:
    row = _base_cols(p)
    if tipo == TIPO_RECORD:
        dias = p.get("dias_restantes")
        row["FECHA_VENCIMIENTO"] = p.get("fecha_vencimiento") or ""
        row["DIAS_RESTANTES"] = dias if dias is not None else ""
    if tipo == TIPO_MES:
        row["MES"] = p.get("mes") or ""
        row["DIAS_EN_MES"] = p.get("dias_mes") or 0
        row["PERIODOS"] = p.get("periodos_mes") or ""
    row["TOTAL_DIAS"] = p.get("total_dias") or 0
    row["TOPE_DIAS"] = p.get("tope_dias") or 0
    row["ESTADO_PLANIFICACION"] = p.get("estado_plan") or ""
    if tipo in (TIPO_PENDIENTES, TIPO_SIN_PROGRAMAR):
        row["ESTADO_FLUJO"] = flujo_estado_label(p.get("flujo_estado"), rol)
    return row


SHEET_BY_TIPO = {
    TIPO_RECORD: "RECORD_POR_VENCER",
    TIPO_MES: "MES_SIGUIENTE",
    TIPO_SIN_PROGRAMAR: "APTOS_SIN_PROGRAMAR",
    TIPO_PENDIENTES: "PENDIENTES_FLUJO",
}


def build_alert_excel(tipo: str, personas: list[dict], rol: str) -> bytes:
    rows = [_row_for(p, tipo, rol) for p in personas]
    sheet = SHEET_BY_TIPO.get(tipo, "ALERTA")
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet, index=False)
    output.seek(0)
    wb = load_workbook(output)
    _style_workbook(wb, year=0, current_year=0, current_week=0)
    out2 = BytesIO()
    wb.save(out2)
    out2.seek(0)
    return out2.getvalue()
