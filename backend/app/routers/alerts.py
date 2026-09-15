import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..auth import get_current_user
from ..db import get_conn
from ..domain.alerts import attach_jefe_nombres, build_alerts, dates_in_month, next_calendar_month
from ..domain.alerts_export import build_alert_excel
from ..domain.calendar import derecho_vigente, parse_iso_date, today_lima, vacation_record_for
from ..domain.plan import sparse_weeks
from ..domain.workflow import enrich_workers, load_flujos
from ..org_scope import effective_role
from ..rate_limit import limiter
from ..services import list_employees, load_scope_plan

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _workers_for_alerts(cur, user: dict, year: int, empresa, gerencia, area, today: date) -> tuple[list[dict], set]:
    employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
    daily_set, targets = load_scope_plan(cur, year, employees)
    dnis = [e["dni"] for e in employees]
    flujos = load_flujos(cur, year, dnis)
    rows = []
    for e in employees:
        weeks = sparse_weeks(targets, e["dni"])
        total = sum(weeks.values())
        tope = derecho_vigente(parse_iso_date(e.get("fecha_ingreso")), today)
        rec = vacation_record_for(parse_iso_date(e.get("fecha_ingreso")), [], year, today)
        vence = rec.get("fecha_vencimiento")
        rows.append({
            **e,
            "weeks": weeks,
            "total_dias": total,
            "tope_dias": tope,
            "record_vacacional": rec.get("record_vacacional") or "",
            "fecha_vencimiento": vence.isoformat() if isinstance(vence, date) else None,
        })
    rows = enrich_workers(rows, flujos, user, today)
    cur.execute(
        """SELECT dni, nombre, area, jefatura, gerencia, cargo_actual
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
    return rows, daily_set


@router.get("")
def get_alerts(
    year: int = Query(...),
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        workers, daily_set = _workers_for_alerts(cur, user, year, empresa, gerencia, area, today)
        ny, nm = next_calendar_month(today)
        if ny != year:
            daily_next, _ = load_scope_plan(cur, ny, workers)
            daily_for_month = daily_next
        else:
            daily_for_month = daily_set
    dias_mes = dates_in_month(daily_for_month, ny, nm)
    return build_alerts(
        today=today,
        year=year,
        role=effective_role(user),
        workers=workers,
        dias_mes_siguiente=dias_mes,
    )


@router.get("/export")
@limiter.limit("8/minute")
def export_alert(
    request: Request,
    year: int = Query(...),
    tipo: str = Query(...),
    mes: str = Query(default=""),
    area_filtro: str = Query(default=""),
    jefe_filtro: str = Query(default=""),
    flujo_filtro: str = Query(default=""),
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        workers, daily_set = _workers_for_alerts(cur, user, year, empresa, gerencia, area, today)
        ny, nm = next_calendar_month(today)
        if ny != year:
            daily_next, _ = load_scope_plan(cur, ny, workers)
            daily_for_month = daily_next
        else:
            daily_for_month = daily_set
    dias_mes = dates_in_month(daily_for_month, ny, nm)
    rol = effective_role(user)
    payload = build_alerts(
        today=today,
        year=year,
        role=rol,
        workers=workers,
        dias_mes_siguiente=dias_mes,
    )
    item = next(
        (i for i in payload["items"] if i["tipo"] == tipo and (not mes or i.get("mes") == mes)),
        None,
    )
    if not item:
        raise HTTPException(404, "No hay datos para exportar de esa alerta.")

    personas = item["personas"]
    if area_filtro:
        personas = [p for p in personas if (p.get("area") or "").strip() == area_filtro]
    if jefe_filtro:
        personas = [
            p for p in personas if (p.get("jefe_nombre") or p.get("jefatura") or "").strip() == jefe_filtro
        ]
    if flujo_filtro:
        personas = [p for p in personas if (p.get("flujo_estado") or "BORRADOR") == flujo_filtro]

    data = build_alert_excel(tipo, personas, rol)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", tipo)[:40] or "ALERTA"
    filename = f"ALERTA_{safe}_{year}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
