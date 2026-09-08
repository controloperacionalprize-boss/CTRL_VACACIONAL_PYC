from datetime import date

from app.domain.alerts import (
    TIPO_MES,
    TIPO_PENDIENTES,
    TIPO_RECORD,
    TIPO_SIN_PROGRAMAR,
    attach_jefe_nombres,
    build_alerts,
    is_last_week_of_month,
    next_calendar_month,
    prioridad_record,
)


def _w(**kw):
    base = {
        "dni": "10000001",
        "nombre": "María Pérez",
        "area": "T.I.",
        "jefatura": "T.I.",
        "gerencia": "Planificación",
        "apto": True,
        "total_dias": 0,
        "tope_dias": 30,
        "flujo_estado": "BORRADOR",
        "fecha_vencimiento": "2026-12-08",
    }
    base.update(kw)
    return base


def test_prioridad_record_critica_sin_plan():
    assert prioridad_record(12, 0, 30) == "critica"
    assert prioridad_record(90, 30, 30) == "informativa"
    assert prioridad_record(-2, 10, 30) == "critica"


def test_ultima_semana_agosto():
    assert is_last_week_of_month(date(2026, 8, 25))
    assert is_last_week_of_month(date(2026, 8, 31))
    assert not is_last_week_of_month(date(2026, 8, 24))
    assert next_calendar_month(date(2026, 8, 28)) == (2026, 9)


def test_record_una_persona_texto_concreto():
    today = date(2026, 9, 8)
    payload = build_alerts(
        today=today,
        year=2026,
        role="JEFE",
        workers=[_w()],
        dias_mes_siguiente={},
    )
    item = next(i for i in payload["items"] if i["tipo"] == TIPO_RECORD)
    assert item["count"] == 1
    assert "María Pérez" in item["descripcion"]
    assert "08/12/2026" in item["descripcion"]
    assert "91" in item["descripcion"] or "90" in item["descripcion"]
    assert item["personas"][0]["href"].startswith("/?alerta=record_vence")
    assert "dni=10000001" in item["personas"][0]["href"]
    assert payload["resumen"]["records_90"] == 1
    assert item["accion"] == "Ver en Planificación"


def test_record_fuera_de_ventana_no_alerta():
    payload = build_alerts(
        today=date(2026, 9, 8),
        year=2026,
        role="ADMIN",
        workers=[_w(fecha_vencimiento="2027-06-01")],
        dias_mes_siguiente={},
    )
    assert payload["resumen"]["records_90"] == 0
    assert all(i["tipo"] != TIPO_RECORD for i in payload["items"])


def test_no_apto_no_entra_en_record():
    payload = build_alerts(
        today=date(2026, 9, 8),
        year=2026,
        role="ADMIN",
        workers=[_w(apto=False)],
        dias_mes_siguiente={},
    )
    assert payload["resumen"]["records_90"] == 0


def test_mes_siguiente_solo_ultima_semana():
    workers = [_w(dni="1", nombre="Ana", total_dias=5)]
    dias = {"1": [date(2026, 9, 14), date(2026, 9, 15)]}
    fuera = build_alerts(
        today=date(2026, 8, 20),
        year=2026,
        role="GERENTE",
        workers=workers,
        dias_mes_siguiente=dias,
    )
    assert fuera["resumen"]["vacaciones_mes_siguiente"] == 1
    mes_fuera = next(i for i in fuera["items"] if i["tipo"] == TIPO_MES)
    assert mes_fuera["en_inbox"] is False
    assert mes_fuera["prioridad"] == "informativa"

    dentro = build_alerts(
        today=date(2026, 8, 28),
        year=2026,
        role="GERENTE",
        workers=workers,
        dias_mes_siguiente=dias,
    )
    item = next(i for i in dentro["items"] if i["tipo"] == TIPO_MES)
    assert item["prioridad"] == "importante"
    assert item["en_inbox"] is True
    assert "septiembre" in item["titulo"].lower()
    assert "1 trabajador" in item["descripcion"]
    assert "septiembre" in item["descripcion"]
    assert item["href_plan"].startswith("/?alerta=mes_siguiente")
    assert "mes=2026-09" in item["href_plan"]
    assert "listado" in item["accion"].lower()
    assert "quién" not in item["accion"].lower()
    assert "supervisar" not in item["accion"].lower()


