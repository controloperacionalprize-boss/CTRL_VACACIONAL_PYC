"""Vigencia y fecha de cese desde el maestro de trabajadores."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .calendar import parse_iso_date
from .excel_norm import is_worker_vigente, normalize_workers, read_master_and_cronograma

ROOT = Path(__file__).resolve().parents[3]
_CACHE: dict = {"mtime": None, "by_dni": {}}


def _norm_dni(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def load_master_vigencia() -> dict[str, dict]:
    path = ROOT / "trabajadores.xlsx"
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _CACHE["mtime"] == mtime and _CACHE["by_dni"]:
        return _CACHE["by_dni"]
    master, _crono, _rec = read_master_and_cronograma(path)
    workers = normalize_workers(master)
    by_dni: dict[str, dict] = {}
    for _, row in workers.iterrows():
        dni = _norm_dni(row.get("DNI"))
        if not dni:
            continue
        cese = row.get("FECHA_CESE")
        if pd.isna(cese):
            cese_iso = None
        elif isinstance(cese, date):
            cese_iso = cese.isoformat()
        else:
            parsed = parse_iso_date(cese)
            cese_iso = parsed.isoformat() if isinstance(parsed, date) else None
        vigencia = str(row.get("VIGENCIA") or "").strip()
        if not vigencia and cese_iso is None:
            continue
        by_dni[dni] = {
            "vigencia": vigencia,
            "fecha_cese": cese_iso,
            "activo": is_worker_vigente(vigencia) and (
                cese_iso is None or parse_iso_date(cese_iso) >= date.today()
            ),
        }
    _CACHE["mtime"] = mtime
    _CACHE["by_dni"] = by_dni
    return by_dni


def apply_master_vigencia(employees: list[dict]) -> list[dict]:
    extra = load_master_vigencia()
    if not extra:
        return employees
    out = []
    for emp in employees:
        info = extra.get(_norm_dni(emp.get("dni")))
        if not info:
            out.append(emp)
            continue
        merged = dict(emp)
        if info.get("vigencia"):
            merged["vigencia"] = info["vigencia"]
        if info.get("fecha_cese"):
            merged["fecha_cese"] = info["fecha_cese"]
        out.append(merged)
    return out


def cuenta_asistencia_el_dia(emp: dict, d: date) -> bool:
    if emp.get("activo") is False and not emp.get("fecha_cese"):
        return False
    f_ingreso = parse_iso_date(emp.get("fecha_ingreso"))
    if isinstance(f_ingreso, date) and d < f_ingreso:
        return False
    cese = parse_iso_date(emp.get("fecha_cese"))
    if isinstance(cese, date) and d > cese:
        return False
    if not is_worker_vigente(emp.get("vigencia")) and not isinstance(cese, date):
        return False
    return True


def vigente_en_periodo(emp: dict, start: date, end: date) -> bool:
    d = start
    while d <= end:
        if d.weekday() < 5 and cuenta_asistencia_el_dia(emp, d):
            return True
        d += timedelta(days=1)
    return False
