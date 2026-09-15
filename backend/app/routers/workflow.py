from collections import defaultdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..db import get_conn
from ..domain.calendar import (
    es_apto,
    index_dates_by_dni,
    parse_iso_date,
    primer_inicio_jefatura,
    reject_if_art8_invalido,
    reject_if_plan_not_completo,
    today_lima,
    vacation_periods,
)
from ..domain.plan import persist_employee
from ..domain.workflow import (
    EDITABLE,
    ENVIADO,
    ESTADO_LABEL,
    OBSERVADO,
    RECEPCIONADO,
    VALIDADO,
    apply_recepcion_directa,
    apply_transition,
    apply_uploaded_periods,
    bandeja_estados_for,
    cumple_record_de,
    enrich_workers,
    flujo_from_row,
    goce_y_derecho,
    load_flujos,
    programmed_days_for,
    reject_if_cannot_edit,
    reject_if_cannot_send,
    upsert_flujo,
)
from ..domain.workflow_excel import build_flujo_excel, parse_flujo_upload
from ..org_scope import effective_role
from ..rate_limit import limiter
from ..services import get_employee, list_employees, load_scope_plan
from ..upload_limit import UploadTooLarge, read_upload_limited

router = APIRouter(prefix="/api/flujo", tags=["flujo"])


def _http(exc: ValueError) -> HTTPException:
    return HTTPException(400, str(exc))


class FlujoAction(BaseModel):
    year: int = Field(ge=2000, le=2100)
    dnis: list[str] = Field(min_length=1, max_length=400)
    observacion: str = Field(default="", max_length=2000)


def _items_for(
    cur,
    user: dict,
    year: int,
    empresa=None,
    gerencia=None,
    area=None,
    estados: list[str] | None = None,
    *,
    with_photos: bool = True,
):
    today = today_lima()
    employees = list_employees(cur, user, empresa, gerencia, area, with_photos=with_photos)
    daily_set, targets = load_scope_plan(cur, year, employees)
    flujos = load_flujos(cur, year, [e["dni"] for e in employees])
    rows = enrich_workers(employees, flujos, user, today)
    dates_by_dni = index_dates_by_dni(daily_set, year)
    items = []
    for w in rows:
        estado = w["flujo_estado"]
        if estados is not None and estado not in estados:
            continue
        dni = str(w["dni"])
        dias_dni = dates_by_dni.get(dni, [])
        items.append({
            **w,
            "dias_programados": len(dias_dni) or programmed_days_for(dni, daily_set, targets),
            "estado_label": ESTADO_LABEL.get(estado, estado),
            "periodos": [
                {
                    "inicio": p["inicio"].isoformat(),
                    "fin": p["fin"].isoformat(),
                    "dias": int(p["dias"]),
                }
                for p in vacation_periods(daily_set, dni, year, today, dates=dias_dni)
            ],
        })
    items.sort(key=lambda r: (r["nombre"] or "").casefold())
    return items, daily_set, targets, today


def _apply_destino(cur, user: dict, year: int, dnis: list[str], destino: str, observacion: str = ""):
    today = today_lima()
    ok, errors = [], []
    with_scope = []
    seen = set()
    for raw in dnis:
        dni = str(raw).strip()
        if not dni or dni in seen:
            continue
        seen.add(dni)
        emp = get_employee(cur, user, dni)
        if not emp:
            errors.append(f"{dni}: no está en tu alcance.")
            continue
        with_scope.append(emp)
    daily_set, targets = load_scope_plan(cur, year, with_scope)
    flujos = load_flujos(cur, year, [e["dni"] for e in with_scope])
    for emp in with_scope:
        dni = str(emp["dni"])
        row = flujos.get(dni) or flujo_from_row(None)
        try:
            if destino == ENVIADO:
                reject_if_cannot_send(emp, daily_set, targets, year, today)
            if destino == RECEPCIONADO and not es_apto(emp, today):
                raise ValueError(f"{emp['nombre']} ya no cumple el año de servicio.")
            updated = apply_transition(row, user, destino, observacion=observacion, today=today)
            if destino == ENVIADO:
                updated["apto"] = True
                cumple = cumple_record_de(emp, today)
                updated["cumple_record"] = cumple.isoformat() if cumple else None
            upsert_flujo(cur, year, dni, updated)
            ok.append({"dni": dni, "nombre": emp["nombre"], "estado": destino})
        except ValueError as exc:
            errors.append(f"{emp['nombre']}: {exc}")
    return {"ok": ok, "errors": errors, "enviados": len(ok), "rechazados": len(errors)}


@router.get("")
def list_flujo(
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
    bandeja: bool = Query(default=False),
):
    estados = bandeja_estados_for(user) if bandeja else None
    with get_conn(write=False) as conn:
        items, _d, _t, _today = _items_for(conn.cursor(), user, year, empresa, gerencia, area, estados)
    role = effective_role(user)
    return {
        "year": year,
        "rol": role,
        "bandeja": bandeja,
        "items": items,
        "pendientes": sum(
            1
            for i in items
            if (role == "GERENTE" and i["flujo_estado"] == ENVIADO)
            or (role == "ADMIN" and i["flujo_estado"] == VALIDADO)
            or (role == "JEFE" and i["flujo_estado"] == OBSERVADO)
        ),
    }


