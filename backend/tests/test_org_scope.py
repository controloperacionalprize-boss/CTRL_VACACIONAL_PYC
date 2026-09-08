from app.org_scope import (
    dnis_from_maestro,
    division_for_area,
    effective_role,
    employee_in_scope,
    employee_sql_scope,
    resolve_division,
)


def test_compras_cae_en_administracion():
    assert division_for_area("Compras") == "Administración y Finanzas"
    assert resolve_division("Administración") == "Administración y Finanzas"


def test_packing_es_industrial():
    assert resolve_division("Packing") == "Industrial"
    assert resolve_division("Industrial") == "Industrial"


def test_corporativo_es_corporativa():
    assert resolve_division("Corporativo") == "Corporativa"


def test_planificacion_larga_del_roster():
    assert (
        resolve_division("Planificación, Control Operacional y de Gestión")
        == "Planificación"
    )
    assert (
        resolve_division("PLANIFICACIÓN Y CONTROL OPERACIONAL Y DE GESTIÓN")
        == "Planificación"
    )


def test_ti_cae_en_planificacion():
    assert division_for_area("T.I.") == "Planificación"
    assert division_for_area("T.I. y Sistemas") == "Planificación"
    assert division_for_area("TI") == "Planificación"
    user = {"rol": "GERENTE", "gerencia": "Planificación", "is_admin": False}
    ti = {
        "area": "T.I.",
        "division": "AQU II",
        "gerencia": "PLANIFICACIÓN Y CONTROL OPERACIONAL Y DE GESTIÓN",
    }
    assert employee_in_scope(user, ti)


def test_user_legacy_es_gerente():
    assert effective_role({"rol": "USER", "is_admin": False}) == "GERENTE"
    assert effective_role({"rol": "ADMIN", "is_admin": True}) == "ADMIN"
    assert effective_role({"rol": "JEFE"}) == "JEFE"


def test_gerente_ve_areas_de_su_division():
    user = {"rol": "GERENTE", "gerencia": "Industrial", "is_admin": False}
    packing = {"division": "Packing", "gerencia": "Industrial", "area": "Packing"}
    compras = {"division": "Administración", "gerencia": "Administración", "area": "Compras"}
    assert employee_in_scope(user, packing)
    assert not employee_in_scope(user, compras)


def test_jefe_solo_su_area():
    user = {"rol": "JEFE", "area": "Compras", "gerencia": "Administración", "is_admin": False}
    compras = {"area": "Compras", "jefatura": "Compras", "division": "Administración"}
    tesoreria = {"area": "Tesorería", "jefatura": "Tesorería", "division": "Administración"}
    assert employee_in_scope(user, compras)
    assert not employee_in_scope(user, tesoreria)


def test_jefe_sin_area_no_ve_nada():
    user = {"rol": "JEFE", "area": "", "gerencia": "Industrial", "is_admin": False}
    sql, _ = employee_sql_scope(user)
    assert "FALSE" in sql
    assert not employee_in_scope(user, {"area": "Packing"})


def test_admin_sin_filtro_sql():
    sql, params = employee_sql_scope({"rol": "ADMIN", "is_admin": True})
    assert sql == ""
    assert params == []


def test_jefe_tesoreria_con_tildes():
    user = {"rol": "JEFE", "area": "Tesorería", "is_admin": False}
    assert employee_in_scope(user, {"area": "TESORERIA", "jefatura": ""})
    assert employee_in_scope(user, {"area": "Tesorería", "jefatura": "Tesorería"})


def test_gerente_no_puede_tocar_dni_de_otra_division_via_excel():
    """Mismo control que usan los routers de flujo (cargar_excel/_apply_destino):
    list_employees/get_employee filtran por employee_sql_scope antes de aplicar
    cualquier fila del Excel, así que un DNI de otra división nunca debe pasar
    el filtro de scope, sin importar lo que diga la fila del Excel."""
    gerente_industrial = {"rol": "GERENTE", "gerencia": "Industrial", "is_admin": False}
    empleado_de_administracion = {
        "dni": "111",
        "division": "Administración",
        "gerencia": "Administración",
        "area": "Compras",
    }
    empleado_de_industrial = {
        "dni": "222",
        "division": "Packing",
        "gerencia": "Industrial",
        "area": "Packing",
    }
    assert not employee_in_scope(gerente_industrial, empleado_de_administracion)
    assert employee_in_scope(gerente_industrial, empleado_de_industrial)

    sql, params = employee_sql_scope(gerente_industrial)
    assert "FALSE" not in sql
    # El fragmento SQL solo debe traer alias de "Industrial", nunca de "Administración".
    aliases = [v for group in params if isinstance(group, list) for v in group]
    assert all("administracion" not in str(v).lower() for v in aliases)


def test_maestro_aws_amplia_dnis_del_jefe():
    user = {"rol": "JEFE", "area": "Compras", "is_admin": False}
    maestro = [
        {"dni": "111", "area": "Compras"},
        {"dni": "222", "area": "Tesorería"},
        {"dni": "111.0", "area": "COMPRAS"},
    ]
    assert dnis_from_maestro(user, maestro) == ["111"]
