from datetime import date
from io import BytesIO
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.attendance import fetch_merged_attendance
from app.attendance_excel import encode_sharing_url, parse_attendance_excel
from app.domain.employee_calendar import employee_calendar_payload


def test_encode_sharing_url():
    sid = encode_sharing_url("https://aquanqape.sharepoint.com/:x:/s/OficinasPrizePeru/abc")
    assert sid.startswith("u!")


def test_parse_excel_documento_fecha():
    buf = BytesIO()
    df = pd.DataFrame(
        {
            "Documento": ["123", "123", "999"],
            "Fecha": ["17/08/2026", "18/08/2026", "20/08/2026"],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="AQ1", index=False)
    by_dni, mx = parse_attendance_excel(buf.getvalue())
    assert by_dni["123"] == {date(2026, 8, 17), date(2026, 8, 18)}
    assert mx == date(2026, 8, 20)


def test_merge_excel_completa_despues_de_bd(monkeypatch):
    db = {date(2026, 8, 14), date(2026, 8, 15), date(2026, 8, 16)}
    xl = {
        date(2026, 8, 15),
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 23),
    }
    monkeypatch.setattr("app.attendance.attendance_configured", lambda: True)
    monkeypatch.setattr("app.attendance.excel_attendance_configured", lambda: True)
    monkeypatch.setattr("app.attendance.fetch_attendance_dates", lambda dni, year: set(db))
    monkeypatch.setattr("app.attendance.fetch_excel_attendance_dates", lambda dni, year: set(xl))
    monkeypatch.setattr("app.attendance.excel_attendance_ok", lambda: True)
    monkeypatch.setattr("app.attendance.excel_coverage_max_date", lambda year: date(2026, 8, 23))

    merged, ok, coverage = fetch_merged_attendance("123", 2026)
    assert ok is True
    assert date(2026, 8, 16) in merged
    assert date(2026, 8, 17) in merged
    assert date(2026, 8, 23) in merged
    assert coverage == date(2026, 8, 23)


def test_coverage_until_no_pinta_faltas_despues():
    worker = {
        "dni": "1",
        "nombre": "Pepe",
        "empresa": "X",
        "area": "A",
        "cargo_actual": "C",
        "fecha_ingreso": "2026-01-01",
        "gerencia": "G",
    }
    payload = employee_calendar_payload(
        worker,
        2026,
        [],
        asistencia={date(2026, 8, 20)},
        attendance_ok=True,
        coverage_until=date(2026, 8, 23),
    )
    assert "2026-08-21" in payload["sin_marcacion"]
    assert all(d <= "2026-08-23" for d in payload["sin_marcacion"])
