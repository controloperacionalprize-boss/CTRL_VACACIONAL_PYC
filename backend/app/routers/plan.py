from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from ..auth import get_current_user
from ..db import get_conn
from ..domain.calendar import (
    DERECHO_ANUAL,
    TOTAL_SEMANAS,
    allowed_type,
    apply_consecutive_span,
    clear_dates_for_week,
    count_year_days,
    date_is_past,
    derecho_vigente,
    ensure_within_derecho,
    is_business_day,
    key_daily,
    parse_iso_date,
    record_cumplido,
    move_vacation_period,
    refresh_week_targets,
    reject_if_art8_invalido,
    reject_if_exceeds_saldo,
    reject_if_start_in_past,
    selected_count,
    today_lima,
    vacation_periods,
    week_dates,
    week_is_locked,
)
from ..domain.plan import log_change, persist_employee, validate_plan
from ..services import get_employee, list_employees, load_scope_plan

router = APIRouter(prefix="/api/plan", tags=["plan"])


def _http_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(400, str(exc))


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
        employees = list_employees(cur, user, empresa, gerencia, area, q)
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

    rows = []
    for e in sorted(employees, key=lambda x: x["nombre"].casefold()):
        weeks = [int(targets.get((e["dni"], w), 0)) for w in range(1, TOTAL_SEMANAS + 1)]
        n = counts.get(e["dni"], 0)
        tope, es_adelanto = _derecho_for_emp(e, today)
        rows.append({
            **e,
            "weeks": weeks,
            "total_dias": sum(weeks),
            "cambios": n,
            "record_cumplido": not es_adelanto,
            "tope_dias": tope,
        })

    return {
        "year": year,
        "today": today.isoformat(),
        "current_year": current_year,
        "current_week": current_week,
        "total_semanas": TOTAL_SEMANAS,
        "workers": rows,
        "kpis": {
            "trabajadores": len(rows),
            "programados": sum(1 for r in rows if r["total_dias"] > 0),
            "pendientes": sum(1 for r in rows if r["total_dias"] == 0),
            "dias": sum(r["total_dias"] for r in rows),
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
        emp = get_employee(cur, user, dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, year, [emp])
    dates = week_dates(year, week)
    today = today_lima()
    selected = [d.isoformat() for d in dates if key_daily(dni, d) in daily_set]
    return {
        "dni": dni,
        "week": week,
        "today": today.isoformat(),
        "locked": week_is_locked(year, week, today),
        "target": int(targets.get((dni, week), 0)),
        "dates": [
            {
                "fecha": d.isoformat(),
                "weekday": d.weekday(),
                "selected": d.isoformat() in selected,
                "past": date_is_past(d, today),
            }
            for d in dates
        ],
        "tipo": emp["tipo_personal"],
    }


@router.patch("/week")
def patch_week(body: WeekPatch, user: dict = Depends(get_current_user)):
    if week_is_locked(body.year, body.week):
        raise HTTPException(400, "Esa semana ya pasó y no se puede cambiar.")
    with get_conn() as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, body.dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, body.year, [emp])
        old = int(targets.get((body.dni, body.week), 0))
        if body.days == 0:
            clear_dates_for_week(
                daily_set, body.dni, body.year, body.week, keep_past=True
            )
            deltas = refresh_week_targets(
                daily_set, targets, body.dni, body.year, [body.week]
            )
            try:
                reject_if_art8_invalido(daily_set, body.dni, body.year)
            except ValueError as exc:
                raise _http_value_error(exc) from exc
        else:
            if not body.start_date:
                raise HTTPException(400, "Si pones días de vacaciones, indica desde qué fecha empiezan.")
            if body.start_date not in set(week_dates(body.year, body.week)):
                raise HTTPException(400, f"La fecha debe caer en la semana {body.week}.")
            try:
                reject_if_start_in_past(body.start_date)
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            # Saldo: al editar la semana se liberan sus días actuales antes de pedir N nuevos.
            programados = count_year_days(daily_set, body.dni, body.year)
            liberados = selected_count(daily_set, body.dni, week_dates(body.year, body.week))
            programados_base = programados - liberados
            derecho, es_adelanto = _derecho_for_emp(emp, today_lima())
            try:
                reject_if_exceeds_saldo(
                    nombre=emp["nombre"],
                    pedidas=body.days,
                    programados_base=programados_base,
                    derecho=derecho,
                    es_adelanto=es_adelanto,
                )
                _, deltas = apply_consecutive_span(
                    daily_set,
                    targets,
                    body.dni,
                    emp["tipo_personal"],
                    body.start_date,
                    body.days,
                    body.year,
                    clear_week=body.week,
                )
                ensure_within_derecho(
                    daily_set,
                    body.dni,
                    body.year,
                    nombre=emp["nombre"],
                    pedidas=body.days,
                    programados_base=programados_base,
                    derecho=derecho,
                    es_adelanto=es_adelanto,
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        _log_week_deltas(cur, emp, body.year, deltas, user)
    weeks = {str(wk): new for wk, _old, new in deltas}
    return {"ok": True, "weeks": weeks, "selected": weeks.get(str(body.week), 0)}


@router.patch("/daily")
def patch_daily(body: DailyPatch, user: dict = Depends(get_current_user)):
    if week_is_locked(body.year, body.week):
        raise HTTPException(400, "Esa semana ya pasó y no se puede cambiar.")
    with get_conn() as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, body.dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, body.year, [emp])
        allowed = set(week_dates(body.year, body.week))
        modo = allowed_type(emp["tipo_personal"], body.dni)
        today = today_lima()
        for d in body.dates:
            if d not in allowed:
                continue
            if date_is_past(d, today) and key_daily(body.dni, d) not in daily_set:
                raise HTTPException(
                    400,
                    f"No se puede marcar el {d.strftime('%d/%m/%Y')}: solo desde hoy hacia adelante.",
                )
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
        programados = count_year_days(daily_set, body.dni, body.year)
        programados_base = programados - n
        derecho, es_adelanto = _derecho_for_emp(emp, today)
        try:
            reject_if_exceeds_saldo(
                nombre=emp["nombre"],
                pedidas=n,
                programados_base=programados,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
            ensure_within_derecho(
                daily_set,
                body.dni,
                body.year,
                nombre=emp["nombre"],
                pedidas=n,
                programados_base=programados,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
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
    with get_conn() as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, body.dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, body.year, [emp])
        programados = count_year_days(daily_set, body.dni, body.year)
        derecho, es_adelanto = _derecho_for_emp(emp, today_lima())
        try:
            reject_if_exceeds_saldo(
                nombre=emp["nombre"],
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
            )
            ensure_within_derecho(
                daily_set,
                body.dni,
                body.year,
                nombre=emp["nombre"],
                pedidas=body.days,
                programados_base=programados,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        _log_week_deltas(cur, emp, body.year, deltas, user)
    return {
        "ok": True,
        "fechas": [d.isoformat() for d in nuevas],
        "weeks": {str(wk): new for wk, _old, new in deltas},
        "fin": nuevas[-1].isoformat() if nuevas else None,
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
        emp = get_employee(cur, user, dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, _targets = load_scope_plan(cur, year, [emp])
    today = today_lima()
    periods = vacation_periods(daily_set, dni, year, today)
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
                "editable": p["editable"],
            }
            for p in periods
        ],
    }


@router.post("/period-move")
def period_move(body: PeriodMoveIn, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, body.dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, body.year, [emp])
        today = today_lima()
        periods = vacation_periods(daily_set, body.dni, body.year, today)
        found = next((p for p in periods if p["inicio"] == body.old_start), None)
        if not found:
            raise HTTPException(400, "No se encontró ese período de vacaciones.")
        n = int(body.days) if body.days is not None else int(found["dias"])
        programados = count_year_days(daily_set, body.dni, body.year)
        programados_base = programados - int(found["dias"])
        derecho, es_adelanto = _derecho_for_emp(emp, today)
        try:
            reject_if_exceeds_saldo(
                nombre=emp["nombre"],
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
            )
            ensure_within_derecho(
                daily_set,
                body.dni,
                body.year,
                nombre=emp["nombre"],
                pedidas=n,
                programados_base=programados_base,
                derecho=derecho,
                es_adelanto=es_adelanto,
            )
        except ValueError as exc:
            raise _http_value_error(exc) from exc
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        _log_week_deltas(cur, emp, body.year, deltas, user)
    return {
        "ok": True,
        "fechas": [d.isoformat() for d in nuevas],
        "fin": nuevas[-1].isoformat() if nuevas else None,
        "weeks": {str(wk): new for wk, _old, new in deltas},
        "dias": n,
    }


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
        employees = list_employees(cur, user, empresa, gerencia, area)
        daily_set, targets = load_scope_plan(cur, year, employees)
    errors, warnings, groups = validate_plan(employees, targets, daily_set, year)
    return {
        "errors": errors,
        "groups": groups,
        "warnings": warnings[:80],
        "warning_count": len(warnings),
    }
