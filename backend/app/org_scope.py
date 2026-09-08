"""Alcance de visibilidad: gerente → división, jefe → área.

El catálogo área → división es el mismo que en tracking (códigos Neon).
Las etiquetas libres del maestro (Excel / QBiz) se normalizan a ese catálogo.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .textnorm import strip_marks

ROLES = {"ADMIN", "GERENTE", "JEFE", "USER"}
_ROLE_GERENTE = frozenset({"GERENTE", "USER"})


def fold_label(valor: str | None) -> str:
    s = strip_marks(valor or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fold_list(*labels: str) -> list[str]:
    out: set[str] = set()
    for raw in labels:
        key = fold_label(raw)
        if key:
            out.add(key.lower())
    return sorted(out)


def sql_fold_expr(col: str) -> str:
    """Equivalente SQL de fold_label (minúsculas, sin tildes ni puntuación)."""
    if col not in {"division", "gerencia", "area", "jefatura", "empresa"}:
        raise ValueError(f"Columna no permitida: {col}")
    return (
        "trim(regexp_replace(translate(lower(" + col + "), "
        "'áéíóúüñäëïöüàèìòù','aeiouunaeiouaeiou'), "
        "'[^a-z0-9]+', ' ', 'g'))"
    )


def _norm_dni(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


# Código de área (tracking) → división canónica.
CODIGO_TO_DIVISION: dict[str, str] = {
    "RS": "Personas y Cultura",
    "AD": "Personas y Cultura",
    "BS": "Personas y Cultura",
    "SM": "Personas y Cultura",
    "SO": "Personas y Cultura",
    "SP": "Corporativa",
    "CX": "Corporativa",
    "CT": "Corporativa",
    "CB": "Administración y Finanzas",
    "TS": "Administración y Finanzas",
    "AL": "Administración y Finanzas",
    "CM": "Administración y Finanzas",
    "TR": "Administración y Finanzas",
    "CG": "Administración y Finanzas",
    "TI": "Planificación",
    "CO": "Planificación",
    "IS": "Industrial",
    "PC": "Industrial",
    "AI": "Industrial",
    "PY": "Industrial",
    "MN": "Industrial",
    "PD": "Industrial",
    "AP": "Industrial",
    "RC": "Industrial",
    "FD": "Industrial",
    "CP": "Industrial",
    "GS": "Industrial",
    "GI": "Industrial",
    "MP": "Industrial",
    "CS": "Cosecha y Operaciones",
    "PR": "Cosecha y Operaciones",
    "MC": "Cosecha y Operaciones",
    "MO": "Cosecha y Operaciones",
    "ME": "Cosecha y Operaciones",
    "MM": "Cosecha y Operaciones",
    "CC": "Cosecha y Operaciones",
    "PI": "Cosecha y Operaciones",
    "GC": "Cosecha y Operaciones",
    "FS": "Agrícola",
    "PA": "Agrícola",
    "FN": "Agrícola",
    "GA": "Agrícola",
}

# Etiqueta libre (Excel / QBiz / roster) → código de área.
AREA_TO_CODIGO: dict[str, str] = {
    "COMPRAS": "CM",
    "CONTABILIDAD": "CB",
    "ALMACEN": "AL",
    "CONTROL DE GESTION": "CG",
    "MANTENIMIENTO INDUSTRIAL": "MN",
    "FITOSANIDAD": "FS",
    "TESORERIA": "TS",
    "SEGURIDAD PATRIMONIAL": "SP",
    "FRIO Y DESPACHO": "FD",
    "COMERCIO EXTERIOR": "CX",
    "RECEPCION": "RC",
    "CERTIFICACIONES": "CT",
    "COSECHA": "CS",
    "PRODUCCION AGRICOLA": "PA",
    "FERTIRRIEGO Y NUTRICION": "FN",
    "FERTIRIEGO": "FN",
    "PROYECCIONES": "PR",
    "PROYECTOS INDUSTRIAL": "PY",
    "PROYECTOS INDUSTRIALES": "PY",
    "MANTENIMIENTO HIDRAULICO": "MO",
    "MANTENIMIENTO HIDRAULICO Y OSMOSIS": "MO",
    "MANTENIMIENTO Y OSMOSIS": "MO",
    "TECNOLOGIA DE LA INFORMACION": "TI",
    "TECNOLOGIA DE LA INFORMACION Y SISTEMAS": "TI",
    "TEC DE INFORMACION Y SISTEMAS": "TI",
    "T I": "TI",
    "TI": "TI",
    "T I Y SISTEMAS": "TI",
    "TI Y SISTEMAS": "TI",
    "CONTROL OPERACIONAL": "CO",
    "PLANIFICACION Y CONTROL OPERACIONAL": "CO",
    "PLANIFICACION Y CONTROL DE PRODUCCION": "PC",
    "PLANIFICACION Y CONTROL DE LA PRODUCCION": "PC",
    "GESTION DE CULTURA": "GS",
    "GESTION DE CULTURA DE SEGURIDAD": "GS",
    "SANEAMIENTO Y BPM": "IS",
    "INOCUIDAD Y SANEAMIENTO": "IS",
    "CALIDAD INDUSTRIAL": "CP",
    "CALIDAD PLANTA": "CP",
    "PRODUCCION INDUSTRIAL": "PD",
    "PRODUCCION": "PD",
    "PACKING": "PD",
    "INDUSTRIAL": "PD",
    "OPERACIONES INDUSTRIAL": "PD",
    "CAMPO": "CS",
    "OPERACIONES": "CS",
    "SUB GERENCIA COSECHA Y OPERACIONES": "CS",
    "SUB GERENCIA AGRICOLA": "PA",
    "GESTION DEL TALENTO HUMANO": "AD",
    "GESTION HUMANA": "AD",
    "ADMINISTRACION DE PERSONAL": "AD",
    "ADMINISTRACION DE PERSONAS": "AD",
    "RECLUTAMIENTO Y SELECCION": "RS",
    "SSOMA": "SM",
    "SALUD OCUPACIONAL": "SO",
    "BIENESTAR SOCIAL": "BS",
    "GESTION DE LA INFORMACION COSECHA Y OPERACIONES": "GC",
    "REPORTERIA COSECHA Y OPERACIONES": "GC",
    "REPORTERIA J OPERACIONES": "GC",
    "GESTION DE LA INFORMACION AGRICOLA": "GA",
    "GESTION DE LA INFORMACION": "GI",
    "INDICADORES Y GESTION DE LA INFORMACION": "GI",
    "SISTEMAS INTEGRADOS DE GESTION": "CP",
    "SIG": "CP",
    "TRANSPORTES": "TR",
    "ABASTECIMIENTO INDUSTRIAL": "AI",
    "ALMACEN PISO": "AP",
    "MANTENIMIENTO DE CAMPO": "MC",
    "MANTENIMIENTO ELECTRICO": "ME",
    "MANTENIMIENTO MECANICO": "MM",
    "CALIDAD CAMPO": "CC",
    "PROYECTOS DE INVERSION AGRICOLA": "PI",
}

# División canónica (fold) → nombres que aparecen en maestro / QBiz / roster.
_DIVISION_ALIASES: dict[str, tuple[str, ...]] = {
    "ADMINISTRACION Y FINANZAS": (
        "Administración y Finanzas",
        "Administración",
        "Administracion",
    ),
    "PLANIFICACION": (
        "Planificación",
        "Planificacion",
        "Planificación y Control Operacional",
        "Planificación, Control Operacional y de Gestión",
        "Planificación y Control Operacional y de Gestión",
    ),
    "COSECHA Y OPERACIONES": ("Cosecha y Operaciones",),
    "AGRICOLA": ("Agrícola", "Agricola", "División Agrícola", "Division Agricola"),
    "PERSONAS Y CULTURA": (
        "Personas y Cultura",
        "GTH",
        "Gestión del Talento Humano",
        "Gestion del Talento Humano",
    ),
    "INDUSTRIAL": ("Industrial", "Packing"),
    "CORPORATIVA": (
        "Corporativa",
        "Corporativo",
        "Comercio Exterior",
        "Patrimonial",
        "Certificaciones",
    ),
}

_CANONICAL_BY_FOLD: dict[str, str] = {}
for _canon in CODIGO_TO_DIVISION.values():
    _CANONICAL_BY_FOLD[fold_label(_canon)] = _canon
for _fold, _names in _DIVISION_ALIASES.items():
    _canon = _CANONICAL_BY_FOLD.get(_fold) or _names[0]
    _CANONICAL_BY_FOLD[_fold] = _canon
    for _n in _names:
        _CANONICAL_BY_FOLD[fold_label(_n)] = _canon


def effective_role(user: dict[str, Any] | None) -> str:
    rol = str((user or {}).get("rol") or "").upper()
    if rol == "ADMIN" or (user or {}).get("is_admin"):
        return "ADMIN"
    if rol == "JEFE":
        return "JEFE"
    if rol in _ROLE_GERENTE:
        return "GERENTE"
    return rol or "GERENTE"


def area_codigo(area: str | None) -> str | None:
    key = fold_label(area)
    return AREA_TO_CODIGO.get(key) if key else None


def division_for_area(area: str | None) -> str | None:
    codigo = area_codigo(area)
    if not codigo:
        return None
    return CODIGO_TO_DIVISION.get(codigo)


def resolve_division(*labels: str | None) -> str | None:
    for raw in labels:
        key = fold_label(raw)
        if not key:
            continue
        if key in _CANONICAL_BY_FOLD:
            return _CANONICAL_BY_FOLD[key]
        via_area = division_for_area(raw)
        if via_area:
            return via_area
    return None


def division_name_aliases(canonical: str) -> list[str]:
    key = fold_label(canonical)
    names = list(_DIVISION_ALIASES.get(key, ()))
    if canonical:
        names.append(canonical)
    return names


def area_labels_for_codigo(codigo: str) -> list[str]:
    return [label for label, code in AREA_TO_CODIGO.items() if code == codigo]


def area_labels_for_division(canonical: str) -> list[str]:
    wanted = fold_label(canonical)
    out: list[str] = []
    for label, codigo in AREA_TO_CODIGO.items():
        if fold_label(CODIGO_TO_DIVISION.get(codigo, "")) == wanted:
            out.append(label)
    return out


def jefe_match_values(user: dict[str, Any]) -> list[str]:
    area = (user.get("area") or "").strip()
    if not area:
        return []
    labels = [area]
    codigo = area_codigo(area)
    if codigo:
        labels.extend(area_labels_for_codigo(codigo))
        labels.append(codigo)
    return fold_list(*labels)


def gerente_match_values(user: dict[str, Any]) -> list[str]:
    division = resolve_division(user.get("gerencia"), user.get("division"), user.get("area"))
    raw = (user.get("gerencia") or user.get("division") or "").strip()
    labels = [raw] if raw else []
    if division:
        labels.extend(division_name_aliases(division))
        labels.extend(area_labels_for_division(division))
    return fold_list(*labels)


def dnis_from_maestro(
    user: dict[str, Any],
    maestro: Iterable[dict[str, Any]] | None,
) -> list[str]:
    """DNIs del maestro AWS/QBiz que caen en el alcance del usuario."""
    if not maestro:
        return []
    role = effective_role(user)
    out: list[str] = []
    if role == "JEFE":
        allowed = set(jefe_match_values(user))
        if not allowed:
            return []
        for row in maestro:
            area = str(row.get("area") or "")
            if fold_label(area).lower() in allowed:
                dni = _norm_dni(row.get("dni"))
                if dni:
                    out.append(dni)
        return sorted(set(out))
    if role == "GERENTE":
        division = resolve_division(user.get("gerencia"), user.get("division"), user.get("area"))
        if not division:
            return []
        wanted = fold_label(division)
        for row in maestro:
            row_div = resolve_division(row.get("division"), row.get("area"))
            if row_div and fold_label(row_div) == wanted:
                dni = _norm_dni(row.get("dni"))
                if dni:
                    out.append(dni)
        return sorted(set(out))
    return []


def employee_sql_scope(
    user: dict[str, Any],
    extra_dnis: list[str] | None = None,
) -> tuple[str, list]:
    """Fragmento AND … para filtrar `employees`. Vacío si es admin."""
    if effective_role(user) == "ADMIN":
        return "", []
    dnis = [str(x).strip() for x in (extra_dnis or []) if str(x).strip()]
    role = effective_role(user)
    if role == "GERENTE":
        aliases = gerente_match_values(user)
        if not aliases and not dnis:
            return " AND FALSE", []
        fold_div = sql_fold_expr("division")
        fold_ger = sql_fold_expr("gerencia")
        fold_area = sql_fold_expr("area")
        sql = f" AND ({fold_div} = ANY(%s) OR {fold_ger} = ANY(%s) OR {fold_area} = ANY(%s)"
        params: list = [aliases, aliases, aliases]
        if dnis:
            sql += " OR dni = ANY(%s)"
            params.append(dnis)
        sql += ")"
        return sql, params
    if role == "JEFE":
        aliases = jefe_match_values(user)
        if not aliases and not dnis:
            return " AND FALSE", []
        fold_area = sql_fold_expr("area")
        fold_jef = sql_fold_expr("jefatura")
        sql = f" AND ({fold_area} = ANY(%s) OR {fold_jef} = ANY(%s)"
        params = [aliases or [""], aliases or [""]]
        if dnis:
            sql += " OR dni = ANY(%s)"
            params.append(dnis)
        sql += ")"
        return sql, params
    return " AND FALSE", []


def employee_in_scope(user: dict[str, Any], emp: dict[str, Any]) -> bool:
    if effective_role(user) == "ADMIN":
        return True
    role = effective_role(user)
    if role == "GERENTE":
        aliases = set(gerente_match_values(user))
        if not aliases:
            return False
        for field in ("division", "gerencia", "area"):
            if fold_label(emp.get(field)).lower() in aliases:
                return True
        return False
    if role == "JEFE":
        aliases = set(jefe_match_values(user))
        if not aliases:
            return False
        for field in ("area", "jefatura"):
            if fold_label(emp.get(field)).lower() in aliases:
                return True
        return False
    return False
