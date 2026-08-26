"""Normalización de texto compartida (fotos, empresas, nombres)."""

from __future__ import annotations

import unicodedata


def strip_marks(value: str) -> str:
    nk = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in nk if not unicodedata.combining(c))
