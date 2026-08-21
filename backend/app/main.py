from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import check_connection, close_pool
from .attendance_db import close_attendance_pool
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.catalog import router as catalog_router
from .routers.dashboard import router as dashboard_router
from .routers.plan import router as plan_router
from .routers.reports import router as reports_router

# Cambia con cada fix de deploy para verificar en /api/version qué código está vivo.
DEPLOY_MARK = "plan-syntax-fix-v2"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()
    close_attendance_pool()


settings = get_settings()
_docs = "/docs" if settings.expose_docs else None
app = FastAPI(
    title="Vacaciones API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=_docs,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(catalog_router)
app.include_router(plan_router)
app.include_router(dashboard_router)
app.include_router(reports_router)


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health(request: Request):
    """Liveness: GET y HEAD (UptimeRobot / Render). Sin tocar la base de datos."""
    if request.method == "HEAD":
        return Response(status_code=200)
    return JSONResponse({"ok": True})


@app.get("/api/version")
def version():
    """Sirve para confirmar que Render tomó el último deploy."""
    return {"ok": True, "deploy": DEPLOY_MARK}


@app.api_route("/api/health/db", methods=["GET", "HEAD"])
def health_db(request: Request):
    """Readiness: confirma que Neon responde."""
    ok = check_connection()
    if request.method == "HEAD":
        return Response(status_code=200 if ok else 503)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 503)
