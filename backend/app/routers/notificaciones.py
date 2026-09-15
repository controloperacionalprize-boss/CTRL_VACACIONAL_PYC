"""Avisos por correo a jefaturas: quién falta programar y quién sale el mes siguiente.

Reemplaza el correo que Personas y Cultura envía a mano a inicio de cada mes.
"""
from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..config import get_settings
from ..db import get_conn
from ..domain.alerts import dates_in_month, month_label, next_calendar_month
from ..domain.calendar import es_apto, group_consecutive_dates, index_dates_by_dni, today_lima
from ..domain.workflow import OBSERVADO, goce_y_derecho, load_flujos
from ..mailer import Correo, MailError, Mailer, cc_fijo, email_valido, mail_configured
from ..mensajes import load_mensajes, rellenar
from ..org_scope import resolve_division
from ..services import list_employees, load_scope_plan

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])

MAX_FILAS = 40


def _jefes(cur) -> list[dict]:
    cur.execute(
        """SELECT correo, nombre_persona, nombre_usuario, gerencia, area
           FROM users
           WHERE activo = TRUE AND upper(rol) = 'JEFE' AND COALESCE(area, '') <> ''
           ORDER BY nombre_persona, correo"""
    )
    out = []
    for r in cur.fetchall():
        gerencia = r["gerencia"] or ""
        area = r["area"] or ""
        out.append({
            "correo": r["correo"],
            "nombre": r["nombre_persona"] or r["nombre_usuario"] or r["correo"],
            "rol": "JEFE",
            "gerencia": gerencia,
            "area": area,
            "division": resolve_division(gerencia, area) or gerencia,
        })
    return out


def resumen_jefe(cur, jefe: dict, year: int, today: date) -> dict:
    """Lo que se le avisa a una jefatura (mismo alcance que ve en la app)."""
    employees = list_employees(cur, jefe, with_photos=False)
    aptos = [e for e in employees if es_apto(e, today)]
    daily_set, targets = load_scope_plan(cur, year, aptos)
    por_dni = index_dates_by_dni(daily_set, year)
    flujos = load_flujos(cur, year, [e["dni"] for e in aptos])
    ny, nm = next_calendar_month(today)
    if ny != year:
        daily_next, _ = load_scope_plan(cur, ny, aptos)
        mes = dates_in_month(daily_next, ny, nm)
    else:
        mes = dates_in_month(daily_set, ny, nm)

    pendientes, salidas, observados = [], [], []
    for e in aptos:
        dni = str(e["dni"])
        dias, derecho, _ = goce_y_derecho(e, daily_set, targets, year, today, dates=por_dni.get(dni, []))
        if dias < derecho:
            pendientes.append(f"- {e['nombre']}: {dias} de {derecho} días programados")
        if (flujos.get(dni) or {}).get("estado") == OBSERVADO:
            nota = (flujos[dni].get("observacion") or "").strip()
            observados.append(f"- {e['nombre']}" + (f": {nota}" if nota else ""))
        if mes.get(dni):
            tramos = " · ".join(f"{a.strftime('%d/%m')}–{b.strftime('%d/%m')}" for a, b in group_consecutive_dates(mes[dni]))
            salidas.append(f"- {e['nombre']}: {tramos}")
    return {
        "correo": jefe["correo"],
        "nombre": jefe["nombre"],
        "area": jefe["area"],
        "mes": month_label(ny, nm),
        "pendientes": pendientes,
        "salidas": salidas,
        "observados": observados,
    }


def _detalle(r: dict) -> str:
    bloques = []
    for titulo, filas in (
        ("Falta programar el goce completo", r["pendientes"]),
        ("Planes observados por corregir", r["observados"]),
        (f"Salen de vacaciones en {r['mes'].lower()}", r["salidas"]),
    ):
        if not filas:
            continue
        extra = f"\n- … y {len(filas) - MAX_FILAS} más" if len(filas) > MAX_FILAS else ""
        bloques.append(f"{titulo} ({len(filas)}):\n" + "\n".join(filas[:MAX_FILAS]) + extra)
    return "\n\n".join(bloques)


