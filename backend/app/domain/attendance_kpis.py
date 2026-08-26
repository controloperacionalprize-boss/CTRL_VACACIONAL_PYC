"""KPI de jornada: horario 06:30–17:05 con margen de entrada hasta 06:50.

Cumple si entra ≤ 06:50 y sale ≥ 17:05. No se usan costos.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any

from .calendar import today_lima
from .employee_calendar import exento_control_asistencia
from .holidays_pe import peru_holidays
from .worker_vigencia import cuenta_asistencia_el_dia, vigente_en_periodo

ENTRADA_OFICIAL = time(6, 30)
SALIDA_OFICIAL = time(17, 5)
ENTRADA_LIMITE = time(6, 50)
SALIDA_MINIMA = time(17, 5)
JORNADA_MINUTOS = 10 * 60 + 35  # 06:30 → 17:05
TRUJILLO_ENTRADA = time(8, 0)
TRUJILLO_SALIDA = time(18, 0)
TRUJILLO_MARGEN = time(8, 20)
TRUJILLO_MINUTOS = 10 * 60
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TIPOS_SIN_JORNADA_OFICINA = frozenset({"OPERATIVO", "PLANTA"})


def norm_dni(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def usa_jornada_oficina(worker: dict) -> bool:
    tipo = (worker.get("tipo_personal") or "").strip().upper()
    return tipo not in TIPOS_SIN_JORNADA_OFICINA


def _index_shifts(shifts: dict[str, dict[date, dict[str, Any]]]) -> dict[str, dict[date, dict[str, Any]]]:
    out: dict[str, dict[date, dict[str, Any]]] = {}
    for dni, days in shifts.items():
        out[norm_dni(dni)] = days
    return out


def floor_minute(t: time) -> time:
    return t.replace(second=0, microsecond=0)


def minutes_of(t: time) -> int:
    t = floor_minute(t)
    return t.hour * 60 + t.minute


def format_hm(total_min: int) -> str:
    total_min = max(0, int(total_min))
    h, m = divmod(total_min, 60)
    return f"{h} h {m:02d} m"


def month_span(year: int, month: int, *, today: date | None = None) -> tuple[date, date]:
    today = today or today_lima()
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    end = min(end, today)
    return start, end


def es_sede_trujillo(dispositivo: str | None, worker: dict | None = None) -> bool:
    parts = [dispositivo or ""]
    if worker:
        parts.extend(
            str(worker.get(k) or "")
            for k in ("area", "gerencia", "division", "jefatura", "empresa")
        )
    return "trujillo" in " ".join(parts).casefold()


def limites_jornada(dispositivo: str | None, worker: dict | None = None) -> tuple[time, time]:
    if es_sede_trujillo(dispositivo, worker):
        return TRUJILLO_MARGEN, TRUJILLO_SALIDA
    return ENTRADA_LIMITE, SALIDA_MINIMA


def classify_shift(
    entrada: time | None,
    salida: time | None,
    n: int,
    *,
    entrada_limite: time = ENTRADA_LIMITE,
    salida_minima: time = SALIDA_MINIMA,
) -> str:
    """Una jornada evaluable: cumple | tardanza | salida_temprano | jornada | no_marcan | sin_hora."""
    if n <= 0:
        return "no_marcan"
    if entrada is None or salida is None:
        return "sin_hora" if n > 0 else "no_marcan"
    entrada = floor_minute(entrada)
    salida = floor_minute(salida)
    if n == 1 or entrada == salida:
        return "no_marcan"
    late = entrada > entrada_limite
    early = salida < salida_minima
    if not late and not early:
        return "cumple"
    if late and early:
        return "jornada"
    if late:
        return "tardanza"
    return "salida_temprano"


def lost_minutes(
    kind: str,
    entrada: time | None,
    salida: time | None,
    *,
    entrada_limite: time = ENTRADA_LIMITE,
    salida_minima: time = SALIDA_MINIMA,
) -> int:
    if kind == "cumple" or kind == "sin_hora":
        return 0
    if kind == "no_marcan":
        return JORNADA_MINUTOS
    if entrada:
        entrada = floor_minute(entrada)
    if salida:
        salida = floor_minute(salida)
    lost = 0
    if entrada and entrada > entrada_limite:
        lost += minutes_of(entrada) - minutes_of(entrada_limite)
    if salida and salida < salida_minima:
        lost += minutes_of(salida_minima) - minutes_of(salida)
    return lost


def cargo_bucket(worker: dict) -> str:
    cargo = (worker.get("cargo_actual") or "").strip().lower()
    tipo = (worker.get("tipo_personal") or "").strip()
    if "director" in cargo:
        return "Directores"
    if "gerente" in cargo:
        return "Gerentes"
    if "jefe" in cargo:
        return "Jefes"
    if "analista" in cargo:
        return "Analistas"
    if "asistente" in cargo:
        return "Asistentes"
    if "operar" in cargo or tipo.upper() == "OPERATIVO":
        return "Operarios"
    return tipo or "Otros"


def _iter_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def motivo_no_marcan(oficina: bool, n: int, entrada: time | None, salida: time | None) -> str:
    if not oficina:
        return "operativo_sin_marca"
    if n == 1 or (entrada is not None and salida is not None and entrada == salida):
        return "una_marca"
    if n <= 0 or entrada is None or salida is None:
        return "una_marca" if n > 0 else "sin_marca"
    return "sin_marca"


def iter_asistencia_eventos(
    employees: list[dict],
    daily_set: set[str],
    shifts: dict[str, dict[date, dict[str, Any]]],
    *,
    start: date,
    end: date,
):
    holidays = peru_holidays(start.year) | peru_holidays(end.year)
    indexed = _index_shifts(shifts)
    for emp in employees:
        if exento_control_asistencia(emp):
            continue
        dni = norm_dni(emp["dni"])
        area = (emp.get("area") or "Sin área").strip() or "Sin área"
        bucket = cargo_bucket(emp)
        oficina = usa_jornada_oficina(emp)
        punches = indexed.get(dni) or {}
        for d in _iter_days(start, end):
            if d.weekday() >= 5 or d in holidays:
                continue
            if not cuenta_asistencia_el_dia(emp, d):
                continue
            if f"{emp['dni']}|{d.isoformat()}" in daily_set or f"{dni}|{d.isoformat()}" in daily_set:
                continue
            row = punches.get(d) or {}
            n = int(row.get("n") or 0)
            n_rows = int(row.get("n_rows") or 0)
            entrada = row.get("entrada")
            salida = row.get("salida")
            dispositivo = str(row.get("dispositivo") or "")
            ent_lim, sal_min = limites_jornada(dispositivo, emp)
            presente = n > 0 or n_rows > 0 or entrada is not None or salida is not None
            if not oficina:
                kind = "cumple" if presente else "no_marcan"
            elif n_rows > 0 and n == 0 and (entrada is None or salida is None):
                kind = "sin_hora"
            else:
                kind = classify_shift(
                    entrada, salida, n, entrada_limite=ent_lim, salida_minima=sal_min
                )
            yield {
                "dni": dni,
                "nombre": emp.get("nombre") or dni,
                "area": area,
                "tipo_personal": (emp.get("tipo_personal") or "").strip(),
                "cargo": (emp.get("cargo_actual") or "").strip(),
                "bucket": bucket,
                "oficina": oficina,
                "fecha": d,
                "weekday": d.weekday(),
                "kind": kind,
                "motivo": motivo_no_marcan(oficina, n, entrada, salida) if kind == "no_marcan" else "",
                "n": n,
                "entrada": entrada,
                "salida": salida,
                "dispositivo": dispositivo,
                "ent_lim": ent_lim,
                "sal_min": sal_min,
                "sede": "Trujillo" if es_sede_trujillo(dispositivo, emp) else "Paiján",
            }


def _resumen_no_marcan(eventos: list[dict]) -> dict:
    rows = [e for e in eventos if e["kind"] == "no_marcan"]
    por_dia_map: dict[date, dict[str, int]] = defaultdict(
        lambda: {"casos": 0, "sin_marca": 0, "una_marca": 0, "operativo_sin_marca": 0}
    )
    for e in rows:
        bucket = por_dia_map[e["fecha"]]
        bucket["casos"] += 1
        mot = e.get("motivo") or "sin_marca"
        if mot in bucket:
            bucket[mot] += 1
    por_dia = [
        {
            "fecha": d.isoformat(),
            "dia": DIAS_SEMANA[d.weekday()],
            **vals,
        }
        for d, vals in sorted(por_dia_map.items())
    ]
    return {
        "casos": len(rows),
        "personas": len({e["dni"] for e in rows}),
        "sin_marca": sum(1 for e in rows if e.get("motivo") == "sin_marca"),
        "una_marca": sum(1 for e in rows if e.get("motivo") == "una_marca"),
        "operativo_sin_marca": sum(1 for e in rows if e.get("motivo") == "operativo_sin_marca"),
        "por_dia": por_dia,
    }


def build_asistencia_kpis(
    employees: list[dict],
    daily_set: set[str],
    shifts: dict[str, dict[date, dict[str, Any]]],
    *,
    start: date,
    end: date,
    configured: bool,
    times_ok: bool,
) -> dict:
    total_people = len(employees)
    dist = defaultdict(int)
    dist_min = defaultdict(int)
    late_mins: list[int] = []
    early_mins: list[int] = []
    weekday_bad = [0] * 7
    weekday_n = [0] * 7
    area_all: dict[str, set[str]] = defaultdict(set)
    area_jornada_ok: dict[str, int] = defaultdict(int)
    area_jornada_bad: dict[str, int] = defaultdict(int)
    tipo_ok: dict[str, int] = defaultdict(int)
    tipo_bad: dict[str, int] = defaultdict(int)
    person_inc: dict[str, dict] = {}
    evaluados = 0
    personas_incumplen = 0
    evaluable_days = 0
    cumple_days = 0

    for emp in employees:
        dni = norm_dni(emp["dni"])
        if exento_control_asistencia(emp):
            continue
        if not vigente_en_periodo(emp, start, end):
            continue
        evaluados += 1
        area = (emp.get("area") or "Sin área").strip() or "Sin área"
        area_all[area].add(dni)
        person_inc.setdefault(
            dni,
            {"nombre": emp.get("nombre") or dni, "area": area, "incidentes": 0, "minutos": 0},
        )

    eventos = list(iter_asistencia_eventos(employees, daily_set, shifts, start=start, end=end))
    incumplen_dnis: set[str] = set()
    for ev in eventos:
        kind = ev["kind"]
        dni = ev["dni"]
        area = ev["area"]
        bucket = ev["bucket"]
        wd = ev["weekday"]
        entrada = ev["entrada"]
        salida = ev["salida"]
        ent_lim = ev["ent_lim"]
        sal_min = ev["sal_min"]
        person = person_inc[dni]
        if kind == "sin_hora":
            continue
        if kind == "no_marcan":
            dist[kind] += 1
            continue
        weekday_n[wd] += 1
        if kind == "cumple":
            evaluable_days += 1
            cumple_days += 1
            tipo_ok[bucket] += 1
            area_jornada_ok[area] += 1
            continue
        evaluable_days += 1
        tipo_bad[bucket] += 1
        area_jornada_bad[area] += 1
        incumplen_dnis.add(dni)
        lost = lost_minutes(kind, entrada, salida, entrada_limite=ent_lim, salida_minima=sal_min)
        dist[kind] += 1
        dist_min[kind] += lost
        person["incidentes"] += 1
        person["minutos"] += lost
        weekday_bad[wd] += 1
        if kind in ("tardanza", "jornada") and entrada and entrada > ent_lim:
            late_mins.append(minutes_of(entrada) - minutes_of(ent_lim))
        if kind in ("salida_temprano", "jornada") and salida and salida < sal_min:
            early_mins.append(minutes_of(sal_min) - minutes_of(salida))
    personas_incumplen = len(incumplen_dnis)
    no_marcan = _resumen_no_marcan(eventos)

    total_lost = sum(dist_min.values())
    clock_days = max(1, evaluable_days)
    incumple_pct = round(100 * (evaluable_days - cumple_days) / clock_days, 1) if evaluable_days else 0.0
    cumple_pct = round(100 * cumple_days / clock_days, 1) if evaluable_days else 0.0
    dias_eq = round(total_lost / JORNADA_MINUTOS, 1) if total_lost else 0.0
    jornadas_fuera = max(0, evaluable_days - cumple_days)
    pct_personas = round(100 * personas_incumplen / evaluados, 1) if evaluados else 0.0
    detalle_incumplimiento = {
        "jornadas_con_2_marcas": evaluable_days,
        "jornadas_ok": cumple_days,
        "jornadas_fuera": jornadas_fuera,
        "pct_jornadas": incumple_pct,
        "personas_evaluadas": evaluados,
        "personas_con_al_menos_un_dia": personas_incumplen,
        "pct_personas": pct_personas,
        "tardanzas": dist["tardanza"],
        "salidas_temprano": dist["salida_temprano"],
        "ambos": dist["jornada"],
    }

    dist_rows = [
        ("tardanza", "Tardanzas", dist["tardanza"]),
        ("salida_temprano", "Salidas temprano", dist["salida_temprano"]),
        ("jornada", "Llega tarde y sale temprano", dist["jornada"]),
    ]
    dist_total = sum(v for _, _, v in dist_rows) or 1
    distribucion = [
        {
            "key": k,
            "label": lab,
            "value": v,
            "pct": round(100 * v / dist_total, 1),
        }
        for k, lab, v in dist_rows
        if v
    ]

    late_n = dist["tardanza"] + dist["jornada"]
    early_n = dist["salida_temprano"] + dist["jornada"]

    ranking_area = []
    for name, all_dnis in area_all.items():
        ok_d = area_jornada_ok[name]
        bad_d = area_jornada_bad[name]
        n_j = ok_d + bad_d
        if n_j == 0:
            continue
        pct = round(100 * bad_d / n_j, 1)
        ranking_area.append(
            {
                "name": name,
                "short": name[:16] + ("…" if len(name) > 16 else ""),
                "evaluados": len(all_dnis),
                "incumplen": bad_d,
                "pct": pct,
                "label": f"{pct}%",
            }
        )
    ranking_area.sort(key=lambda r: r["pct"], reverse=True)

    ranking_personas = sorted(
        (p for p in person_inc.values() if p["incidentes"] > 0),
        key=lambda p: (p["incidentes"], p["minutos"]),
        reverse=True,
    )[:10]
    for p in ranking_personas:
        p["horas_txt"] = format_hm(p["minutos"])

    por_tipo = []
    tipo_names = sorted(set(tipo_ok) | set(tipo_bad))
    for name in tipo_names:
        ok = tipo_ok[name]
        bad = tipo_bad[name]
        n = ok + bad
        if n == 0:
            continue
        por_tipo.append(
            {
                "name": name,
                "n": n,
                "cumple": ok,
                "incumple": bad,
                "cumple_pct": round(100 * ok / n, 1),
                "incumple_pct": round(100 * bad / n, 1),
            }
        )
    por_tipo.sort(key=lambda r: r["incumple_pct"], reverse=True)

    tendencia = []
    for i, lab in enumerate(DIAS_SEMANA):
        n = weekday_n[i]
        pct = round(100 * weekday_bad[i] / n, 1) if n else 0.0
        tendencia.append({"dia": i, "label": lab, "pct": pct, "casos": weekday_bad[i], "n": n})
    tendencia = tendencia[:5]

    recomendaciones = []
    if late_n:
        recomendaciones.append(
            {
                "title": "Llegadas fuera de margen",
                "body": f"{late_n} jornadas con entrada fuera del margen de su sede.",
            }
        )
    if early_n:
        recomendaciones.append(
            {
                "title": "Salidas antes de las 17:05",
                "body": f"{early_n} jornadas salen antes del horario de su sede.",
            }
        )
    if dist["no_marcan"]:
        recomendaciones.append(
            {
                "title": "Marcación incompleta o ausente",
                "body": f"{dist['no_marcan']} días laborables sin entrada y salida.",
            }
        )
    if ranking_area:
        top = ranking_area[0]
        recomendaciones.append(
            {
                "title": f"Revisar {top['name']}",
                "body": f"{top['pct']}% de jornadas fuera de margen en {top['name']}.",
            }
        )

    alerta = None
    if personas_incumplen and dias_eq >= 1:
        alerta = {
            "nivel": "alto" if incumple_pct >= 25 else "medio",
            "texto": (
                f"{dias_eq} días equivalentes de jornada se pierden en el periodo "
                f"({format_hm(total_lost)}). {personas_incumplen} colaboradores fuera de margen."
            ),
        }

    return {
        "configured": configured,
        "times_ok": times_ok,
        "periodo": {"desde": start.isoformat(), "hasta": end.isoformat()},
        "horario": {
            "entrada": ENTRADA_OFICIAL.strftime("%H:%M"),
            "salida": SALIDA_OFICIAL.strftime("%H:%M"),
            "margen_entrada": ENTRADA_LIMITE.strftime("%H:%M"),
            "jornada_minutos": JORNADA_MINUTOS,
            "trujillo": {
                "entrada": TRUJILLO_ENTRADA.strftime("%H:%M"),
                "margen_entrada": TRUJILLO_MARGEN.strftime("%H:%M"),
                "salida": TRUJILLO_SALIDA.strftime("%H:%M"),
            },
        },
        "total_people": total_people,
        "evaluados": evaluados,
        "incumplimiento_pct": incumple_pct,
        "personas_incumplen": personas_incumplen,
        "detalle_incumplimiento": detalle_incumplimiento,
        "horas_no_laboradas_min": total_lost,
        "horas_no_laboradas_txt": format_hm(total_lost),
        "dias_equivalentes": dias_eq,
        "llegadas_tarde": {
            "casos": late_n,
            "promedio_min": round(sum(late_mins) / len(late_mins)) if late_mins else 0,
        },
        "salidas_temprano": {
            "casos": early_n,
            "promedio_min": round(sum(early_mins) / len(early_mins)) if early_mins else 0,
        },
        "no_marcan": no_marcan,
        "cumplimiento_jornada_pct": cumple_pct,
        "distribucion": distribucion,
        "horas_por_categoria": [
            {"key": k, "label": lab, "minutos": dist_min[k], "txt": format_hm(dist_min[k])}
            for k, lab, _ in dist_rows
            if dist_min[k]
        ],
        "tendencia_semana": tendencia,
        "ranking_area": ranking_area[:8],
        "ranking_personas": ranking_personas,
        "por_tipo": por_tipo,
        "recomendaciones": recomendaciones[:4],
        "alerta": alerta,
    }
