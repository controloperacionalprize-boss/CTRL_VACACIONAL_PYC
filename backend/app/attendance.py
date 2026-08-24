"""Une asistencia de BD + Excel SharePoint (Excel completa lo que falte)."""
from __future__ import annotations

from datetime import date

from .attendance_db import attendance_configured, fetch_attendance_dates
from .attendance_excel import (
    excel_attendance_configured,
    excel_attendance_ok,
    excel_coverage_max_date,
    fetch_excel_attendance_dates,
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
