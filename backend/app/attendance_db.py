from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from datetime import date, datetime, time
from urllib.parse import quote, urlparse, urlunparse

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

_pool: SimpleConnectionPool | None = None
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IDENT_SPACES = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_ .º°\-]+$")
_PLACEHOLDER = ("USUARIO", "PASSWORD", "NOMBRE_BD")


def _quote_col(name: str) -> str:
    n = (name or "").strip()
    if not _IDENT_SPACES.match(n):
        raise ValueError(f"Identificador SQL inválido: {name!r}")
    return '"' + n.replace('"', "") + '"'


def _safe_ident(name: str, fallback: str) -> str:
    n = (name or fallback).strip()
    if not _IDENT.match(n):
        raise ValueError(f"Identificador SQL inválido: {name!r}")
    return n


def _encode_db_url(url: str) -> str:
    """Re-encodea user/password por si tienen *, @, #, etc."""
    parsed = urlparse(url.strip())
    if not parsed.scheme.startswith("postgres") or parsed.username is None:
        return url.strip()
    user = quote(parsed.username, safe="")
    password = quote(parsed.password or "", safe="")
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:{password}@{host}{port}" if password else f"{user}@{host}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def attendance_configured() -> bool:
    url = (get_settings().attendance_database_url or "").strip()
    if not url or any(p in url for p in _PLACEHOLDER):
        return False
    return url.startswith(("postgresql://", "postgres://"))


def close_attendance_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def _pool_or_none() -> SimpleConnectionPool | None:
    global _pool
    if not attendance_configured():
        return None
    if _pool is None:
        dsn = _encode_db_url(get_settings().attendance_database_url)
        _pool = SimpleConnectionPool(
            1,
            5,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
    return _pool


@contextmanager
def _conn():
    pool = _pool_or_none()
    if pool is None:
        yield None
        return
    conn = pool.getconn()
    try:
        yield conn
        conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def fetch_attendance_dates(dni: str, year: int) -> set[date]:
    if not attendance_configured():
        return set()
    s = get_settings()
    try:
        schema = _safe_ident(s.attendance_schema, "public")
        table = _safe_ident(s.attendance_table, "marcaciones")
        dni_col = _safe_ident(s.attendance_dni_column, "dni")
        date_col = _safe_ident(s.attendance_date_column, "fecha")
    except ValueError as exc:
        logger.warning("%s", exc)
        return set()

    sql = (
        f'SELECT DISTINCT "{date_col}"::date AS fecha '
        f'FROM "{schema}"."{table}" '
        f'WHERE CAST("{dni_col}" AS text) = %s '
        f'AND "{date_col}"::date >= %s AND "{date_col}"::date < %s'
    )
    try:
        with _conn() as conn:
            if conn is None:
                return set()
            with conn.cursor() as cur:
                cur.execute(sql, (str(dni).strip(), date(year, 1, 1), date(year + 1, 1, 1)))
                return {
                    r["fecha"]
                    for r in cur.fetchall()
                    if isinstance(r.get("fecha"), date)
                }
    except Exception:
        logger.exception("Asistencia: fallo leyendo DNI=%s anio=%s", dni, year)
        return set()


def fetch_coverage_max_date() -> date | None:
    """Última fecha de marcación en la BD (todas las personas). None si no hay datos."""
    if not attendance_configured():
        return None
    s = get_settings()
    try:
        schema = _safe_ident(s.attendance_schema, "public")
        table = _safe_ident(s.attendance_table, "marcaciones")
        date_col = _safe_ident(s.attendance_date_column, "fecha")
    except ValueError as exc:
        logger.warning("%s", exc)
        return None
    sql = f'SELECT MAX("{date_col}"::date) AS fecha FROM "{schema}"."{table}"'
    try:
        with _conn() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone() or {}
                fecha = row.get("fecha")
                return fecha if isinstance(fecha, date) else None
    except Exception:
        logger.exception("Asistencia: no se pudo leer la fecha máxima de la BD")
        return None


def _as_time(value: object) -> time | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        if value.hour == 0 and value.minute == 0:
            return None
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text[:8] if fmt.endswith("%S") else text[:5], fmt).time()
            if parsed.hour == 0 and parsed.minute == 0:
                return None
            return parsed
        except ValueError:
            continue
    return None


def fetch_attendance_shifts(
    dnis: list[str], start: date, end: date
) -> dict[str, dict[date, dict]]:
    """Min/max de Tiempo por DNI y fecha. Vacío si no hay columna de hora o no hay datos."""
    if not attendance_configured() or not dnis or start > end:
        return {}
    s = get_settings()
    try:
        schema = _safe_ident(s.attendance_schema, "public")
        table = _safe_ident(s.attendance_table, "marcaciones")
        dni_col = _safe_ident(s.attendance_dni_column, "dni")
        date_col = _safe_ident(s.attendance_date_column, "fecha")
        time_col = _safe_ident(s.attendance_time_column, "Tiempo")
        device_col = _quote_col("Nombre del dispositivo")
    except ValueError as exc:
        logger.warning("%s", exc)
        return {}

    sql = (
        f'SELECT CAST("{dni_col}" AS text) AS dni, "{date_col}"::date AS fecha, '
        f'MIN("{time_col}") FILTER (WHERE "{time_col}" IS NOT NULL AND "{time_col}" > TIME \'00:00:00\') AS entrada, '
        f'MAX("{time_col}") FILTER (WHERE "{time_col}" IS NOT NULL AND "{time_col}" > TIME \'00:00:00\') AS salida, '
        f'COUNT(*) FILTER (WHERE "{time_col}" IS NOT NULL AND "{time_col}" > TIME \'00:00:00\') AS n, '
        f'COUNT(*) AS n_rows, '
        f'(ARRAY_AGG({device_col}) FILTER (WHERE {device_col} IS NOT NULL))[1] AS dispositivo '
        f'FROM "{schema}"."{table}" '
        f'WHERE CAST("{dni_col}" AS text) = ANY(%s) '
        f'AND "{date_col}"::date >= %s AND "{date_col}"::date <= %s '
        f'GROUP BY 1, 2'
    )
    out: dict[str, dict[date, dict]] = {}
    try:
        with _conn() as conn:
            if conn is None:
                return {}
            with conn.cursor() as cur:
                cur.execute(sql, ([str(x).strip() for x in dnis], start, end))
                for r in cur.fetchall():
                    dni = str(r.get("dni") or "").strip()
                    fecha = r.get("fecha")
                    if not dni or not isinstance(fecha, date):
                        continue
                    n = int(r.get("n") or 0)
                    n_rows = int(r.get("n_rows") or 0)
                    out.setdefault(dni, {})[fecha] = {
                        "entrada": _as_time(r.get("entrada")),
                        "salida": _as_time(r.get("salida")),
                        "n": n,
                        "n_rows": n_rows,
                        "dispositivo": str(r.get("dispositivo") or "").strip(),
                    }
    except Exception:
        logger.exception("Asistencia: no se pudieron leer horas %s–%s", start, end)
        return {}
    return out
