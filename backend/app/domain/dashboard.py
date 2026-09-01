from __future__ import annotations

from collections import defaultdict
from datetime import date

from .calendar import (
    TOTAL_SEMANAS,
    es_apto,
    key_daily,
    parse_daily_key,
    today_lima,
    week_label,
)


def build_dashboard(employees, targets, daily_set, year, today: date | None = None):
    today = today or today_lima()
    plantilla = list(employees)
    aptos = [w for w in plantilla if es_apto(w, today)]
    current_year, current_week, _ = today.isocalendar()
    dni_to_row = {str(w["dni"]): w for w in aptos}
    n_aptos = len(aptos)

    dias_por_dni: dict[str, int] = defaultdict(int)
    for (dni, _week), dias in targets.items():
        if dni in dni_to_row:
            dias_por_dni[dni] += int(dias)

    agg_gerencia: dict[str, int] = defaultdict(int)
    agg_area: dict[str, int] = defaultdict(int)
    agg_tipo: dict[str, int] = defaultdict(int)
    agg_jefatura: dict[str, int] = defaultdict(int)
    for dni, dias in dias_por_dni.items():
        if dias <= 0:
            continue
        w = dni_to_row[dni]
        agg_gerencia[w["gerencia"]] += dias
        agg_area[w["area"]] += dias
        agg_tipo[w["tipo_personal"]] += dias
        agg_jefatura[w["jefatura"]] += dias

    heatmap = [[0] * TOTAL_SEMANAS for _ in range(7)]
    week_people: list[set[str]] = [set() for _ in range(TOTAL_SEMANAS)]
    for item in daily_set:
        dni, d = parse_daily_key(item)
        if dni not in dni_to_row:
            continue
        iso_y, iso_w, iso_wd = d.isocalendar()
        if iso_y != year or not (1 <= iso_w <= TOTAL_SEMANAS):
            continue
        heatmap[iso_wd - 1][iso_w - 1] += 1
        week_people[iso_w - 1].add(dni)

    weekly_unique_absent = [len(s) for s in week_people]
    week_risk_rows = []
    for week in range(1, TOTAL_SEMANAS + 1):
        mx = max(heatmap[r][week - 1] for r in range(7))
        week_risk_rows.append({
            "semana": week,
            "periodo": week_label(year, week),
            "max_ausentes_dia": mx,
            "max_ausencia_pct": (mx / n_aptos) if n_aptos else 0,
        })
    week_risk = sorted(week_risk_rows, key=lambda r: r["max_ausentes_dia"], reverse=True)

    personas_hoy = 0
    if year == current_year:
        personas_hoy = sum(key_daily(dni, today) in daily_set for dni in dni_to_row)

    if year == current_year:
        futuras = [r for r in week_risk_rows if r["semana"] >= current_week]
    elif year > current_year:
        futuras = week_risk_rows
    else:
        futuras = []
    programados = sum(1 for n in dias_por_dni.values() if n > 0)

    return {
        "total_people": len(plantilla),
        "aptos": n_aptos,
        "programados": programados,
        "pendientes": max(n_aptos - programados, 0),
        "dias_totales": sum(dias_por_dni.values()),
        "personas_hoy": personas_hoy,
        "cobertura_prom": (
            1 - (sum(weekly_unique_absent) / (n_aptos * TOTAL_SEMANAS)) if n_aptos else 1
        ),
        "agg_gerencia": dict(agg_gerencia),
        "agg_area": dict(agg_area),
        "agg_tipo": dict(agg_tipo),
        "agg_jefatura": dict(agg_jefatura),
        "heatmap": heatmap,
        "weekly_unique_absent": weekly_unique_absent,
        "week_risk": week_risk,
        "proximas_criticas": sorted(futuras, key=lambda r: r["max_ausentes_dia"], reverse=True)[:3],
        "current_week": current_week if year == current_year else None,
    }