def test_pendientes_admin_solo_validados():
    workers = [
        _w(dni="1", nombre="Ana", flujo_estado="VALIDADO", total_dias=30),
        _w(dni="2", nombre="Luis", flujo_estado="ENVIADO", total_dias=30),
    ]
    payload = build_alerts(
        today=date(2026, 9, 8),
        year=2026,
        role="ADMIN",
        workers=workers,
        dias_mes_siguiente={},
    )
    item = next(i for i in payload["items"] if i["tipo"] == TIPO_PENDIENTES)
    assert item["count"] == 1
    assert "Ana" in item["descripcion"]
    assert item["href"] == "/validaciones"
    assert payload["resumen"]["pendientes_plan"] == 1


def test_sin_programar_y_sin_genericos():
    payload = build_alerts(
        today=date(2026, 9, 8),
        year=2026,
        role="JEFE",
        workers=[_w(), _w(dni="2", nombre="Luis Rojas", fecha_vencimiento="2027-12-01")],
        dias_mes_siguiente={},
    )
    item = next(i for i in payload["items"] if i["tipo"] == TIPO_SIN_PROGRAMAR)
    assert item["count"] == 2
    assert item["accion"] == "Ver las 2 personas en Planificación"
    blob = " ".join(i["descripcion"] for i in payload["items"]).lower() + " " + " ".join(i["accion"] for i in payload["items"]).lower()
    for banned in (
        "tienes una nueva notificación",
        "hay información pendiente",
        "revisa el sistema",
        "se requiere tu atención",
        "supervisar el cumplimiento",
        "quién sale el mes siguiente",
    ):
        assert banned not in blob


def test_jefe_nombre_cruzado_por_area():
    workers = [_w()]
    attach_jefe_nombres(
        workers,
        [{"nombre": "HUAMAN RODRIGUEZ JORDAN NINO", "area": "T.I.", "jefatura": "T.I."}],
        [{"nombre_persona": "Carlos Ríos", "area": "T.I.", "correo": "carlos@example.com"}],
    )
    assert workers[0]["jefe_nombre"] == "HUAMAN RODRIGUEZ JORDAN NINO"
    payload = build_alerts(
        today=date(2026, 9, 8),
        year=2026,
        role="GERENTE",
        workers=workers,
        dias_mes_siguiente={},
    )
    persona = next(i for i in payload["items"] if i["tipo"] == TIPO_RECORD)["personas"][0]
    assert persona["jefe_nombre"] == "HUAMAN RODRIGUEZ JORDAN NINO"
    assert persona["division"] == "Planificación"


def test_jefe_nombre_usa_usuario_si_no_hay_maestro():
    workers = [_w()]
    attach_jefe_nombres(
        workers,
        [],
        [{"nombre_persona": "Carlos Ríos", "area": "T.I.", "correo": "carlos@example.com"}],
    )
    assert workers[0]["jefe_nombre"] == "Carlos Ríos"


def test_jefe_nombre_no_mezcla_areas_del_mismo_codigo():
    workers = [_w(area="OPERACIONES", jefatura="OPERACIONES")]
    attach_jefe_nombres(
        workers,
        [
            {"nombre": "REYES SANCHEZ JOSSELYN MICHELLE", "area": "OPERACIONES", "jefatura": "OPERACIONES"},
            {"nombre": "SOTELO SAAVEDRA ELVIS DANIEL", "area": "COSECHA", "jefatura": "COSECHA"},
        ],
    )
    assert workers[0]["jefe_nombre"] == "REYES SANCHEZ JOSSELYN MICHELLE"
