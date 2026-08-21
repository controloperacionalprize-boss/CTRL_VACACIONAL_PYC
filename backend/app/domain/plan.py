from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .calendar import (
    DIAS_ES,
    MAX_DIAS,
    TOTAL_SEMANAS,
    allowed_type,
    is_weekend,
    key_daily,
    now_lima,
    parse_daily_key,
    selected_count,
    week_dates,
)


def load_plan_for_year(cur, year: int, dnis: list[str] | None = None):
    daily_set: set[str] = set()
    targets: dict[tuple[str, int], int] = {}
    if dnis is not None and not dnis:
        return daily_set, targets
    if dnis:
        cur.execute(
            "SELECT dni, fecha FROM daily_plan WHERE anio = %s AND dni = ANY(%s)",
            (year, dnis),
        )
    else:
        cur.execute("SELECT dni, fecha FROM daily_plan WHERE anio = %s", (year,))
    for row in cur.fetchall():
        fecha = row["fecha"]
        if isinstance(fecha, date):
            daily_set.add(key_daily(str(row["dni"]), fecha))
        else:
            daily_set.add(key_daily(str(row["dni"]), date.fromisoformat(str(fecha))))
    if dnis:
        cur.execute(
            "SELECT dni, semana, dias FROM weekly_plan WHERE anio = %s AND dni = ANY(%s)",
            (year, dnis),
        )
    else:
        cur.execute("SELECT dni, semana, dias FROM weekly_plan WHERE anio = %s", (year,))
    for row in cur.fetchall():
        targets[(str(row["dni"]), int(row["semana"]))] = int(row["dias"])
    return daily_set, targets


def persist_employee(cur, year: int, emp: dict, daily_set: set[str], targets: dict, usuario: str):
    dni = str(emp["dni"])
    jefatura = emp["jefatura"]
    cur.execute("DELETE FROM daily_plan WHERE anio = %s AND dni = %s", (year, dni))
    cur.execute("DELETE FROM weekly_plan WHERE anio = %s AND dni = %s", (year, dni))
    daily_rows = []
    prefix = f"{dni}|"
    for item in daily_set:
        if not item.startswith(prefix):
            continue
        _, fecha = parse_daily_key(item)
        daily_rows.append((jefatura, year, dni, fecha, "PROGRAMADO", usuario))
    if daily_rows:
        cur.executemany(
            """INSERT INTO daily_plan
               (jefatura, anio, dni, fecha, estado, usuario)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            daily_rows,
        )
    weekly_rows = []
    for (d, semana), dias in targets.items():
        if d == dni and int(dias) > 0:
            weekly_rows.append((jefatura, year, dni, int(semana), int(dias), usuario))
    if weekly_rows:
        cur.executemany(
            """INSERT INTO weekly_plan
               (jefatura, anio, dni, semana, dias, usuario)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            weekly_rows,
        )


