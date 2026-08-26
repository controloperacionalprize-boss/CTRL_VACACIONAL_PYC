"""Genera ATTENDANCE_EXCEL_REFRESH_TOKEN (MFA) y lo escribe en .env.

  cd backend
  python scripts/obtener_token_excel_sharepoint.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.attendance_excel import (  # noqa: E402
    _CACHE_FILE,
    download_excel_bytes,
    extract_refresh_token_from_cache_file,
    get_graph_token,
    parse_attendance_excel,
)
from app.config import get_settings  # noqa: E402


def _try_copy_sibling_cache() -> bool:
    sibling = (
        Path(__file__).resolve().parents[3]
        / "ScriptVistasPython"
        / ".msal_token_cache.bin"
    )
    if not sibling.exists():
        return False
    _CACHE_FILE.write_text(sibling.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Cache ScriptVistas reutilizada -> {_CACHE_FILE}")
    return True


def _upsert_env(key: str, value: str) -> None:
    env_path = ROOT.parent / ".env"
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    text = env_path.read_text(encoding="utf-8")
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", line, text, count=1, flags=re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    text = re.sub(r"^ATTENDANCE_MSAL_CACHE=.*$\n?", "", text, flags=re.M)
    env_path.write_text(text, encoding="utf-8")


def main() -> int:
    s = get_settings()
    url = (
        (s.attendance_excel_share_url or "").strip()
        or (s.attendance_excel_sharepoint_url or "").strip()
        or "(default HIK V2)"
    )
    print(f"Excel: {url}")

    if not _CACHE_FILE.exists() or _CACHE_FILE.stat().st_size < 20:
        if _try_copy_sibling_cache():
            try:
                get_graph_token(interactive=False)
            except Exception:
                get_graph_token(interactive=True)
        else:
            get_graph_token(interactive=True)
    else:
        try:
            get_graph_token(interactive=False)
        except Exception:
            get_graph_token(interactive=True)

    refresh = extract_refresh_token_from_cache_file()
    if not refresh:
        print("ERROR: no hay RefreshToken en la cache MSAL.")
        return 1

    _upsert_env("ATTENDANCE_EXCEL_REFRESH_TOKEN", refresh)
    print(f"ATTENDANCE_EXCEL_REFRESH_TOKEN en .env ({len(refresh)} chars).")

    get_settings.cache_clear()
    raw = download_excel_bytes(interactive=False)
    by_dni, max_date, _shifts = parse_attendance_excel(raw)
    print(f"OK: {len(by_dni)} DNIs, ultima fecha {max_date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
