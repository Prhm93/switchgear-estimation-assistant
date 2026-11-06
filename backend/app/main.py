"""FastAPI application factory.

Routes:
    GET /          Home page; /projects and the product screens (see :mod:`backend.app.web`).
    GET /health    Design system and health-check page (HTML); /system redirects here.
    GET /healthz   Machine-readable health status (JSON), used by Docker.

With no DATABASE_URL the app still starts: /, /health and /healthz work and
the product screens answer 503 with a plain explanation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, web
from .config import Settings
from .db import DatabaseStatus, check_database, migrate, session_factory
from .paths import STATIC_DIR, TEMPLATES_DIR
from .services import sync_catalogue
from .storage import LocalStorage, Storage

log = logging.getLogger(__name__)


class HealthStatus(BaseModel):
    """Response body of /healthz."""

    app: str
    version: str
    environment: str
    database: DatabaseStatus


def _prepare_database(app: FastAPI, settings: Settings) -> None:
    """Bring the schema up to date and load the parts catalogue; never stops the app from starting."""
    if settings.database_url is None:
        return
    try:
        migrate(settings.database_url)
        with app.state.sessions() as session:
            sync_catalogue(session, settings)
    except Exception as error:  # an unreachable database is reported by /healthz, not raised here
        log.warning("Database not prepared: %s", error)


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings and storage; production reads the env."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _prepare_database(app, settings)
        yield
        if app.state.sessions is not None:  # release pooled connections (and SQLite file handles)
            app.state.sessions.kw["bind"].dispose()

    app = FastAPI(title=settings.app_name, version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = session_factory(settings.database_url) if settings.database_url else None
    app.state.storage = storage or LocalStorage(settings.storage_dir)
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def current_health() -> HealthStatus:
        return HealthStatus(
            app="ok",
            version=__version__,
            environment=settings.environment,
            database=check_database(settings.database_url),
        )

    @app.get("/healthz", response_model=HealthStatus)
    def healthz() -> HealthStatus:
        return current_health()

    @app.get("/health", response_class=HTMLResponse)
    def health_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "health.html",
            {"app_name": settings.app_name, "environment": settings.environment, "health": current_health()},
        )

    @app.get("/system", include_in_schema=False)
    def old_health_page() -> RedirectResponse:
        """The health page moved to /health; old bookmarks still work."""
        return RedirectResponse("/health", status_code=301)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: HTTPException) -> Response:
        """Errors as a page in the design for browsers, as JSON for everything else."""
        if "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
        return templates.TemplateResponse(
            request, "error.html",
            {"app_name": settings.app_name, "environment": settings.environment,
             "status": error.status_code, "detail": error.detail},
            status_code=error.status_code,
        )

    app.include_router(web.router)
    return app


app = create_app()
