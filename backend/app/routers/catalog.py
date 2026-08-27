from math import ceil

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..db import get_conn
from ..services import filter_options, list_employees, list_employees_page

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
    q: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=0, ge=0, le=100),
    photos: bool = Query(default=True),
    sort: str = Query(default="nombre"),
    order: str = Query(default="asc"),
):
    """page_size=0 devuelve el listado completo (calendario / selectores)."""
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        if page_size == 0:
            rows = list_employees(cur, user, empresa, gerencia, area, q, with_photos=photos)
            n = len(rows)
            return {"items": rows, "total": n, "page": 1, "page_size": n, "pages": 1}
        items, total = list_employees_page(
            cur,
            user,
            empresa,
            gerencia,
            area,
            q,
            limit=page_size,
            offset=(page - 1) * page_size,
            with_photos=photos,
            sort=sort,
            order=order,
        )
    pages = max(1, ceil(total / page_size)) if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
