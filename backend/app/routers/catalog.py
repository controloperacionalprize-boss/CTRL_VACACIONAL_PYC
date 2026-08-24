from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..db import get_conn
from ..services import filter_options, list_employees

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/filters")
def filters(
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    with get_conn(write=False) as conn:
        return filter_options(conn.cursor(), user, empresa, gerencia, area)


@router.get("/employees")
def employees(
    user: dict = Depends(get_current_user),
    empresa: list[str] | None = Query(default=None),
    gerencia: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
):
    with get_conn(write=False) as conn:
        rows = list_employees(conn.cursor(), user, empresa, gerencia, area)
    return {"items": rows, "total": len(rows)}
