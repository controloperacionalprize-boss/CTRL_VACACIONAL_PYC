from datetime import date
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..attendance import fetch_merged_attendance
from ..auth import get_current_user
from ..db import get_conn
from ..domain.calendar import today_lima
from ..domain.employee_calendar import employee_calendar_payload
from ..domain.export import build_record, export_excel
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
):
    today = today_lima()
    cy, cw, _ = today.isocalendar()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area)
        daily_set, targets = load_scope_plan(cur, year, employees)
        dnis = [e["dni"] for e in employees]
        log_rows = []
        if dnis:
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
    )
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)[:40] or "PLAN"
    filename = f"VACACIONES_{year}_{safe}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
