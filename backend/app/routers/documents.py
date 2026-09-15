"""Cola de documentos de Personas y Cultura: qué emitir, PDF, ZIP, reimpresión y envío por correo."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from ..auth import require_admin
from ..db import get_conn
from ..doc_service import (
    attach_jefes,
    fecha_de,
    load_emitido,
    load_emitidos,
    lock_persona,
    pendientes_por_dni,
    registrar,
    reimpresion,
    render_item,
)
from ..domain.calendar import dates_for_dni_year, today_lima
from ..domain.doc_emision import (
    EMITIDO,
    ESTADO_LABEL,
    MAX_ZIP,
    POR_EMITIR,
    PROXIMO,
    TITULO_DE_TIPO,
    tramo_json,
    tramos_desde_json,
)
from ..domain.documents import TEMPLATES
from ..domain.workflow import RECEPCIONADO, _ts, load_flujos
from ..mailer import Adjunto, Correo, MailError, Mailer, cc_fijo, mail_configured
from ..mensajes import correos_trabajador, load_mensajes, rellenar
from ..services import get_employee, list_employees, load_scope_plan

router = APIRouter(prefix="/api/documentos", tags=["documentos"])

MAX_ENVIO = 20


def _persona(emp: dict) -> dict:
    return {
        "dni": str(emp.get("dni") or ""),
        "nombre": emp.get("nombre") or "",
        "area": (emp.get("area") or "").strip(),
        "jefatura": (emp.get("jefatura") or "").strip(),
        "jefe_nombre": (emp.get("jefe_nombre") or "").strip(),
        "gerencia": (emp.get("gerencia") or emp.get("division") or "").strip(),
    }


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, date) else (str(d) if d else None)


def _item_json(emp: dict, item: dict) -> dict:
    tramo = item.get("tramo")
    return {
        **_persona(emp),
        "key": item["key"],
        "tipo": item["tipo"],
        "escenario": item["escenario"],
        "titulo": item["titulo"],
        "estado": item["estado"],
        "estado_label": ESTADO_LABEL[item["estado"]],
        "tramo": tramo_json(tramo) if tramo else None,
        "incluye_memorando": bool(tramo) and item["tipo"] in {"fraccionamiento", "modificacion"},
        "periodos": [tramo_json(p) for p in item.get("periodos") or []],
        "periodos_anteriores": [tramo_json(p) for p in item.get("periodos_anteriores") or []],
        "emitir_desde": _iso(item.get("emitir_desde")),
    }


def _fila_json(emp: dict, fila: dict) -> dict:
    tramo = None
    if fila.get("tramo_inicio") and fila.get("tramo_fin"):
        tramo = tramo_json({"inicio": fila["tramo_inicio"], "fin": fila["tramo_fin"], "dias": fila["dias"]})
    return {
        **_persona(emp),
        "id": int(fila["id"]),
        "tipo": fila["tipo"],
        "titulo": TITULO_DE_TIPO.get(fila["tipo"], fila["tipo"]),
        "estado": EMITIDO,
        "estado_label": ESTADO_LABEL[EMITIDO],
        "tramo": tramo,
        "periodos": [tramo_json(p) for p in tramos_desde_json(fila.get("periodos"))],
        "emitido_at": _ts(fila.get("emitido_at")),
        "emitido_por": fila.get("emitido_nombre") or fila.get("emitido_por") or "",
        "descargas": int(fila.get("descargas") or 0),
        "enviado_at": _ts(fila.get("enviado_at")),
        "enviado_a": fila.get("enviado_a") or "",
        "envio_error": fila.get("envio_error") or "",
    }


def _recepcionados(cur, user: dict, year: int, empresa, gerencia, area) -> list[dict]:
    employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
    flujos = load_flujos(cur, year, [e["dni"] for e in employees])
    return [e for e in employees if (flujos.get(e["dni"]) or {}).get("estado") == RECEPCIONADO]


@router.get("")
def listar_documentos(
    year: int = Query(...),
    user: dict = Depends(require_admin),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        recep = _recepcionados(cur, user, year, empresa, gerencia, area)
        items: list[dict] = []
        emitidos_json: list[dict] = []
        bloqueados: list[dict] = []
        if recep:
            daily_set, _t = load_scope_plan(cur, year, recep)
            emitidos = load_emitidos(cur, year, [e["dni"] for e in recep])
            attach_jefes(cur, recep)
            pendientes = pendientes_por_dni(recep, daily_set, emitidos, year, today)
            for emp in recep:
                dni = str(emp["dni"])
                pend, _dates, motivo = pendientes[dni]
                items.extend(_item_json(emp, it) for it in pend)
                emitidos_json.extend(_fila_json(emp, f) for f in emitidos.get(dni, []))
                if motivo:
                    # Recepcionado pero luego editado (p. ej. caso extraordinario): no se emite hasta corregir.
                    bloqueados.append({**_persona(emp), "motivo": motivo})
    items.sort(key=lambda r: (r["estado"] != POR_EMITIR, (r["tramo"] or {}).get("inicio") or "", r["nombre"]))
    emitidos_json.sort(key=lambda r: r["emitido_at"] or "", reverse=True)
    return {
        "year": year,
        "resumen": {
            POR_EMITIR: sum(1 for i in items if i["estado"] == POR_EMITIR),
            PROXIMO: sum(1 for i in items if i["estado"] == PROXIMO),
            EMITIDO: len(emitidos_json),
        },
        "max_zip": MAX_ZIP,
        "max_envio": MAX_ENVIO,
        "correo_activo": mail_configured(),
        "items": items,
        "emitidos": emitidos_json,
        "bloqueados": sorted(bloqueados, key=lambda r: r["nombre"]),
    }


class DocRef(BaseModel):
    """Un documento: pendiente (dni + key) o ya emitido (id)."""

    dni: str = ""
    key: str = ""
    id: int | None = None

    @field_validator("dni", "key")
    @classmethod
    def trim(cls, v: str) -> str:
        return (v or "").strip()


class DocsIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    docs: list[DocRef] = Field(min_length=1, max_length=MAX_ZIP)


def _resolver(cur, user: dict, year: int, ref: DocRef, today: date) -> tuple[dict, dict, list[date], list[int]]:
    """(empleado, item, fechas del plan, ids en plan_documento). Registra la emisión si estaba pendiente."""
    if ref.id is not None:
        fila = load_emitido(cur, ref.id)
        if not fila or int(fila["anio"]) != int(year):
            raise HTTPException(404, "Ese documento no existe.")
        emp = get_employee(cur, user, fila["dni"])
        if not emp:
            raise HTTPException(404, "No está en tu alcance.")
        attach_jefes(cur, [emp])
        daily_set, _t = load_scope_plan(cur, year, [emp])
        item = reimpresion(cur, fila)
        item["fecha_doc"] = fecha_de(fila.get("emitido_at"))
        return emp, item, dates_for_dni_year(daily_set, emp["dni"], year), [int(fila["id"])]

    emp = get_employee(cur, user, ref.dni)
    if not emp:
        raise HTTPException(404, "No está en tu alcance.")
    attach_jefes(cur, [emp])
    flujos = load_flujos(cur, year, [emp["dni"]])
    if (flujos.get(emp["dni"]) or {}).get("estado") != RECEPCIONADO:
        raise HTTPException(409, f"{emp['nombre']}: solo se emite de un plan ya recepcionado.")
    lock_persona(cur, year, emp["dni"])
    daily_set, _t = load_scope_plan(cur, year, [emp])
    emitidos = load_emitidos(cur, year, [emp["dni"]])
    items, dates, motivo = pendientes_por_dni([emp], daily_set, emitidos, year, today)[str(emp["dni"])]
    if motivo:
        raise HTTPException(409, f"{emp['nombre']}: {motivo}")
    item = next((i for i in items if i["key"] == ref.key), None)
    if not item:
        raise HTTPException(
            409,
            f"{emp['nombre']}: ese documento ya se emitió o el plan cambió. Actualiza la lista.",
        )
    ids = registrar(cur, year, emp["dni"], item, user)
    item["fecha_doc"] = today
    return emp, item, dates, ids


def _pdf(emp: dict, item: dict, year: int, dates: list[date]) -> tuple[bytes, str]:
    try:
        return render_item(emp, item, year=year, fecha_doc=item["fecha_doc"], programmed=dates)
    except ValueError as exc:
        raise HTTPException(400, f"{emp['nombre']}: {exc}") from exc


def _pdf_response(pdf: bytes, name: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class UnoIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    doc: DocRef


@router.post("/descargar")
def descargar_uno(body: UnoIn, user: dict = Depends(require_admin)):
    today = today_lima()
    with get_conn() as conn:
        cur = conn.cursor()
        emp, item, dates, _ids = _resolver(cur, user, body.year, body.doc, today)
        pdf, name = _pdf(emp, item, body.year, dates)
    return _pdf_response(pdf, name)


@router.post("/zip")
def descargar_zip(body: DocsIn, user: dict = Depends(require_admin)):
    today = today_lima()
    buf = BytesIO()
    with get_conn() as conn:
        cur = conn.cursor()
        with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
            used: set[str] = set()
            for ref in body.docs:
                emp, item, dates, _ids = _resolver(cur, user, body.year, ref, today)
                pdf, name = _pdf(emp, item, body.year, dates)
                folder = TEMPLATES[item["escenario"]][1]
                arc = f"{folder}/{name}"
                if arc in used:
                    arc = f"{folder}/{len(used)}_{name}"
                used.add(arc)
                zf.writestr(arc, pdf)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="documentos_gth_{body.year}.zip"'},
    )


def _periodo_texto(item: dict) -> str:
    tramo = item.get("tramo")
    if tramo:
        return f"del {tramo['inicio'].strftime('%d/%m/%Y')} al {tramo['fin'].strftime('%d/%m/%Y')}"
    periodos = item.get("periodos") or []
    return f"{len(periodos)} períodos, {sum(int(p['dias']) for p in periodos)} días"


class EnvioIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    docs: list[DocRef] = Field(min_length=1, max_length=MAX_ENVIO)


@router.post("/enviar")
def enviar_por_correo(body: EnvioIn, user: dict = Depends(require_admin)):
    """Emite (si falta) y envía cada PDF al correo del trabajador, con copia a Personas y Cultura.

    Cada documento se confirma por separado: si un correo falla, lo ya enviado queda registrado.
    """
    if not mail_configured():
        raise HTTPException(
            409,
            "El envío por correo aún no está configurado en el servidor (SMTP). "
            "Descarga el PDF y entrégalo mientras tanto.",
        )
    today = today_lima()
    enviados: list[dict] = []
    errores: list[str] = []
    try:
        with Mailer() as mailer:
            for ref in body.docs:
                with get_conn() as conn:
                    cur = conn.cursor()
                    try:
                        emp, item, dates, ids = _resolver(cur, user, body.year, ref, today)
                    except HTTPException as exc:
                        errores.append(str(exc.detail))
                        continue
                    destino, fuente = correos_trabajador(cur, emp)
                    if not destino:
                        _marcar_envio(cur, ids, "", "Sin correo registrado en Cubis.")
                        errores.append(f"{emp['nombre']}: no tiene correo registrado (se emitió igual).")
                        continue
                    pdf, name = _pdf(emp, item, body.year, dates)
                    textos = load_mensajes(cur)
                    valores = {
                        "nombre": emp.get("nombre") or "",
                        "documento": item["titulo"],
                        "periodo": _periodo_texto(item),
                        "dias": (item.get("tramo") or {}).get("dias")
                        or sum(int(p["dias"]) for p in item.get("periodos") or []),
                        "dni": emp.get("dni") or "",
                    }
                    try:
                        mailer.enviar(
                            Correo(
                                para=[destino],
                                cc=cc_fijo(),
                                asunto=rellenar(textos["doc_asunto"], valores),
                                cuerpo=rellenar(textos["doc_cuerpo"], valores),
                                adjuntos=[Adjunto(name, pdf)],
                            )
                        )
                    except MailError as exc:
                        _marcar_envio(cur, ids, destino, str(exc))
                        errores.append(f"{emp['nombre']}: {exc}")
                        continue
                    _marcar_envio(cur, ids, destino, "")
                    enviados.append({"dni": emp["dni"], "nombre": emp["nombre"], "correo": destino, "fuente": fuente})
    except MailError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"enviados": len(enviados), "detalle": enviados, "errores": errores}


def _marcar_envio(cur, ids: list[int], destino: str, error: str) -> None:
    if not ids:
        return
    if error:
        cur.execute(
            "UPDATE plan_documento SET envio_error = %s WHERE id = ANY(%s)",
            (error[:500], ids),
        )
        return
    cur.execute(
        "UPDATE plan_documento SET enviado_at = NOW(), enviado_a = %s, envio_error = '' WHERE id = ANY(%s)",
        (destino, ids),
    )
