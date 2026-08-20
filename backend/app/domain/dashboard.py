from __future__ import annotations

from datetime import date

from .calendar import TOTAL_SEMANAS, key_daily, week_dates, week_label


def build_dashboard(employees, targets, daily_set, year, today: date | None = None):
    today = today or date.today()
    current_year, current_week, _ = today.isocalendar()
    dnis = [str(w["dni"]) for w in employees]
    dni_to_row = {str(w["dni"]): w for w in employees}
    total_people = len(employees)

    dias_por_dni: dict[str, int] = {}
    for (dni, _week), dias in targets.items():
        if dni in dni_to_row:
            dias_por_dni[dni] = dias_por_dni.get(dni, 0) + int(dias)

    agg_gerencia, agg_area, agg_tipo, agg_jefatura = {}, {}, {}, {}
    for dni, dias in dias_por_dni.items():
        w = dni_to_row.get(dni)
        if w is None or dias <= 0:
            continue
        agg_gerencia[w["gerencia"]] = agg_gerencia.get(w["gerencia"], 0) + dias
        agg_area[w["area"]] = agg_area.get(w["area"], 0) + dias
        agg_tipo[w["tipo_personal"]] = agg_tipo.get(w["tipo_personal"], 0) + dias
        agg_jefatura[w["jefatura"]] = agg_jefatura.get(w["jefatura"], 0) + dias

    heatmap = [[0] * TOTAL_SEMANAS for _ in range(7)]
    weekly_unique_absent = [0] * TOTAL_SEMANAS
    week_max_absent = [0] * TOTAL_SEMANAS

    for week in range(1, TOTAL_SEMANAS + 1):
        dates = week_dates(year, week)
        personas_semana = set()
        for idx, d in enumerate(dates):
            count = 0
            for dni in dnis:
                if key_daily(dni, d) in daily_set:
                    count += 1
                    personas_semana.add(dni)
            heatmap[idx][week - 1] = count
        weekly_unique_absent[week - 1] = len(personas_semana)
        week_max_absent[week - 1] = max((heatmap[idx][week - 1] for idx in range(7)), default=0)

    week_risk_rows = []
    for week in range(1, TOTAL_SEMANAS + 1):
        max_absent = week_max_absent[week - 1]
        week_risk_rows.append({
            "semana": week,
            "periodo": week_label(year, week),
            "max_ausentes_dia": max_absent,
            "max_ausencia_pct": (max_absent / total_people) if total_people else 0,
        })
    week_risk = sorted(week_risk_rows, key=lambda r: r["max_ausentes_dia"], reverse=True)

    personas_hoy = 0
    if year == current_year:
        personas_hoy = sum(key_daily(dni, today) in daily_set for dni in dnis)

    if year == current_year:
        futuras = [r for r in week_risk_rows if r["semana"] >= current_week]
    elif year > current_year:
        futuras = week_risk_rows
    else:
        futuras = []
    proximas_criticas = sorted(futuras, key=lambda r: r["max_ausentes_dia"], reverse=True)[:3]
    programados = sum(1 for dni in dnis if dias_por_dni.get(dni, 0) > 0)

    return {
        "total_people": total_people,
        "programados": programados,
        "pendientes": max(total_people - programados, 0),
        "dias_totales": sum(dias_por_dni.values()),
        "personas_hoy": personas_hoy,
        "cobertura_prom": (
            1 - (sum(weekly_unique_absent) / (total_people * TOTAL_SEMANAS))
            if total_people
            else 1
        ),
        "agg_gerencia": agg_gerencia,
        "agg_area": agg_area,
        "agg_tipo": agg_tipo,
        "agg_jefatura": agg_jefatura,
        "heatmap": heatmap,
        "weekly_unique_absent": weekly_unique_absent,
        "week_risk": week_risk,
        "proximas_criticas": proximas_criticas,
        "current_week": current_week if year == current_year else None,
    }
