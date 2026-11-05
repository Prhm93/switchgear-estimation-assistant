"""Tests against a running PostgreSQL with pgvector.

These skip unless DATABASE_URL points at a reachable server, so they do not
run in CI. Run them locally with the stack up (see docs/stage-0.md).
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import check_database
from backend.app.main import create_app

pytestmark = pytest.mark.database


@pytest.fixture(scope="module")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    if check_database(url).state != "ok":
        pytest.skip("database not reachable")
    return url


def test_pgvector_extension_is_installed(database_url: str) -> None:
    status = check_database(database_url)
    assert status.state == "ok"
    assert status.pgvector is not None


def test_healthz_reports_database_ok(database_url: str) -> None:
    with TestClient(create_app(Settings(database_url=database_url))) as client:
        body = client.get("/healthz").json()
    assert body["database"]["state"] == "ok"
