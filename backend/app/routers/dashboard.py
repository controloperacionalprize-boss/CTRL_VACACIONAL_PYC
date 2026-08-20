from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..db import get_conn
from ..domain.dashboard import build_dashboard
from ..services import list_employees, load_scope_plan

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
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
    return build_dashboard(employees, targets, daily_set, year)
