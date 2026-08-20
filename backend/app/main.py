from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import check_connection, close_pool
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.catalog import router as catalog_router
from .routers.dashboard import router as dashboard_router
from .routers.plan import router as plan_router
from .routers.reports import router as reports_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


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


@app.get("/api/health")
def health():
    """Liveness simple: confirma que el proceso responde, sin tocar la base de datos."""
    return {"ok": True}


@app.head("/api/health")
def health_head():
    return Response(status_code=200)


@app.get("/api/health/db")
def health_db(response: Response):
    """Readiness: úsalo en el orquestador (Azure/Render/Railway) para saber si Neon responde."""
    ok = check_connection()
    if not ok:
        response.status_code = 503
    return {"ok": ok}


@app.head("/api/health/db")
def health_db_head(response: Response):
    ok = check_connection()
    response.status_code = 200 if ok else 503
    return response
