"""Documentos de Personas y Cultura en HTML (vista previa) y PDF (descarga)."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from .documents import TEMPLATES, TEMPLATES_DIR, DocContext, fecha_larga, fecha_slash, rango_narrativo

FONTS_DIR = Path(__file__).resolve().parents[1] / "data" / "fonts"
LOGO_PATH = TEMPLATES_DIR / "logo_gth.png"

REPRESENTANTE = "YESSICA SELENE TORRES VILCHEZ"
REPRESENTANTE_DNI = "40642893"

ART8 = (
    "De acuerdo con lo establecido en el artículo 8 del D.S.002-2019-TR «las vacaciones "
    "se pueden fraccionar de la siguiente manera: i) Un primer bloque de al menos quince (15) "
    "días calendario, que se goza de forma ininterrumpida o puede distribuirse en dos periodos "
    "de los cuales uno es de al menos siete (7) días y el otro de al menos ocho (8) días "
    "calendario ininterrumpido. ii) El resto del descanso vacacional puede gozarse en periodos "
    "mínimos de un (1) día calendario. iii) Las partes pueden acordar el orden en el que se "
    "goza lo señalado en los numerales precedentes»."
)

_DIAS_PALABRA = {
    1: "un",
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
    11: "once",
    12: "doce",
    13: "trece",
    14: "catorce",
    15: "quince",
    16: "dieciséis",
    17: "diecisiete",
    18: "dieciocho",
    19: "diecinueve",
    20: "veinte",
    21: "veintiún",
    22: "veintidós",
    23: "veintitrés",
    24: "veinticuatro",
    25: "veinticinco",
    26: "veintiséis",
    27: "veintisiete",
    28: "veintiocho",
    29: "veintinueve",
    30: "treinta",
}


def dias_en_palabras(n: int) -> str:
    return _DIAS_PALABRA.get(int(n), str(n))


def dias_con_palabras(n: int) -> str:
    return f"{n} ({dias_en_palabras(n)}) días"


def suma_dias(periodos) -> int:
    return sum(int(p.get("dias") or 0) for p in periodos)


@dataclass(frozen=True)
class SignCol:
    nombre: str
    linea2: str
    rol: str


def _period_rows(periodos) -> list[tuple[str, str, str, str]]:
    labels = (
        "Primer periodo",
        "Segundo periodo",
        "Tercer periodo",
        "Cuarto periodo",
        "Quinto periodo",
    )
    needed = max(len(periodos), 3)
    rows: list[tuple[str, str, str, str]] = []
    for i in range(needed):
        label = labels[i] if i < len(labels) else f"Periodo {i + 1}"
        if i < len(periodos):
            p = periodos[i]
            rows.append((label, str(p["dias"]), fecha_slash(p["inicio"]), fecha_slash(p["fin"])))
        else:
            rows.append((label, "", "", ""))
    return rows


def _logo_data_uri() -> str:
    if not LOGO_PATH.is_file():
        return ""
    b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def document_plain(escenario: int, ctx: DocContext) -> str:
    """Texto corrido para pruebas (mismo contenido que HTML/PDF)."""
    parts: list[str] = []
    for kind, payload in _blocks(escenario, ctx):
        if kind in {"title", "p", "meta", "h2"}:
            parts.append(str(payload))
        elif kind == "table":
            for row in payload:
                parts.append(" | ".join(row))
        elif kind == "signs":
            for col in payload:
                parts.extend(line for line in (col.nombre, col.linea2, col.rol) if line)
    return "\n".join(parts)


def _blocks(escenario: int, ctx: DocContext):
    if escenario == 1:
        yield from _esc_memorando(ctx, goce_continuo=True)
    elif escenario == 2:
        yield from _esc_fraccionamiento(ctx)
    elif escenario == 3:
        yield from _esc_modificacion(ctx)
    elif escenario == 4:
        yield from _esc_adelanto(ctx)
    else:
        raise ValueError("No hay plantilla para ese escenario.")


def _encabezado_solicitud(titulo: str, ctx: DocContext):
    yield "title", titulo
    yield "meta", f"Fecha: {fecha_larga(ctx.fecha)}"
    yield "meta", "Atención:"
    yield "meta", (ctx.jefe or "").strip() or "Nombre del jefe de sub área o jefe inmediato"
    yield "meta", (ctx.cargo_jefe or "").strip() or "(Cargo)"
    yield "meta", "Cc: Sub Gerencia de Personas y Cultura"
    yield "meta", "Área Administración de Personal- Remuneraciones"


def _firma_trabajador(
    ctx: DocContext,
    *,
    name_label: str = "Nombres y apellidos del trabajador",
    dni_label: str = "DNI N°",
) -> SignCol:
    nombre = (ctx.nombre or "").strip()
    dni = (ctx.dni or "").strip()
    if nombre:
        return SignCol(nombre, f"DNI N° {dni}" if dni else dni_label, "")
    return SignCol(name_label, dni_label, "")


def _firmas_solicitud(ctx: DocContext, **labels):
    yield "signs", (_firma_trabajador(ctx, **labels),)


def _firmas_acuerdo(ctx: DocContext, *, empleador_primero: bool = True):
    empleador = SignCol("", "", "EL EMPLEADOR")
    trabajador = _firma_trabajador(
        ctx,
        name_label="NOMBRES Y APELLIDOS DEL TRABAJADOR",
        dni_label="DNI",
    )
    if empleador_primero:
        yield "signs", (empleador, trabajador)
    else:
        yield "signs", (trabajador, empleador)


def _firmas_memorando(_ctx: DocContext):
    yield "signs", (
        SignCol("", "", "SUB GERENCIA DE PERSONAS Y CULTURA"),
        SignCol("", "", "FIRMA Y HUELLA DEL TRABAJADOR"),
    )


def _firmas_convenio_adelanto(ctx: DocContext):
    yield "signs", (
        SignCol("", "", "LA EMPRESA"),
        _firma_trabajador(ctx, name_label="Nombre y apellidos", dni_label="DNI N°"),
    )


def _esc_memorando(
    ctx: DocContext,
    *,
    goce_continuo: bool,
    titulo: str | None = None,
    cuerpo: list[str] | None = None,
    saludo: str = "Estimado colaborador (a):",
):
    yield "logo", None
    yield "title", titulo or "MEMORANDO DE VACACIONES"
    yield "meta", f"Fecha: {fecha_larga(ctx.fecha)}"
    yield "meta", f"Señor (Sra.): {ctx.nombre}" if (ctx.nombre or "").strip() else "Señor (Sra.):"
    yield "meta", f"DNI N°: {ctx.dni}" if (ctx.dni or "").strip() else "DNI N°:"
    yield "p", saludo
    if cuerpo:
        for par in cuerpo:
            yield "p", par
    elif goce_continuo:
        yield "p", (
            "Por medio de la presente cumplimos con comunicarle que se le aprueba su solicitud "
            f"de descanso vacacional, correspondiente al récord vacacional {ctx.record}."
        )
        yield "p", (
            "Por lo tanto, se concede a su solicitud y se le otorga "
            f"{dias_con_palabras(ctx.dias)} de descanso vacacional, "
            f"programándose {rango_narrativo(ctx.inicio, ctx.fin)}."
        )
    yield "p", "Atentamente."
    yield from _firmas_memorando(ctx)


def _esc_fraccionamiento(ctx: DocContext):
    yield "logo", None
    yield from _encabezado_solicitud("SOLICITUD FRACCIONAMIENTO DE DESCANSO VACACIONAL", ctx)
    yield "p", "Estimados Señores:"
    yield "p", (
        "Por intermedio de la presente, solicito a su despacho el fraccionamiento de mi descanso "
        f"vacacional del récord vacacional {ctx.record}, según la siguiente propuesta:"
    )
    yield "table", _period_rows(ctx.periodos)
    yield "p", (
        f"Sobre la base de la norma antes citada, solicito se me conceda el descanso vacacional "
        f"del récord vacacional {ctx.record} en forma fraccionada conforme el detalle antes "
        "señalado, pudiendo estar sujeta de variaciones que serán programadas de mutuo acuerdo."
    )
    yield "p", "Sin otro particular,"
    yield "p", "Atentamente."
    yield from _firmas_solicitud(ctx)

    yield "break", None
    yield "logo", None
    yield "title", "ACUERDO COMÚN DE FRACCIONAMIENTO DE DESCANSO VACACIONAL"
    empresa = ctx.empresa or "________________"
    ruc = ctx.ruc or "________________"
    yield "p", (
        "Conste por medio del presente documento, un acuerdo laboral de fraccionamiento de "
        f"descanso vacacional que celebran de una parte la Empresa {empresa} con RUC N° {ruc}, "
        f"representado por {REPRESENTANTE}, con DNI {REPRESENTANTE_DNI}, a quien en adelante se le "
        f"denominará EMPLEADOR y de la otra parte El (A) Señor (Sra) {ctx.nombre} identificado "
        f"con DNI N° {ctx.dni}, a quien en adelante se le denominará EL(A) TRABAJADOR(A), "
        "conforme a lo siguiente:"
    )
    yield "p", (
        "Primero: EL(A) TRABAJADOR(A) ha cumplido con el año de prestación de servicios y el "
        "récord vacacional establecidos por ley para gozar del derecho de vacaciones remuneradas, "
        "siendo que ha presentado su solicitud de fraccionamiento de vacaciones de manera libre y "
        "espontánea. El EMPLEADOR conforme a su actividad empresarial está en disponibilidad de "
        "autorizar el fraccionamiento de vacaciones propuesto."
    )
    yield "p", f"Segundo: {ART8}"
    yield "p", (
        f"Tercero: Con fecha {fecha_larga(ctx.fecha)}, El TRABAJADOR solicita el fraccionamiento "
        f"del descanso vacacional del récord vacacional {ctx.record}; solicitud que es aprobada "
        f"por el EMPLEADOR y, de común acuerdo, deciden establecer como periodos fraccionados de "
        f"vacaciones del récord {ctx.record}, los siguientes:"
    )
    yield "table", _period_rows(ctx.periodos)
    total = suma_dias(ctx.periodos) or ctx.dias
    yield "p", (
        f"Cuarto: Sumados los periodos indicados hacen los {total} días calendarios establecidos "
        "por ley para gozar del descanso vacacional."
    )
    yield "p", (
        f"Quinto: Ambas partes firman el presente acuerdo, {firma_cierre(ctx)}, no habiendo "
        "mediado dolo, vicio o error en el mismo."
    )
    yield from _firmas_acuerdo(ctx, empleador_primero=False)

    if not ctx.memorando:
        return
    yield "break", None
    yield from _esc_memorando(
        ctx,
        goce_continuo=False,
        saludo="Estimado colaborador (a)",
        cuerpo=[
            (
                "Por medio de la presente cumplimos con comunicarle que se le concede su solicitud "
                f"de fraccionamiento de descanso vacacional por el periodo de {ctx.dias} días, "
                f"correspondiente al récord vacacional {ctx.record}."
            ),
            (
                "De acuerdo con lo establecido en el artículo 8 del D.S.002-2019-TR «las vacaciones "
                "se pueden fraccionar de la siguiente manera: i) Un primer bloque de al menos quince (15) "
                "días calendario, que se goza de forma ininterrumpida o puede distribuirse en dos periodos "
                "de los cuales uno es de al menos siete (7) días y el otro de al menos ocho (8) días "
                "calendario ininterrumpido. ii) El resto del descanso vacacional puede gozarse en periodos "
                "mínimos de un (1) día calendario. iii) Las partes pueden acordar el orden en el que se "
                "goza lo señalado en los numerales precedentes."
            ),
            (
                "Por lo tanto, se concede a su solicitud y se le otorga "
                f"{ctx.dias} días de descanso vacacional, "
                f"programándose {rango_narrativo(ctx.inicio, ctx.fin)}."
            ),
        ],
    )


def _esc_modificacion(ctx: DocContext):
    anteriores = ctx.periodos_anteriores or ctx.periodos
    fecha_convenio = fecha_larga(ctx.fecha_convenio or ctx.fecha)
    yield "logo", None
    yield from _encabezado_solicitud(
        "SOLICITUD DE MODIFICACIÓN DE FRACCIONAMIENTO DE DESCANSO VACACIONAL", ctx
    )
    yield "p", "Estimados Señores:"
    yield "p", (
        "Por intermedio de la presente, solicito a su despacho la modificación del Acuerdo común "
        f"de fraccionamiento de descanso vacacional, de fecha {fecha_convenio}, del récord "
        f"vacacional {ctx.record}, según la siguiente propuesta:"
    )
    yield "table", _period_rows(ctx.periodos)
    yield "p", "Sobre la base de la norma antes citada, solicito se me conceda la modificación del descanso vacacional conforme el detalle antes señalado."
    yield "p", "Sin otro particular,"
    yield "p", "Atentamente."
    yield from _firmas_solicitud(ctx)

    yield "break", None
    yield "logo", None
    yield "title", "ACUERDO COMÚN DE MODIFICACIÓN DE FRACCIONAMIENTO DE DESCANSO VACACIONAL"
    empresa = ctx.empresa or "________________"
    ruc = ctx.ruc or "________________"
    yield "p", (
        "Conste por medio del presente documento, un acuerdo laboral de modificación de "
        f"fraccionamiento de descanso vacacional que celebran de una parte la Empresa {empresa} "
        f"con RUC N° {ruc}, representado por {REPRESENTANTE}, con DNI {REPRESENTANTE_DNI}, a quien "
        f"en adelante se le denominará EMPLEADOR y de la otra parte El (A) Señor (Sra) {ctx.nombre} "
        f"identificado con DNI N° {ctx.dni}, a quien en adelante se le denominará EL(A) "
        "TRABAJADOR(A), conforme a lo siguiente:"
    )
    yield "p", (
        "Primero: EL(A) TRABAJADOR(A) ha cumplido con el año de prestación de servicios y el "
        "récord vacacional establecidos por ley para gozar del derecho de vacaciones remuneradas, "
        "siendo que ha presentado su solicitud de fraccionamiento de vacaciones de manera libre y "
        "espontánea. El EMPLEADOR conforme a su actividad empresarial está en disponibilidad de "
        "autorizar el fraccionamiento de vacaciones propuesto."
    )
    yield "p", f"Segundo: {ART8}"
    yield "h2", "Tercero: ANTECEDENTES"
    yield "p", (
        f"Con fecha {fecha_convenio}, El TRABAJADOR solicitó el fraccionamiento del "
        f"descanso vacacional del récord {ctx.record}; solicitud que fue aprobada por el EMPLEADOR "
        "y, de común acuerdo, decidieron establecer como periodos fraccionados de vacaciones del "
        f"récord {ctx.record}, los siguientes:"
    )
    yield "table", _period_rows(anteriores)
    yield "p", (
        f"Cuarto: Con fecha {fecha_larga(ctx.fecha)}, EL(A) TRABAJADOR(A) solicitó la modificación "
        "del Acuerdo común de fraccionamiento de descanso vacacional, propuesta que es aprobada "
        "por EL EMPLEADOR y, de mutuo acuerdo, pactan como nuevos periodos vacacionales, los siguientes:"
    )
    yield "table", _period_rows(ctx.periodos)
    total = suma_dias(ctx.periodos) or ctx.dias
    yield "p", (
        f"Sumados los periodos indicados hacen los {total} días calendarios establecidos por ley "
        "para gozar del descanso vacacional."
    )
    yield "p", (
        f"Quinto: Ambas partes firman el presente acuerdo, {firma_cierre(ctx)}, no habiendo "
        "mediado dolo, vicio o error en el mismo."
    )
    yield from _firmas_acuerdo(ctx)

    if not ctx.memorando:
        return
    yield "break", None
    yield from _esc_memorando(
        ctx,
        goce_continuo=False,
        cuerpo=[
            (
                "Por medio de la presente cumplimos con comunicarle que se le aprueba su solicitud "
                f"de modificación de fraccionamiento de descanso vacacional, correspondiente al "
                f"récord vacacional {ctx.record}."
            ),
            (
                "Por lo tanto, se concede a su solicitud y se le otorga "
                f"{dias_con_palabras(ctx.dias)} de descanso vacacional, "
                f"programándose {rango_narrativo(ctx.inicio, ctx.fin)}."
            ),
        ],
    )


def _esc_adelanto(ctx: DocContext):
    derecho = fecha_slash(ctx.derecho_desde) if ctx.derecho_desde else "________________"
    yield "logo", None
    yield "title", f"SOLICITA ADELANTO DE GOCE DE VACACIONES DEL RECORD VACACIONAL {ctx.record}"
    yield "meta", f"Fecha: {fecha_larga(ctx.fecha)}"
    yield "meta", "Atención:"
    yield "meta", (ctx.jefe or "").strip() or "Nombre del jefe de sub área o jefe inmediato"
    yield "meta", (ctx.cargo_jefe or "").strip() or "(Cargo)"
    yield "meta", "Cc: Sub Gerencia de Personas y Cultura."
    yield "meta", "Área Administración de Personal- Remuneraciones"
    yield "p", "Estimados Sres.:"
    yield "p", (
        "Por intermedio de la presente, solicito a su despacho el adelanto del goce del descanso "
        f"vacacional del récord {ctx.record}, derecho que adquiriré a partir del día {derecho}, "
        "de conformidad con lo dispuesto en Disposición Complementaria Modificatoria Única del "
        "Decreto Legislativo N° 1405, la cual modifica el Decreto Legislativo N° 713 y el Decreto "
        "Supremo N° 002-2019-TR."
    )
    yield "p", (
        "Por razones de índole personal, necesito adelantar el goce del descanso vacacional "
        f"por {ctx.dias} días, {rango_narrativo(ctx.inicio, ctx.fin)}."
    )
    yield "p", "Sobre la base de las normas antes citadas, solicito atender mi solicitud."
    yield "p", "Sin otro particular,"
    yield "p", "Atentamente."
    yield from _firmas_solicitud(
        ctx,
        name_label="NOMBRES Y APELLIDOS DEL TRABAJADOR",
        dni_label="DNI",
    )

    yield "break", None
    yield "logo", None
    yield "title", "CONVENIO DE ADELANTO DE GOCE DE DESCANSO VACACIONAL"
    empresa = ctx.empresa or "________________"
    ruc = ctx.ruc or "________________"
    yield "p", (
        "Conste por el presente documento que se firma por duplicado, el CONVENIO DE ADELANTO DE "
        f"GOCE DE DESCANSO VACACIONAL, celebrado entre {empresa} con RUC {ruc}, representada por "
        f"{REPRESENTANTE} identificada con DNI N° {REPRESENTANTE_DNI} a quien en adelante se "
        f"denominará LA EMPRESA y, de la otra parte el Sr (a). {ctx.nombre} con DNI N° {ctx.dni}, "
        "a quién en adelante se le denominará EL(A) TRABAJADOR (A), en los términos y condiciones siguientes:"
    )
    yield "h2", "PRIMERO: DEL ADELANTO DEL GOCE DE DESCANSO VACACIONAL"
    yield "p", (
        "De conformidad con lo dispuesto en Disposición Complementaria Modificatoria Única del "
        "Decreto Legislativo N.° 1405, la cual modifica el Decreto Legislativo N.° 713 y en "
        "aplicación del principio constitucional de igualdad ante la ley, modifica los artículos "
        "10, 17 y 19 del Decreto Legislativo N.° 713, para los trabajadores del régimen laboral "
        "general del sector privado y, en consecuencia, se regula y autoriza el adelanto de "
        "vacaciones, bajo los siguientes términos:"
    )
    yield "p", (
        "«Artículo 10 (…) Por acuerdo escrito entre las partes, pueden adelantarse días de "
        "descanso a cuenta del período vacacional que se genere a futuro conforme a lo previsto "
        "en el presente artículo."
    )
    yield "p", (
        "En caso de extinción del vínculo laboral, los días de descanso otorgados por adelantado "
        "al trabajador son compensados con los días de vacaciones truncas adquiridos a la fecha "
        "de cese. Los días de descanso otorgados por adelantado que no puedan compensarse con los "
        "días de vacaciones truncas adquiridos, no generan obligación de compensación a cargo del "
        "trabajador.»"
    )
    yield "h2", "SEGUNDO"
    yield "p", (
        "Por su parte, mediante Decreto Supremo N° 002-2019-TR, que contiene el Reglamento del "
        "Decreto Legislativo N° 1405, se establece en los artículos 5 y 6, lo siguiente:"
    )
    yield "p", (
        "«Artículo 5.- Adelanto de días de descanso a cuenta del período vacacional: El empleador "
        "y el trabajador pueden acordar, previamente y por escrito, el adelanto de días de "
        "descanso a cuenta del período vacacional que se genere a futuro; incluso por un número "
        "de días mayor a la proporción del récord vacacional generado a la fecha del acuerdo."
    )
    yield "p", "Artículo 6.- Compensación del descanso adelantado"
    yield "p", (
        "6.1. Mientras subsista el vínculo laboral, los días de descanso adelantado se compensan "
        "con los días del descanso vacacional una vez cumplido el récord establecido en el "
        "artículo 10 de la Ley."
    )
    yield "p", (
        "6.2. En caso de cese antes de cumplir el récord, la liquidación de beneficios sociales "
        "detalla de modo expreso la compensación de los días de descanso adelantado con los días "
        "que componen las vacaciones truncas. El trabajador no está obligado a pagar ni a "
        "compensar de forma alguna los días del descanso adelantado que no pudieran ser "
        "compensados de las vacaciones truncas.»"
    )
    yield "h2", "TERCERO"
    yield "p", (
        "LAS PARTES se han reunido a solicitud del(a) trabajador(a) quien manifiesta su voluntad "
        "de adelantar el descanso vacacional para atender asuntos de índole personal, "
        f"correspondiente al récord vacacional {ctx.record}, derecho al descanso que el(a) "
        f"TRABAJADOR(A) adquirirá recién a partir del día {derecho}."
    )
    yield "h2", "CUARTO"
    yield "p", (
        "LA EMPRESA ha aprobado la solicitud de adelanto de descanso vacacional y, en "
        f"consecuencia, ambas partes acuerdan el ADELANTO DE DÍAS DE DESCANSO VACACIONAL POR "
        f"{ctx.dias} DÍAS A CUENTA DEL RÉCORD VACACIONAL {ctx.record}, vacaciones que se "
        f"programarán {rango_narrativo(ctx.inicio, ctx.fin)}."
    )
    yield "h2", "QUINTO"
    yield "p", (
        "EL TRABAJADOR(A) reconoce y acepta que mientras subsista el vínculo laboral, los días de "
        "descanso adelantado se compensan con los días del descanso vacacional una vez cumplido "
        "el récord vacacional que en esta oportunidad está adelantando. Así mismo, en CESE de la "
        "relación laboral LA EMPRESA queda autorizada a compensar los días de descanso gozados a "
        "cuenta de las vacaciones truncas que se generen."
    )
    yield "p", f"En señal de conformidad y aceptación, firman ambas partes {firma_cierre(ctx)}."
    yield from _firmas_convenio_adelanto(ctx)


def firma_cierre(ctx: DocContext) -> str:
    return (
        f"a los {ctx.fecha.day} días del mes de "
        f"{('enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre')[ctx.fecha.month - 1]} "
        f"del año {ctx.fecha.year}"
    )


def render_html(escenario: int, ctx: DocContext) -> str:
    logo = _logo_data_uri()
    chunks: list[str] = [
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'/>",
        "<title>Documento de Personas y Cultura</title><style>",
        """
        @page { size: A4; margin: 12mm 15mm 14mm 15mm; }
        * { box-sizing: border-box; }
        body { font-family: 'Calibri', 'Segoe UI', Arial, sans-serif; font-size: 10.5px; color: #1a1a1a; line-height: 1.38; margin: 0; background: #e8e8e8; }
        .sheet { width: 210mm; min-height: 297mm; margin: 12px auto; padding: 12mm 16mm 16mm; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.12); }
        .logo { height: 40px; }
        h1 { font-size: 12.5px; letter-spacing: .04em; text-align: center; margin: 6px 0 10px; }
        h2 { font-size: 10.5px; margin: 10px 0 6px; }
        p { margin: 0 0 7px; text-align: justify; }
        .meta { margin: 0 0 2px; text-align: left; }
        .meta + p { margin-top: 8px; }
        h2 + p { margin-top: 2px; }
        table { width: 100%; border-collapse: collapse; margin: 6px 0 8px; font-size: 10px; }
        th, td { border: 1px solid #333; padding: 3px 6px; }
        th { background: #f2f2f2; }
        .signs { display: flex; gap: 22px; margin-top: 10mm; align-items: flex-end; page-break-inside: avoid; break-inside: avoid; }
        .sign { flex: 1; text-align: center; }
        .signs.one { justify-content: center; }
        .signs.one .sign { flex: 0 0 72mm; max-width: 72mm; }
        .sign-gap { height: 18mm; width: 100%; flex-shrink: 0; }
        .sign .line { border-top: 1px solid #111; margin: 0 12px 6px; }
        .sign .name { font-weight: 700; }
        .sign .rol { font-size: 9px; margin-top: 1px; }
        @media print { body { background: #fff; } .sheet { margin: 0; box-shadow: none; page-break-after: always; } }
        """,
        "</style></head><body>",
    ]
    open_sheet = False

    def ensure_sheet():
        nonlocal open_sheet
        if not open_sheet:
            chunks.append("<section class='sheet'>")
            open_sheet = True

    def close_sheet():
        nonlocal open_sheet
        if open_sheet:
            chunks.append("</section>")
            open_sheet = False

    for kind, payload in _blocks(escenario, ctx):
        if kind == "break":
            close_sheet()
            continue
        ensure_sheet()
        if kind == "logo":
            if logo:
                chunks.append(f"<img class='logo' alt='Personas y Cultura' src='{logo}'/>")
        elif kind == "title":
            chunks.append(f"<h1>{html.escape(str(payload))}</h1>")
        elif kind == "h2":
            chunks.append(f"<h2>{html.escape(str(payload))}</h2>")
        elif kind == "meta":
            chunks.append(f"<p class='meta'>{html.escape(str(payload))}</p>")
        elif kind == "p":
            chunks.append(f"<p>{html.escape(str(payload))}</p>")
        elif kind == "table":
            chunks.append("<table><thead><tr><th>PERIODOS</th><th>DÍAS</th><th>FECHA INICIO</th><th>FECHA DE TÉRMINO</th></tr></thead><tbody>")
            for row in payload:
                cells = "".join(f"<td>{html.escape(c)}</td>" for c in row)
                chunks.append(f"<tr>{cells}</tr>")
            chunks.append("</tbody></table>")
        elif kind == "signs":
            one = " one" if len(payload) == 1 else ""
            chunks.append(f"<div class='signs{one}'>")
            for col in payload:
                chunks.append("<div class='sign'><div class='sign-gap'></div><div class='line'></div>")
                if col.nombre:
                    chunks.append(f"<div class='name'>{html.escape(col.nombre)}</div>")
                if col.linea2:
                    chunks.append(f"<div>{html.escape(col.linea2)}</div>")
                if col.rol:
                    cls = "name" if not col.nombre else "rol"
                    chunks.append(f"<div class='{cls}'>{html.escape(col.rol)}</div>")
                chunks.append("</div>")
            chunks.append("</div>")
    close_sheet()
    chunks.append("</body></html>")
    return "".join(chunks)


class _GthPdf(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(90, 90, 90)
        self.cell(0, 8, f"{self.page_no()}", align="C")
        self.set_text_color(26, 26, 26)


def pdf_page_count(data: bytes) -> int:
    """Páginas de un PDF generado con fpdf2 (no cuenta el nodo /Pages)."""
    return len(re.findall(rb"/Type /Page(?!s)", data))


def render_pdf(escenario: int, ctx: DocContext) -> bytes:
    pdf = _GthPdf(format="A4", unit="mm")
    bottom = 14
    pdf.set_auto_page_break(auto=True, margin=bottom)
    pdf.add_font("DejaVu", "", str(FONTS_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_font("DejaVu", "I", str(FONTS_DIR / "DejaVuSans-Oblique.ttf"))
    pdf.set_margins(16, 12, 16)
    heading = FontFace(emphasis="BOLD", size_pt=8.5)
    body_size = 10
    body_h = 4.7
    meta_h = 4.5
    # Aire tras el texto + hueco para firmar. Si no cabe el de 22 mm, se achica
    # hasta 16 mm; por debajo de eso salta de hoja (evita pegar la raya al párrafo).
    sign_air = 6
    sign_spacer = 22
    sign_spacer_min = 16
    prev = ""

    def new_page():
        pdf.add_page()
        pdf.set_font("DejaVu", "", body_size)
        pdf.set_text_color(26, 26, 26)

    def room_left() -> float:
        return pdf.h - bottom - pdf.get_y()

    def need(mm: float) -> None:
        if room_left() < mm:
            new_page()

    def sign_h(cols: tuple[SignCol, ...]) -> float:
        lines = 1
        for col in cols:
            n = sum(1 for part in (col.nombre, col.linea2, col.rol) if part)
            lines = max(lines, n)
        return 5 + lines * 4.2

    new_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    for kind, payload in _blocks(escenario, ctx):
        if kind == "break":
            new_page()
            prev = ""
            continue
        if kind == "logo":
            if LOGO_PATH.is_file():
                need(16)
                pdf.image(str(LOGO_PATH), x=pdf.l_margin, y=pdf.get_y(), h=12)
                pdf.ln(14)
            prev = kind
            continue
        if kind == "title":
            pdf.set_font("DejaVu", "B", 11.5)
            pdf.multi_cell(usable, 5.4, str(payload), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)
            pdf.set_font("DejaVu", "", body_size)
            prev = kind
            continue
        if kind == "h2":
            pdf.ln(2)
            pdf.set_font("DejaVu", "B", body_size)
            pdf.multi_cell(usable, body_h, str(payload), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1.5)
            pdf.set_font("DejaVu", "", body_size)
            prev = kind
            continue
        if kind == "meta":
            pdf.multi_cell(usable, meta_h, str(payload), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            prev = kind
            continue
        if kind == "p":
            if prev in {"title", "meta"}:
                pdf.ln(2.5)
            pdf.multi_cell(usable, body_h, str(payload), align="J", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1.1)
            prev = kind
            continue
        if kind == "table":
            rows = 1 + len(payload)
            need(5 + rows * 6)
            pdf.ln(1)
            with pdf.table(
                col_widths=(48, 22, 40, 48),
                text_align=("LEFT", "CENTER", "CENTER", "CENTER"),
                headings_style=heading,
                line_height=5.4,
            ) as table:
                hdr = table.row()
                for cell in ("PERIODOS", "DÍAS", "FECHA INICIO", "FECHA DE TÉRMINO"):
                    hdr.cell(cell)
                for row_vals in payload:
                    row = table.row()
                    for cell in row_vals:
                        row.cell(cell)
            pdf.ln(1.6)
            prev = kind
            continue
        if kind == "signs":
            cols: tuple[SignCol, ...] = payload
            n = max(len(cols), 1)
            labels = sign_h(cols)
            pdf.set_auto_page_break(auto=False)
            leftover = room_left()
            needed = sign_air + sign_spacer + labels + 2
            compact = sign_air + sign_spacer_min + labels + 2
            if leftover >= needed:
                air, spacer = sign_air, sign_spacer
            elif leftover >= compact:
                air = sign_air
                spacer = max(sign_spacer_min, leftover - air - labels - 2)
            else:
                pdf.set_auto_page_break(auto=True, margin=bottom)
                new_page()
                pdf.set_auto_page_break(auto=False)
                air, spacer = sign_air, sign_spacer
            y0 = pdf.get_y() + air + spacer
            if n == 1:
                col_w = 72
                x_base = pdf.l_margin + (usable - col_w) / 2
            else:
                col_w = usable / n
                x_base = pdf.l_margin
            for i, col in enumerate(cols):
                x = x_base + i * col_w
                line_w = min(62, col_w - 10)
                pdf.set_xy(x + (col_w - line_w) / 2, y0)
                pdf.cell(line_w, 1, border="T")
                y = y0 + 4
                if col.nombre:
                    pdf.set_xy(x, y)
                    pdf.set_font("DejaVu", "B", 8.5)
                    pdf.multi_cell(col_w, 4.1, col.nombre, align="C", new_x=XPos.LEFT, new_y=YPos.NEXT)
                    y = pdf.get_y()
                if col.linea2:
                    pdf.set_xy(x, y)
                    pdf.set_font("DejaVu", "", 8)
                    pdf.multi_cell(col_w, 4.0, col.linea2, align="C", new_x=XPos.LEFT, new_y=YPos.NEXT)
                    y = pdf.get_y()
                if col.rol:
                    pdf.set_xy(x, y)
                    pdf.set_font("DejaVu", "B" if not col.nombre else "", 8.5 if not col.nombre else 8)
                    pdf.multi_cell(col_w, 4.0, col.rol, align="C", new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.set_auto_page_break(auto=True, margin=bottom)
            pdf.set_y(y0 + labels)
            pdf.set_font("DejaVu", "", body_size)
            prev = kind

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def filename_pdf(escenario: int, ctx: DocContext) -> str:
    _name, slug = TEMPLATES[escenario]
    safe_dni = "".join(ch for ch in ctx.dni if ch.isalnum()) or "trabajador"
    return f"{slug}_{safe_dni}_{ctx.inicio.isoformat()}.pdf"
