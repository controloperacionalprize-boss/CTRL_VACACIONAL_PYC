from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, field_validator

from ..auth import get_current_user, require_admin
from ..db import get_conn
from ..doc_service import attach_jefes, item_context, load_emitidos, pendientes_por_dni, render_item
from ..domain.calendar import (
    DERECHO_ANUAL,
    TOTAL_SEMANAS,
    allowed_type,
    apply_consecutive_span,
    clear_dates_for_week,
    count_days_in_record,
    date_is_past,
    dates_for_dni_year,
    derecho_vigente,
    ensure_within_derecho,
    is_business_day,
    iso_monday,
    key_daily,
    parse_iso_date,
    primer_inicio_jefatura,
    record_cumplido,
    move_vacation_period,
    refresh_week_targets,
    reject_if_art8_invalido,
    reject_if_despues_de_vencimiento,
    reject_if_exceeds_saldo,
    reject_if_start_in_past,
    reject_if_tramo_cerrado,
    selected_count,
    today_lima,
    tramo_cerrado,
    vacation_periods,
    vacation_record_for,
    week_dates,
    week_is_locked,
)
from ..domain.documents_pdf import render_html
from ..domain.plan import log_change, persist_employee, sparse_weeks, validate_plan
from ..domain.workflow import (
    enrich_workers,
    flujo_from_row,
    load_flujos,
    reject_if_cannot_edit,
)
from ..org_scope import effective_role
from ..services import get_employee, list_employees, load_scope_plan

router = APIRouter(prefix="/api/plan", tags=["plan"])

_NOT_IN_SCOPE = "Esa persona no aparece con el filtro actual."


def _http_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(400, str(exc))


def _es_admin(user: dict) -> bool:
    return effective_role(user) == "ADMIN"


def _semana_bloqueada(user: dict, year: int, week: int, today: date) -> bool:
    """Semanas pasadas: nadie. Semana cuyo viernes previo ya pasó: solo Personas y Cultura (extraordinario)."""
    if week_is_locked(year, week, today):
        return True
    monday = iso_monday(year, week)
    return not _es_admin(user) and monday is not None and tramo_cerrado(monday, today)


def _reject_if_semana_bloqueada(user: dict, year: int, week: int, today: date) -> None:
    if week_is_locked(year, week, today):
        raise HTTPException(400, "Esa semana ya pasó y no se puede cambiar.")
    monday = iso_monday(year, week)
    if not _es_admin(user) and monday is not None:
        try:
            reject_if_tramo_cerrado(monday, today)
        except ValueError as exc:
            raise _http_value_error(exc) from exc


def _reject_if_inicio_cerrado(user: dict, inicio: date, today: date) -> None:
    if _es_admin(user):
        return
    try:
        reject_if_tramo_cerrado(inicio, today)
    except ValueError as exc:
        raise _http_value_error(exc) from exc


def _pendientes_plan(cur, emp: dict, daily_set, year: int, today: date) -> tuple[list[dict], str, list[date]]:
    """(documentos pendientes, motivo si no hay ninguno, fechas del plan). Misma regla que Documentos."""
    dni = str(emp["dni"])
    emitidos = load_emitidos(cur, year, [dni])
    items, dates, motivo = pendientes_por_dni([emp], daily_set, emitidos, year, today)[dni]
    if motivo or items or not dates:
        return items, motivo, dates
    return [], "Sus documentos ya se emitieron. Reimprímelos desde Documentos.", dates


def _documento_plan(cur, user: dict, emp: dict, daily_set, targets, year: int, today: date) -> dict:
    """Para la respuesta de guardar: {"documento": {...}} o {"documento_falta": motivo}. Solo Personas y Cultura."""
    if not _es_admin(user):
        return {}
    items, falta, _dates = _pendientes_plan(cur, emp, daily_set, year, today)
    if not items:
        return {"documento_falta": falta} if falta else {}
    first = items[0]
    return {"documento": {"escenario": first["escenario"], "titulo": first["titulo"], "key": first["key"]}}


