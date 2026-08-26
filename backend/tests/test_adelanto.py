from datetime import date

import pytest

from app.domain.calendar import (
    DERECHO_ANUAL,
    derecho_vigente,
    dias_acumulados_adelanto,
    ensure_within_derecho,
    key_daily,
    meses_completos,
    reject_if_exceeds_saldo,
    record_cumplido,
)


def test_meses_completos_basico():
    assert meses_completos(date(2026, 1, 1), date(2026, 8, 21)) == 7
    assert meses_completos(date(2026, 1, 15), date(2026, 8, 10)) == 6
    assert meses_completos(date(2026, 1, 15), date(2026, 8, 15)) == 7
    assert meses_completos(date(2026, 9, 1), date(2026, 8, 21)) == 0


def test_record_cumplido_al_año():
    ingreso = date(2026, 1, 1)
    assert not record_cumplido(ingreso, date(2026, 12, 31))
    assert record_cumplido(ingreso, date(2027, 1, 1))


def test_record_cumplido_sin_fecha_no_restringe():
    assert record_cumplido(None, date(2026, 1, 1)) is True


def test_dias_acumulados_2_5_por_mes():
    ingreso = date(2026, 1, 1)
    # 7 meses completos al 21/08/2026 → 7 * 2.5 = 17.5 → floor 17
    assert dias_acumulados_adelanto(ingreso, date(2026, 8, 21)) == 17
    # 12 meses → tope 30 (aunque 12*2.5=30 exacto)
    assert dias_acumulados_adelanto(ingreso, date(2027, 1, 1)) == 30


def test_derecho_vigente_antes_y_despues_del_año():
    ingreso = date(2026, 1, 1)
    assert derecho_vigente(ingreso, date(2026, 8, 21)) == 17
    assert derecho_vigente(ingreso, date(2027, 1, 1)) == DERECHO_ANUAL


def test_reject_si_excede_acumulado_de_adelanto():
    # Caso 4 del correo: ingreso 01/01/2026, hoy 19/08/2026 → ~7 meses → 17 días acumulados.
    ingreso = date(2026, 1, 1)
    hoy = date(2026, 8, 19)
    tope = derecho_vigente(ingreso, hoy)
    assert tope == 17
    reject_if_exceeds_saldo(nombre="X", pedidas=10, programados_base=0, derecho=tope, es_adelanto=True)
    with pytest.raises(ValueError, match="acumulado para adelanto"):
        reject_if_exceeds_saldo(nombre="X", pedidas=20, programados_base=0, derecho=tope, es_adelanto=True)


def test_ensure_within_derecho_usa_tope_dinamico():
    dni = "1"
    year = 2026
    daily: set[str] = set()
    for i in range(18):
        daily.add(key_daily(dni, date(year, 3, 1 + i)))
    with pytest.raises(ValueError, match="acumulado para adelanto"):
        ensure_within_derecho(
            daily, dni, year, nombre="X", pedidas=18, programados_base=0, derecho=17, es_adelanto=True
        )
