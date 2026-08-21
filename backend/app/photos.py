"""Fotos de personal desde el repo público CCozd/PICTURES.

Prioridad de match:
1) usuario del correo en personal_roster.json (ej. eabanto@… → eabanto.jpg)
2) fallback: inicial + apellido (slug) por si el roster no tiene a la persona
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

from .config import get_settings

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_CACHE: tuple[float, dict[str, str]] | None = None
_CACHE_TTL = 3600
_PARTICULAS = {"de", "del", "la", "las", "los", "y", "e", "da", "do", "das", "dos"}
_ROSTER_PATH = Path(__file__).resolve().parent / "data" / "personal_roster.json"


def _strip_accents(s: str) -> str:
    nk = unicodedata.normalize("NFD", s)
    return "".join(c for c in nk if unicodedata.category(c) != "Mn")


def normalize_token(s: str) -> str:
    s = _strip_accents((s or "").strip().lower())
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def name_tokens(nombre: str) -> list[str]:
    raw = re.split(r"[\s,]+", (nombre or "").strip())
    out: list[str] = []
    for p in raw:
        t = normalize_token(p)
        if t and t not in _PARTICULAS:
            out.append(t)
    return out


def name_token_set(nombre: str) -> frozenset[str]:
    """Clave estable para cruzar 'Vera, Luis Yoshi' ↔ 'VERA PEREZ LUIS YOSHI'."""
    return frozenset(name_tokens(nombre))


def slug_candidates(nombre: str) -> list[str]:
    """Fallback: inicial(nombre) + apellido (orden occidental o PE)."""
    parts = name_tokens(nombre)
    if not parts:
        return []
    if len(parts) == 1:
        return [parts[0]]

    cands: list[str] = []

    def add(slug: str) -> None:
        if slug and slug not in cands:
            cands.append(slug)

    a, b = parts[0], parts[1]
    add(a[0] + b)
    add(b[0] + a)

    if len(parts) >= 3:
        ap1, ap2 = parts[0], parts[1]
        for nom in parts[2:]:
            add(nom[0] + ap1)
            add(nom[0] + ap2)
        add(parts[0][0] + parts[-1])
        add(parts[0][0] + parts[-2])

    return cands


def usuario_from_email(email: str | None) -> str | None:
    """Parte local del correo en minúsculas (antes de @)."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return None
    local = e.split("@", 1)[0].strip()
    return local or None


@lru_cache(maxsize=1)
def load_roster() -> list[dict]:
    if not _ROSTER_PATH.is_file():
        return []
    try:
        data = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def roster_by_name_tokens() -> dict[frozenset[str], str]:
    """tokens(nombre) → usuario de correo (prioriza @aquanqa / corporativo)."""
    ranked: dict[frozenset[str], tuple[int, str]] = {}
    for row in load_roster():
        usuario = row.get("usuario") or usuario_from_email(row.get("email"))
        if not usuario:
            continue
        key = name_token_set(str(row.get("nombre") or ""))
        if not key:
            continue
        email = str(row.get("email") or "").lower()
        # Preferir cuentas corporativas sobre gmail/hotmail al haber colisión de nombre.
        score = 2 if any(d in email for d in ("aquanqa", "prize.cl", "onmicrosoft")) else 1
        prev = ranked.get(key)
        if prev is None or score > prev[0]:
            ranked[key] = (score, usuario.lower())
    return {k: v for k, (_s, v) in ranked.items()}


def usuario_for_nombre(nombre: str | None) -> str | None:
    """Resuelve usuario de foto vía roster JSON (match por tokens de nombre)."""
    if not nombre:
        return None
    key = name_token_set(nombre)
    if not key:
        return None
    by_name = roster_by_name_tokens()
    if key in by_name:
        return by_name[key]
    # Subconjunto: DB con más apellidos que el roster (o al revés).
    best: tuple[int, str] | None = None
    for roster_key, usuario in by_name.items():
        inter = len(key & roster_key)
        if inter < 2:
            continue
        # Exigir que casi todos los tokens del más corto estén contenidos.
        shorter = min(len(key), len(roster_key))
        if inter < shorter:
            continue
        if best is None or inter > best[0]:
            best = (inter, usuario)
    return best[1] if best else None


def _fetch_index() -> dict[str, str]:
    """stem lowercase → filename en el repo."""
    settings = get_settings()
    if not settings.pictures_enabled:
        return {}
    repo = (settings.pictures_repo or "").strip()
    if not repo:
        return {}
    url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "CtrlVacacionesPC"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return {}

    index: dict[str, str] = {}
    for item in data.get("tree") or []:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if "/" in path:
            continue
        lower = path.lower()
        if "." not in lower:
            continue
        stem, ext = lower.rsplit(".", 1)
        if f".{ext}" not in _IMG_EXT or not stem:
            continue
        index[stem] = path
    return index


def picture_index(*, force: bool = False) -> dict[str, str]:
    global _CACHE
    now = time.monotonic()
    if not force and _CACHE and (now - _CACHE[0]) < _CACHE_TTL:
        return _CACHE[1]
    idx = _fetch_index()
    if idx or force or _CACHE is None:
        _CACHE = (now, idx)
        return idx
    return _CACHE[1] if _CACHE else {}


def _url_for_stem(stem: str, index: dict[str, str], base: str) -> str | None:
    if stem in index:
        return f"{base}/{index[stem]}"
    close = get_close_matches(stem, list(index.keys()), n=3, cutoff=0.88)
    for cand in close:
        if cand and stem and cand[0] == stem[0]:
            return f"{base}/{index[cand]}"
    return None


def resolve_foto_url(nombre: str | None) -> str | None:
    """URL raw de GitHub o None si no hay match / fotos pausadas."""
    settings = get_settings()
    if not settings.pictures_enabled:
        return None
    base = (settings.pictures_base_url or "").rstrip("/")
    if not base or not nombre:
        return None

    index = picture_index()
    if not index:
        return None

    # 1) Match preciso: usuario del correo en el roster JSON.
    usuario = usuario_for_nombre(nombre)
    if usuario:
        hit = _url_for_stem(usuario, index, base)
        if hit:
            return hit

    # 2) Fallback histórico: inicial + apellido.
    for slug in slug_candidates(nombre):
        hit = _url_for_stem(slug, index, base)
        if hit:
            return hit

    return None


def enrich_employee_photo(emp: dict) -> dict:
    if not emp.get("foto_url"):
        emp = {**emp, "foto_url": resolve_foto_url(emp.get("nombre"))}
    return emp


def coverage_report(nombres: list[str]) -> dict:
    """Cuántos nombres empatan con una foto (para revisar typos / sin roster)."""
    matched = []
    missing = []
    for n in nombres:
        url = resolve_foto_url(n)
        usuario = usuario_for_nombre(n)
        if url:
            matched.append({"nombre": n, "usuario": usuario, "foto_url": url})
        else:
            missing.append({
                "nombre": n,
                "usuario": usuario,
                "slugs": slug_candidates(n),
            })
    return {
        "total": len(nombres),
        "con_foto": len(matched),
        "sin_foto": len(missing),
        "matched": matched,
        "missing": missing,
        "archivos_en_repo": len(picture_index()),
        "roster_size": len(load_roster()),
    }
