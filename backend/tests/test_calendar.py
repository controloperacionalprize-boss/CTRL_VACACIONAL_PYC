from datetime import date

import pytest

from app.domain.calendar import (
    allowed_type,
    apply_consecutive_span,
    compute_consecutive_dates,
    reject_if_start_in_past,
    week_is_locked,
)

# Fecha fija para que los casos de agosto 2026 no choquen con "hoy" real.
_HOY = date(2026, 8, 17)


def test_todos_usan_dias_corridos():
    """Admin, operativo o desconocido: mismos 7 días corridos desde el viernes."""
    start = date(2026, 8, 21)
    for tipo in ("ADMINISTRATIVO", "OPERATIVO", "GERENCIA", "PLANTA"):
        days = compute_consecutive_dates(tipo, start, 7)
        assert days == [
            date(2026, 8, 21),
            date(2026, 8, 22),
            date(2026, 8, 23),
            date(2026, 8, 24),
            date(2026, 8, 25),
            date(2026, 8, 26),
            date(2026, 8, 27),
        ]


def test_admin_siete_dias_desde_viernes_cruza_semana():
    start = date(2026, 8, 21)
    daily, targets = set(), {}
    apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", start, 7, 2026, clear_week=34, today=_HOY
    )
    assert dict(targets) == {("1", 34): 3, ("1", 35): 4}


def test_operativo_jueves_siete_dias_cruza_semana():
    start = date.fromisocalendar(2026, 34, 4)
    daily, targets = set(), {}
    _, deltas = apply_consecutive_span(
        daily, targets, "1", "OPERATIVO", start, 7, 2026, today=_HOY
    )
    assert dict(targets) == {("1", 34): 4, ("1", 35): 3}
    assert [(w, n) for w, _o, n in deltas] == [(34, 4), (35, 3)]


def test_desconocido_usa_calendario():
    days = compute_consecutive_dates("PLANTA", date.fromisocalendar(2026, 34, 4), 5)
    assert [d.weekday() for d in days] == [3, 4, 5, 6, 0]


def test_exclusion_por_dni_solo_habiles(monkeypatch):
    monkeypatch.setattr(
        "app.domain.calendar.DNI_SOLO_DIAS_HABILES",
        frozenset({"999"}),
    )
    assert allowed_type("OPERATIVO", "999") == "HABIL"
    assert allowed_type("ADMINISTRATIVO", "1") == "CALENDARIO"
    days = compute_consecutive_dates("ADMINISTRATIVO", date(2026, 3, 2), 10, dni="999")
    assert all(d.weekday() < 5 for d in days)
    assert len(days) == 10


def test_lock():
    assert week_is_locked(2020, 1, date(2026, 8, 19))


def test_no_programar_inicio_en_el_pasado():
    with pytest.raises(ValueError, match="solo desde hoy"):
        reject_if_start_in_past(date(2026, 8, 20), today=date(2026, 8, 21))
    reject_if_start_in_past(date(2026, 8, 21), today=date(2026, 8, 21))


def test_apply_rechaza_inicio_pasado():
    daily, targets = set(), {}
    with pytest.raises(ValueError, match="solo desde hoy"):
        apply_consecutive_span(
            daily,
            targets,
            "1",
            "ADMINISTRATIVO",
            date(2026, 8, 17),
            3,
            2026,
            today=date(2026, 8, 21),
        )


def test_pepe_no_programa_despues_del_vencimiento():
    """Récord mar-2026/mar-2027: goce hasta mar-2028; abril-2028 se rechaza."""
    from app.domain.calendar import fecha_vencimiento_de, reject_if_despues_de_vencimiento

    ingreso = date(2026, 3, 15)
    limite = fecha_vencimiento_de(ingreso, 2026, today=date(2026, 9, 7))
    assert limite == date(2028, 3, 14)
    reject_if_despues_de_vencimiento(
        [date(2028, 3, 14)], ingreso, 2026, today=date(2026, 9, 7)
    )
    with pytest.raises(ValueError, match="14/03/2028"):
        reject_if_despues_de_vencimiento(
            [date(2028, 4, 1)], ingreso, 2026, nombre="Pepe", today=date(2026, 9, 7)
        )
    daily, targets = set(), {}
    with pytest.raises(ValueError, match="14/03/2028"):
        apply_consecutive_span(
            daily,
            targets,
            "1",
            "ADMINISTRATIVO",
            date(2028, 4, 1),
            5,
            2026,
            today=date(2026, 9, 7),
            fecha_ingreso=ingreso,
            nombre="Pepe",
        )


