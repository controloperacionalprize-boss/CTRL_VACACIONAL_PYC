from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, load_user_by_email, make_session_token
from ..microsoft import poll_device_flow, start_device_flow

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
def microsoft_start():
    return start_device_flow()


@router.post("/microsoft/poll")
def microsoft_poll(body: PollIn):
    result = poll_device_flow(body.flow_id)
    if result.get("status") == "pending":
        return {"status": "pending"}
    user = load_user_by_email(result["email"])
    if not user:
        raise HTTPException(
            403,
            f"La cuenta {result['email']} no está autorizada para usar esta aplicación, o está inactiva.",
        )
    return {
        "status": "ok",
        "access_token": make_session_token(user["correo"]),
        "token_type": "bearer",
        "user": user,
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
