from datetime import date

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..db import get_conn
from ..domain.alerts import attach_jefe_nombres, build_alerts, dates_in_month, next_calendar_month
from ..domain.calendar import derecho_vigente, parse_iso_date, today_lima, vacation_record_for
from ..domain.plan import sparse_weeks
from ..domain.workflow import enrich_workers, load_flujos
from ..org_scope import effective_role
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
