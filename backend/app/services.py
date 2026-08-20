from __future__ import annotations

from datetime import date

from .domain.calendar import reconcile_targets_with_daily
from .domain.plan import load_plan_for_year

EMP_COLS = (
    "dni, nombre, empresa, division, gerencia, area, jefatura, "
    "cargo_actual, fecha_ingreso, tipo_personal, activo"
)


def employee_from_row(row) -> dict:
    fi = row["fecha_ingreso"]
    return {
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


def _scope_sql(user: dict, empresa, gerencia, division, q: str | None = None) -> tuple[str, list]:
    sql = " FROM employees WHERE activo = TRUE"
    params: list = []
    if not user.get("is_admin"):
        sql += " AND lower(gerencia) = lower(%s)"
        params.append(user.get("gerencia") or "")
    if empresa and "TODAS" not in empresa:
        sql += " AND lower(empresa) = ANY(%s)"
        params.append([x.lower() for x in empresa])
    if user.get("is_admin") and gerencia and "TODAS" not in gerencia:
        sql += " AND lower(gerencia) = ANY(%s)"
        params.append([x.lower() for x in gerencia])
    if division and "TODAS" not in division:
        sql += " AND lower(division) = ANY(%s)"
        params.append([x.lower() for x in division])
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        sql += (
            " AND (nombre ILIKE %s OR dni ILIKE %s OR area ILIKE %s"
            " OR cargo_actual ILIKE %s OR division ILIKE %s OR gerencia ILIKE %s)"
        )
        params.extend([like, like, like, like, like, like])
    return sql, params


def list_employees(cur, user: dict, empresa=None, gerencia=None, division=None, q: str | None = None):
    where, params = _scope_sql(user, empresa, gerencia, division, q)
    cur.execute(f"SELECT {EMP_COLS}{where} ORDER BY nombre", params)
    return [employee_from_row(r) for r in cur.fetchall()]


def get_employee(cur, user: dict, dni: str) -> dict | None:
    sql = f"SELECT {EMP_COLS} FROM employees WHERE activo = TRUE AND dni = %s"
    params: list = [str(dni)]
    if not user.get("is_admin"):
        sql += " AND lower(gerencia) = lower(%s)"
        params.append(user.get("gerencia") or "")
    cur.execute(sql, params)
    row = cur.fetchone()
    return employee_from_row(row) if row else None


def filter_options(cur, user: dict):
    where, params = _scope_sql(user, None, None, None)
    cur.execute(f"SELECT empresa, gerencia, division{where}", params)
    empresas: set[str] = set()
    gerencias: set[str] = set()
    divisiones: set[str] = set()
    for r in cur.fetchall():
        if r["empresa"]:
            empresas.add(r["empresa"])
        if r["gerencia"]:
            gerencias.add(r["gerencia"])
        if r["division"]:
            divisiones.add(r["division"])
    return {
        "empresas": sorted(empresas),
        "gerencias": sorted(gerencias) if user.get("is_admin") else [user.get("gerencia")],
        "divisiones": sorted(divisiones),
        "is_admin": user.get("is_admin"),
    }


def load_scope_plan(cur, year: int, employees: list[dict]):
    dnis = [e["dni"] for e in employees]
    daily_set, targets = load_plan_for_year(cur, year, dnis)
    targets, _ = reconcile_targets_with_daily(daily_set, targets, year)
    return daily_set, targets
