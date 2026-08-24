from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.employee_calendar import employee_calendar_payload
from app.domain.holidays_pe import peru_holidays


def test_feriados_2026_incluye_fiestas_patrias_y_semana_santa():
    h = peru_holidays(2026)
    assert date(2026, 7, 28) in h
    assert date(2026, 7, 29) in h
    assert date(2026, 4, 2) in h  # Jueves Santo 2026
    assert date(2026, 4, 3) in h  # Viernes Santo 2026


def test_calendar_payload_colorea_nolab_sin_asistencia():
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
        [date(2026, 8, 21)],
        asistencia={date(2026, 8, 20)},
        attendance_ok=True,
    )
    assert "2026-08-21" in payload["fechas"]
    assert "2026-08-20" in payload["asistencia"]
    assert "2026-08-22" in payload["no_laborables"]  # sábado
    assert "2026-07-28" in payload["no_laborables"]  # feriado
    assert "2026-08-19" in payload["sin_marcacion"]  # miércoles sin marca ni vacación


def test_sin_marcacion_solo_desde_fecha_ingreso():
    worker = {
        "dni": "76823932",
        "nombre": "Nuevo",
        "empresa": "X",
        "area": "A",
        "cargo_actual": "C",
        "fecha_ingreso": "2026-04-21",
        "gerencia": "G",
    }
    payload = employee_calendar_payload(
        worker, 2026, [], asistencia=set(), attendance_ok=True
    )
    assert "2026-01-15" not in payload["sin_marcacion"]
    assert "2026-02-10" not in payload["sin_marcacion"]
    assert "2026-04-20" not in payload["sin_marcacion"]
    # Fin de semana / feriados previos al ingreso tampoco van como no_laborables
    # (el front los pinta como “antes del ingreso”).
    assert "2026-01-03" not in payload["no_laborables"]  # sábado
    assert "2026-04-02" not in payload["no_laborables"]  # Jueves Santo < ingreso
    assert "2026-04-25" in payload["no_laborables"]  # sábado ya con vínculo
    # 21/04/2026 = martes: si es <= hoy, cuenta como falta
    if date.today() >= date(2026, 4, 21):
        assert "2026-04-21" in payload["sin_marcacion"]
