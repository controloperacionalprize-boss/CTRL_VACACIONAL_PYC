"""Maestro de trabajadores en AWS (`qbiz_funcionarios_raw`), misma BD que la marcación."""
from __future__ import annotations

import logging
import time
from typing import Any

from .attendance_db import attendance_configured, _conn

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "rows": []}
_TTL_SEC = 15 * 60


def _cell(payload: dict, *keys: str) -> str:
    for key in keys:
        val = payload.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s and s.lower() != "nan":
            return s
    return ""


def _norm_dni(value: str) -> str:
    text = (value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def load_funcionarios_org(*, force: bool = False) -> list[dict[str, str]]:
    """Lista {dni, area, division} desde QBiz. Vacío si no hay tabla o AWS."""
    now = time.monotonic()
    if not force and _CACHE["rows"] and now - _CACHE["at"] < _TTL_SEC:
        return _CACHE["rows"]
    if not attendance_configured():
        return []
    sql = "SELECT payload FROM qbiz_funcionarios_raw"
    try:
        with _conn() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute(sql)
                raw_rows = cur.fetchall()
    except Exception:
        logger.info("Maestro AWS: no se pudo leer qbiz_funcionarios_raw (se usa solo Neon).")
        return []

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in raw_rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            continue
        dni = _norm_dni(_cell(payload, "DNI", "dni", "Cod_Funcionario", "COD_FUNCIONARIO"))
        if not dni or dni in seen:
            continue
        area = _cell(payload, "ÁREA", "AREA", "Area")
        division = _cell(payload, "DIVISIÓN", "DIVISION", "Division")
        seen.add(dni)
        out.append({"dni": dni, "area": area, "division": division})
    _CACHE["at"] = now
    _CACHE["rows"] = out
    return out
