"""Relleno de plantillas Word (Personas y Cultura)."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.domain.documents import (
    EMPRESAS,
    build_context,
    empresa_legal,
    fill_template,
    fill_text,
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


def test_word_generado_sin_comentarios_de_plantilla():
    data = fill_template(
        2,
        _ctx(
            fin=date(2026, 9, 15),
            dias=15,
            periodos=[{"inicio": date(2026, 9, 1), "fin": date(2026, 9, 15), "dias": 15}],
            programmed=[date(2026, 9, 1)],
        ),
    )
    with ZipFile(BytesIO(data)) as z:
        names = z.namelist()
        assert "word/comments.xml" not in names
        assert "word/people.xml" not in names
        xml = z.read("word/document.xml").decode("utf-8")
        assert "commentRangeStart" not in xml
        assert "commentReference" not in xml
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        assert "comments" not in rels.lower()
    assert "ANA PEREZ GOMEZ" in _all_text(data)


def test_pdf_memorando_incluye_datos_y_no_deja_placeholders():
    from app.domain.documents_pdf import document_plain, render_pdf

    ctx = _ctx()
    text = document_plain(1, ctx)
    assert "ANA PEREZ GOMEZ" in text
    assert "12345678" in text
    assert "26 de agosto de 2026" in text
    assert "30 (treinta) días" in text
    assert "SUB GERENCIA DE PERSONAS Y CULTURA" in text
    assert "FIRMA Y HUELLA DEL TRABAJADOR" in text
    assert "GTH" not in text.split("Atentamente.")[-1]
    assert "xxxxx" not in text.lower()
    data = render_pdf(1, ctx)
    assert data.startswith(b"%PDF")
    assert len(data) > 2000
    from app.domain.documents_pdf import pdf_page_count

    assert pdf_page_count(data) == 1


def test_pdf_no_deja_hoja_sola_de_firmas():
    """Solicitud+convenio+memo caben sin una página extra solo para firmar."""
    from app.domain.documents_pdf import pdf_page_count, render_pdf

    plan7 = [
        {"inicio": date(2026, 9, 14), "fin": date(2026, 9, 20), "dias": 7},
        {"inicio": date(2026, 9, 28), "fin": date(2026, 10, 5), "dias": 8},
        {"inicio": date(2026, 10, 19), "fin": date(2026, 10, 21), "dias": 3},
        {"inicio": date(2026, 11, 2), "fin": date(2026, 11, 4), "dias": 3},
        {"inicio": date(2026, 11, 16), "fin": date(2026, 11, 18), "dias": 3},
        {"inicio": date(2026, 12, 2), "fin": date(2026, 12, 4), "dias": 3},
        {"inicio": date(2026, 12, 16), "fin": date(2026, 12, 18), "dias": 3},
    ]
    fraccion = _ctx(
        inicio=date(2026, 9, 14),
        fin=date(2026, 9, 20),
        dias=7,
        periodos=plan7,
        programmed=[date(2026, 9, 14)],
    )
    adelanto = _ctx(
        emp=_emp(fecha_ingreso=date(2026, 4, 1)),
        inicio=date(2026, 8, 26),
        fin=date(2026, 8, 30),
        dias=5,
        periodos=[{"inicio": date(2026, 8, 26), "fin": date(2026, 8, 30), "dias": 5}],
        programmed=[date(2026, 8, 26)],
    )
    modificacion = _ctx(
        fin=date(2026, 10, 19),
        dias=15,
        periodos=[
            {"inicio": date(2026, 10, 5), "fin": date(2026, 10, 19), "dias": 15},
            {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
        ],
        periodos_anteriores=[
            {"inicio": date(2026, 9, 1), "fin": date(2026, 9, 15), "dias": 15},
            {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
        ],
        programmed=[date(2026, 10, 5)],
    )
    # Un documento por pieza (solicitud / convenio / memo): no una 4.ª hoja huérfana.
    assert pdf_page_count(render_pdf(1, _ctx())) == 1
    assert pdf_page_count(render_pdf(2, fraccion)) <= 3
    assert pdf_page_count(render_pdf(3, modificacion)) <= 3
    assert pdf_page_count(render_pdf(4, adelanto)) <= 3


def test_pdf_fraccionamiento_llena_tablas_y_firmas():
    from app.domain.documents_pdf import document_plain

    ctx = _ctx(
        fin=date(2026, 9, 15),
        dias=15,
        periodos=[
            {"inicio": date(2026, 9, 1), "fin": date(2026, 9, 15), "dias": 15},
            {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
        ],
        programmed=[date(2026, 9, 1)],
    )
    text = document_plain(2, ctx)
    assert "01/09/2026" in text
    assert "15/12/2026" in text
    assert "ANA PEREZ GOMEZ" in text
    assert "YESSICA SELENE TORRES VILCHEZ" in text
    assert "EL EMPLEADOR" in text
    assert "SUB GERENCIA DE PERSONAS Y CULTURA" in text
    assert "FIRMA Y HUELLA DEL TRABAJADOR" in text
    assert "JEFE INMEDIATO" not in text
    pie = text.split("Atentamente.")[-1]
    assert "ANA PEREZ" not in pie
    assert "FIRMA Y HUELLA DEL TRABAJADOR" in pie


def test_pdf_adelanto_usa_rango_y_record():
    from app.domain.documents_pdf import document_plain

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
    text = document_plain(4, ctx)
    assert "POR 5 DÍAS" in text
    assert "del 26 al 30 de agosto del año 2026" in text
    assert "Operaciones" in text
    assert "xxxx" not in text.lower()
    assert "junio del año" not in text
    assert "JEFE INMEDIATO" not in text
    assert "LA EMPRESA" in text.split("firman ambas partes")[-1]
    solicitud = text.split("CONVENIO DE ADELANTO")[0]
    assert solicitud.count("ANA PEREZ GOMEZ") == 1


def test_pdf_modificacion_solicitud_una_firma():
    from app.domain.documents_pdf import document_plain

    ctx = _ctx(
        fin=date(2026, 10, 19),
        dias=15,
        periodos=[
            {"inicio": date(2026, 10, 5), "fin": date(2026, 10, 19), "dias": 15},
            {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
        ],
        periodos_anteriores=[
            {"inicio": date(2026, 9, 1), "fin": date(2026, 9, 15), "dias": 15},
            {"inicio": date(2026, 12, 1), "fin": date(2026, 12, 15), "dias": 15},
        ],
        programmed=[date(2026, 10, 5)],
    )
    solicitud = document_plain(3, ctx).split("ACUERDO COMÚN")[0]
    assert solicitud.count("ANA PEREZ GOMEZ") == 1


def test_pdf_memorando_sin_nombre_deja_texto_de_firma():
    from app.domain.documents_pdf import document_plain

    ctx = _ctx(emp=_emp(nombre="", dni=""))
    text = document_plain(1, ctx)
    assert "SUB GERENCIA DE PERSONAS Y CULTURA" in text
    assert "FIRMA Y HUELLA DEL TRABAJADOR" in text
    pie = text.split("Atentamente.")[-1]
    assert "ANA PEREZ" not in pie
    assert "DNI N°" not in pie

