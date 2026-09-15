"""Maestro de trabajadores en AWS (`qbiz_funcionarios_raw`), misma BD que la marcación."""
from __future__ import annotations

import logging
import time
from typing import Any

from .attendance_db import attendance_configured, _conn
from .textnorm import strip_marks

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "rows": [], "loaded": False}
_TTL_SEC = 15 * 60
# Si AWS no responde, no reintentar en cada request (cada intento abre conexión y cuesta CPU).
_FAIL_TTL_SEC = 5 * 60


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


def _emails(payload: dict) -> tuple[str, str]:
    """(corporativo, personal) desde las columnas de correo que traiga QBiz, se llamen como se llamen."""
    corporativo = personal = ""
    for key, val in payload.items():
        name = strip_marks(str(key)).upper()
        if "CORREO" not in name and "EMAIL" not in name and "MAIL" not in name:
            continue
        text = str(val or "").strip()
        if "@" not in text or text.lower() == "nan":
            continue
        if "PERSONAL" in name:
            personal = personal or text
        else:
            corporativo = corporativo or text
    return corporativo, personal


def load_funcionarios_org(*, force: bool = False) -> list[dict[str, str]]:
    """Lista {dni, area, division, correo, correo_personal} desde QBiz. Vacío si no hay tabla o AWS."""
    now = time.monotonic()
    ttl = _TTL_SEC if _CACHE["rows"] else _FAIL_TTL_SEC
    if not force and _CACHE["loaded"] and now - _CACHE["at"] < ttl:
        return _CACHE["rows"]
    if not attendance_configured():
        return []
    sql = "SELECT payload FROM qbiz_funcionarios_raw"
    try:
        with _conn() as conn:
            if conn is None:
                raw_rows = []
            else:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    raw_rows = cur.fetchall()
    except Exception:
        logger.info("Maestro AWS: no se pudo leer qbiz_funcionarios_raw (se usa solo Neon).")
        raw_rows = []

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
        correo, correo_personal = _emails(payload)
        seen.add(dni)
        out.append({
            "dni": dni,
            "area": area,
            "division": division,
            "correo": correo,
            "correo_personal": correo_personal,
        })
    _CACHE["at"] = now
    _CACHE["rows"] = out
    _CACHE["loaded"] = True
    _CACHE["version"] = int(_CACHE.get("version") or 0) + 1
    return out


def maestro_version() -> int:
    """Cambia cada vez que se recarga el maestro (sirve de clave para cachés derivadas)."""
    return int(_CACHE.get("version") or 0)
