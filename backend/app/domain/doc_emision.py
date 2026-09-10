"""Emisión de documentos GTH: cola Admin sobre planes ya recepcionados.

El flujo (RECEPCIONADO) no cambia al descargar. Aquí solo se registra si GTH
ya sacó el PDF, y si el plan de días se movió después.
"""
from __future__ import annotations

from datetime import date

from .calendar import record_cumplido
from .documents import TITULOS, documento_meta

POR_EMITIR = "por_emitir"
EMITIDO = "emitido"
POR_REEMITIR = "por_reemitir"

ESTADOS_EMISION = (POR_EMITIR, EMITIDO, POR_REEMITIR)

ESTADO_EMISION_LABEL = {
    POR_EMITIR: "Por emitir",
    EMITIDO: "Emitido",
    POR_REEMITIR: "Por reemitir",
}

MAX_ZIP = 40


def plan_hash(dates: list[date]) -> str:
    return "|".join(d.isoformat() for d in sorted(dates))


def emision_estado(saved_hash: str | None, current_hash: str) -> str:
    if not saved_hash:
        return POR_EMITIR
    if saved_hash != current_hash:
        return POR_REEMITIR
    return EMITIDO


def escenario_de_plan(*, es_adelanto: bool, period_sizes: list[int]) -> dict:
    """Tipo GTH del plan vigente (sin ‘modificación’: eso es un momento, no el plan)."""
    return documento_meta(es_adelanto=es_adelanto, moved=False, period_sizes=period_sizes)


def es_adelanto_de(emp: dict, today: date) -> bool:
    from .calendar import parse_iso_date

    ingreso = emp.get("fecha_ingreso")
    if not isinstance(ingreso, date):
        ingreso = parse_iso_date(ingreso)
    return not record_cumplido(ingreso, today)


def periodos_json(periodos: list[dict]) -> list[dict]:
    out = []
    for p in periodos:
        inicio = p.get("inicio")
        fin = p.get("fin")
        out.append({
            "inicio": inicio.isoformat() if isinstance(inicio, date) else str(inicio or ""),
            "fin": fin.isoformat() if isinstance(fin, date) else str(fin or ""),
            "dias": int(p.get("dias") or 0),
        })
    return out


def item_documento(
    emp: dict,
    *,
    periodos: list[dict],
    dates: list[date],
    today: date,
    emision: dict | None,
    recepcionado_at: str | None,
) -> dict | None:
    if not dates or not periodos:
        return None
    sizes = [int(p.get("dias") or 0) for p in periodos]
    adelanto = es_adelanto_de(emp, today)
    meta = escenario_de_plan(es_adelanto=adelanto, period_sizes=sizes)
    current = plan_hash(dates)
    saved = (emision or {}).get("plan_hash") or None
    estado = emision_estado(saved, current)
    inicio = periodos[0]["inicio"]
    fin = periodos[-1]["fin"]
    return {
        "dni": str(emp.get("dni") or ""),
        "nombre": emp.get("nombre") or "",
        "area": (emp.get("area") or "").strip(),
        "jefatura": (emp.get("jefatura") or "").strip(),
        "jefe_nombre": (emp.get("jefe_nombre") or "").strip(),
        "gerencia": (emp.get("gerencia") or emp.get("division") or "").strip(),
        "escenario": meta["escenario"],
        "titulo": meta["titulo"],
        "dias": sum(sizes),
        "periodos": periodos_json(periodos),
        "inicio": inicio.isoformat() if isinstance(inicio, date) else str(inicio),
        "fin": fin.isoformat() if isinstance(fin, date) else str(fin),
        "estado_emision": estado,
        "estado_emision_label": ESTADO_EMISION_LABEL[estado],
        "recepcionado_at": recepcionado_at,
        "descargas": int((emision or {}).get("descargas") or 0),
        "descargado_at": (emision or {}).get("descargado_at"),
        "descargado_por": (emision or {}).get("descargado_nombre")
        or (emision or {}).get("descargado_por")
        or "",
        "plan_hash": current,
    }
