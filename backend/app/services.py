from __future__ import annotations

from datetime import date

from .domain.calendar import reconcile_targets_with_daily
from .domain.plan import load_plan_for_year
from .funcionarios_org import load_funcionarios_org, maestro_version
from .org_scope import (
    sql_fold_expr,
    dnis_from_maestro,
    effective_role,
    employee_sql_scope,
    fold_list,
    gerente_match_values,
    resolve_division,
)
from .photos import enrich_employee_photo

EMP_COLS = (
    "dni, nombre, empresa, division, gerencia, area, jefatura, "
    "cargo_actual, fecha_ingreso, tipo_personal, activo"
)


def employee_from_row(row, *, with_photo: bool = True) -> dict:
    fi = row["fecha_ingreso"]
    emp = {
        "dni": str(row["dni"]),
        "nombre": row["nombre"],
        "empresa": row["empresa"],
        "division": row["division"],
        "gerencia": row["gerencia"],
        "area": row["area"],
        "jefatura": row["jefatura"],
        "cargo_actual": row["cargo_actual"],
        "fecha_ingreso": fi.isoformat() if isinstance(fi, date) else (str(fi) if fi else None),
        "tipo_personal": row["tipo_personal"],
        "activo": bool(row["activo"]),
    }
    return enrich_employee_photo(emp) if with_photo else emp


_MAESTRO_DNIS_CACHE: dict[tuple, list[str]] = {}


def _maestro_dnis(user: dict) -> list[str]:
    """DNIs extra del maestro QBiz para el alcance del usuario.

    Cruzar todo el maestro (resolve_division por fila) en cada request consume mucho CPU;
    el resultado solo cambia cuando cambia el maestro o el alcance del usuario.
    """
    role = effective_role(user)
    if role == "ADMIN":
        return []
    try:
        maestro = load_funcionarios_org()
        key = (role, user.get("gerencia") or "", user.get("division") or "", user.get("area") or "", maestro_version())
        cached = _MAESTRO_DNIS_CACHE.get(key)
        if cached is None:
            if len(_MAESTRO_DNIS_CACHE) > 256:
                _MAESTRO_DNIS_CACHE.clear()
            cached = dnis_from_maestro(user, maestro)
            _MAESTRO_DNIS_CACHE[key] = cached
        return cached
    except Exception:
        return []


def _scope_sql(user: dict, empresa, gerencia, area, q: str | None = None) -> tuple[str, list]:
    sql = " FROM employees WHERE activo = TRUE"
    params: list = []
    role = effective_role(user)
    if role != "ADMIN":
        frag, extra = employee_sql_scope(user, extra_dnis=_maestro_dnis(user))
        sql += frag
        params.extend(extra)
        gerencia = None
        if role == "JEFE":
            area = None
    if empresa and "TODAS" not in empresa:
        sql += " AND lower(empresa) = ANY(%s)"
        params.append([x.lower() for x in empresa])
    if role == "ADMIN" and gerencia and "TODAS" not in gerencia:
        aliases: list[str] = []
        for g in gerencia:
            aliases.extend(gerente_match_values({"gerencia": g}))
        aliases = sorted(set(aliases))
        if aliases:
            sql += (
                f" AND ({sql_fold_expr('gerencia')} = ANY(%s) OR {sql_fold_expr('division')} = ANY(%s)"
                f" OR {sql_fold_expr('area')} = ANY(%s))"
            )
            params.extend([aliases, aliases, aliases])
    if area and "TODAS" not in area:
        folded = fold_list(*area)
        if folded:
            sql += f" AND {sql_fold_expr('area')} = ANY(%s)"
            params.append(folded)
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        sql += (
            " AND (nombre ILIKE %s OR dni ILIKE %s OR area ILIKE %s"
            " OR cargo_actual ILIKE %s OR division ILIKE %s OR gerencia ILIKE %s)"
        )
        params.extend([like, like, like, like, like, like])
    return sql, params


