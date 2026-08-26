from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from app.domain.calendar import vacation_record_for
from app.domain.employee_calendar import employee_calendar_payload
from app.domain.export import export_excel


def test_record_primer_anio():
    rec = vacation_record_for(date(2026, 1, 1), [], 2026, today=date(2026, 8, 21))
    assert rec["record_vacacional"] == "2026-2027"
    assert rec["cumple_record"] == date(2027, 1, 1)
    assert rec["record_cumplido"] is False
    assert rec["dias_pendientes"] == 30


def test_record_cuenta_programados_y_gozados():
    programmed = [date(2026, 8, 1), date(2026, 8, 2), date(2026, 9, 1)]
    rec = vacation_record_for(date(2026, 1, 1), programmed, 2026, today=date(2026, 8, 21))
    assert rec["dias_programados"] == 3
    assert rec["dias_gozados"] == 2  # 1 y 2 ago ya pasaron
    assert rec["dias_pendientes"] == 27


def test_calendar_payload_incluye_record():
    worker = {
        "dni": "1",
        "nombre": "Pepe",
        "empresa": "X",
        "area": "A",
        "cargo_actual": "C",
        "fecha_ingreso": "2026-01-01",
        "gerencia": "G",
    }
    payload = employee_calendar_payload(worker, 2026, [date(2026, 9, 1), date(2026, 9, 2)])
    assert payload["record"]["record_vacacional"] == "2026-2027"
    assert payload["record"]["dias_programados"] == 2
    assert payload["periodos"][0]["inicio"] == "2026-09-01"
    assert payload["periodos"][0]["fin"] == "2026-09-02"


def test_excel_hojas_alineadas_con_web():
    data = export_excel([], set(), {}, 2026, "X", 2026, 34, [], "u", "n", [])
    wb = load_workbook(BytesIO(data))
    assert wb.sheetnames == ["RESUMEN", "PLANIFICACION", "PERIODOS", "RECORD_VACACIONAL", "CAMBIOS"]
    assert "DETALLE_DIARIO" not in wb.sheetnames
    assert "PLAN_SEMANAL" not in wb.sheetnames
    assert "VACACIONES" not in wb.sheetnames
