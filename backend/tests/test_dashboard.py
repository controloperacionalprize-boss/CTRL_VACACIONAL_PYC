from datetime import date

from app.domain.dashboard import build_dashboard


def _emp(dni: str, ingreso: str, **extra):
    return {
        "dni": dni,
        "nombre": dni,
        "gerencia": "G",
        "area": "A",
        "tipo_personal": "ADMINISTRATIVO",
        "jefatura": "J",
        "fecha_ingreso": ingreso,
        **extra,
    }


def test_dashboard_sin_programar_solo_aptos():
    today = date(2026, 8, 31)
    apto_sin = _emp("1", "2024-01-01")
    nuevo_sin = _emp("2", "2026-03-01")
    dash = build_dashboard([apto_sin, nuevo_sin], {}, set(), 2026, today=today)
    assert dash["total_people"] == 2
    assert dash["aptos"] == 1
    assert dash["programados"] == 0
    assert dash["pendientes"] == 1


def test_dashboard_ignora_dias_de_adelanto():
    today = date(2026, 8, 31)
    apto = _emp("1", "2024-01-01")
    nuevo = _emp("2", "2026-03-01")
    targets = {("1", 10): 5, ("2", 10): 3}
    dash = build_dashboard([apto, nuevo], targets, set(), 2026, today=today)
    assert dash["total_people"] == 2
    assert dash["aptos"] == 1
    assert dash["programados"] == 1
    assert dash["pendientes"] == 0
    assert dash["dias_totales"] == 5
    assert dash["agg_gerencia"] == {"G": 5}
