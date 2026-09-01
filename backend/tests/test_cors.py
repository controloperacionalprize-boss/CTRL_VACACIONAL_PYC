from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.config import Settings

PREVIEW = (
    "https://ctrl-vacacional-jfoiec8be-controloperacionalprize-boss-projects.vercel.app"
)
PROD = "https://ctrl-vacacional-pyc.vercel.app"
TEAM_PROD = "https://ctrl-vacacional-pyc-controloperacionalprize-boss-projects.vercel.app"


def _settings(**kw) -> Settings:
    return Settings(
        database_url="postgresql://u:p@localhost/db",
        jwt_secret="test-jwt-secret-ok",
        **kw,
    )


def _cors_app(settings: Settings) -> TestClient:
    async def start(_request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/auth/microsoft/start", start, methods=["POST"])])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["*"],
    )
    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/auth/microsoft/start",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )


def test_regex_cubre_preview_de_equipo_vercel():
    s = _settings()
    assert s.allows_cors_origin(PREVIEW)
    assert s.allows_cors_origin(PROD)
    assert s.allows_cors_origin(TEAM_PROD)
    assert s.allows_cors_origin("http://localhost:5173")
    assert not s.allows_cors_origin("https://otro-proyecto.vercel.app")
    assert not s.allows_cors_origin("https://ctrl-vacacional-pyc.vercel.app.evil.com")


def test_preflight_preview_vercel_devuelve_allow_origin():
    client = _cors_app(_settings())
    res = _preflight(client, PREVIEW)
    assert res.status_code in (200, 204)
    assert res.headers.get("access-control-allow-origin") == PREVIEW
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_preflight_origen_ajeno_sin_allow_origin():
    client = _cors_app(_settings())
    res = _preflight(client, "https://malicioso.example")
    assert res.headers.get("access-control-allow-origin") in (None, "")
