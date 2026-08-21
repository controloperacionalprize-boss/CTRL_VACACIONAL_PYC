from __future__ import annotations

from datetime import date, timedelta

from .calendar import DERECHO_ANUAL, format_antiguedad, group_consecutive_dates, parse_iso_date, today_lima, vacation_record_for
from .holidays_pe import peru_holidays


def employee_calendar_payload(
    worker,
    anio: int,
    fechas: list[date],
    *,
    asistencia: set[date] | None = None,
    attendance_ok: bool = False,
):
    f_ingreso = parse_iso_date(worker.get("fecha_ingreso"))

    vac = set(fechas)
    asist = set(asistencia or ())
    holidays = peru_holidays(anio)
    today = today_lima()
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

    rec = vacation_record_for(f_ingreso if isinstance(f_ingreso, date) else None, fechas, anio, today)
    cumple = rec["cumple_record"]
    vencimiento = rec["fecha_vencimiento"]

    return {
        "empleado": worker,
        "anio": anio,
        "antiguedad": format_antiguedad(f_ingreso if isinstance(f_ingreso, date) else None),
        "consumido": rec["dias_programados"],
        "disponible": rec["dias_pendientes"],
        "record": {
            "record_vacacional": rec["record_vacacional"],
            "cumple_record": cumple.isoformat() if cumple else None,
            "fecha_vencimiento": vencimiento.isoformat() if vencimiento else None,
            "dias_programados": rec["dias_programados"],
            "dias_gozados": rec["dias_gozados"],
            "dias_pendientes": rec["dias_pendientes"],
            "record_cumplido": rec["record_cumplido"],
            "derecho": DERECHO_ANUAL,
        },
        "fechas": [x.isoformat() for x in fechas],
        "asistencia": sorted(x.isoformat() for x in asist),
        "sin_marcacion": sin_marcacion,
        "no_laborables": no_laborables,
        "attendance_ok": attendance_ok,
        "periodos": periodos,
    }
