from datetime import date
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..attendance import fetch_merged_attendance
from ..auth import get_current_user
from ..db import get_conn
from ..domain.calendar import es_apto, today_lima
from ..domain.employee_calendar import employee_calendar_payload
from ..domain.export import RECORD_SHEETS, build_record, export_excel, programmed_dnis
from ..services import get_employee, list_employees, load_scope_plan

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/calendar/{dni}")
def calendar_emp(
    dni: str,
    year: int,
    user: dict = Depends(get_current_user),
):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        inicio = date(year, 1, 1)
        fin = date(year + 1, 1, 1)
        cur.execute(
            """SELECT fecha FROM daily_plan
               WHERE dni = %s AND anio = %s AND fecha >= %s AND fecha < %s""",
            (dni, year, inicio, fin),
        )
        fechas = [r["fecha"] for r in cur.fetchall() if isinstance(r["fecha"], date)]
    asistencia, ok, coverage = fetch_merged_attendance(dni, year)
    return employee_calendar_payload(
        emp,
        year,
        sorted(fechas),
        asistencia=asistencia,
        attendance_ok=ok,
        coverage_until=coverage,
    )


@router.get("/export")
def export_plan(
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
    label: str = "PLAN",
    solo_aptos: bool = Query(default=False),
    con_vacaciones: bool = Query(default=False),
):
    today = today_lima()
    cy, cw, _ = today.isocalendar()
    record_only = solo_aptos and con_vacaciones
    if record_only:
        label = "APTOS"
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area)
        if solo_aptos:
            employees = [e for e in employees if es_apto(e, today)]
        daily_set, targets = load_scope_plan(cur, year, employees)
        if con_vacaciones:
            have = programmed_dnis(targets, daily_set)
            employees = [e for e in employees if str(e["dni"]) in have]
        dnis = [e["dni"] for e in employees]
        log_rows = []
        if dnis and not record_only:
            cur.execute(
                """SELECT id, fecha_hora, jefatura, anio, dni, nombre, tipo_persona,
                          semana_anterior, dias_anterior, semana_nueva, dias_nuevos,
                          usuario, nombre_persona, correo
                   FROM change_log WHERE anio = %s AND dni = ANY(%s)
                   ORDER BY fecha_hora DESC, id DESC""",
                (year, dnis),
            )
            log_rows = [dict(r) for r in cur.fetchall()]
        dias_map: dict[str, list[date]] = {d: [] for d in dnis}
        if dnis:
            cur.execute("SELECT dni, fecha FROM daily_plan WHERE dni = ANY(%s)", (dnis,))
            for r in cur.fetchall():
                f = r["fecha"]
                if isinstance(f, date):
                    dias_map.setdefault(str(r["dni"]), []).append(f)
        historial = build_record(employees, dias_map, year, today)
    data = export_excel(
        employees,
        daily_set,
        targets,
        year,
        label,
        cy,
        cw,
        log_rows,
        user.get("usuario") or user["correo"],
        user.get("nombre_persona") or user.get("nombre_usuario"),
        historial,
        sheets=RECORD_SHEETS if record_only else None,
    )
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)[:40] or "PLAN"
    filename = f"VACACIONES_{year}_{safe}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
