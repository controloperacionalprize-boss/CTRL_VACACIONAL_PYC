from __future__ import annotations

from datetime import date, timedelta

from .calendar import DERECHO_ANUAL, format_antiguedad, group_consecutive_dates
from .holidays_pe import peru_holidays


def employee_calendar_payload(
    worker,
    anio: int,
    fechas: list[date],
    *,
    asistencia: set[date] | None = None,
    attendance_ok: bool = False,
):
    f_ingreso = worker.get("fecha_ingreso")
    if isinstance(f_ingreso, str) and f_ingreso:
        f_ingreso = date.fromisoformat(f_ingreso[:10])

    vac = set(fechas)
    asist = set(asistencia or ())
    holidays = peru_holidays(anio)
    today = date.today()
    desde = f_ingreso if isinstance(f_ingreso, date) else date(anio, 1, 1)

    no_laborables: list[str] = []
    sin_marcacion: list[str] = []
    d = date(anio, 1, 1)
    end = date(anio + 1, 1, 1)
    while d < end:
        if d.weekday() >= 5 or d in holidays:
            no_laborables.append(d.isoformat())
        elif (
            attendance_ok
            and desde <= d <= today
            and d not in vac
            and d not in asist
        ):
            sin_marcacion.append(d.isoformat())
        d += timedelta(days=1)

    periodos = []
    for ini, fin in group_consecutive_dates(fechas):
        periodos.append({
            "tipo": "Vacaciones",
            "inicio": ini.isoformat(),
            "fin": fin.isoformat(),
            "dias": sum(1 for x in fechas if ini <= x <= fin),
        })

    return {
        "empleado": worker,
        "anio": anio,
        "antiguedad": format_antiguedad(f_ingreso if isinstance(f_ingreso, date) else None),
        "consumido": len(fechas),
        "disponible": max(DERECHO_ANUAL - len(fechas), -99),
        "fechas": [x.isoformat() for x in fechas],
        "asistencia": sorted(x.isoformat() for x in asist),
        "sin_marcacion": sin_marcacion,
        "no_laborables": no_laborables,
        "attendance_ok": attendance_ok,
        "periodos": periodos,
    }
