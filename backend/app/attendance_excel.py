"""Excel de asistencia HIK desde SharePoint (MSAL Office + link :x:/s/...)."""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from zoneinfo import ZoneInfo

import msal
import pandas as pd

from .config import get_settings

logger = logging.getLogger(__name__)

_MSAL_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
_MSAL_AUTHORITY = "https://login.microsoftonline.com/common"
_MSAL_SCOPES = ["https://graph.microsoft.com/Files.Read.All"]

# SP_HIK_V2_URL (ScriptVistas / Control Operacional).
DEFAULT_SHARE_URL = (
    "https://aquanqape.sharepoint.com/:x:/s/OficinasPrizePeru/"
    "IQASVoFGz1YGRrZ3y1evRGebAYPOBVtwO-n7iVbrwsbjhow?e=62Iffv"
)

_CACHE_FILE = Path(__file__).resolve().parents[1] / ".msal_attendance_cache.bin"
# El HIK se actualiza de un día para otro: una descarga por día basta.
_FAIL_BACKOFF_SEC = 5 * 60
_LIMA = ZoneInfo("America/Lima")
_LOCK = Lock()
_refreshing = False
_cache: dict = {
    "loaded_at": 0.0,
    "loaded_day": None,
    "by_dni": {},
    "max_date": None,
    "ok": False,
    "error": None,
    "fail_until": 0.0,
}


def _lima_today() -> date:
    return datetime.now(_LIMA).date()


def _cache_is_fresh() -> bool:
    return bool(_cache.get("ok") and _cache.get("loaded_day") == _lima_today())


def _excel_url() -> str:
    s = get_settings()
    return (
        (s.attendance_excel_share_url or "").strip()
        or (s.attendance_excel_sharepoint_url or "").strip()
        or DEFAULT_SHARE_URL
    )


def encode_sharing_url(url: str) -> str:
    b64 = base64.b64encode(url.strip().encode("utf-8")).decode("ascii")
    return "u!" + b64.rstrip("=").replace("/", "_").replace("+", "-")


def _es_link_compartido(url: str) -> bool:
    path = urllib.parse.urlparse(url.strip()).path.lower()
    return any(m in path for m in ("/:x:/", "/:f:/", "/:u:/", "/:b:/", "/:w:/", "/:p:/"))


def extract_refresh_token_from_cache_file(path: Path | None = None) -> str:
    p = path or _CACHE_FILE
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    best = ""
    for entry in (data.get("RefreshToken") or {}).values():
        secret = str((entry or {}).get("secret") or "").strip()
        if len(secret) > len(best):
            best = secret
    return best


def _decode_msal_cache_env(raw: str) -> str:
    text = raw.strip().strip('"').strip("'")
    if text.startswith("{"):
        return text
    try:
        decoded = base64.b64decode(text).decode("utf-8")
        if decoded.lstrip().startswith("{"):
            return decoded
    except Exception:
        pass
    return text

