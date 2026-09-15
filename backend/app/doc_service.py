"""Emisión de documentos de Personas y Cultura sobre la base de datos: qué falta, PDF y registro."""
from __future__ import annotations

from datetime import date, datetime

from .db import insert_documento
from .domain.alerts import attach_jefe_nombres
from .domain.calendar import (
    art8_fraccion_ok,
    es_apto,
    index_dates_by_dni,
    parse_iso_date,
    vacation_periods,
)
from .domain.doc_emision import (
    documentos_pendientes,
    filas_a_registrar,
    item_desde_fila,
)
from .domain.documents import DocContext, build_context
from .domain.documents_pdf import PARTE_LABEL, filename_pdf, partes_de, render_pdf
from .domain.workflow import goce_y_derecho

_DOC_COLS = (
    "id, anio, dni, tipo, tramo_inicio, tramo_fin, dias, periodos, periodos_anteriores, "
    "fecha_convenio, emitido_at, emitido_por, emitido_nombre, descargas, enviado_at, "
    "enviado_a, envio_error"
)


def load_emitidos(cur, year: int, dnis: list[str]) -> dict[str, list[dict]]:
    if not dnis:
        return {}
    cur.execute(
        f"SELECT {_DOC_COLS} FROM plan_documento WHERE anio = %s AND dni = ANY(%s) ORDER BY emitido_at, id",
        (year, [str(d) for d in dnis]),
    )
    out: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        out.setdefault(str(r["dni"]), []).append(dict(r))
    return out


def load_emitido(cur, doc_id: int) -> dict | None:
    cur.execute(f"SELECT {_DOC_COLS} FROM plan_documento WHERE id = %s", (int(doc_id),))
    row = cur.fetchone()
    return dict(row) if row else None


def lock_persona(cur, year: int, dni: str) -> None:
    """Serializa emisiones de la misma persona (evita registrar dos veces el mismo documento)."""
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"doc:{year}:{dni}",))


def attach_jefes(cur, rows: list[dict]) -> None:
    """Completa jefe_nombre (maestro de jefes y usuarios JEFE) para Documentos y el PDF."""
    cur.execute(
        """SELECT dni, nombre, area, jefatura, gerencia, cargo_actual
           FROM employees
           WHERE activo = TRUE AND cargo_actual ILIKE %s""",
        ("JEFE%",),
    )
    org_jefes = list(cur.fetchall())
    cur.execute(
        """SELECT correo, nombre_persona, nombre_usuario, area, gerencia
           FROM users
           WHERE activo = TRUE AND upper(rol) = 'JEFE' AND COALESCE(area, '') <> ''"""
    )
    attach_jefe_nombres(rows, org_jefes, list(cur.fetchall()))


def es_adelanto(emp: dict, today: date) -> bool:
    return not es_apto(emp, today)


def motivo_bloqueo(
    emp: dict,
    daily_set: set[str],
    periodos: list[dict],
    dates: list[date],
    year: int,
    today: date,
) -> str:
    """Por qué no se emite nada todavía ("" si se puede).

    Regla de Personas y Cultura (reunión 11/09/2026): no se procesa un fraccionamiento parcial. Sin el derecho
    completo programado, o sin cumplir el Art. 8, no sale solicitud, convenio ni memorando.
    El adelanto no sigue esta regla: va por tramo.
    """
    if not periodos or es_adelanto(emp, today):
        return ""
    dias, derecho, _ = goce_y_derecho(emp, daily_set, None, year, today, dates=dates)
    if dias != derecho:
        return (
            f"Faltan {derecho - dias} día(s) para completar los {derecho}. La solicitud y el "
            "convenio de fraccionamiento (o el memorando) se generan cuando esté programado "
            "todo el derecho."
        )
    if not art8_fraccion_ok([int(p["dias"]) for p in periodos]):
        return "El fraccionamiento no cumple el Art. 8: no se generan documentos."
    return ""


def pendientes_por_dni(
    employees: list[dict],
    daily_set: set[str],
    emitidos: dict[str, list[dict]],
    year: int,
    today: date,
) -> dict[str, tuple[list[dict], list[date], str]]:
    """{dni: (items pendientes, fechas del plan, motivo de bloqueo)} en una sola pasada por daily_set."""
    fechas = index_dates_by_dni(daily_set, year)
    out: dict[str, tuple[list[dict], list[date], str]] = {}
    for emp in employees:
        dni = str(emp["dni"])
        dates = fechas.get(dni, [])
        periodos = [
            {"inicio": p["inicio"], "fin": p["fin"], "dias": p["dias"]}
            for p in vacation_periods(daily_set, dni, year, today, dates=dates)
        ]
        motivo = motivo_bloqueo(emp, daily_set, periodos, dates, year, today)
        items = [] if motivo else documentos_pendientes(
            periodos=periodos,
            emitidos=emitidos.get(dni, []),
            today=today,
            es_adelanto=es_adelanto(emp, today),
        )
        out[dni] = (items, dates, motivo)
    return out


def item_context(emp: dict, item: dict, *, year: int, fecha_doc: date, programmed: list[date]) -> DocContext:
    periodos = item.get("periodos") or []
    tramo = item.get("tramo")
    if tramo:
        inicio, fin, dias = tramo["inicio"], tramo["fin"], int(tramo["dias"])
    elif periodos:
        inicio, fin = periodos[0]["inicio"], periodos[-1]["fin"]
        dias = sum(int(p["dias"]) for p in periodos)
    else:
        raise ValueError("Este documento no tiene períodos.")
    return build_context(
        emp,
        today=fecha_doc,
        year=year,
        inicio=inicio,
        fin=fin,
        dias=dias,
        periodos=periodos,
        periodos_anteriores=item.get("periodos_anteriores") or [],
        programmed=programmed,
        memorando=bool(tramo),
        fecha_convenio=item.get("fecha_convenio"),
    )


def render_item(
    emp: dict,
    item: dict,
    *,
    year: int,
    fecha_doc: date,
    programmed: list[date],
    parte: str = "",
) -> tuple[bytes, str]:
    """PDF del documento; con `parte` ("solicitud", "convenio", "memorando"…) solo esa hoja."""
    ctx = item_context(emp, item, year=year, fecha_doc=fecha_doc, programmed=programmed)
    escenario = int(item["escenario"])
    return render_pdf(escenario, ctx, parte), filename_pdf(escenario, ctx, parte)


def partes_item(item: dict) -> list[dict]:
    """[{id, label}] de los documentos que se pueden bajar por separado."""
    tipo = item.get("tipo")
    con_memorando = bool(item.get("tramo")) or tipo in {"memorando", "adelanto"}
    return [
        {"id": p, "label": PARTE_LABEL[p]}
        for p in partes_de(int(item["escenario"]), con_memorando)
    ]


def nombre_usuario(user: dict) -> str:
    return user.get("nombre_persona") or user.get("nombre_usuario") or user.get("correo") or ""


def registrar(cur, year: int, dni: str, item: dict, user: dict) -> list[int]:
    return [
        insert_documento(
            cur,
            year,
            dni,
            fila,
            emitido_por=user.get("correo") or "",
            emitido_nombre=nombre_usuario(user),
        )
        for fila in filas_a_registrar(item)
    ]


def reimpresion(cur, fila: dict) -> dict:
    cur.execute("UPDATE plan_documento SET descargas = descargas + 1 WHERE id = %s", (fila["id"],))
    return item_desde_fila(fila)


def fecha_de(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return parse_iso_date(value) or date.today()
