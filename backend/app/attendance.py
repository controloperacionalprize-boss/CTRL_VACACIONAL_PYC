"""Une asistencia de BD + Excel SharePoint (Excel completa lo que falte)."""
from __future__ import annotations

from datetime import date

from .attendance_db import attendance_configured, fetch_attendance_dates, fetch_attendance_shifts, fetch_coverage_max_date
from .domain.attendance_kpis import norm_dni
from .attendance_excel import (
    excel_attendance_configured,
    excel_attendance_ok,
    excel_coverage_max_date,
    fetch_excel_attendance_dates,
    fetch_excel_shifts,
)


def attendance_sources_configured() -> bool:
    return attendance_configured() or excel_attendance_configured()


def fetch_merged_attendance(dni: str, year: int) -> tuple[set[date], bool, date | None]:
    """BD primero; Excel aporta solo días posteriores al último de la BD."""
    db_ok = attendance_configured()
    xl_ok_cfg = excel_attendance_configured()

    db_days = fetch_attendance_dates(dni, year) if db_ok else set()
    xl_days = fetch_excel_attendance_dates(dni, year) if xl_ok_cfg else set()
    xl_live = excel_attendance_ok() if xl_ok_cfg else False

    if db_days:
        max_db = max(db_days)
        merged = db_days | {d for d in xl_days if d > max_db}
    else:
        merged = set(xl_days)

    ok = db_ok or xl_live

    coverage = None
    candidates: list[date] = []
    if merged:
        candidates.append(max(merged))
    xl_max = excel_coverage_max_date(year) if xl_live else None
    if isinstance(xl_max, date):
        candidates.append(xl_max)
    if candidates:
        coverage = max(candidates)

    return merged, ok, coverage


def fetch_merged_shifts(
    dnis: list[str], start: date, end: date
) -> tuple[dict[str, dict[date, dict]], bool]:
    """Turnos (min/max hora) por DNI. El Excel aporta la hora si la BD solo trae la fecha."""
    db_ok = attendance_configured()
    xl_ok_cfg = excel_attendance_configured()
    db = fetch_attendance_shifts(dnis, start, end) if db_ok else {}
    xl = fetch_excel_shifts(dnis, start, end) if xl_ok_cfg else {}
    max_db = fetch_coverage_max_date() if db_ok else None

    merged: dict[str, dict[date, dict]] = {}
    for dni, days in db.items():
        merged[norm_dni(dni)] = dict(days)
    for dni, days in xl.items():
        bucket = merged.setdefault(norm_dni(dni), {})
        for fecha, row in days.items():
            existing = bucket.get(fecha)
            xl_timed = row.get("entrada") is not None and row.get("salida") is not None
            db_timed = bool(existing) and existing.get("entrada") is not None and existing.get("salida") is not None
            if existing is None:
                if max_db is None or fecha > max_db:
                    bucket[fecha] = row
            elif xl_timed and not db_timed:
                bucket[fecha] = row
    times_ok = any(
        row.get("entrada") is not None
        and row.get("salida") is not None
        and int(row.get("n") or 0) >= 2
        for days in merged.values()
        for row in days.values()
    )
    return merged, times_ok