def _load_employee_plan(cur, user: dict, dni: str, year: int):
    emp = get_employee(cur, user, dni)
    if not emp:
        raise HTTPException(404, _NOT_IN_SCOPE)
    daily_set, targets = load_scope_plan(cur, year, [emp])
    return emp, daily_set, targets


def _guard_flujo_edit(cur, user: dict, emp: dict, year: int, today: date | None = None) -> None:
    today = today or today_lima()
    flujos = load_flujos(cur, year, [emp["dni"]])
    estado = (flujos.get(str(emp["dni"])) or flujo_from_row(None))["estado"]
    try:
        reject_if_cannot_edit(user, emp, estado, today)
    except ValueError as exc:
        raise _http_value_error(exc) from exc


def _persist_and_log(cur, year: int, emp: dict, daily_set, targets, user: dict, deltas: list) -> None:
    persist_employee(cur, year, emp, daily_set, targets, user["correo"])
    _log_week_deltas(cur, emp, year, deltas, user)


def _reject_if_no_saldo(
    emp: dict,
    *,
    pedidas: int,
    programados_base: int,
    derecho: int,
    es_adelanto: bool,
) -> None:
    reject_if_exceeds_saldo(
        nombre=emp["nombre"],
        pedidas=pedidas,
        programados_base=programados_base,
        derecho=derecho,
        es_adelanto=es_adelanto,
    )


def _ensure_saldo(
    emp: dict,
    *,
    pedidas: int,
    programados_base: int,
    daily_set,
    dni: str,
    year: int,
    derecho: int,
    es_adelanto: bool,
) -> None:
    ensure_within_derecho(
        daily_set,
        dni,
        year,
        nombre=emp["nombre"],
        pedidas=pedidas,
        programados_base=programados_base,
        derecho=derecho,
        es_adelanto=es_adelanto,
        fecha_ingreso=emp.get("fecha_ingreso"),
    )


def _derecho_for_emp(emp: dict, today: date) -> tuple[int, bool]:
    """(tope de días, es_adelanto) según si el trabajador ya cumplió el récord anual."""
    ingreso = parse_iso_date(emp.get("fecha_ingreso"))
    es_adelanto = not record_cumplido(ingreso, today)
    return derecho_vigente(ingreso, today), es_adelanto


def _log_week_deltas(cur, emp: dict, year: int, deltas: list, user: dict) -> None:
    for wk, old_days, new_days in deltas:
        if old_days == new_days:
            continue
        log_change(
            cur,
            jefatura=emp["jefatura"],
            year=year,
            dni=emp["dni"],
            nombre=emp["nombre"],
            tipo=emp["tipo_personal"],
            old_week=wk,
            old_days=old_days,
            new_week=wk,
            new_days=new_days,
            user=user,
        )


class WeekPatch(BaseModel):
    year: int
    dni: str
    week: int
    days: int
    start_date: date | None = None
    empresa: list[str] | None = None
    gerencia: list[str] | None = None
    area: list[str] | None = None

    @field_validator("start_date", mode="before")
    @classmethod
    def empty_start_date(cls, v):
        if v == "":
            return None
        return v

    @field_validator("days")
    @classmethod
    def days_in_week(cls, v: int) -> int:
        # 0 limpia; 1–DERECHO_ANUAL puede derramar a semanas siguientes.
        if v < 0 or v > DERECHO_ANUAL:
            raise ValueError(f"Indica entre 0 y {DERECHO_ANUAL} días.")
        return v