def _con_novedades(r: dict) -> bool:
    return bool(r["pendientes"] or r["observados"] or r["salidas"])


def _vista(r: dict) -> dict:
    return {
        "correo": r["correo"],
        "nombre": r["nombre"],
        "area": r["area"],
        "pendientes": len(r["pendientes"]),
        "observados": len(r["observados"]),
        "salidas": len(r["salidas"]),
        "correo_valido": email_valido(r["correo"]),
    }


@router.get("/jefaturas")
def vista_previa(year: int = Query(..., ge=2000, le=2100), user: dict = Depends(require_admin)):
    today = today_lima()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        resumenes = [resumen_jefe(cur, j, year, today) for j in _jefes(cur)]
        cur.execute("SELECT valor, actualizado FROM app_config WHERE clave = 'jefes_ultimo_envio'")
        ultimo = cur.fetchone()
    return {
        "year": year,
        "correo_activo": mail_configured(),
        "ultimo_envio": ultimo["valor"] if ultimo else "",
        "jefaturas": [_vista(r) for r in resumenes if _con_novedades(r)],
        "sin_novedades": sum(1 for r in resumenes if not _con_novedades(r)),
    }


class EnvioJefesIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    # Vacío = todas las jefaturas con novedades.
    correos: list[str] = Field(default_factory=list, max_length=500)


def _enviar(year: int, correos: list[str], autor: str) -> dict:
    if not mail_configured():
        raise HTTPException(
            409, "El envío por correo aún no está configurado en el servidor (SMTP)."
        )
    today = today_lima()
    wanted = {c.strip().lower() for c in correos if c.strip()}
    enviados, errores = [], []
    with get_conn() as conn:
        cur = conn.cursor()
        textos = load_mensajes(cur)
        resumenes = [
            resumen_jefe(cur, j, year, today)
            for j in _jefes(cur)
            if not wanted or j["correo"].lower() in wanted
        ]
        try:
            with Mailer() as mailer:
                for r in resumenes:
                    if not _con_novedades(r):
                        continue
                    valores = {"jefe": r["nombre"], "area": r["area"], "mes": r["mes"], "detalle": _detalle(r)}
                    try:
                        mailer.enviar(
                            Correo(
                                para=[r["correo"]],
                                cc=cc_fijo(),
                                asunto=rellenar(textos["jefe_asunto"], valores),
                                cuerpo=rellenar(textos["jefe_cuerpo"], valores),
                            )
                        )
                        enviados.append(r["correo"])
                    except MailError as exc:
                        errores.append(f"{r['nombre']}: {exc}")
        except MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        if enviados:
            cur.execute(
                """INSERT INTO app_config (clave, valor, actualizado, actualizado_por)
                   VALUES ('jefes_ultimo_envio', %s, NOW(), %s)
                   ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor,
                       actualizado = NOW(), actualizado_por = EXCLUDED.actualizado_por""",
                (f"{today.strftime('%d/%m/%Y')} · {len(enviados)} jefatura(s) · {autor}", autor),
            )
    return {"enviados": len(enviados), "errores": errores}


@router.post("/jefaturas")
def enviar_jefaturas(body: EnvioJefesIn, user: dict = Depends(require_admin)):
    return _enviar(body.year, body.correos, user.get("correo") or "")


@router.post("/jefaturas/cron")
def enviar_jefaturas_cron(x_cron_token: str = Header(default="")):
    """Para una tarea programada mensual (Render Cron / UptimeRobot). Requiere CRON_TOKEN."""
    esperado = (get_settings().cron_token or "").strip()
    if not esperado or not hmac.compare_digest(x_cron_token.strip(), esperado):
        raise HTTPException(404, "No encontrado.")
    today = today_lima()
    return _enviar(today.year, [], "tarea programada")
