"""Tests for the health endpoint, the System status page and the design samples page."""

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


def test_design_samples_render_every_component(client: TestClient) -> None:
    response = client.get("/health/design")
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
        "kpi",
        "data-table",
        "Sample data",
        "btn--tonal",
    ):
        assert marker in html, f"{marker} missing from the design samples page"


def test_design_samples_are_not_served_in_production() -> None:
    with TestClient(create_app(Settings(environment="production"))) as client:
        assert client.get("/health/design").status_code == 404
        assert "Design samples" not in client.get("/health").text


def test_system_status_shows_the_real_settings(client: TestClient) -> None:
    html = client.get("/health").text
    assert "System status" in html and "Not configured" in html
    assert "Drawing PDFs and pictures" in html and "Quote check for model values" in html
    assert "/health/design" in html  # developers find the samples from here (not in production)


def test_health_page_uses_no_forbidden_wording(client: TestClient) -> None:
    """Design rule: plain professional labels, no 'magic' wording or sparkle symbols."""
    html = (client.get("/health").text + client.get("/health/design").text).lower()
    for word in ("magic", "sparkle", "ai-powered", "✨"):
        assert word not in html


def test_stylesheet_fonts_and_icons_are_served(client: TestClient) -> None:
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "--red" in css.text
    for font in ("IBMPlexSans-Regular.woff2", "IBMPlexMono-Regular.woff2",
                 "InstrumentSerif-Regular.woff2", "InstrumentSerif-Italic.woff2"):
        response = client.get(f"/static/fonts/{font}")
        assert response.status_code == 200
        assert response.content[:4] == b"wOF2"
    assert client.get("/static/icons/icons.svg").status_code == 200


def test_old_system_address_redirects_to_health(client: TestClient) -> None:
    response = client.get("/system", follow_redirects=False)
    assert response.status_code == 301 and response.headers["location"] == "/health"


def test_home_page_works_without_a_database(client: TestClient) -> None:
    html = client.get("/").text
    assert "checked</em> estimates" in html
    assert 'action="/enquiries"' in html  # the hero form creates an enquiry
    assert 'action="/enquiries/sample"' in html
    assert "Not affiliated with or endorsed by any company" in html
    assert "Sign in" not in html  # hidden until login is built
    assert "[PLACEHOLDER]" not in html  # every number now comes from docs/stage-3.md and docs/stage-4.md
    for number in ("0.778", "0.727", "0.497", "0.813", "0.893", "0.863", "0.572"):
        assert number in html
    assert "tuned on this set" in html  # the relaxed-check number is labelled
    assert "Strict quote check, fixed baseline. Not held out: these sets were used during development." in html
    assert "Test set; the linker was tuned on 3 of these drawings." in html
