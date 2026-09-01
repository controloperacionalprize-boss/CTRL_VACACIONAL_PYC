from datetime import date, timedelta

import pytest

from app.domain.calendar import (
    DERECHO_ANUAL,
    apply_consecutive_span,
    count_year_days,
    ensure_within_derecho,
    key_daily,
    mensaje_sin_saldo,
)


def test_mensaje_sin_saldo_con_resto():
    msg = mensaje_sin_saldo("Ana Perez", 30, 15)
    assert "Ana Perez" in msg
    assert "15" in msg
    assert str(DERECHO_ANUAL) in msg


def test_mensaje_sin_saldo_agotado():
    msg = mensaje_sin_saldo("Ana Perez", 5, DERECHO_ANUAL)
    assert "ya tiene los" in msg


def test_ensure_bloquea_sobre_derecho():
    dni = "123"
    year = 2026
    daily: set[str] = set()
    # 20 días ya programados
    for i in range(20):
        daily.add(key_daily(dni, date(year, 1, 5 + i)))
    # Simula quedar en 35
    for i in range(15):
        daily.add(key_daily(dni, date(year, 3, 1 + i)))
    assert count_year_days(daily, dni, year) == 35
    with pytest.raises(ValueError, match="solo le quedan"):
        ensure_within_derecho(
            daily, dni, year, nombre="Luis Vera", pedidas=15, programados_base=20
        )


def test_reject_if_exceeds_saldo():
    from app.domain.calendar import reject_if_exceeds_saldo

    reject_if_exceeds_saldo(nombre="X", pedidas=10, programados_base=20)
    with pytest.raises(ValueError, match="solo le quedan"):
        reject_if_exceeds_saldo(nombre="Luis Vera", pedidas=15, programados_base=20)


def test_ensure_dos_records_30_mas_30_ok():
    dni = "1"
    year = 2026
    ingreso = date(2020, 4, 15)
    daily: set[str] = set()
    for i in range(30):
        daily.add(key_daily(dni, date(year, 1, 5) + timedelta(days=i)))
    for i in range(30):
        daily.add(key_daily(dni, date(year, 6, 1) + timedelta(days=i)))
    ensure_within_derecho(
        daily,
        dni,
        year,
        nombre="Jorge",
        pedidas=30,
        programados_base=0,
        fecha_ingreso=ingreso,
    )


def test_span_luego_ensure_ok_en_limite():
    dni = "999"
    year = 2026
    daily: set[str] = set()
    targets: dict = {}
    apply_consecutive_span(
        daily,
        targets,
        dni,
        "OPERATIVO",
        date(year, 8, 17),
        DERECHO_ANUAL,
        year,
        today=date(year, 8, 17),
    )
    assert count_year_days(daily, dni, year) == DERECHO_ANUAL
    ensure_within_derecho(
        daily, dni, year, nombre="X", pedidas=DERECHO_ANUAL, programados_base=0
    )
