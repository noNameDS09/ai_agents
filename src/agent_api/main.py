"""FastAPI app factory: middleware, routers, startup/shutdown."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .api.v1 import chat as chat_router
from .api.v1 import tools as tools_router
from .config import settings
from .database import init_db
from .service.agent import AgentService, get_service

# Compliance domain (optional — only if compliance module is available)
try:
    from compliance.api import router as compliance_router
    _HAS_COMPLIANCE = True
except ImportError:
    _HAS_COMPLIANCE = False


class HealthResponse(BaseModel):
    status: str
    database: str
    inference_configured: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Narrow attack surface first.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak internals to the client.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal server error"},
        )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health(
        service: Annotated[AgentService, Depends(get_service)],
    ):
        # Health is intentionally unauthenticated and not rate-limited.
        result = await service.health()
        status_ = (
            "ok"
            if result["database"] == "ok" and result["inference_configured"]
            else "degraded"
        )
        return HealthResponse(status=status_, **result)

    app.include_router(chat_router.router, prefix="/v1")
    app.include_router(tools_router.router, prefix="/v1")

    if _HAS_COMPLIANCE:
        app.include_router(compliance_router)

    # Serve the React/Vite frontend (same origin, no CORS needed for the UI).
    # Built with `npm run build` (or `vite build`) into frontend/dist.
    #   /assets -> frontend/dist/assets   (JS/CSS assets)
    #   everything else (non-API) -> frontend/dist/index.html (SPA fallback)
    _frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    _dist_dir = os.path.join(_frontend_dir, "dist")
    _assets_dir = os.path.join(_dist_dir, "assets")

    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = ""):
        # Let API routes and docs take precedence (they're registered above).
        index = os.path.join(_dist_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "frontend not built. run `npm run build` in frontend/"
            },
        )

    return app


app = create_app()