def test_mover_periodo_no_puede_pasar_del_vencimiento():
    """El mismo límite de vencimiento del récord aplica al mover un período (no solo al crearlo)."""
    from app.domain.calendar import move_vacation_period

    ingreso = date(2026, 3, 15)
    daily, targets = set(), {}
    apply_consecutive_span(
        daily,
        targets,
        "1",
        "ADMINISTRATIVO",
        date(2026, 9, 10),
        7,
        2026,
        today=date(2026, 9, 7),
        fecha_ingreso=ingreso,
        nombre="Pepe",
    )
    with pytest.raises(ValueError, match="14/03/2028"):
        move_vacation_period(
            daily,
            targets,
            "1",
            "ADMINISTRATIVO",
            2026,
            date(2026, 9, 10),
            date(2028, 4, 1),
            today=date(2026, 9, 7),
            fecha_ingreso=ingreso,
            nombre="Pepe",
            # El tramo del 10/09 ya está en semana cerrada: solo Personas y Cultura lo mueve.
            permitir_cerrado=True,
        )


def test_cierre_de_edicion_es_el_viernes_de_la_semana_anterior():
    from app.domain.calendar import cierre_edicion, primer_inicio_jefatura, tramo_cerrado

    lunes_40 = date(2026, 9, 28)
    miercoles_40 = date(2026, 9, 30)
    assert cierre_edicion(lunes_40) == date(2026, 9, 25)
    assert cierre_edicion(miercoles_40) == date(2026, 9, 25)
    assert not tramo_cerrado(miercoles_40, today=date(2026, 9, 25))
    assert tramo_cerrado(miercoles_40, today=date(2026, 9, 26))
    # Viernes: todavía programa la semana siguiente. Sábado: ya la subsiguiente.
    assert primer_inicio_jefatura(date(2026, 9, 25)) == lunes_40
    assert primer_inicio_jefatura(date(2026, 9, 26)) == date(2026, 10, 5)
    assert primer_inicio_jefatura(date(2026, 9, 21)) == lunes_40


def test_jefatura_no_mueve_tramo_de_semana_cerrada_pero_administracion_si():
    from app.domain.calendar import move_vacation_period, vacation_periods

    daily, targets = set(), {}
    apply_consecutive_span(
        daily, targets, "1", "ADMINISTRATIVO", date(2026, 9, 30), 7, 2026, today=date(2026, 9, 20)
    )
    hoy = date(2026, 9, 28)  # semana 40 ya cerró el viernes 25
    periodo = vacation_periods(daily, "1", 2026, hoy)[0]
    assert periodo["estado"] == "cerrado"
    with pytest.raises(ValueError, match="ya cerró"):
        move_vacation_period(
            daily, targets, "1", "ADMINISTRATIVO", 2026, date(2026, 9, 30), date(2026, 10, 21), today=hoy
        )
    nuevas, _deltas, _old = move_vacation_period(
        daily,
        targets,
        "1",
        "ADMINISTRATIVO",
        2026,
        date(2026, 9, 30),
        date(2026, 10, 21),
        today=hoy,
        permitir_cerrado=True,
    )
    assert nuevas[0] == date(2026, 10, 21)


def test_excel_de_jefatura_no_agrega_dias_en_semana_cerrada():
    from app.domain.calendar import key_daily
    from app.domain.workflow import apply_uploaded_periods

    hoy = date(2026, 9, 28)
    daily = {key_daily("1", date(2026, 10, 1))}
    targets: dict = {}
    periods = [{"fecha_inicio": date(2026, 10, 2), "fecha_fin": date(2026, 10, 3)}]
    with pytest.raises(ValueError, match="semana ya cerrada"):
        apply_uploaded_periods(
            daily, targets, "1", 2026, periods, today=hoy, primer_inicio=date(2026, 10, 5), nombre="Ana"
        )
    ok = [{"fecha_inicio": date(2026, 10, 12), "fecha_fin": date(2026, 10, 13)}]
    apply_uploaded_periods(daily, targets, "1", 2026, ok, today=hoy, primer_inicio=date(2026, 10, 5))
    assert key_daily("1", date(2026, 10, 1)) in daily, "lo de la semana cerrada se conserva"
    assert key_daily("1", date(2026, 10, 12)) in daily
