from pathlib import Path
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
_WEAK_JWT = {"dev-secret", "secret", "changeme", "jwt_secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", Path(__file__).resolve().parents[1] / ".env"),
        extra="ignore",
    )

    database_url: str
    auth_mode: str = "microsoft"
    jwt_secret: str
    ms_client_id: str = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
    ms_authority: str = "https://login.microsoftonline.com/common"
    ms_scope: str = "openid profile email"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    expose_docs: bool = False

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 16 or v.lower() in _WEAK_JWT:
            raise ValueError(
                "Define JWT_SECRET en .env: mínimo 16 caracteres y no uses un valor de ejemplo."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
