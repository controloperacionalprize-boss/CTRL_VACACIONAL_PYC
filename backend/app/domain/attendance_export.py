"""Excel de detalle de asistencia (persona × día)."""
from __future__ import annotations

from datetime import date, time
from io import BytesIO
from typing import Any

import pandas as pd

from .attendance_kpis import DIAS_SEMANA, iter_asistencia_eventos

KIND_LABEL = {
    "cumple": "Cumple",
    "tardanza": "Tardanza",
    "salida_temprano": "Salida temprana",
    "jornada": "Tarde y sale temprano",
    "no_marcan": "No marcan",
    "sin_hora": "Presencia sin hora",
}
MOTIVO_LABEL = {
    "sin_marca": "Sin ninguna marca",
    "una_marca": "Solo una marca",
    "operativo_sin_marca": "Operativo/planta sin marca",
}


def _hm(t: time | None) -> str:
    if t is None:
        return ""
    return t.strftime("%H:%M")


def export_asistencia_excel(
    employees: list[dict],
    daily_set: set[str],
    shifts: dict[str, dict[date, dict[str, Any]]],
    *,
    start: date,
    end: date,
    kpis: dict,
) -> bytes:
    eventos = list(iter_asistencia_eventos(employees, daily_set, shifts, start=start, end=end))
    detalle = [
        {
            "Fecha": e["fecha"].isoformat(),
            "Día": DIAS_SEMANA[e["weekday"]],
            "DNI": e["dni"],
            "Nombre": e["nombre"],
            "Área": e["area"],
            "Tipo personal": e["tipo_personal"],
            "Cargo": e["cargo"],
            "Sede": e["sede"],
            "Resultado": KIND_LABEL.get(e["kind"], e["kind"]),
            "Motivo no marca": MOTIVO_LABEL.get(e["motivo"], e["motivo"]),
            "Marcas": e["n"],
            "Entrada": _hm(e["entrada"]),
            "Salida": _hm(e["salida"]),
            "Dispositivo": e["dispositivo"],
        }
        for e in eventos
    ]
    no_marcan = [r for r in detalle if r["Resultado"] == KIND_LABEL["no_marcan"]]
    incumple = [r for r in detalle if r["Resultado"] in (
        KIND_LABEL["tardanza"],
        KIND_LABEL["salida_temprano"],
        KIND_LABEL["jornada"],
    )]

    por_dia_rows = []
    for row in kpis.get("no_marcan", {}).get("por_dia") or []:
        por_dia_rows.append(
            {
                "Fecha": row["fecha"],
                "Día": row["dia"],
                "No marcan (persona-días)": row["casos"],
                "Sin ninguna marca": row.get("sin_marca", 0),
                "Solo una marca": row.get("una_marca", 0),
                "Operativo/planta sin marca": row.get("operativo_sin_marca", 0),
            }
        )

    por_persona: dict[str, dict] = {}
    for e in eventos:
        p = por_persona.setdefault(
            e["dni"],
            {
                "DNI": e["dni"],
                "Nombre": e["nombre"],
                "Área": e["area"],
                "Tipo personal": e["tipo_personal"],
                "No marcan": 0,
                "Sin ninguna marca": 0,
                "Solo una marca": 0,
                "Operativo sin marca": 0,
                "Cumple": 0,
                "Tardanza": 0,
                "Salida temprana": 0,
                "Tarde y sale temprano": 0,
            },
        )
        kind = e["kind"]
        if kind == "no_marcan":
            p["No marcan"] += 1
            mot = e.get("motivo") or ""
            if mot == "sin_marca":
                p["Sin ninguna marca"] += 1
            elif mot == "una_marca":
                p["Solo una marca"] += 1
            elif mot == "operativo_sin_marca":
                p["Operativo sin marca"] += 1
        elif kind == "cumple":
            p["Cumple"] += 1
        elif kind == "tardanza":
            p["Tardanza"] += 1
        elif kind == "salida_temprano":
            p["Salida temprana"] += 1
        elif kind == "jornada":
            p["Tarde y sale temprano"] += 1
    personas = sorted(por_persona.values(), key=lambda r: r["No marcan"], reverse=True)

    nm = kpis.get("no_marcan") or {}
    det = kpis.get("detalle_incumplimiento") or {}
    resumen = [
        {"Dato": "Periodo desde", "Valor": start.isoformat()},
        {"Dato": "Periodo hasta", "Valor": end.isoformat()},
        {"Dato": "Evaluados", "Valor": kpis.get("evaluados", 0)},
        {"Dato": "Incumplimiento % (jornadas)", "Valor": kpis.get("incumplimiento_pct", 0)},
        {"Dato": "Jornadas con 2 marcas", "Valor": det.get("jornadas_con_2_marcas", 0)},
        {"Dato": "Jornadas fuera de margen", "Valor": det.get("jornadas_fuera", 0)},
        {"Dato": "No marcan (persona-días)", "Valor": nm.get("casos", 0)},
        {"Dato": "Personas con al menos un día sin marcar", "Valor": nm.get("personas", 0)},
        {"Dato": "Sin ninguna marca", "Valor": nm.get("sin_marca", 0)},
        {"Dato": "Solo una marca", "Valor": nm.get("una_marca", 0)},
        {"Dato": "Operativo/planta sin marca", "Valor": nm.get("operativo_sin_marca", 0)},
        {
            "Dato": "Nota",
            "Valor": "No marcan suma persona × día laborable, no personas distintas. Vacaciones del plan no entran.",
        },
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(resumen).to_excel(writer, sheet_name="Resumen", index=False)
        pd.DataFrame(por_dia_rows).to_excel(writer, sheet_name="No_marcan_por_dia", index=False)
        pd.DataFrame(no_marcan).to_excel(writer, sheet_name="No_marcan", index=False)
        pd.DataFrame(personas).to_excel(writer, sheet_name="Por_persona", index=False)
        pd.DataFrame(incumple).to_excel(writer, sheet_name="Fuera_de_margen", index=False)
        pd.DataFrame(detalle).to_excel(writer, sheet_name="Detalle_diario", index=False)
        for ws in writer.book.worksheets:
            ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "A2"
    return output.getvalue()