def _load_msal_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    raw = (get_settings().attendance_msal_cache or "").strip()
    if raw:
        try:
            cache.deserialize(_decode_msal_cache_env(raw))
            return cache
        except Exception:
            logger.warning("ATTENDANCE_MSAL_CACHE inválido; intento archivo local.")
    if _CACHE_FILE.exists():
        try:
            cache.deserialize(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return cache


def _save_msal_cache(cache: msal.SerializableTokenCache) -> None:
    if not getattr(cache, "has_state_changed", False):
        return
    try:
        _CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
    except OSError as exc:
        logger.warning("No se pudo guardar caché MSAL: %s", exc)


def msal_cache_configured() -> bool:
    if (get_settings().attendance_excel_refresh_token or "").strip():
        return True
    if (get_settings().attendance_msal_cache or "").strip():
        return True
    return _CACHE_FILE.exists() and _CACHE_FILE.stat().st_size > 20


def excel_attendance_configured() -> bool:
    return msal_cache_configured()


def get_graph_token(*, interactive: bool = False) -> str:
    refresh = (get_settings().attendance_excel_refresh_token or "").strip()
    app = msal.PublicClientApplication(
        client_id=_MSAL_CLIENT_ID,
        authority=_MSAL_AUTHORITY,
        token_cache=_load_msal_cache(),
    )

    # 1) Refresh token (Render / .env)
    if refresh:
        result = app.acquire_token_by_refresh_token(refresh, scopes=_MSAL_SCOPES)
        if result and "access_token" in result:
            _save_msal_cache(app.token_cache)
            return result["access_token"]
        logger.warning(
            "ATTENDANCE_EXCEL_REFRESH_TOKEN no sirvió: %s",
            (result or {}).get("error_description") or (result or {}).get("error"),
        )

    # 2) Caché MSAL local
    accounts = app.get_accounts()
    result = (
        app.acquire_token_silent(_MSAL_SCOPES, account=accounts[0]) if accounts else None
    )
    if result and "access_token" in result:
        _save_msal_cache(app.token_cache)
        return result["access_token"]

    if not interactive:
        raise RuntimeError(
            "No hay token SharePoint. Ejecuta: python scripts/obtener_token_excel_sharepoint.py"
        )

    flow = app.initiate_device_flow(scopes=_MSAL_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"No se pudo iniciar device flow: {flow}")
    print(flow.get("message") or flow)
    result = app.acquire_token_by_device_flow(flow)
    _save_msal_cache(app.token_cache)
    if not result or "access_token" not in result:
        raise RuntimeError(
            f"Error de autenticación: {(result or {}).get('error_description', result)}"
        )
    return result["access_token"]


def _graph_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _graph_download(url: str, token: str | None, *, timeout: int = 180) -> bytes:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_excel_bytes(*, interactive: bool = False) -> bytes:
    url = _excel_url()
    tok = get_graph_token(interactive=interactive)
    if _es_link_compartido(url):
        share_id = encode_sharing_url(url)
        meta = _graph_get(
            f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem",
            tok,
        )
        dl = meta.get("@microsoft.graph.downloadUrl")
        if dl:
            return _graph_download(dl, token=None)
        return _graph_download(
            f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem/content",
            tok,
        )

    # Ruta /sites/.../archivo.xlsx
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.hostname or "aquanqape.sharepoint.com"
    parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
    if len(parts) < 4 or parts[0].lower() != "sites":
        raise ValueError("URL SharePoint no reconocida.")
    site_path = f"/sites/{parts[1]}"
    rel = "/".join(parts[3:])
    site = _graph_get(f"https://graph.microsoft.com/v1.0/sites/{host}:{site_path}", tok)
    site_id = site["id"]
    item_enc = urllib.parse.quote(rel)
    meta = _graph_get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{item_enc}",
        tok,
    )
    dl = meta.get("@microsoft.graph.downloadUrl")
    if dl:
        return _graph_download(dl, token=None)
    return _graph_download(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{item_enc}:/content",
        tok,
    )


def _norm_col(name: object) -> str:
    return str(name or "").strip().lower().replace(".", "").replace("_", " ")


def _pick_col(columns: list, candidates: tuple[str, ...]) -> str | None:
    norms = {_norm_col(c): c for c in columns}
    for cand in candidates:
        if cand in norms:
            return norms[cand]
    for norm, original in norms.items():
        for cand in candidates:
            if cand in norm:
                return original
    return None


def _to_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    for dayfirst in (True, False):
        try:
            return pd.to_datetime(text, dayfirst=dayfirst).date()
        except Exception:
            continue
    return None


