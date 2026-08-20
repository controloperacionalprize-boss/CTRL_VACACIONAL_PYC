from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from ..auth import get_current_user
from ..db import get_conn
from ..domain.calendar import (
    TOTAL_SEMANAS,
    allowed_type,
    apply_consecutive_span,
    apply_week_number,
    clear_dates_for_week,
    is_business_day,
    key_daily,
    selected_count,
    week_dates,
    week_is_locked,
)
from ..domain.plan import log_change, persist_employee, validate_plan
from ..services import get_employee, list_employees, load_scope_plan

router = APIRouter(prefix="/api/plan", tags=["plan"])


class WeekPatch(BaseModel):
    year: int
    dni: str
    week: int
    days: int
    start_date: date | None = None
    empresa: list[str] | None = None
    gerencia: list[str] | None = None
    division: list[str] | None = None

    @field_validator("start_date", mode="before")
    @classmethod
    def empty_start_date(cls, v):
        if v == "":
            return None
        return v

    @field_validator("days")
    @classmethod
    def days_in_week(cls, v: int) -> int:
        if v < 0 or v > 7:
            raise ValueError("Cada semana admite de 0 a 7 días.")
        return v


class ConsecutiveIn(BaseModel):
    year: int
    dni: str
    start_date: date
    days: int
    empresa: list[str] | None = None
    gerencia: list[str] | None = None
    division: list[str] | None = None

    @field_validator("start_date", mode="before")
    @classmethod
    def require_start_date(cls, v):
        if v in (None, ""):
            raise ValueError("Indica desde qué día empiezan las vacaciones.")
        return v

    @field_validator("days")
    @classmethod
    def days_range(cls, v: int) -> int:
        if v < 1 or v > 90:
            raise ValueError("Indica cuántos días son (entre 1 y 90).")
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
    division: list[str] | None = None


@router.get("")
def get_plan(
    year: int = Query(...),
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    division: list[str] | None = Query(default=None),
    q: str = Query(default=""),
):
    today = date.today()
    current_year, current_week, _ = today.isocalendar()
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, division, q)
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
        rows.append({
            **e,
            "weeks": weeks,
            "total_dias": sum(weeks),
            "cambios": n,
        })

    return {
        "year": year,
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
    selected = [d.isoformat() for d in dates if key_daily(dni, d) in daily_set]
    return {
        "dni": dni,
        "week": week,
        "locked": week_is_locked(year, week),
        "target": int(targets.get((dni, week), 0)),
        "dates": [{"fecha": d.isoformat(), "weekday": d.weekday(), "selected": d.isoformat() in selected} for d in dates],
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
            apply_week_number(daily_set, body.dni, emp["tipo_personal"], body.week, 0, body.year)
            targets.pop((body.dni, body.week), None)
            deltas = [(body.week, old, 0)]
        elif body.days == 7:
            apply_week_number(daily_set, body.dni, emp["tipo_personal"], body.week, 7, body.year)
            targets[(body.dni, body.week)] = int(body.days)
            deltas = [(body.week, old, body.days)]
        else:
            if not body.start_date:
                raise HTTPException(400, "Si pones de 1 a 6 días, indica desde qué fecha empiezan.")
            week_set = set(week_dates(body.year, body.week))
            if body.start_date not in week_set:
                raise HTTPException(400, f"La fecha debe caer en la semana {body.week}.")
            try:
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
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        for wk, old_days, new_days in deltas:
            if old_days == new_days:
                continue
            log_change(
                cur,
                jefatura=emp["jefatura"],
                year=body.year,
                dni=body.dni,
                nombre=emp["nombre"],
                tipo=emp["tipo_personal"],
                old_week=wk,
                old_days=old_days,
                new_week=wk,
                new_days=new_days,
                user=user,
            )
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
        clear_dates_for_week(daily_set, body.dni, body.year, body.week)
        allowed = set(week_dates(body.year, body.week))
        modo = allowed_type(emp["tipo_personal"])
        for d in body.dates:
            if d not in allowed:
                continue
            if modo != "CALENDARIO" and not is_business_day(d):
                continue
            daily_set.add(key_daily(body.dni, d))
        n = selected_count(daily_set, body.dni, week_dates(body.year, body.week))
        old = int(targets.get((body.dni, body.week), 0))
        if n:
            targets[(body.dni, body.week)] = min(n, 7)
        else:
            targets.pop((body.dni, body.week), None)
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        if old != n:
            log_change(
                cur,
                jefatura=emp["jefatura"],
                year=body.year,
                dni=body.dni,
                nombre=emp["nombre"],
                tipo=emp["tipo_personal"],
                old_week=body.week,
                old_days=old,
                new_week=body.week,
                new_days=n,
                user=user,
            )
    return {"ok": True, "days": n}


@router.post("/consecutive")
def consecutive(body: ConsecutiveIn, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        emp = get_employee(cur, user, body.dni)
        if not emp:
            raise HTTPException(404, "Esa persona no aparece con el filtro actual.")
        daily_set, targets = load_scope_plan(cur, body.year, [emp])
        try:
            nuevas, deltas = apply_consecutive_span(
                daily_set,
                targets,
                body.dni,
                emp["tipo_personal"],
                body.start_date,
                body.days,
                body.year,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        persist_employee(cur, body.year, emp, daily_set, targets, user["correo"])
        for wk, old_days, new_days in deltas:
            if old_days == new_days:
                continue
            log_change(
                cur,
                jefatura=emp["jefatura"],
                year=body.year,
                dni=body.dni,
                nombre=emp["nombre"],
                tipo=emp["tipo_personal"],
                old_week=wk,
                old_days=old_days,
                new_week=wk,
                new_days=new_days,
                user=user,
            )
    return {
        "ok": True,
        "fechas": [d.isoformat() for d in nuevas],
        "weeks": {str(wk): new for wk, _old, new in deltas},
    }


@router.get("/validate")
def validate(
    year: int,
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    division: list[str] | None = Query(default=None),
):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        employees = list_employees(cur, user, empresa, gerencia, division)
        daily_set, targets = load_scope_plan(cur, year, employees)
    errors, warnings, groups = validate_plan(employees, targets, daily_set, year)
    return {
        "errors": errors,
        "groups": groups,
        "warnings": warnings[:80],
        "warning_count": len(warnings),
    }
