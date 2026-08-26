import re

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..attendance import attendance_sources_configured, fetch_merged_shifts
from ..attendance_db import fetch_coverage_max_date
from ..attendance_excel import excel_coverage_max_date
from ..auth import get_current_user
from ..db import get_conn
from ..domain.attendance_export import export_asistencia_excel
from ..domain.attendance_kpis import build_asistencia_kpis, month_span
from ..domain.calendar import today_lima
from ..domain.worker_vigencia import apply_master_vigencia, vigente_en_periodo
from ..services import list_employees, load_scope_plan

router = APIRouter(prefix="/api/asistencia", tags=["asistencia"])


def _asistencia_context(year: int, month: int | None, user: dict, empresa, gerencia, area):
    today = today_lima()
    mes = month or today.month
    start, end = month_span(year, mes, today=today)
    coverage = fetch_coverage_max_date()
    xl_max = excel_coverage_max_date(year)
    caps = [d for d in (coverage, xl_max) if d is not None]
    if caps:
        end = min(end, max(caps))

    configured = attendance_sources_configured()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area)
        employees = apply_master_vigencia(employees)
        employees = [e for e in employees if vigente_en_periodo(e, start, end)]
        daily_set, _targets = load_scope_plan(cur, year, employees)

    dnis = [e["dni"] for e in employees]
    shifts, times_ok = fetch_merged_shifts(dnis, start, end) if dnis and start <= end else ({}, configured)
    return employees, daily_set, shifts, start, end, configured, times_ok


@router.get("/export")
def asistencia_export(
    year: int,
    user: dict = Depends(get_current_user),
    month: int | None = Query(default=None, ge=1, le=12),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    employees, daily_set, shifts, start, end, configured, times_ok = _asistencia_context(
        year, month, user, empresa, gerencia, area
    )
    kpis = build_asistencia_kpis(
        employees,
        daily_set,
        shifts,
        start=start,
        end=end,
        configured=configured,
        times_ok=times_ok,
    )
    data = export_asistencia_excel(
        employees, daily_set, shifts, start=start, end=end, kpis=kpis
    )
    filename = f"ASISTENCIA_{start.isoformat()}_{end.isoformat()}.xlsx"
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def asistencia(
    year: int,
    user: dict = Depends(get_current_user),
    month: int | None = Query(default=None, ge=1, le=12),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    employees, daily_set, shifts, start, end, configured, times_ok = _asistencia_context(
        year, month, user, empresa, gerencia, area
    )
    return build_asistencia_kpis(
        employees,
        daily_set,
        shifts,
        start=start,
        end=end,
        configured=configured,
        times_ok=times_ok,
    )
