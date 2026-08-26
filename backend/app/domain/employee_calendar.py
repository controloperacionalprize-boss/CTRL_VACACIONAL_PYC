from __future__ import annotations

from datetime import date, timedelta

from .calendar import DERECHO_ANUAL, format_antiguedad, group_consecutive_dates, parse_iso_date, today_lima, vacation_record_for
from .holidays_pe import peru_holidays


def exento_control_asistencia(worker) -> bool:
    """Jefes/gerentes/subgerentes suelen no marcar biométrico: no pintar faltas; sí pintar asistencia (verde)."""
    cargo = (worker.get("cargo_actual") or "").strip().lower()
    return any(k in cargo for k in ("jefe", "gerente", "sub gerente"))

def employee_calendar_payload(
    worker,
    anio: int,
    fechas: list[date],
    *,
    asistencia: set[date] | None = None,
    attendance_ok: bool = False,
    coverage_until: date | None = None,
):
    f_ingreso = parse_iso_date(worker.get("fecha_ingreso"))

    vac = set(fechas)
    asist = set(asistencia or ())
    exento = exento_control_asistencia(worker)
    holidays = peru_holidays(anio)
    today = today_lima()
    desde = f_ingreso if isinstance(f_ingreso, date) else date(anio, 1, 1)
    # No pintar faltas más allá de lo que BD/Excel realmente cubren (ej. Excel al 23).
    hasta = today
    if isinstance(coverage_until, date):
        hasta = min(today, coverage_until)

    no_laborables: list[str] = []
    sin_marcacion: list[str] = []
    # Jefes/gerentes: verde en días laborables cubiertos (no marcan biométrico).
    asist_exento: list[str] = []
    d = date(anio, 1, 1)
    end = date(anio + 1, 1, 1)
    while d < end:
        # Días previos al ingreso: sin faltas ni “no laborable” pintado (el front los marca deshabilitados).
        if isinstance(f_ingreso, date) and d < f_ingreso:
            d += timedelta(days=1)
            continue
        if d.weekday() >= 5 or d in holidays:
            no_laborables.append(d.isoformat())
        elif attendance_ok and desde <= d <= hasta and d not in vac:
            if exento:
                asist_exento.append(d.isoformat())
            elif d not in asist:
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

    if exento:
        asistencia_out = asist_exento
    else:
        asistencia_out = sorted(
            x.isoformat()
            for x in asist
            if not isinstance(f_ingreso, date) or x >= f_ingreso
        )

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
        "asistencia": asistencia_out,
        "sin_marcacion": sin_marcacion,
        "no_laborables": no_laborables,
        "attendance_ok": attendance_ok,
        "exento_marcacion": exento,
        "periodos": periodos,
    }