def list_employees(
    cur,
    user: dict,
    empresa=None,
    gerencia=None,
    area=None,
    q: str | None = None,
    *,
    with_photos: bool = True,
):
    where, params = _scope_sql(user, empresa, gerencia, area, q)
    cur.execute(f"SELECT {EMP_COLS}{where} ORDER BY nombre, dni", params)
    return [employee_from_row(r, with_photo=with_photos) for r in cur.fetchall()]


_EMP_SORT = {
    "nombre": "nombre",
    "fecha_ingreso": "fecha_ingreso",
}


def list_employees_page(
    cur,
    user: dict,
    empresa=None,
    gerencia=None,
    area=None,
    q: str | None = None,
    *,
    limit: int,
    offset: int,
    with_photos: bool = False,
    sort: str = "nombre",
    order: str = "asc",
) -> tuple[list[dict], int]:
    where, params = _scope_sql(user, empresa, gerencia, area, q)
    cur.execute(f"SELECT COUNT(*) AS n{where}", params)
    total = int(cur.fetchone()["n"])
    col = _EMP_SORT.get(sort, "nombre")
    direction = "DESC" if str(order).lower() == "desc" else "ASC"
    extra = " NULLS LAST" if col == "fecha_ingreso" else ""
    cur.execute(
        f"SELECT {EMP_COLS}{where} ORDER BY {col} {direction}{extra}, dni LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    items = [employee_from_row(r, with_photo=with_photos) for r in cur.fetchall()]
    return items, total


def get_employee(cur, user: dict, dni: str) -> dict | None:
    sql = f"SELECT {EMP_COLS} FROM employees WHERE activo = TRUE AND dni = %s"
    params: list = [str(dni)]
    frag, extra = employee_sql_scope(user, extra_dnis=_maestro_dnis(user))
    sql += frag
    params.extend(extra)
    cur.execute(sql, params)
    row = cur.fetchone()
    return employee_from_row(row) if row else None

def _distinct_values(cur, user: dict, column: str, empresa=None, gerencia=None, area=None) -> list[str]:
    filters = {"empresa": empresa, "gerencia": gerencia, "area": area}
    filters[column] = None
    where, params = _scope_sql(user, filters["empresa"], filters["gerencia"], filters["area"])
    cur.execute(
        f"SELECT DISTINCT {column}{where} AND {column} IS NOT NULL AND {column} <> '' ORDER BY {column}",
        params,
    )
    return [r[column] for r in cur.fetchall()]


def filter_options(cur, user: dict, empresa=None, gerencia=None, area=None):
    role = effective_role(user)
    empresas = _distinct_values(cur, user, "empresa", empresa, gerencia, area)
    gerencias = _distinct_values(cur, user, "gerencia", empresa, gerencia, area)
    areas = _distinct_values(cur, user, "area", empresa, gerencia, area)
    division = resolve_division(user.get("gerencia"), user.get("area")) or (
        user.get("gerencia") or ""
    )
    if role == "GERENTE":
        gerencias = [g for g in gerencias if g] or ([division] if division else [])
    elif role == "JEFE":
        gerencias = [g for g in gerencias if g] or ([division] if division else [])
        own_area = (user.get("area") or "").strip()
        areas = [a for a in areas if a] or ([own_area] if own_area else [])
    return {
        "empresas": empresas,
        "gerencias": gerencias,
        "areas": areas,
        "is_admin": role == "ADMIN",
        "is_gerente": role == "GERENTE",
        "is_jefe": role == "JEFE",
        "rol": role,
    }


def load_scope_plan(cur, year: int, employees: list[dict]):
    dnis = [e["dni"] for e in employees]
    daily_set, targets = load_plan_for_year(cur, year, dnis)
    targets, _ = reconcile_targets_with_daily(daily_set, targets, year)
    return daily_set, targets
