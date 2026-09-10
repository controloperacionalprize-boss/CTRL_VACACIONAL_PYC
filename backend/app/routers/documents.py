"""Cola Admin de documentos GTH: listar, PDF individual y ZIP."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from ..auth import require_admin
from ..db import get_conn
from ..domain.alerts import attach_jefe_nombres
from ..domain.calendar import dates_for_dni_year, parse_iso_date, today_lima, vacation_periods
from ..domain.doc_emision import (
    EMITIDO,
    MAX_ZIP,
    POR_EMITIR,
    POR_REEMITIR,
    item_documento,
    plan_hash,
)
from ..domain.documents import TEMPLATES, TITULOS, build_context
from ..domain.documents_pdf import filename_pdf, render_pdf
from ..domain.workflow import RECEPCIONADO, _ts, load_flujos
from ..services import list_employees, load_scope_plan

router = APIRouter(prefix="/api/documentos", tags=["documentos"])


def _attach_jefes(cur, rows: list[dict]) -> None:
    cur.execute(
        """SELECT nombre, area, jefatura, gerencia, cargo_actual
           FROM employees
           WHERE activo = TRUE AND cargo_actual ILIKE %s""",
        ("JEFE%",),
    )
    org_jefes = list(cur.fetchall())
    cur.execute(
        """SELECT correo, nombre_persona, nombre_usuario, area, gerencia
           FROM users
           WHERE activo = TRUE AND upper(rol) = 'JEFE' AND COALESCE(area, '') <> ''"""
    )
    attach_jefe_nombres(rows, org_jefes, list(cur.fetchall()))


def _load_emisiones(cur, year: int, dnis: list[str]) -> dict[str, dict]:
    if not dnis:
        return {}
    cur.execute(
        """SELECT anio, dni, escenario, plan_hash, descargas, descargado_at,
                  descargado_por, descargado_nombre
           FROM plan_documento_emision
           WHERE anio = %s AND dni = ANY(%s)""",
        (year, dnis),
    )
    out: dict[str, dict] = {}
    for r in cur.fetchall():
        out[str(r["dni"])] = {
            "escenario": int(r["escenario"] or 0),
            "plan_hash": r["plan_hash"] or "",
            "descargas": int(r["descargas"] or 0),
            "descargado_at": _ts(r["descargado_at"]),
            "descargado_por": r["descargado_por"] or "",
            "descargado_nombre": r["descargado_nombre"] or "",
        }
    return out


def _cola(cur, user: dict, year: int, empresa, gerencia, area, today: date) -> list[dict]:
    employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
    dnis = [e["dni"] for e in employees]
    flujos = load_flujos(cur, year, dnis)
    recep = [e for e in employees if (flujos.get(e["dni"]) or {}).get("estado") == RECEPCIONADO]
    if not recep:
        return []
    daily_set, _targets = load_scope_plan(cur, year, recep)
    emisiones = _load_emisiones(cur, year, [e["dni"] for e in recep])
    _attach_jefes(cur, recep)
    items = []
    for e in recep:
        dates = dates_for_dni_year(daily_set, e["dni"], year)
        periodos = vacation_periods(daily_set, e["dni"], year, today, dates=dates)
        fl = flujos.get(e["dni"]) or {}
        row = item_documento(
            e,
            periodos=periodos,
            dates=dates,
            today=today,
            emision=emisiones.get(e["dni"]),
            recepcionado_at=fl.get("recepcionado_at"),
        )
        if row:
            items.append(row)
    items.sort(key=lambda r: ((r.get("nombre") or ""), r["dni"]))
    return items


def _pdf_bytes(emp: dict, year: int, daily_set: set, today: date) -> tuple[bytes, str, int, str, list[dict]]:
    dates = dates_for_dni_year(daily_set, emp["dni"], year)
    periodos = vacation_periods(daily_set, emp["dni"], year, today, dates=dates)
    row = item_documento(
        emp,
        periodos=periodos,
        dates=dates,
        today=today,
        emision=None,
        recepcionado_at=None,
    )
    if not row:
        raise HTTPException(400, "Este plan no tiene períodos para armar el documento.")
    inicio = periodos[0]["inicio"]
    fin = periodos[-1]["fin"]
    dias = int(periodos[0]["dias"] or 0)
    ctx = build_context(
        emp,
        today=today,
        year=year,
        inicio=inicio,
        fin=fin,
        dias=dias,
        periodos=periodos,
        programmed=dates,
    )
    escenario = row["escenario"]
    return (
        render_pdf(escenario, ctx),
        filename_pdf(escenario, ctx),
        escenario,
        plan_hash(dates),
        periodos,
    )


def _registrar(cur, year: int, dni: str, escenario: int, current_hash: str, user: dict) -> None:
    nombre = (
        user.get("nombre_persona")
        or user.get("nombre_usuario")
        or user.get("correo")
        or ""
    )
    cur.execute(
        """INSERT INTO plan_documento_emision (
               anio, dni, escenario, plan_hash, descargas,
               descargado_at, descargado_por, descargado_nombre
           ) VALUES (%s, %s, %s, %s, 1, NOW(), %s, %s)
           ON CONFLICT (anio, dni) DO UPDATE SET
               escenario = EXCLUDED.escenario,
               plan_hash = EXCLUDED.plan_hash,
               descargas = plan_documento_emision.descargas + 1,
               descargado_at = NOW(),
               descargado_por = EXCLUDED.descargado_por,
               descargado_nombre = EXCLUDED.descargado_nombre""",
        (year, dni, escenario, current_hash, user.get("correo") or "", nombre),
    )


def _emp_recepcionado(cur, user: dict, year: int, dni: str, empresa, gerencia, area):
    employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
    emp = next((e for e in employees if str(e["dni"]) == str(dni)), None)
    if not emp:
        raise HTTPException(404, "No está en tu alcance.")
    flujos = load_flujos(cur, year, [emp["dni"]])
    if (flujos.get(emp["dni"]) or {}).get("estado") != RECEPCIONADO:
        raise HTTPException(409, "Solo se emite el PDF de un plan ya recepcionado.")
    return emp


@router.get("")
def listar_documentos(
    year: int = Query(...),
    user: dict = Depends(require_admin),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    with get_conn(write=False) as conn:
        items = _cola(conn.cursor(), user, year, empresa, gerencia, area, today)
    resumen = {
        POR_EMITIR: sum(1 for i in items if i["estado_emision"] == POR_EMITIR),
        POR_REEMITIR: sum(1 for i in items if i["estado_emision"] == POR_REEMITIR),
        EMITIDO: sum(1 for i in items if i["estado_emision"] == EMITIDO),
    }
    return {
        "year": year,
        "resumen": resumen,
        "max_zip": MAX_ZIP,
        "tipos": [{"escenario": k, "titulo": v} for k, v in TITULOS.items()],
        "items": items,
    }


class DescargarIn(BaseModel):
    year: int
    dni: str


class ZipIn(BaseModel):
    year: int
    dnis: list[str]

    @field_validator("dnis")
    @classmethod
    def dnis_ok(cls, v: list[str]) -> list[str]:
        out = [str(x).strip() for x in v if str(x).strip()]
        if not out:
            raise ValueError("Elige al menos una persona.")
        if len(out) > MAX_ZIP:
            raise ValueError(f"Como máximo {MAX_ZIP} documentos por ZIP.")
        return out


@router.post("/descargar")
def descargar_uno(
    body: DescargarIn,
    user: dict = Depends(require_admin),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    with get_conn() as conn:
        cur = conn.cursor()
        emp = _emp_recepcionado(cur, user, body.year, body.dni, empresa, gerencia, area)
        daily_set, _ = load_scope_plan(cur, body.year, [emp])
        pdf, name, escenario, current_hash, _periodos = _pdf_bytes(emp, body.year, daily_set, today)
        _registrar(cur, body.year, emp["dni"], escenario, current_hash, user)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/zip")
def descargar_zip(
    body: ZipIn,
    user: dict = Depends(require_admin),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    wanted = set(body.dnis)
    buf = BytesIO()
    ok = 0
    errors: list[str] = []
    with get_conn() as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
        by_dni = {str(e["dni"]): e for e in employees if str(e["dni"]) in wanted}
        missing = [d for d in body.dnis if d not in by_dni]
        if missing:
            raise HTTPException(404, f"No están en tu alcance: {', '.join(missing[:8])}.")
        flujos = load_flujos(cur, body.year, list(by_dni))
        recep = [by_dni[d] for d in body.dnis if (flujos.get(d) or {}).get("estado") == RECEPCIONADO]
        if len(recep) != len(body.dnis):
            raise HTTPException(409, "Solo se emite el PDF de planes ya recepcionados.")
        daily_set, _ = load_scope_plan(cur, body.year, recep)
        with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
            used: set[str] = set()
            for emp in recep:
                try:
                    pdf, name, escenario, current_hash, _p = _pdf_bytes(
                        emp, body.year, daily_set, today
                    )
                except HTTPException as exc:
                    errors.append(f"{emp.get('nombre') or emp['dni']}: {exc.detail}")
                    continue
                folder = TEMPLATES[escenario][1]
                arc = f"{folder}/{name}"
                if arc in used:
                    arc = f"{folder}/{emp['dni']}_{name}"
                used.add(arc)
                zf.writestr(arc, pdf)
                _registrar(cur, body.year, emp["dni"], escenario, current_hash, user)
                ok += 1
    if ok == 0:
        raise HTTPException(400, errors[0] if errors else "No se pudo armar ningún PDF.")
    zipname = f"documentos_gth_{body.year}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zipname}"'},
    )
