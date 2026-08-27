from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request

from ..attendance_excel import warmup_excel_cache
from ..auth import get_current_user, load_user_by_email, make_session_token
from ..microsoft import poll_device_flow, start_device_flow
from ..rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PollIn(BaseModel):
    flow_id: str


@router.get("/config")
def auth_config():
    return {
        "auth_mode": "microsoft",
        "verification_uri": "https://microsoft.com/devicelogin",
    }


@router.post("/microsoft/start")
@limiter.limit("10/minute")
def microsoft_start(request: Request):
    return start_device_flow()


@router.post("/microsoft/poll")
@limiter.limit("60/minute")
def microsoft_poll(request: Request, body: PollIn):
    result = poll_device_flow(body.flow_id)
    if result.get("status") == "pending":
        return {"status": "pending"}
    user = load_user_by_email(result["email"])
    if not user:
        raise HTTPException(
            403,
            f"La cuenta {result['email']} no está autorizada para usar esta aplicación, o está inactiva.",
        )
    warmup_excel_cache()
    return {
        "status": "ok",
        "access_token": make_session_token(user["correo"]),
        "token_type": "bearer",
        "user": user,
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    warmup_excel_cache()
    return user
