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

    attendance_database_url: str = ""
    attendance_schema: str = "public"
    attendance_table: str = "marcaciones"
    attendance_dni_column: str = "dni"
    attendance_date_column: str = "fecha"
    attendance_time_column: str = "Tiempo"

    # Excel SharePoint HIK (completa huecos de la BD). Token: script MFA.
    attendance_excel_share_url: str = ""
    attendance_excel_sharepoint_url: str = ""
    attendance_excel_refresh_token: str = ""
    attendance_msal_cache: str = ""

    # Fotos: https://github.com/CCozd/PICTURES (match por usuario de correo en personal_roster.json)
    pictures_enabled: bool = True
    pictures_repo: str = "CCozd/PICTURES"
    pictures_base_url: str = "https://raw.githubusercontent.com/CCozd/PICTURES/main"

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 16 or v.lower() in _WEAK_JWT:
            raise ValueError(
                "Define JWT_SECRET en .env: mínimo 16 caracteres y no uses un valor de ejemplo."
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def cors_origins_ok(cls, v: str) -> str:
        # Quita comillas accidentales y barras finales: "https://x.vercel.app/" → https://x.vercel.app
        parts = []
        for raw in (v or "").split(","):
            o = raw.strip().strip("\"'").rstrip("/")
            if o:
                parts.append(o)
        return ",".join(parts)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]


@lru_cache
def get_settings() -> Settings:
    return Settings()