def _to_dni(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    return text


def parse_attendance_excel(
    content: bytes, *, after: date | None = None
) -> tuple[dict[str, set[date]], date | None]:
    """Lee el Excel y se queda solo con fechas posteriores a `after` (hueco vs BD)."""
    by_dni: dict[str, set[date]] = {}
    max_date: date | None = None
    xl = pd.ExcelFile(BytesIO(content))
    for sheet in xl.sheet_names:
        try:
            df = pd.read_excel(xl, sheet_name=sheet)
        except Exception:
            logger.exception("Excel asistencia: hoja %s", sheet)
            continue
        if df.empty:
            continue
        cols = list(df.columns)
        dni_col = _pick_col(cols, ("documento", "dni", "id", "codigo", "código"))
        fecha_col = _pick_col(cols, ("fecha", "fecha marcacion", "fecha marcación", "dia", "día"))
        if not dni_col or not fecha_col:
            continue
        dnis = df[dni_col].map(_to_dni)
        fechas = pd.to_datetime(df[fecha_col], dayfirst=True, errors="coerce")
        mask = dnis.ne("") & fechas.notna()
        if after is not None:
            cutoff = pd.Timestamp(after)
            mask &= fechas.dt.normalize() > cutoff
        if not mask.any():
            continue
        for dni, ts in zip(dnis[mask].tolist(), fechas[mask].tolist()):
            fecha = ts.date() if hasattr(ts, "date") else _to_date(ts)
            if not dni or not fecha:
                continue
            by_dni.setdefault(str(dni), set()).add(fecha)
            if max_date is None or fecha > max_date:
                max_date = fecha
    return by_dni, max_date


def _snapshot() -> dict:
    with _LOCK:
        return {
            "ok": bool(_cache.get("ok")),
            "by_dni": _cache.get("by_dni") or {},
            "max_date": _cache.get("max_date"),
            "loaded_day": _cache.get("loaded_day"),
            "error": _cache.get("error"),
        }


def _store_cache(by_dni: dict, max_date: date | None, error: str | None = None) -> None:
    with _LOCK:
        _cache.update(
            {
                "loaded_at": time.time(),
                "loaded_day": _lima_today(),
                "by_dni": by_dni,
                "max_date": max_date,
                "ok": True,
                "error": error,
                "fail_until": 0.0,
            }
        )


def _refresh_worker() -> None:
    global _refreshing
    try:
        if not excel_attendance_configured():
            with _LOCK:
                _cache.update(
                    {
                        "ok": False,
                        "by_dni": {},
                        "max_date": None,
                        "error": "sin caché MSAL",
                    }
                )
            return
        from .attendance_db import attendance_configured, fetch_coverage_max_date

        after = fetch_coverage_max_date() if attendance_configured() else None
        today = _lima_today()
        if after is not None and after >= today:
            _store_cache({}, after)
            logger.info("BD de asistencia al día (%s); no se descarga el Excel.", after)
            return
        raw = download_excel_bytes(interactive=False)
        by_dni, max_date = parse_attendance_excel(raw, after=after)
        if max_date is None and after is not None:
            max_date = after
        _store_cache(by_dni, max_date)
        logger.info(
            "Excel asistencia: hueco desde %s → %s DNIs, última fecha %s (1 vez/día Lima).",
            after.isoformat() if after else "el inicio",
            len(by_dni),
            max_date,
        )
    except Exception as exc:
        logger.exception("Excel asistencia SharePoint: %s", exc)
        with _LOCK:
            # Conserva la última descarga buena; no borra datos por un fallo puntual.
            _cache["error"] = str(exc)
            _cache["fail_until"] = time.time() + _FAIL_BACKOFF_SEC
            if not _cache.get("ok"):
                _cache.update({"by_dni": {}, "max_date": None})
    finally:
        with _LOCK:
            _refreshing = False


def schedule_excel_refresh(*, force: bool = False) -> None:
    """Arranca una descarga en segundo plano. Nunca bloquea al caller."""
    global _refreshing
    with _LOCK:
        if _refreshing:
            return
        if not force and _cache_is_fresh():
            return
        if not force and float(_cache.get("fail_until") or 0) > time.time():
            return
        _refreshing = True
    Thread(target=_refresh_worker, name="excel-asistencia", daemon=True).start()


def warmup_excel_cache() -> None:
    """Al arrancar o al iniciar sesión: una descarga si aún no hay datos de hoy."""
    if excel_attendance_configured():
        schedule_excel_refresh()


def fetch_excel_attendance_dates(dni: str, year: int) -> set[date]:
    snap = _snapshot()
    if not snap.get("ok") or snap.get("loaded_day") != _lima_today():
        schedule_excel_refresh()
    if not snap.get("ok"):
        return set()
    days = snap["by_dni"].get(str(dni).strip(), set())
    return {d for d in days if d.year == year}


def excel_coverage_max_date(year: int | None = None) -> date | None:
    snap = _snapshot()
    if not snap.get("ok"):
        schedule_excel_refresh()
        return None
    if snap.get("loaded_day") != _lima_today():
        schedule_excel_refresh()
    mx = snap.get("max_date")
    if not isinstance(mx, date):
        return None
    if year is not None and mx.year != year:
        best: date | None = None
        for days in snap.get("by_dni", {}).values():
            for d in days:
                if d.year == year and (best is None or d > best):
                    best = d
        return best
    return mx


def excel_attendance_ok() -> bool:
    if not excel_attendance_configured():
        return False
    snap = _snapshot()
    if not snap.get("ok") or snap.get("loaded_day") != _lima_today():
        schedule_excel_refresh()
    return bool(snap.get("ok"))
