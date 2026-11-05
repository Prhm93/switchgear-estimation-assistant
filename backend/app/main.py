"""FastAPI application factory and the Stage 0 routes.

Routes:
    GET /         Design system health-check page (HTML).
    GET /healthz  Machine-readable health status (JSON), used by Docker.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import __version__
from .config import Settings
from .db import DatabaseStatus, check_database
from .paths import STATIC_DIR, TEMPLATES_DIR


class HealthStatus(BaseModel):
    """Response body of /healthz."""

    app: str
    version: str
    environment: str
    database: DatabaseStatus


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings; production reads the env."""
    settings = settings or Settings()
    app = FastAPI(title=settings.app_name, version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

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

    @app.get("/", response_class=HTMLResponse)
    def health_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "health.html",
            {"app_name": settings.app_name, "health": current_health()},
        )

    return app


app = create_app()
