from datetime import date
from io import BytesIO

import pandas as pd

from app.attendance import fetch_merged_attendance
from app import attendance_excel as xlmod
from app.attendance_excel import encode_sharing_url, parse_attendance_excel
from app.domain.employee_calendar import employee_calendar_payload


def _reset_xl_cache():
    with xlmod._LOCK:
        xlmod._refreshing = False
        xlmod._cache.update(
            {
                "loaded_at": 0.0,
                "loaded_day": None,
                "by_dni": {},
                "max_date": None,
                "ok": False,
                "error": None,
                "fail_until": 0.0,
                "by_dni_shifts": {},
            }
        )


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
    by_dni, mx, _shifts = parse_attendance_excel(buf.getvalue())
    assert by_dni["123"] == {date(2026, 8, 17), date(2026, 8, 18)}
    assert mx == date(2026, 8, 20)


def test_parse_excel_con_hora():
    buf = BytesIO()
    df = pd.DataFrame(
        {
            "Documento": ["123", "123"],
            "Fecha": ["19/08/2026", "19/08/2026"],
            "Tiempo": ["06:50:00", "17:15:00"],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="AQ1", index=False)
    by_dni, mx, shifts = parse_attendance_excel(buf.getvalue())
    row = shifts["123"][date(2026, 8, 19)]
    assert row["n"] == 2
    assert str(row["entrada"])[:5] == "06:50"
    assert str(row["salida"])[:5] == "17:15"
    assert mx == date(2026, 8, 19)


def test_parse_excel_solo_hueco_despues_de_bd():
    buf = BytesIO()
    df = pd.DataFrame(
        {
            "Documento": ["123", "123", "123", "123"],
            "Fecha": ["14/08/2026", "16/08/2026", "17/08/2026", "23/08/2026"],
        }
    )
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="AQ1", index=False)
    by_dni, mx, _shifts = parse_attendance_excel(buf.getvalue(), after=date(2026, 8, 16))
    assert by_dni["123"] == {date(2026, 8, 17), date(2026, 8, 23)}
    assert mx == date(2026, 8, 23)
    assert date(2026, 8, 16) not in by_dni["123"]


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


def test_merge_turnos_excel_completa_hora_si_bd_solo_tiene_fecha(monkeypatch):
    from datetime import time

    from app.attendance import fetch_merged_shifts

    d = date(2026, 8, 19)
    db = {"123": {d: {"entrada": None, "salida": None, "n": 0, "n_rows": 2}}}
    xl = {"123": {d: {"entrada": time(6, 50), "salida": time(17, 15), "n": 2, "n_rows": 2}}}
    monkeypatch.setattr("app.attendance.attendance_configured", lambda: True)
    monkeypatch.setattr("app.attendance.excel_attendance_configured", lambda: True)
    monkeypatch.setattr("app.attendance.fetch_attendance_shifts", lambda *a, **k: db)
    monkeypatch.setattr("app.attendance.fetch_excel_shifts", lambda *a, **k: xl)
    monkeypatch.setattr("app.attendance.fetch_coverage_max_date", lambda: d)
    merged, times_ok = fetch_merged_shifts(["123"], d, d)
    assert times_ok is True
    assert merged["123"][d]["entrada"] == time(6, 50)
    assert merged["123"][d]["salida"] == time(17, 15)


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


def test_excel_en_memoria_no_vuelve_a_descargar(monkeypatch):
    _reset_xl_cache()
    monkeypatch.setattr(
        xlmod,
        "download_excel_bytes",
        lambda **k: (_ for _ in ()).throw(AssertionError("no debe descargar")),
    )
    with xlmod._LOCK:
        xlmod._cache.update(
            {
                "ok": True,
                "loaded_day": xlmod._lima_today(),
                "by_dni": {"123": {date(2026, 8, 17)}},
                "max_date": date(2026, 8, 17),
            }
        )
    days = xlmod.fetch_excel_attendance_dates("123", 2026)
    assert date(2026, 8, 17) in days
    _reset_xl_cache()


def test_calendario_no_espera_si_excel_aun_no_esta(monkeypatch):
    _reset_xl_cache()
    scheduled = []
    monkeypatch.setattr(xlmod, "schedule_excel_refresh", lambda **k: scheduled.append(True))
    days = xlmod.fetch_excel_attendance_dates("123", 2026)
    assert days == set()
    assert scheduled
    _reset_xl_cache()
