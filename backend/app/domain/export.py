from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd

from .calendar import TOTAL_SEMANAS, add_years, format_antiguedad, group_consecutive_dates
from .plan import daily_rows, group_periods


def semaforo_fill(value):
    try:
        value = int(value)
    except Exception:
        return None
    colors = {1: "F8696B", 2: "F8696B", 3: "F9C47A", 4: "FFEB84", 5: "FFEB84", 6: "9ED17A", 7: "63BE7B"}
    color = colors.get(value)
    return PatternFill("solid", fgColor=color) if color else None


def build_record(employees, dias_map: dict[str, list[date]]):
    rows = []
    for w in employees:
        dni = str(w["dni"])
        f_ingreso = w.get("fecha_ingreso")
        if isinstance(f_ingreso, str) and f_ingreso:
            f_ingreso = date.fromisoformat(f_ingreso[:10])
        tiene = isinstance(f_ingreso, date)
        if tiene:
            record = f"{f_ingreso.year}-{f_ingreso.year + 1}"
            cumple = add_years(f_ingreso, 1) - timedelta(days=1)
            vencimiento = add_years(f_ingreso, 2) - timedelta(days=1)
            dias_gozados = sum(1 for d in dias_map.get(dni, []) if cumple <= d <= vencimiento)
            dias_pendientes = 30 - dias_gozados
        else:
            record = ""
            cumple = vencimiento = None
            dias_gozados = dias_pendientes = None
        rows.append({
            "EMPRESA": w.get("empresa", ""),
            "DNI": dni,
            "NOMBRE": w["nombre"],
            "FECHA_INGRESO": f_ingreso.strftime("%d/%m/%Y") if tiene else "",
            "DIVISION": w.get("division", ""),
            "GERENCIA": w["gerencia"],
            "AREA": w["area"],
            "RECORD_VACACIONAL": record,
            "CUMPLE_RECORD": cumple.strftime("%d/%m/%Y") if cumple else "",
            "DIAS_PENDIENTES": dias_pendientes,
            "DIAS_GOZADOS": dias_gozados,
            "FECHA_VENCIMIENTO": vencimiento.strftime("%d/%m/%Y") if vencimiento else "",
            "ANTIGUEDAD": format_antiguedad(f_ingreso if tiene else None),
        })
    return rows


def employee_calendar_payload(worker, anio: int, fechas: list[date]):
    f_ingreso = worker.get("fecha_ingreso")
    if isinstance(f_ingreso, str) and f_ingreso:
        f_ingreso = date.fromisoformat(f_ingreso[:10])
    periods = group_consecutive_dates(fechas)
    period_rows = []
    for ini, fin in periods:
        duracion = sum(1 for d in fechas if ini <= d <= fin)
        period_rows.append({
            "tipo": "Vacaciones",
            "inicio": ini.isoformat(),
            "fin": fin.isoformat(),
            "dias": duracion,
        })
    return {
        "empleado": worker,
        "anio": anio,
        "antiguedad": format_antiguedad(f_ingreso if isinstance(f_ingreso, date) else None),
        "consumido": len(fechas),
        "disponible": max(30 - len(fechas), -99),
        "fechas": [d.isoformat() for d in fechas],
        "periodos": period_rows,
    }