def log_change(cur, *, jefatura, year, dni, nombre, tipo, old_week, old_days, new_week, new_days, user):
    cur.execute(
        """INSERT INTO change_log
        (jefatura, anio, dni, nombre, tipo_persona, fecha_hora,
         semana_anterior, dias_anterior, semana_nueva, dias_nuevos, usuario,
         nombre_persona, correo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            str(jefatura),
            int(year),
            str(dni),
            str(nombre),
            str(tipo),
            now_lima(),
            None if old_week is None else int(old_week),
            int(old_days or 0),
            None if new_week is None else int(new_week),
            int(new_days or 0),
            user.get("usuario") or user.get("correo"),
            user.get("nombre_persona") or user.get("nombre_usuario"),
            user.get("correo"),
        ),
    )


GROUP_META = {
    "mismatch": {
        "title": "El número de la semana no coincide con las fechas",
        "hint": "El número que ves en planificación (0 a 7) no coincide con las fechas guardadas día por día.",
    },
    "range": {
        "title": "Una semana tiene más de 7 días",
        "hint": "En cada semana solo se pueden programar de 0 a 7 días.",
    },
}


def validate_plan(employees, targets, daily_set, year, today: date | None = None):
    from .calendar import week_is_locked

    today = today or date.today()
    warnings = []
    issues: list[dict] = []

    for w in employees:
        dni = str(w["dni"])
        modo = allowed_type(w["tipo_personal"], dni)
        for week in range(1, TOTAL_SEMANAS + 1):
            if week_is_locked(year, week, today):
                continue
            target = int(targets.get((dni, week), 0))
            dates = week_dates(year, week)
            selected = selected_count(daily_set, dni, dates)
            weekend_n = sum(key_daily(dni, d) in daily_set for d in dates if is_weekend(d))
            label = f"{w['nombre']} — semana {week}"

            if target < 0 or target > MAX_DIAS:
                issues.append({"code": "range", "sample": f"{label}: aparecen {target} días (el máximo es 7)."})
                continue

            # Oficina con sáb/dom: viene del archivo original; no es algo a corregir aquí.
            if modo == "HABIL" and weekend_n > 0:
                continue

            if 0 < target < 7 and selected != target:
                issues.append(
                    {
                        "code": "mismatch",
                        "sample": f"{label}: en planificación hay {target} día(s) y en el detalle hay {selected}.",
                    }
                )
            elif target == 7:
                expected = 7 if modo == "CALENDARIO" else 5
                if selected != expected:
                    issues.append(
                        {
                            "code": "mismatch",
                            "sample": f"{label}: una semana completa son {expected} día(s) y están marcados {selected}.",
                        }
                    )

    groups = []
    for code, meta in GROUP_META.items():
        samples = [i["sample"] for i in issues if i["code"] == code]
        if not samples:
            continue
        groups.append({**meta, "code": code, "count": len(samples), "samples": samples})

    errors = [i["sample"] for i in issues]

    total = len(employees)
    if total and daily_set:
        emp_dnis = {str(w["dni"]) for w in employees}
        by_day: Counter[date] = Counter()
        for item in daily_set:
            dni, d = parse_daily_key(item)
            if dni in emp_dnis and d >= today:
                by_day[d] += 1
        for d, absent in by_day.items():
            pct = absent / total
            if pct >= 0.50:
                warnings.append(
                    f"El {d.strftime('%d/%m/%Y')} hay {absent} de {total} personas de vacaciones ({pct:.0%}). Es un día muy cargado."
                )
            elif pct >= 0.30:
                warnings.append(
                    f"El {d.strftime('%d/%m/%Y')} hay {absent} de {total} personas de vacaciones ({pct:.0%}). Conviene revisar cobertura."
                )
    return errors, warnings, groups


def group_periods(employees, daily_set: set[str], year: int):
    by_dni: dict[str, list[date]] = defaultdict(list)
    emp = {str(e["dni"]): e for e in employees}
    for item in daily_set:
        dni, d = parse_daily_key(item)
        if d.year != year and d.isocalendar()[0] != year:
            pass
        if dni not in emp:
            continue
        by_dni[dni].append(d)

    result = []
    for dni, dates in by_dni.items():
        w = emp[dni]
        calendar_days = allowed_type(w["tipo_personal"], str(w["dni"])) == "CALENDARIO"
        dates = sorted(dates)
        group_id = 0
        groups: dict[int, list[date]] = defaultdict(list)
        previous = None
        for current in dates:
            if previous is not None:
                if calendar_days:
                    contiguous = (current - previous).days == 1
                else:
                    days = (current - previous).days
                    contiguous = days == 1 or (
                        previous.weekday() == 4 and current.weekday() == 0 and days <= 3
                    )
                if not contiguous:
                    group_id += 1
            groups[group_id].append(current)
            previous = current
        for gdates in groups.values():
            result.append({
                "dni": dni,
                "nombre": w["nombre"],
                "gerencia": w["gerencia"],
                "area": w["area"],
                "jefatura": w["jefatura"],
                "tipo_personal": w["tipo_personal"],
                "fecha_inicio": gdates[0].isoformat(),
                "fecha_fin": gdates[-1].isoformat(),
                "dias": len(gdates),
            })
    result.sort(key=lambda r: (r["fecha_inicio"], r["gerencia"], r["area"], r["nombre"]))
    return result


def daily_rows(employees, daily_set, year):
    emp = {str(e["dni"]): e for e in employees}
    rows = []
    for item in sorted(daily_set):
        dni, d = parse_daily_key(item)
        w = emp.get(dni)
        if not w:
            continue
        if d.isocalendar()[0] != year and d.year != year:
            continue
        rows.append({
            "dni": dni,
            "nombre": w["nombre"],
            "gerencia": w["gerencia"],
            "area": w["area"],
            "jefatura": w["jefatura"],
            "tipo_personal": w["tipo_personal"],
            "fecha": d.isoformat(),
            "semana": int(d.isocalendar().week),
            "dia": DIAS_ES.get(d.strftime("%A"), d.strftime("%A")),
            "estado": "PROGRAMADO",
        })
    rows.sort(key=lambda r: (r["semana"], r["nombre"], r["fecha"]))
    return rows