@router.post("/enviar")
def enviar(body: FlujoAction, user: dict = Depends(get_current_user)):
    if effective_role(user) != "JEFE":
        raise HTTPException(403, "Solo el jefe envía el plan al gerente.")
    with get_conn() as conn:
        return _apply_destino(conn.cursor(), user, body.year, body.dnis, ENVIADO)


@router.post("/enviar-aptos")
def enviar_aptos(
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    if effective_role(user) != "JEFE":
        raise HTTPException(403, "Solo el jefe envía el plan al gerente.")
    with get_conn() as conn:
        cur = conn.cursor()
        items, daily_set, targets, today = _items_for(
            cur, user, year, empresa, gerencia, area, with_photos=False
        )
        dates_by_dni = index_dates_by_dni(daily_set, year)
        incompletos = []
        dnis = []
        for i in items:
            if not i.get("apto"):
                continue
            dias, derecho, _ = goce_y_derecho(
                i, daily_set, targets, year, today, dates=dates_by_dni.get(str(i["dni"]), [])
            )
            if dias != derecho:
                incompletos.append(i)
            elif i["flujo_estado"] in EDITABLE:
                dnis.append(i["dni"])
        if incompletos:
            n = len(incompletos)
            raise HTTPException(
                400,
                f"No puedes enviar al gerente: {n} persona{'s' if n != 1 else ''} "
                f"no tiene{'n' if n != 1 else ''} el goce completo "
                "(la suma de períodos debe ser el derecho, por ejemplo 30 de 30). "
                "Corrígelo en Planificación o en el Excel.",
            )
        if not dnis:
            raise HTTPException(400, "No hay aptos con el goce completo en borrador para enviar.")
        return _apply_destino(cur, user, year, dnis, ENVIADO)


@router.post("/validar")
def validar(body: FlujoAction, user: dict = Depends(get_current_user)):
    if effective_role(user) != "GERENTE":
        raise HTTPException(403, "Solo el gerente valida el envío del jefe.")
    with get_conn() as conn:
        return _apply_destino(conn.cursor(), user, body.year, body.dnis, VALIDADO)


@router.post("/observar")
def observar(body: FlujoAction, user: dict = Depends(get_current_user)):
    if effective_role(user) not in {"GERENTE", "ADMIN"}:
        raise HTTPException(403, "Solo el gerente o Personas y Cultura pueden observar.")
    with get_conn() as conn:
        return _apply_destino(conn.cursor(), user, body.year, body.dnis, OBSERVADO, body.observacion)


@router.post("/recepcionar")
def recepcionar(body: FlujoAction, user: dict = Depends(get_current_user)):
    if effective_role(user) != "ADMIN":
        raise HTTPException(403, "Solo Personas y Cultura recepciona la validación del gerente.")
    with get_conn() as conn:
        return _apply_destino(conn.cursor(), user, body.year, body.dnis, RECEPCIONADO)


@router.post("/recepcionar-directo")
def recepcionar_directo(body: FlujoAction, user: dict = Depends(get_current_user)):
    """Plan que programó Personas y Cultura: pasa a Recepcionado y sus documentos a Documentos."""
    if effective_role(user) != "ADMIN":
        raise HTTPException(403, "Solo Personas y Cultura puede recepcionar directamente.")
    today = today_lima()
    ok, errors = [], []
    with get_conn() as conn:
        cur = conn.cursor()
        emps = []
        for dni in dict.fromkeys(str(d).strip() for d in body.dnis if str(d).strip()):
            emp = get_employee(cur, user, dni)
            if emp:
                emps.append(emp)
            else:
                errors.append(f"{dni}: no está en tu alcance.")
        daily_set, targets = load_scope_plan(cur, body.year, emps)
        flujos = load_flujos(cur, body.year, [e["dni"] for e in emps])
        for emp in emps:
            dni = str(emp["dni"])
            try:
                # Mismas reglas que el envío del jefe: apto, derecho completo y Art. 8.
                reject_if_cannot_send(emp, daily_set, targets, body.year, today)
                updated = apply_recepcion_directa(flujos.get(dni) or flujo_from_row(None), user)
                cumple = cumple_record_de(emp, today)
                updated["cumple_record"] = cumple.isoformat() if cumple else None
                upsert_flujo(cur, body.year, dni, updated)
                ok.append({"dni": dni, "nombre": emp["nombre"], "estado": RECEPCIONADO})
            except ValueError as exc:
                errors.append(str(exc) if str(exc).startswith(emp["nombre"]) else f"{emp['nombre']}: {exc}")
    return {"ok": ok, "errors": errors, "recepcionados": len(ok), "rechazados": len(errors)}


@router.get("/excel")
@limiter.limit("8/minute")
def descargar_excel(
    request: Request,
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    today = today_lima()
    cy, cw, _ = today.isocalendar()
    with get_conn(write=False) as conn:
        items, daily_set, targets, _t = _items_for(
            conn.cursor(), user, year, empresa, gerencia, area, with_photos=False
        )
    data = build_flujo_excel(items, daily_set, targets, year, cy, cw, rol=effective_role(user))
    filename = f"FLUJO_VACACIONES_{year}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _validate_period_saldo(emp: dict, daily_set, year: int, today) -> None:
    dni = str(emp["dni"])
    dias, derecho, adelanto = goce_y_derecho(emp, daily_set, None, year, today)
    reject_if_plan_not_completo(
        nombre=emp.get("nombre") or "",
        programados=dias,
        derecho=derecho,
        es_adelanto=adelanto,
    )
    reject_if_art8_invalido(daily_set, dni, year)


@router.post("/excel")
@limiter.limit("8/minute")
async def cargar_excel(
    request: Request,
    year: int,
    user: dict = Depends(get_current_user),
    file: UploadFile = File(...),
):
    try:
        raw = await read_upload_limited(file)
    except UploadTooLarge:
        raise HTTPException(413, "El Excel no puede superar 4 MB.")
    if not raw:
        raise HTTPException(400, "El archivo está vacío.")
    try:
        flujo_rows, periods = parse_flujo_upload(raw)
    except ValueError as exc:
        raise _http(exc) from exc

    role = effective_role(user)
    today = today_lima()
    by_dni_periods: dict[str, list] = defaultdict(list)
    for p in periods:
        by_dni_periods[str(p["dni"])].append(p)
    flujo_by_dni = {str(r["dni"]): r for r in flujo_rows if r.get("dni")}
    all_dnis = set(flujo_by_dni) | set(by_dni_periods)

    ok, errors = [], []
    with get_conn() as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, with_photos=False)
        emp_map = {str(e["dni"]): e for e in employees}
        needed = [emp_map[d] for d in all_dnis if d in emp_map]
        daily_set, targets = load_scope_plan(cur, year, needed) if needed else (set(), {})
        flujos = load_flujos(cur, year, [e["dni"] for e in needed])

        for dni in sorted(all_dnis):
            emp = emp_map.get(dni)
            if not emp:
                errors.append(f"{dni}: no está en tu alcance.")
                continue
            row = flujos.get(dni) or flujo_from_row(None)
            wanted_row = flujo_by_dni.get(dni) or {}
            wanted = str(wanted_row.get("estado") or "").strip().upper()
            nota = str(wanted_row.get("observacion") or "").strip()
            has_periods = dni in by_dni_periods
            try:
                if not es_apto(emp, today):
                    raise ValueError(
                        f"{emp['nombre']} aún no cumple el año de servicio. No se programa ni entra al flujo."
                    )
                if role == "JEFE" and has_periods:
                    reject_if_cannot_edit(user, emp, row["estado"], today)
                    apply_uploaded_periods(
                        daily_set,
                        targets,
                        dni,
                        year,
                        by_dni_periods[dni],
                        today,
                        fecha_ingreso=parse_iso_date(emp.get("fecha_ingreso")),
                        nombre=emp["nombre"],
                        primer_inicio=primer_inicio_jefatura(today),
                    )
                    _validate_period_saldo(emp, daily_set, year, today)
                    persist_employee(cur, year, emp, daily_set, targets, user["correo"])
                if wanted and wanted != row["estado"]:
                    if role == "JEFE" and wanted == ENVIADO:
                        reject_if_cannot_send(emp, daily_set, targets, year, today)
                        updated = apply_transition(row, user, ENVIADO)
                        updated["apto"] = True
                        cumple = cumple_record_de(emp, today)
                        updated["cumple_record"] = cumple.isoformat() if cumple else None
                        upsert_flujo(cur, year, dni, updated)
                        row = updated
                    elif role == "GERENTE" and wanted in {VALIDADO, OBSERVADO}:
                        updated = apply_transition(row, user, wanted, observacion=nota)
                        upsert_flujo(cur, year, dni, updated)
                        row = updated
                    elif role == "ADMIN" and wanted in {RECEPCIONADO, OBSERVADO}:
                        if wanted == RECEPCIONADO and not es_apto(emp, today):
                            raise ValueError(f"{emp['nombre']} ya no cumple el año de servicio.")
                        updated = apply_transition(row, user, wanted, observacion=nota)
                        upsert_flujo(cur, year, dni, updated)
                        row = updated
                    else:
                        raise ValueError(
                            f"Tu rol no puede pasar a {ESTADO_LABEL.get(wanted, wanted)}."
                        )
                ok.append({"dni": dni, "nombre": emp["nombre"], "estado": row["estado"]})
            except ValueError as exc:
                errors.append(str(exc) if str(exc).startswith(str(emp.get("nombre") or "")) else f"{emp['nombre']}: {exc}")
    return {"ok": ok, "errors": errors, "aplicados": len(ok), "rechazados": len(errors)}
