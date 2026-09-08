from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator

from ..auth import require_admin
from ..db import get_conn
from ..photos import coverage_report, picture_index, resolve_foto_url
from ..org_scope import ROLES, division_for_area, resolve_division
from ..services import list_employees

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _iniciales(nombre: str) -> str:
    partes = [p for p in nombre.replace(".", " ").split() if p and "@" not in p]
    if not partes and "@" in nombre:
        partes = [nombre.split("@")[0]]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def _autor_de(ev: dict) -> str:
    return (
        (ev.get("autor_actual") or "").strip()
        or (ev.get("nombre_persona") or "").strip()
        or (ev.get("usuario") or "").strip()
        or (ev.get("correo") or "").strip()
        or "Alguien"
    )


class UserIn(BaseModel):
    correo: str
    usuario: str = ""
    nombre_usuario: str = ""
    nombre_persona: str
    gerencia: str = ""
    area: str = ""
    rol: str = "GERENTE"
    activo: bool = True

    @field_validator("correo")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Indica un correo válido.")
        return v

    @field_validator("rol")
    @classmethod
    def role_ok(cls, v: str) -> str:
        v = (v or "GERENTE").strip().upper()
        if v not in ROLES:
            raise ValueError("El rol debe ser ADMIN, GERENTE o JEFE.")
        return v

    @field_validator("usuario", "nombre_usuario", "nombre_persona", "gerencia", "area")
    @classmethod
    def trim(cls, v: str) -> str:
        return (v or "").strip()

    @model_validator(mode="after")
    def scope_ok(self):
        if not self.nombre_persona:
            raise ValueError("El nombre es obligatorio.")
        if self.rol == "JEFE":
            if not self.area:
                raise ValueError("El jefe debe tener un área.")
            if not self.gerencia:
                self.gerencia = division_for_area(self.area) or resolve_division(self.area) or ""
        elif self.rol != "ADMIN" and not self.gerencia:
            raise ValueError("El gerente debe tener una división.")
        return self


class UserPatch(BaseModel):
    usuario: str | None = None
    nombre_usuario: str | None = None
    nombre_persona: str | None = None
    gerencia: str | None = None
    area: str | None = None
    rol: str | None = None
    activo: bool | None = None

    @field_validator("rol")
    @classmethod
    def role_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in ROLES:
            raise ValueError("El rol debe ser ADMIN, GERENTE o JEFE.")
        return v

    @field_validator("usuario", "nombre_usuario", "nombre_persona", "gerencia", "area")
    @classmethod
    def trim_opt(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip()


USER_PATCH_COLS = (
    "usuario",
    "nombre_usuario",
    "nombre_persona",
    "gerencia",
    "area",
    "rol",
    "activo",
)


def _admin_count(cur) -> int:
    cur.execute("SELECT COUNT(*) AS n FROM users WHERE upper(rol) = 'ADMIN' AND activo = TRUE")
    return int(cur.fetchone()["n"])


def _user_row(r) -> dict:
    gerencia = r["gerencia"] or ""
    area = (r["area"] if "area" in r else "") or ""
    rol = str(r["rol"]).upper()
    return {
        "correo": r["correo"],
        "usuario": r["usuario"] or "",
        "nombre_usuario": r["nombre_usuario"] or "",
        "nombre_persona": r["nombre_persona"] or "",
        "gerencia": gerencia,
        "area": area,
        "division": resolve_division(gerencia, area) or gerencia,
        "rol": rol,
        "activo": bool(r["activo"]),
        "is_admin": rol == "ADMIN",
        "is_gerente": rol in ("GERENTE", "USER"),
        "is_jefe": rol == "JEFE",
    }


@router.get("/users")
def list_users(user: dict = Depends(require_admin)):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT correo, usuario, nombre_usuario, nombre_persona, gerencia, area, rol, activo
               FROM users ORDER BY activo DESC, nombre_persona, correo"""
        )
        items = [_user_row(r) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT gerencia FROM employees WHERE gerencia <> '' ORDER BY gerencia")
        gerencias = [r["gerencia"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT division FROM employees WHERE division <> '' ORDER BY division")
        divisiones = [r["division"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT area FROM employees WHERE area <> '' ORDER BY area")
        areas = [r["area"] for r in cur.fetchall()]
    seen = []
    for name in [*divisiones, *gerencias]:
        if name and name not in seen:
            seen.append(name)
    return {"items": items, "gerencias": seen or gerencias, "areas": areas}


@router.post("/users")
def create_user(body: UserIn, user: dict = Depends(require_admin)):
    usuario = body.usuario or body.correo.split("@")[0]
    nombre_usuario = body.nombre_usuario or body.nombre_persona
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE correo = %s", (body.correo,))
        if cur.fetchone():
            raise HTTPException(409, "Ese correo ya está registrado.")
        cur.execute(
            """INSERT INTO users
               (correo, usuario, nombre_usuario, nombre_persona, gerencia, area, rol, activo)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                body.correo,
                usuario.lower(),
                nombre_usuario,
                body.nombre_persona,
                body.gerencia,
                body.area,
                body.rol,
                body.activo,
            ),
        )
    return {"ok": True, "correo": body.correo}


