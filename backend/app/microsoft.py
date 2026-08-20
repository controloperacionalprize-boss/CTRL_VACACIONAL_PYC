from __future__ import annotations

import secrets
import time
from threading import Lock

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException

from .config import get_settings

_FLOWS: dict[str, dict] = {}
_LOCK = Lock()
_OIDC_SCOPES = ("openid", "profile", "email")


def _token_scope() -> str:
    denied = {"https://graph.microsoft.com/files.read.all", "files.read.all"}
    parts = [p for p in get_settings().ms_scope.split() if p.lower() not in denied]
    for extra in reversed(_OIDC_SCOPES):
        if extra not in parts:
            parts.insert(0, extra)
    return " ".join(parts)


def _verify_id_token(token: str) -> dict:
    settings = get_settings()
    url = settings.ms_authority.rstrip("/") + "/discovery/v2.0/keys"
    key = PyJWKClient(url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=settings.ms_client_id,
        options={"verify_iss": False},
    )


def _claims_from_jwt(token: str | None) -> dict:
    if not token:
        return {}
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _email_from_claims(*claim_sets: dict) -> str:
    keys = (
        "preferred_username",
        "email",
        "upn",
        "unique_name",
        "verified_primary_email",
    )
    for claims in claim_sets:
        for key in keys:
            value = claims.get(key)
            if isinstance(value, list) and value:
                value = value[0]
            text = str(value or "").strip()
            if "@" in text:
                return text
    return ""


def _clean_expired():
    now = time.time()
    dead = [k for k, v in _FLOWS.items() if v["expires_at"] < now]
    for k in dead:
        _FLOWS.pop(k, None)


def start_device_flow() -> dict:
    settings = get_settings()
    url = settings.ms_authority.rstrip("/") + "/oauth2/v2.0/devicecode"
    with httpx.Client(timeout=30) as client:
        res = client.post(
            url,
            data={
                "client_id": settings.ms_client_id,
                "scope": _token_scope(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code >= 400:
        raise HTTPException(502, "No se pudo conectar con Microsoft. Inténtalo de nuevo.")
    data = res.json()
    if "device_code" not in data:
        raise HTTPException(502, "Microsoft no devolvió un código de acceso. Inténtalo de nuevo.")
    flow_id = secrets.token_urlsafe(16)
    with _LOCK:
        _clean_expired()
        _FLOWS[flow_id] = {
            "device_code": data["device_code"],
            "expires_at": time.time() + int(data.get("expires_in", 900)),
        }
    return {
        "flow_id": flow_id,
        "user_code": data.get("user_code", ""),
        "verification_uri": data.get("verification_uri")
        or data.get("verification_uri_complete")
        or "https://microsoft.com/devicelogin",
        "verification_uri_complete": data.get("verification_uri_complete"),
        "expires_in": int(data.get("expires_in", 900)),
        "interval": int(data.get("interval", 5)),
        "message": data.get("message", ""),
    }


def poll_device_flow(flow_id: str) -> dict:
    settings = get_settings()
    with _LOCK:
        flow = _FLOWS.get(flow_id)
    if not flow:
        raise HTTPException(400, "El código de Microsoft expiró. Vuelve a intentarlo.")
    if time.time() > flow["expires_at"]:
        with _LOCK:
            _FLOWS.pop(flow_id, None)
        raise HTTPException(400, "El código de Microsoft expiró. Vuelve a intentarlo.")

    url = settings.ms_authority.rstrip("/") + "/oauth2/v2.0/token"
    with httpx.Client(timeout=30) as client:
        res = client.post(
            url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": settings.ms_client_id,
                "device_code": flow["device_code"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    data = res.json()
    error = data.get("error")
    if error in {"authorization_pending", "slow_down"}:
        return {"status": "pending"}
    if error == "expired_token":
        with _LOCK:
            _FLOWS.pop(flow_id, None)
        raise HTTPException(400, "El código de Microsoft expiró. Vuelve a intentarlo.")
    if error:
        raise HTTPException(
            401,
            "Microsoft rechazó el acceso. Vuelve a intentar e ingresa el código.",
        )
    if "id_token" not in data and "access_token" not in data:
        raise HTTPException(401, "Microsoft no devolvió un token válido.")

    id_claims = {}
    if data.get("id_token"):
        try:
            id_claims = _verify_id_token(str(data["id_token"]))
        except Exception:
            id_claims = _claims_from_jwt(data.get("id_token"))
    access_claims = _claims_from_jwt(data.get("access_token"))
    email = _email_from_claims(id_claims, access_claims)
    if not email and data.get("access_token"):
        try:
            with httpx.Client(timeout=15) as client:
                me = client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                )
            if me.status_code < 400:
                body = me.json()
                extras = body.get("otherMails") or []
                extra = extras[0] if extras else ""
                email = str(
                    body.get("mail")
                    or body.get("userPrincipalName")
                    or extra
                    or ""
                ).strip()
        except Exception:
            email = email
    display_name = str(id_claims.get("name") or access_claims.get("name") or email).strip()
    if not email or "@" not in email:
        raise HTTPException(
            401,
            "No se pudo leer el correo de la cuenta de Microsoft. "
            "Confirma el código en microsoft.com/devicelogin con tu cuenta @aquanqa.pe.",
        )
    with _LOCK:
        _FLOWS.pop(flow_id, None)
    return {
        "status": "ok",
        "email": email,
        "display_name": display_name,
    }