def export_excel(
    employees,
    daily_set,
    targets,
    year,
    label_jefatura,
    current_year,
    current_week,
    change_counts,
    change_log,
    usuario,
    nombre_usuario,
    historial=None,
):
    daily = daily_rows(employees, daily_set, year)
    periods = group_periods(employees, daily_set, year)
    weekly_rows = []
    for w in sorted(employees, key=lambda x: str(x["nombre"]).casefold()):
        dni = str(w["dni"])
        weeks = {f"S{week}": int(targets.get((dni, week), 0)) for week in range(1, TOTAL_SEMANAS + 1)}
        f_ing = w.get("fecha_ingreso")
        if isinstance(f_ing, date):
            f_ing_str = f_ing.strftime("%d/%m/%Y")
        elif f_ing:
            f_ing_str = str(f_ing)
        else:
            f_ing_str = ""
        changes = int(change_counts.get(dni, 0))
        row = {
            "EMPRESA": w.get("empresa", ""),
            "NOMBRE": w["nombre"],
            "DNI": dni,
            "DIVISION": w.get("division", ""),
            "GERENCIA": w["gerencia"],
            "AREA": w["area"],
            "CARGO_ACTUAL": w.get("cargo_actual", ""),
            "F_INGRESO": f_ing_str,
            "TIPO": w["tipo_personal"],
            "TOTAL_DIAS": sum(weeks.values()),
            "CAMBIOS": f"{changes} cambio" if changes == 1 else f"{changes} cambios",
            **weeks,
        }
        weekly_rows.append(row)

    summary = pd.DataFrame([{
        "JEFATURA": label_jefatura,
        "AÑO": year,
        "TRABAJADORES": len(employees),
        "PERSONAS_PROGRAMADAS": len({r["dni"] for r in daily}),
        "DIAS_PROGRAMADOS": len(daily),
        "GENERADO": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "USUARIO_GENERADOR": usuario,
        "NOMBRE_USUARIO": nombre_usuario,
    }])
    periods_df = pd.DataFrame(periods) if periods else pd.DataFrame(
        columns=["dni", "nombre", "gerencia", "area", "jefatura", "tipo_personal", "semana", "fecha_inicio", "fecha_fin", "dias"]
    )
    daily_df = pd.DataFrame(daily) if daily else pd.DataFrame()
    weekly_df = pd.DataFrame(weekly_rows)
    historial_df = pd.DataFrame(historial) if historial else pd.DataFrame()
    change_df = pd.DataFrame(change_log) if change_log else pd.DataFrame()

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="RESUMEN", index=False)
        periods_df.to_excel(writer, sheet_name="VACACIONES", index=False)
        daily_df.to_excel(writer, sheet_name="DETALLE_DIARIO", index=False)
        weekly_df.to_excel(writer, sheet_name="PLAN_SEMANAL", index=False)
        historial_df.to_excel(writer, sheet_name="HISTORIAL", index=False)
        change_df.to_excel(writer, sheet_name="CAMBIOS", index=False)
    output.seek(0)

    wb = load_workbook(output)
    thin = Side(style="thin", color="D0D5DD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="0F172A")
    current_fill = PatternFill("solid", fgColor="0F766E")
    history_fill = PatternFill("solid", fgColor="D0D5DD")

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
        ws.auto_filter.ref = ws.dimensions
        for column_cells in ws.columns:
            max_len = 0
            for cell in column_cells:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
                cell.border = border
                cell.alignment = Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(max_len + 2, 10), 35)

    ws = wb["PLAN_SEMANAL"]
    for col_idx in range(1, ws.max_column + 1):
        header = str(ws.cell(1, col_idx).value or "")
        if header.startswith("S") and header[1:].isdigit():
            week = int(header[1:])
            if year == current_year and week == current_week:
                ws.cell(1, col_idx).fill = current_fill
            elif year == current_year and week < current_week:
                ws.cell(1, col_idx).fill = history_fill
            for row_idx in range(2, ws.max_row + 1):
                fill = semaforo_fill(ws.cell(row_idx, col_idx).value)
                if fill:
                    ws.cell(row_idx, col_idx).fill = fill
                    ws.cell(row_idx, col_idx).font = Font(bold=True, color="000000")

    legend = [
        ("SEMAFORO 1–7 DÍAS", ""),
        ("1–2 días", "F8696B"),
        ("3 días", "F9C47A"),
        ("4–5 días", "FFEB84"),
        ("6 días", "9ED17A"),
        ("7 días", "63BE7B"),
        ("0 días", "FFFFFF"),
    ]
    start_col = ws.max_column + 2
    for i, (label, color) in enumerate(legend, start=1):
        c1 = ws.cell(1 + i, start_col, label)
        if color:
            c1.fill = PatternFill("solid", fgColor=color)
        c1.border = border
    ws.freeze_panes = "F2"

    output2 = BytesIO()
    wb.save(output2)
    output2.seek(0)
    return output2.getvalue()
