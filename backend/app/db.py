from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException
import psycopg2
import psycopg2.extras
from psycopg2.pool import PoolError, SimpleConnectionPool

from .config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
_pool: SimpleConnectionPool | None = None

# Conexiones máximas simultáneas hacia la base de datos. Súbelo si el número
# de personas usando la app a la vez crece bastante (y si el plan de Neon lo soporta).
POOL_MIN = 1
POOL_MAX = 20


def _make_pool(url: str) -> SimpleConnectionPool:
    return SimpleConnectionPool(
        POOL_MIN,
        POOL_MAX,
        dsn=url,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,
    )


def get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        url = get_settings().database_url
        try:
            _pool = _make_pool(url)
        except Exception:
            fallback = url.replace("&channel_binding=require", "").replace(
                "channel_binding=require&", ""
            )
            if fallback == url:
                raise
            _pool = _make_pool(fallback)
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def init_schema(conn=None):
    """Solo para instalaciones nuevas. La API no lo ejecuta al arrancar."""
    own = conn is None
    if own:
        conn = get_pool().getconn()
    try:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        if own:
            get_pool().putconn(conn)


@contextmanager
def get_conn(*, write: bool = True):
    pool = get_pool()
    try:
        conn = pool.getconn()
    except PoolError as exc:
        raise HTTPException(
            503, "El servidor está muy ocupado en este momento. Intenta de nuevo en unos segundos."
        ) from exc
    try:
        yield conn
        if write:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_connection() -> bool:
    """Usado por /api/health para confirmar que la base de datos responde."""
    try:
        with get_conn(write=False) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
