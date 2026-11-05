"""Tests for the health endpoint and the design system health-check page."""

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_healthz_reports_app_ok_without_database(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "ok"
    assert body["database"]["state"] == "not_configured"


def test_healthz_reports_unreachable_database() -> None:
    """A configured but unreachable database is reported, not raised."""
    settings = Settings(
        database_url="postgresql+pg8000://u:p@127.0.0.1:1/none", environment="test"
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/healthz").json()
    assert body["app"] == "ok"
    assert body["database"]["state"] == "unavailable"
    assert body["database"]["pgvector"] is None


def test_health_page_renders_every_component(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Switchgear Estimation Assistant" in html
    for marker in (
        "btn--primary",
        "btn--secondary",
        "btn--ghost",
        "icon-btn",
        "segmented",
        'role="tablist"',
        "doc-card",
        "Extracted",
        "Needs review",
        "Conflict",
        "Approved",
        "conf--high",
        "conf--medium",
        "conf--low",
        "conf--conflict",
    ):
        assert marker in html, f"{marker} missing from the health page"


def test_health_page_shows_database_state(client: TestClient) -> None:
    assert "Not configured" in client.get("/").text


def test_health_page_uses_no_forbidden_wording(client: TestClient) -> None:
    """Design rule: plain professional labels, no 'magic' wording or sparkle symbols."""
    html = client.get("/").text.lower()
    for word in ("magic", "sparkle", "ai-powered", "✨"):
        assert word not in html


def test_stylesheet_fonts_and_icons_are_served(client: TestClient) -> None:
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "--accent" in css.text
    for font in ("IBMPlexSans-Regular.woff2", "IBMPlexMono-Regular.woff2"):
        response = client.get(f"/static/fonts/{font}")
        assert response.status_code == 200
        assert response.content[:4] == b"wOF2"
    assert client.get("/static/icons/icons.svg").status_code == 200
