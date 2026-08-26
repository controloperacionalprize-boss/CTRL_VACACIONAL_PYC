"""Relleno de plantillas Word (GTH)."""

from datetime import date
from io import BytesIO

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.domain.documents import (
    EMPRESAS,
    build_context,
    empresa_legal,
    fill_template,
    fill_text,
    infer_escenario,
    reconstruct_old_periods,
)

_AQU = ("AQU ANQA S.A.C.", "20608345770")
_AQU_II = ("AQU ANQA II S.A.C.", "20610068767")


def _emp(**extra):
    base = {
        "dni": "12345678",
        "nombre": "ANA PEREZ GOMEZ",
        "empresa": "AQUANQA",
        "jefatura": "GTH",
        "fecha_ingreso": date(2024, 8, 1),
    }
    base.update(extra)
    return base


def _ctx(**kwargs):
    defaults = dict(
        emp=_emp(),
        today=date(2026, 8, 26),
        year=2026,
        inicio=date(2026, 9, 1),
        fin=date(2026, 9, 30),
        dias=30,
        periodos=[{"inicio": date(2026, 9, 1), "fin": date(2026, 9, 30), "dias": 30}],
        programmed=[date(2026, 9, 1), date(2026, 9, 30)],
    )
    defaults.update(kwargs)
    return build_context(**defaults)


def _all_text(data: bytes) -> str:
    return "\n".join((t.text or "") for t in Document(BytesIO(data)).element.body.iter(qn("w:t")))


def test_escenario_1_rellena_campos_del_trabajador():
    text = _all_text(fill_template(1, _ctx()))
    assert "ANA PEREZ GOMEZ" in text
    assert "12345678" in text
    assert "26 de agosto de 2026" in text
    assert "01/09/2026" in text
    assert "30/09/2026" in text


@pytest.mark.parametrize(
    "es_adelanto,moved,sizes,esperado",
    [
        (False, False, [30], 1),
        (False, False, [15, 15], 2),
        (True, False, [5], 4),
        (False, True, [15], 3),
    ],
)
def test_infer_escenario(es_adelanto, moved, sizes, esperado):
    assert infer_escenario(es_adelanto=es_adelanto, moved=moved, period_sizes=sizes) == esperado


@pytest.mark.parametrize(
    "alias,esperado",
    [
        ("AQU", _AQU),
        ("AQU ANQA", _AQU),
        ("AQUANQA", _AQU),
        ("AQU ANQA SAC", _AQU),
        ("AQU II", _AQU_II),
        ("AQU ANQA II", _AQU_II),
        ("AQU ANQA II SAC", _AQU_II),
        ("aqu anqa ii s.a.c.", _AQU_II),
    ],
)
def test_empresa_legal_resuelve_alias(alias, esperado):
    assert empresa_legal(alias) == esperado


def test_empresa_legal_desconocida_no_inventa_ruc():
    assert empresa_legal("OTRA SAC") == ("OTRA SAC", "")


def test_catalogo_empresas_ii_va_antes_que_aqu():
    compactos = [aliases for _razon, _ruc, aliases in EMPRESAS]
    assert compactos[0] == frozenset({"AQUII", "AQUANQAII"})


def test_adelanto_rellena_dias_y_cargo():
    ctx = _ctx(
        emp=_emp(
            empresa="AQU II",
            jefatura="CONTROL OPERACIONAL",
            gerencia="Operaciones",
            fecha_ingreso=date(2026, 4, 1),
        ),
        inicio=date(2026, 8, 26),
        fin=date(2026, 8, 30),
        dias=5,
        periodos=[{"inicio": date(2026, 8, 26), "fin": date(2026, 8, 30), "dias": 5}],
        programmed=[date(2026, 8, 26)],
    )
    text = _all_text(fill_template(4, ctx))
    assert "POR 5 DÍAS" in text
    assert "por xxxx" not in text.lower()
    assert "del 26 al 30 de agosto del año 2026" in text
    assert "del xx al xx" not in text.lower()
    assert "Operaciones" in text
    assert "(Cargo)" not in text


def test_adelanto_rellena_rango_aunque_ya_tenga_los_dias():
    ctx = _ctx(dias=7, inicio=date(2026, 9, 1), fin=date(2026, 9, 7))
    fuente = (
        "Por razones de índole personal, necesito adelantar el goce del descanso "
        "vacacional POR 7 DÍAS, del xx al xx de xxx del xxxxx."
    )
    filled = fill_text(fuente, ctx)
    assert "POR 7 DÍAS" in filled
    assert "del 1 al 7 de septiembre del año 2026" in filled
    assert "xx" not in filled.lower()


def test_firmas_usan_nombre_y_dni():
    text = _all_text(
        fill_template(
            2,
            _ctx(
                fin=date(2026, 9, 15),
                dias=15,
                periodos=[{"inicio": date(2026, 9, 1), "fin": date(2026, 9, 15), "dias": 15}],
                programmed=[date(2026, 9, 1)],
            ),
        )
    )
    assert "ANA PEREZ GOMEZ" in text
    assert "12345678" in text
    assert "Nombres y apellidos del trabajador" not in text


def test_fill_text_no_deja_por_xxxx_si_el_record_ya_esta():
    ctx = _ctx(dias=5)
    fuente = "POR xxxx DÍAS A CUENTA DEL RÉCORD VACACIONAL 2026-2027"
    assert "POR 5 DÍAS" in fill_text(fuente, ctx)
    assert "xxxx" not in fill_text(fuente, ctx).lower()


def test_reconstruye_periodo_anterior():
    new = [
        {"inicio": date(2026, 10, 5), "fin": date(2026, 10, 19), "dias": 15},
        {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
    ]
    old = reconstruct_old_periods(new, date(2026, 9, 1), date(2026, 10, 5))
    assert old[0]["inicio"] == date(2026, 9, 1)
    assert old[0]["fin"] == date(2026, 9, 15)
