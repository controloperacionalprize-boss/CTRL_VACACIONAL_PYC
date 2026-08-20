from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .db import get_conn

bearer = HTTPBearer(auto_error=False)


def user_from_row(row) -> dict:
    rol = str(row["rol"]).upper()
    return {
        "correo": row["correo"],
        "usuario": row["usuario"],
        "nombre_usuario": row["nombre_usuario"],
        "nombre_persona": row["nombre_persona"],
        "gerencia": row["gerencia"],
        "rol": rol,
        "activo": bool(row["activo"]),
        "is_admin": rol == "ADMIN",
    }


def load_user_by_email(correo: str) -> dict | None:
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    with get_conn(write=False) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT correo, usuario, nombre_usuario, nombre_persona,
                      gerencia, rol, activo
               FROM users WHERE correo = %s""",
            (correo,),
        )
        row = cur.fetchone()
    if not row:
        return None
    if not row["activo"]:
        return None
    return user_from_row(row)


def make_session_token(correo: str) -> str:
    settings = get_settings()
    payload = {
        "sub": correo,
        "email": correo,
        "exp": datetime.now(timezone.utc) + timedelta(hours=4),
        "iss": "vacaciones-ms",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(401, "La sesión caducó. Vuelve a iniciar sesión.") from exc


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if creds is None:
        raise HTTPException(401, "La sesión caducó. Vuelve a iniciar sesión.")
    claims = decode_session_token(creds.credentials)
    email = claims.get("email") or claims.get("sub") or ""
    user = load_user_by_email(str(email))
    if not user:
        raise HTTPException(
            403,
            "Tu correo no está autorizado para usar esta aplicación, o la cuenta está inactiva.",
        )
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Solo un administrador puede entrar aquí.")
    return user
