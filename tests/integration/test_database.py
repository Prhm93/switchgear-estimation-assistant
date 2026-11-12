"""Tests against a running PostgreSQL with pgvector.

These skip unless DATABASE_URL points at a reachable server. They run on the
tests' own ``*_test`` database (the ``pg_url`` fixture), never on the app's.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import check_database
from backend.app.main import create_app

pytestmark = pytest.mark.database


def test_pgvector_extension_is_installed(pg_url: str) -> None:
    status = check_database(pg_url)
    assert status.state == "ok"
    assert status.pgvector is not None


def test_healthz_reports_database_ok(pg_url: str) -> None:
    with TestClient(create_app(Settings(database_url=pg_url, environment="test"))) as client:
        body = client.get("/healthz").json()
    assert body["database"]["state"] == "ok"
