"""Genera INSERT SQL desde los Excel y opcionalmente los aplica en Neon.

Uso:
  python scripts/generar_sql_neon.py           # solo escribe backend/sql/carga_datos.sql
  python scripts/generar_sql_neon.py --apply   # SQL + carga directa a Neon
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd

from app.db import get_conn
from app.domain.calendar import iso_monday, now_lima
from app.domain.excel_norm import (
    is_user_active,
    is_worker_vigente,
    normalize_cronograma,
    normalize_users,
    normalize_vacation_records,
    normalize_workers,
    read_master_and_cronograma,
)

OUT = ROOT / "backend" / "sql" / "carga_datos.sql"


def sql_lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float) and pd.isna(v):
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if pd.isna(v):
            return "NULL"
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def batch_insert(lines: list[str], table: str, cols: str, rows: list[tuple], conflict: str = "") -> None:
    if not rows:
        return
    chunk = 80
    col_n = len(rows[0])
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        values = ",\n".join("(" + ", ".join(sql_lit(x) for x in row) + ")" for row in part)
        sql = f"INSERT INTO {table} ({cols}) VALUES\n{values}"
        if conflict:
            sql += f"\n{conflict}"
        sql += ";\n"
        lines.append(sql)


def plan_from_cronograma(workers: pd.DataFrame, cronograma: pd.DataFrame):
    dni_to_jef = dict(zip(workers["DNI"].astype(str), workers["JEFATURA"].astype(str)))
    daily_map: dict[tuple, tuple] = {}
    marks: dict[tuple, tuple] = {}
    when = now_lima()
    for _, row in cronograma.iterrows():
        dni = str(row["DNI"])
        f_ini, f_fin = row["FECHA_INICIO"], row["FECHA_FIN"]
        if dni not in dni_to_jef or pd.isna(f_ini) or pd.isna(f_fin) or f_fin < f_ini:
            continue
        jef = dni_to_jef[dni]
        marks[(dni, f_ini, f_fin)] = (dni, f_ini, f_fin, when)
        d = f_ini
        while d <= f_fin:
            daily_key = (jef, d.year, dni, d)
            daily_map[daily_key] = (jef, d.year, dni, d, "PROGRAMADO", "CRONOGRAMA")
            d += timedelta(days=1)
    daily = list(daily_map.values())
    weekly: dict[tuple, int] = {}
    for (jef, _anio, dni, d), _row in daily_map.items():
        iso_year, iso_week, _ = d.isocalendar()
        key = (jef, iso_year, dni, iso_week)
        weekly[key] = weekly.get(key, 0) + 1
    weekly_rows = [
        (jef, anio, dni, sem, min(n, 7), "CRONOGRAMA")
        for (jef, anio, dni, sem), n in weekly.items()
        if n > 0
    ]
    return daily, weekly_rows, list(marks.values())


def load_frames():
    wpath = ROOT / "trabajadores.xlsx"
    upath = ROOT / "usuarios.xlsx"
    if not wpath.exists() or not upath.exists():
        raise SystemExit("Faltan trabajadores.xlsx o usuarios.xlsx en la raíz del proyecto.")
    master, crono_raw, record_raw = read_master_and_cronograma(wpath)
    workers = normalize_workers(master)
    cronograma = normalize_cronograma(crono_raw)
    records = normalize_vacation_records(record_raw)
    users = normalize_users(pd.read_excel(upath))
    users = users[users["CORREO"].ne("")].drop_duplicates("CORREO")
    return workers, cronograma, records, users


def build_sql(workers, cronograma, records, users) -> str:
    daily, weekly_rows, marks = plan_from_cronograma(workers, cronograma)
    lines = [
        "-- Datos cargados desde trabajadores.xlsx y usuarios.xlsx",
        "-- Ejecutar DESPUÉS de schema.sql en el SQL Editor de Neon.",
        "BEGIN;",
        "TRUNCATE TABLE vacation_records, cronograma,",
        "             daily_plan, weekly_plan, employees, users RESTART IDENTITY CASCADE;",
        "",
    ]

    user_rows = []
    for _, u in users.iterrows():
        user_rows.append(
            (
                u["CORREO"].lower(),
                u["USUARIO"],
                u["NOMBRE_USUARIO"],
                u["NOMBRE_PERSONA"],
                u["GERENCIA"],
                str(u["ROL"]).upper(),
                is_user_active(u["ACTIVO"]),
            )
        )
    batch_insert(
        lines,
        "users",
        "correo, usuario, nombre_usuario, nombre_persona, gerencia, rol, activo",
        user_rows,
        "ON CONFLICT (correo) DO UPDATE SET usuario=EXCLUDED.usuario, nombre_usuario=EXCLUDED.nombre_usuario, nombre_persona=EXCLUDED.nombre_persona, gerencia=EXCLUDED.gerencia, rol=EXCLUDED.rol, activo=EXCLUDED.activo",
    )

    emp_rows = []
    for _, w in workers.iterrows():
        fi = w["FECHA_INGRESO"]
        if pd.isna(fi):
            fi = None
        fc = w.get("FECHA_CESE")
        if fc is None or pd.isna(fc):
            fc = None
        vigencia = str(w.get("VIGENCIA") or "").strip()
        emp_rows.append(
            (
                str(w["DNI"]),
                w["NOMBRE"],
                w["EMPRESA"],
                w["DIVISION"],
                w["GERENCIA"],
                w["AREA"],
                w["JEFATURA"],
                w["CARGO_ACTUAL"],
                fi,
                w["TIPO_PERSONAL"],
                vigencia,
                fc,
                is_worker_vigente(vigencia) and (fc is None or fc >= date.today()),
            )
        )
    batch_insert(
        lines,
        "employees",
        "dni, nombre, empresa, division, gerencia, area, jefatura, cargo_actual, fecha_ingreso, tipo_personal, vigencia, fecha_cese, activo",
        emp_rows,
        "ON CONFLICT (dni) DO UPDATE SET nombre=EXCLUDED.nombre, empresa=EXCLUDED.empresa, division=EXCLUDED.division, gerencia=EXCLUDED.gerencia, area=EXCLUDED.area, jefatura=EXCLUDED.jefatura, cargo_actual=EXCLUDED.cargo_actual, fecha_ingreso=EXCLUDED.fecha_ingreso, tipo_personal=EXCLUDED.tipo_personal, vigencia=EXCLUDED.vigencia, fecha_cese=EXCLUDED.fecha_cese, activo=EXCLUDED.activo",
    )

    crono_map: dict[tuple, tuple] = {}
    for _, r in cronograma.iterrows():
        n_dias = r.get("N_DIAS")
        if pd.isna(n_dias):
            n_dias = None
        else:
            try:
                n_dias = int(n_dias)
            except Exception:
                n_dias = None
        key = (str(r["DNI"]), r["FECHA_INICIO"], r["FECHA_FIN"])
        crono_map[key] = (
            str(r["DNI"]),
            r.get("NOMBRE", ""),
            r["FECHA_INICIO"],
            r["FECHA_FIN"],
            n_dias,
            r.get("RECORD_VACACIONAL", ""),
            r.get("OBSERVACION", ""),
            r.get("OBS_PAGOS", ""),
        )
    crono_rows = list(crono_map.values())
    batch_insert(
        lines,
        "cronograma",
        "dni, nombre, fecha_inicio, fecha_fin, n_dias, record_vacacional, observacion, obs_pagos",
        crono_rows,
        "ON CONFLICT (dni, fecha_inicio, fecha_fin) DO UPDATE SET nombre=EXCLUDED.nombre, n_dias=EXCLUDED.n_dias, record_vacacional=EXCLUDED.record_vacacional, observacion=EXCLUDED.observacion, obs_pagos=EXCLUDED.obs_pagos",
    )

    rec_rows = []
    for _, r in records.iterrows():
        def num(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            try:
                return int(float(v))
            except Exception:
                return None

        def dval(v):
            if v is None or pd.isna(v):
                return None
            return v

        def txt(v):
            if v is None or pd.isna(v):
                return ""
            return str(v).strip()

        rec_rows.append(
            (
                str(r["DNI"]),
                r.get("EMPRESA", ""),
                r.get("NOMBRE", ""),
                dval(r.get("FECHA_INGRESO")),
                r.get("DIVISION", ""),
                r.get("SUB_AREA", ""),
                num(r.get("DESDE_PERIODO")),
                num(r.get("HASTA_PERIODO")),
                r.get("RECORD_VACACIONAL", ""),
                dval(r.get("CUMPLE_RECORD")),
                txt(r.get("DIAS_PENDIENTES")),
                txt(r.get("DIAS_GOZADOS")),
                r.get("PROGRAMADO", ""),
                txt(r.get("OBS1")),
                dval(r.get("FECHA_VENCIMIENTO")),
                dval(r.get("FECHA_LIMITE")),
            )
        )
    batch_insert(
        lines,
        "vacation_records",
        "dni, empresa, nombre, fecha_ingreso, division, sub_area, desde_periodo, hasta_periodo, record_vacacional, cumple_record, dias_pendientes, dias_gozados, programado, obs1, fecha_vencimiento, fecha_limite",
        rec_rows,
    )

    batch_insert(
        lines,
        "daily_plan",
        "jefatura, anio, dni, fecha, estado, usuario",
        daily,
        "ON CONFLICT (jefatura, anio, dni, fecha) DO UPDATE SET estado=EXCLUDED.estado, usuario=EXCLUDED.usuario",
    )
    batch_insert(
        lines,
        "weekly_plan",
        "jefatura, anio, dni, semana, dias, usuario",
        weekly_rows,
        "ON CONFLICT (jefatura, anio, dni, semana) DO UPDATE SET dias=EXCLUDED.dias, usuario=EXCLUDED.usuario",
    )

    lines.append("COMMIT;")
    lines.append(
        f"-- Resumen: {len(emp_rows)} empleados, {len(user_rows)} usuarios, "
        f"{len(crono_rows)} cronograma, {len(rec_rows)} récords, "
        f"{len(daily)} días plan, {len(weekly_rows)} semanas."
    )
    return "\n".join(lines) + "\n"


def apply_sql(sql: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cur.execute("SELECT COUNT(*) AS n FROM employees")
        e = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM users")
        u = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM cronograma")
        c = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM vacation_records")
        r = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM daily_plan")
        d = cur.fetchone()["n"]
        print(f"Neon actualizado: {e} empleados, {u} usuarios, {c} cronograma, {r} récords, {d} días en plan")


def main():
    apply = "--apply" in sys.argv
    workers, cronograma, records, users = load_frames()
    sql = build_sql(workers, cronograma, records, users)
    OUT.write_text(sql, encoding="utf-8")
    print(f"SQL generado: {OUT} ({OUT.stat().st_size} bytes)")
    if apply:
        apply_sql(sql)


if __name__ == "__main__":
    main()