class ConsecutiveIn(BaseModel):
    year: int
    dni: str
    start_date: date
    days: int
    empresa: list[str] | None = None
    gerencia: list[str] | None = None
    area: list[str] | None = None

    @field_validator("start_date", mode="before")
    @classmethod
    def require_start_date(cls, v):
        if v in (None, ""):
            raise ValueError("Indica desde qué día empiezan las vacaciones.")
        return v

    @field_validator("days")
    @classmethod
    def days_range(cls, v: int) -> int:
        if v < 1 or v > DERECHO_ANUAL:
            raise ValueError(f"Indica cuántos días son (entre 1 y {DERECHO_ANUAL}).")
        return v

    @field_validator("dni")
    @classmethod
    def require_dni(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("Selecciona a la persona.")
        return v


class DailyPatch(BaseModel):
    year: int
    dni: str
    week: int
    dates: list[date]
    empresa: list[str] | None = None
    gerencia: list[str] | None = None
    area: list[str] | None = None


@router.get("")
def get_plan(
    year: int = Query(...),
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
    q: str = Query(default=""),
):
    today = today_lima()
    current_year, current_week, _ = today.isocalendar()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area, q, with_photos=True)
        daily_set, targets = load_scope_plan(cur, year, employees)
        dnis = [e["dni"] for e in employees]
        counts = {}
        if dnis:
            cur.execute(
                """SELECT dni, COUNT(*) AS n FROM change_log
                   WHERE anio = %s AND dni = ANY(%s) GROUP BY dni""",
                (year, dnis),
            )
            counts = {str(r["dni"]): int(r["n"]) for r in cur.fetchall()}
        flujos = load_flujos(cur, year, dnis)

    rows = []
    aptos = programados = pendientes = dias = 0
    for e in sorted(employees, key=lambda x: x["nombre"].casefold()):
        weeks = sparse_weeks(targets, e["dni"])
        total = sum(weeks.values())
        tope, es_adelanto = _derecho_for_emp(e, today)
        rec = vacation_record_for(parse_iso_date(e.get("fecha_ingreso")), [], year, today)
        vence = rec.get("fecha_vencimiento")
        rows.append({
            **e,
            "weeks": weeks,
            "total_dias": total,
            "cambios": counts.get(e["dni"], 0),
            "record_cumplido": not es_adelanto,
            "tope_dias": tope,
            "record_vacacional": rec.get("record_vacacional") or "",
            "fecha_vencimiento": vence.isoformat() if isinstance(vence, date) else None,
        })
        if es_adelanto:
            continue
        aptos += 1
        dias += total
        if total:
            programados += 1
        else:
            pendientes += 1

    rows = enrich_workers(rows, flujos, user, today)
    # Primer día que este usuario puede programar: Personas y Cultura desde hoy; jefatura desde la
    # primera semana cuyo viernes previo aún no pasa.
    primer_inicio = today if _es_admin(user) else primer_inicio_jefatura(today)

    return {
        "year": year,
        "today": today.isoformat(),
        "primer_inicio": primer_inicio.isoformat(),
        "current_year": current_year,
        "current_week": current_week,
        "total_semanas": TOTAL_SEMANAS,
        "workers": rows,
        "kpis": {
            "trabajadores": aptos,
            "programados": programados,
            "pendientes": pendientes,
            "dias": dias,
        },
    }


@router.get("/week-detail")
def week_detail(
    year: int,
    dni: str,
    week: int,
    user: dict = Depends(get_current_user),
):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, dni, year)
    dates = week_dates(year, week)
    today = today_lima()
    selected = [d.isoformat() for d in dates if key_daily(dni, d) in daily_set]
    return {
        "dni": dni,
        "week": week,
        "today": today.isoformat(),
        "locked": _semana_bloqueada(user, year, week, today),
        "target": int(targets.get((dni, week), 0)),
        "dates": [
            {
                "fecha": d.isoformat(),
                "weekday": d.weekday(),
                "selected": d.isoformat() in selected,
                # "past" = no se puede elegir como inicio (ya pasó o, para jefatura, la semana cerró).
                "past": date_is_past(d, today) or (not _es_admin(user) and tramo_cerrado(d, today)),
            }
            for d in dates
        ],
        "tipo": emp["tipo_personal"],
    }


