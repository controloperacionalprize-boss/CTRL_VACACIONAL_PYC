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
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
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


def _conn_open(conn) -> bool:
    return conn is not None and getattr(conn, "closed", 1) == 0


def _safe_rollback(conn) -> None:
    if not _conn_open(conn):
        return
    try:
        conn.rollback()
    except Exception:
        return


def _conn_alive(conn) -> bool:
    if not _conn_open(conn):
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except Exception:
        _safe_rollback(conn)
        return False


def _checkout():
    pool = get_pool()
    last_error: Exception | None = None
    for _ in range(2):
        try:
            conn = pool.getconn()
        except PoolError as exc:
            raise HTTPException(
                503, "El servidor está muy ocupado en este momento. Intenta de nuevo en unos segundos."
            ) from exc
        if _conn_alive(conn):
            return pool, conn
        last_error = psycopg2.InterfaceError("la conexión del pool ya no responde")
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
    raise HTTPException(503, "No hay conexión con la base de datos. Intenta de nuevo.") from last_error


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


def ensure_scope_columns() -> None:
    """Columnas y tablas nuevas en bases ya existentes."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS area TEXT NOT NULL DEFAULT ''"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_flujo (
                anio INTEGER NOT NULL,
                dni TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'BORRADOR',
                apto BOOLEAN NOT NULL DEFAULT FALSE,
                cumple_record DATE,
                jefe_correo TEXT NOT NULL DEFAULT '',
                enviado_at TIMESTAMPTZ,
                gerente_correo TEXT NOT NULL DEFAULT '',
                validado_at TIMESTAMPTZ,
                admin_correo TEXT NOT NULL DEFAULT '',
                recepcionado_at TIMESTAMPTZ,
                observacion TEXT NOT NULL DEFAULT '',
                actualizado TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (anio, dni)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_flujo_estado ON plan_flujo (anio, estado)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_documento_emision (
                anio INTEGER NOT NULL,
                dni TEXT NOT NULL,
                escenario INTEGER NOT NULL,
                plan_hash TEXT NOT NULL DEFAULT '',
                descargas INTEGER NOT NULL DEFAULT 0,
                descargado_at TIMESTAMPTZ,
                descargado_por TEXT NOT NULL DEFAULT '',
                descargado_nombre TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (anio, dni)
            )
            """
        )


@contextmanager
def get_conn(*, write: bool = True):
    pool, conn = _checkout()
    try:
        yield conn
        if write:
            conn.commit()
        else:
            _safe_rollback(conn)
    except Exception:
        _safe_rollback(conn)
        raise
    finally:
        try:
            pool.putconn(conn, close=not _conn_open(conn))
        except Exception:
            pass


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