@router.patch("/users/{correo}")
def update_user(correo: str, body: UserPatch, user: dict = Depends(require_admin)):
    correo = correo.strip().lower()
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No hay cambios.")
    if correo == user["correo"]:
        if data.get("activo") is False:
            raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
        if data.get("rol") and data["rol"] != "ADMIN":
            raise HTTPException(400, "No puedes quitarte el rol de administrador.")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT rol, activo, gerencia, area FROM users WHERE correo = %s",
            (correo,),
        )
        current = cur.fetchone()
        if not current:
            raise HTTPException(404, "Ese usuario no existe.")
        was_admin = str(current["rol"]).upper() == "ADMIN" and bool(current["activo"])
        new_rol = str(data.get("rol") or current["rol"]).upper()
        new_activo = bool(data["activo"]) if "activo" in data else bool(current["activo"])
        if was_admin and not (new_rol == "ADMIN" and new_activo) and _admin_count(cur) <= 1:
            raise HTTPException(400, "Debe quedar al menos un administrador activo.")
        if any(k in data for k in ("rol", "gerencia", "area")):
            area = data["area"] if "area" in data else (current["area"] or "")
            gerencia = data["gerencia"] if "gerencia" in data else (current["gerencia"] or "")
            if new_rol == "JEFE":
                if not str(area or "").strip():
                    raise HTTPException(400, "El jefe debe tener un área.")
                data["area"] = area
                data["gerencia"] = division_for_area(area) or resolve_division(area) or gerencia
            elif new_rol != "ADMIN":
                if not str(gerencia or "").strip():
                    raise HTTPException(400, "El gerente debe tener una división.")
                data["gerencia"] = gerencia
                if "rol" in data:
                    data["area"] = ""
        fields = []
        params: list = []
        for key in USER_PATCH_COLS:
            if key not in data or data[key] is None:
                continue
            val = data[key]
            if key == "usuario":
                val = str(val).strip().lower()
            elif isinstance(val, str):
                val = val.strip()
            fields.append(f"{key} = %s")
            params.append(val)
        if not fields:
            raise HTTPException(400, "No hay cambios.")
        params.append(correo)
        cur.execute(f"UPDATE users SET {', '.join(fields)}, actualizado = NOW() WHERE correo = %s", params)
    return {"ok": True}


@router.get("/timeline")
def timeline(year: int, user: dict = Depends(require_admin)):
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT cl.id, cl.fecha_hora, cl.jefatura, cl.anio, cl.dni, cl.nombre, cl.tipo_persona,
                      cl.semana_anterior, cl.dias_anterior, cl.semana_nueva, cl.dias_nuevos,
                      cl.usuario, cl.nombre_persona, cl.correo,
                      u.nombre_persona AS autor_actual
               FROM change_log cl
               LEFT JOIN users u ON lower(u.correo) = lower(cl.correo)
               WHERE cl.anio = %s
               ORDER BY cl.fecha_hora ASC, cl.id ASC""",
            (year,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    by_dni: dict[str, list] = defaultdict(list)
    for r in rows:
        by_dni[str(r["dni"])].append(r)

    threads = []
    for dni, events in by_dni.items():
        numbered = []
        for i, ev in enumerate(events, start=1):
            semana = ev.get("semana_nueva") if ev.get("semana_nueva") is not None else ev.get("semana_anterior")
            afectado = (ev.get("nombre") or "").strip() or dni
            autor = _autor_de(ev)
            numbered.append(
                {
                    "id": ev["id"],
                    "n": i,
                    "fecha_hora": ev["fecha_hora"],
                    "semana": semana,
                    "dias_anterior": int(ev.get("dias_anterior") or 0),
                    "dias_nuevos": int(ev.get("dias_nuevos") or 0),
                    "afectado": afectado,
                    "afectado_dni": dni,
                    "afectado_iniciales": _iniciales(afectado),
                    "autor": autor,
                    "correo": (ev.get("correo") or "").strip(),
                    "iniciales": _iniciales(autor),
                    "foto_url": resolve_foto_url(autor),
                    "tipo_persona": ev.get("tipo_persona") or "",
                }
            )
        last = events[-1]
        threads.append(
            {
                "dni": dni,
                "nombre": last.get("nombre") or dni,
                "jefatura": last.get("jefatura") or "",
                "cambios": len(numbered),
                "foto_url": resolve_foto_url(last.get("nombre") or ""),
                "events": numbered,
            }
        )
    threads.sort(key=lambda t: t["nombre"].casefold())
    return {"year": year, "total": len(rows), "threads": threads}


@router.get("/photos/coverage")
def photos_coverage(user: dict = Depends(require_admin)):
    """Qué empleados tienen foto en PICTURES y quiénes no (typos / sin archivo)."""
    with get_conn(write=False) as conn:
        employees = list_employees(conn.cursor(), user)
    report = coverage_report([e["nombre"] for e in employees])
    report["index_ok"] = bool(picture_index())
    return report