@router.patch("/week")
def patch_week(body: WeekPatch, user: dict = Depends(get_current_user)):
    today = today_lima()
    _reject_if_semana_bloqueada(user, body.year, body.week, today)
    with get_conn() as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, body.dni, body.year)
        _guard_flujo_edit(cur, user, emp, body.year)
        nuevas: list = []
        if body.days == 0:
            clear_dates_for_week(
                daily_set, body.dni, body.year, body.week, keep_past=True
            )
            deltas = refresh_week_targets(
                daily_set, targets, body.dni, body.year, [body.week]
            )
            try:
                if not _derecho_for_emp(emp, today)[1]:
                    reject_if_art8_invalido(daily_set, body.dni, body.year)
            except ValueError as exc:
                raise _http_value_error(exc) from exc
        else:
            if not body.start_date:
                raise HTTPException(400, "Si pones días de vacaciones, indica desde qué fecha empiezan.")
            if body.start_date not in set(week_dates(body.year, body.week)):
                raise HTTPException(400, f"La fecha debe caer en la semana {body.week}.")
            try:
                reject_if_start_in_past(body.start_date, today)
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            _reject_if_inicio_cerrado(user, body.start_date, today)
            ingreso = parse_iso_date(emp.get("fecha_ingreso"))
            programados_base = count_days_in_record(
                daily_set,
                body.dni,
                body.year,
                body.start_date,
                ingreso,
                exclude=week_dates(body.year, body.week),
            )
            derecho, es_adelanto = _derecho_for_emp(emp, today_lima())
            try:
                _reject_if_no_saldo(
                    emp,
                    pedidas=body.days,
                    programados_base=programados_base,
                    derecho=derecho,
                    es_adelanto=es_adelanto,
                )
                nuevas, deltas = apply_consecutive_span(
                    daily_set,
                    targets,
                    body.dni,
                    emp["tipo_personal"],
                    body.start_date,
                    body.days,
                    body.year,
                    clear_week=body.week,
                    fecha_ingreso=ingreso,
                    nombre=emp["nombre"],
                    validar_art8=not es_adelanto,
                )
                _ensure_saldo(
                    emp,
                    pedidas=body.days,
                    programados_base=programados_base,
                    daily_set=daily_set,
                    dni=body.dni,
                    year=body.year,
                    derecho=derecho,
                    es_adelanto=es_adelanto,
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
        _persist_and_log(cur, body.year, emp, daily_set, targets, user, deltas)
        doc = _documento_plan(cur, user, emp, daily_set, targets, body.year, today) if body.days else {}
    weeks = {str(wk): new for wk, _old, new in deltas}
    out = {"ok": True, "weeks": weeks, "selected": weeks.get(str(body.week), 0), **doc}
    if nuevas:
        out["fechas"] = [d.isoformat() for d in nuevas]
        out["fin"] = nuevas[-1].isoformat()
    return out


@router.patch("/daily")
def patch_daily(body: DailyPatch, user: dict = Depends(get_current_user)):
    today = today_lima()
    _reject_if_semana_bloqueada(user, body.year, body.week, today)
    with get_conn() as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, body.dni, body.year)
        _guard_flujo_edit(cur, user, emp, body.year)
        allowed = set(week_dates(body.year, body.week))
        modo = allowed_type(emp["tipo_personal"], body.dni)
        for d in body.dates:
            if d not in allowed:
                continue
            if date_is_past(d, today) and key_daily(body.dni, d) not in daily_set:
                raise HTTPException(
                    400,
                    f"No se puede marcar el {d.strftime('%d/%m/%Y')}: solo desde hoy hacia adelante.",
                )
        try:
            reject_if_despues_de_vencimiento(
                list(body.dates),
                parse_iso_date(emp.get("fecha_ingreso")),
                body.year,
                nombre=emp["nombre"],
                today=today,
            )
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        for d in week_dates(body.year, body.week):
            if date_is_past(d, today):
                continue
            daily_set.discard(key_daily(body.dni, d))
        for d in body.dates:
            if d not in allowed or date_is_past(d, today):
                continue
            if modo != "CALENDARIO" and not is_business_day(d):
                continue
            daily_set.add(key_daily(body.dni, d))
        n = selected_count(daily_set, body.dni, week_dates(body.year, body.week))
        ingreso = parse_iso_date(emp.get("fecha_ingreso"))
        anchor = min(body.dates, default=week_dates(body.year, body.week)[0])
        programados_base = count_days_in_record(
            daily_set, body.dni, body.year, anchor, ingreso, exclude=week_dates(body.year, body.week)
        )
        derecho, es_adelanto = _derecho_for_emp(emp, today)
        try:
            _reject_if_no_saldo(
                emp,
                pedidas=n,
                programados_base=programados_base,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
            _ensure_saldo(
                emp,
                pedidas=n,
                programados_base=programados_base,
                daily_set=daily_set,
                dni=body.dni,
                year=body.year,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
            if not es_adelanto:
                reject_if_art8_invalido(daily_set, body.dni, body.year)
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        old = int(targets.get((body.dni, body.week), 0))
        if n:
            targets[(body.dni, body.week)] = min(n, 7)
        else:
            targets.pop((body.dni, body.week), None)
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        if old != n:
            _log_week_deltas(cur, emp, body.year, [(body.week, old, n)], user)
    return {"ok": True, "days": n}


@router.post("/consecutive")
def consecutive(body: ConsecutiveIn, user: dict = Depends(get_current_user)):
    today = today_lima()
    _reject_if_inicio_cerrado(user, body.start_date, today)
    with get_conn() as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, body.dni, body.year)
        _guard_flujo_edit(cur, user, emp, body.year)
        ingreso = parse_iso_date(emp.get("fecha_ingreso"))
        programados = count_days_in_record(daily_set, body.dni, body.year, body.start_date, ingreso)
        derecho, es_adelanto = _derecho_for_emp(emp, today)
        try:
            _reject_if_no_saldo(
                emp,
                pedidas=body.days,
                programados_base=programados,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
            nuevas, deltas = apply_consecutive_span(
                daily_set,
                targets,
                body.dni,
                emp["tipo_personal"],
                body.start_date,
                body.days,
                body.year,
                fecha_ingreso=ingreso,
                nombre=emp["nombre"],
                validar_art8=not es_adelanto,
            )
            _ensure_saldo(
                emp,
                pedidas=body.days,
                programados_base=programados,
                daily_set=daily_set,
                dni=body.dni,
                year=body.year,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        _persist_and_log(cur, body.year, emp, daily_set, targets, user, deltas)
        doc = _documento_plan(cur, user, emp, daily_set, targets, body.year, today)
    return {
        "ok": True,
        "fechas": [d.isoformat() for d in nuevas],
        "weeks": {str(wk): new for wk, _old, new in deltas},
        "fin": nuevas[-1].isoformat() if nuevas else None,
        **doc,
    }


class PeriodMoveIn(BaseModel):
    year: int
    dni: str
    old_start: date
    new_start: date
    days: int | None = None


@router.get("/periods")
def get_periods(year: int, dni: str, user: dict = Depends(get_current_user)):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        _emp, daily_set, _targets = _load_employee_plan(cur, user, dni, year)
    today = today_lima()
    periods = vacation_periods(daily_set, dni, year, today)
    admin = _es_admin(user)
    return {
        "dni": dni,
        "year": year,
        "today": today.isoformat(),
        "periodos": [
            {
                "inicio": p["inicio"].isoformat(),
                "fin": p["fin"].isoformat(),
                "dias": p["dias"],
                "estado": p["estado"],
                # Tramo con la semana ya cerrada: solo Personas y Cultura lo mueve (caso extraordinario).
                "editable": p["editable"] or (admin and p["estado"] == "cerrado"),
            }
            for p in periods
        ],
    }


@router.post("/period-move")
def period_move(body: PeriodMoveIn, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, body.dni, body.year)
        _guard_flujo_edit(cur, user, emp, body.year)
        today = today_lima()
        periods = vacation_periods(daily_set, body.dni, body.year, today)
        found = next((p for p in periods if p["inicio"] == body.old_start), None)
        if not found:
            raise HTTPException(400, "No se encontró ese período de vacaciones.")
        n = int(body.days) if body.days is not None else int(found["dias"])
        ingreso = parse_iso_date(emp.get("fecha_ingreso"))
        old_dates = [
            d for d in dates_for_dni_year(daily_set, body.dni, body.year)
            if found["inicio"] <= d <= found["fin"]
        ]
        programados_base = count_days_in_record(
            daily_set, body.dni, body.year, body.new_start, ingreso, exclude=old_dates
        )
        derecho, es_adelanto = _derecho_for_emp(emp, today)
        try:
            _reject_if_no_saldo(
                emp,
                pedidas=n,
                programados_base=programados_base,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
            nuevas, deltas, _old = move_vacation_period(
                daily_set,
                targets,
                body.dni,
                emp["tipo_personal"],
                body.year,
                body.old_start,
                body.new_start,
                n,
                today=today,
                fecha_ingreso=ingreso,
                nombre=emp["nombre"],
                permitir_cerrado=_es_admin(user),
                validar_art8=not es_adelanto,
            )
            _ensure_saldo(
                emp,
                pedidas=n,
                programados_base=programados_base,
                daily_set=daily_set,
                dni=body.dni,
                year=body.year,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        _persist_and_log(cur, body.year, emp, daily_set, targets, user, deltas)
        doc = _documento_plan(cur, user, emp, daily_set, targets, body.year, today)
    return {
        "ok": True,
        "fechas": [d.isoformat() for d in nuevas],
        "fin": nuevas[-1].isoformat() if nuevas else None,
        "weeks": {str(wk): new for wk, _old, new in deltas},
        "dias": n,
        **doc,
    }


class DocumentoIn(BaseModel):
    year: int
    dni: str
    # Documento pendiente a previsualizar (key de /documento). Sin key: el primero que toca.
    key: str = ""
    formato: str = "pdf"

    @field_validator("formato")
    @classmethod
    def formato_ok(cls, v: str) -> str:
        raw = (v or "pdf").strip().lower()
        if raw not in {"pdf", "html"}:
            raise ValueError("Formato de documento no válido.")
        return raw


@router.post("/documento")
def generar_documento(body: DocumentoIn, user: dict = Depends(require_admin)):
    """Vista previa del documento que le toca al plan. No registra la emisión (eso es en Documentos)."""
    today = today_lima()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        emp, daily_set, targets = _load_employee_plan(cur, user, body.dni, body.year)
        attach_jefes(cur, [emp])
        items, falta, programmed = _pendientes_plan(cur, emp, daily_set, body.year, today)
    if not items:
        raise HTTPException(409, falta or "No hay documento para generar.")
    item = next((i for i in items if i["key"] == body.key), items[0])
    if body.formato == "html":
        ctx = item_context(emp, item, year=body.year, fecha_doc=today, programmed=programmed)
        return HTMLResponse(render_html(item["escenario"], ctx))
    pdf, name = render_item(emp, item, year=body.year, fecha_doc=today, programmed=programmed)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/validate")
def validate(
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, area, with_photos=False)
        daily_set, targets = load_scope_plan(cur, year, employees)
    errors, warnings, groups = validate_plan(employees, targets, daily_set, year)
    return {
        "errors": errors,
        "groups": groups,
        "warnings": warnings[:80],
        "warning_count": len(warnings),
    }
