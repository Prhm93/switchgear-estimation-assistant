"""Shared pytest fixtures.

Tests in this repo run without a database or a model server by default.
Tests that need PostgreSQL are marked ``database`` and skip themselves when
``DATABASE_URL`` is not set or the server cannot be reached. They never use
the database in ``DATABASE_URL`` itself (the app's): the ``pg_url`` fixture
gives them their own ``*_test`` database on the same server and empties it
after each test (see :mod:`tests.isolation`).
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import check_database, migrate
from backend.app.main import create_app
from tests import isolation


@pytest.fixture
def offline_settings() -> Settings:
    """Settings with no database configured, as in CI."""
    return Settings(database_url=None, environment="test")


@pytest.fixture
def client(offline_settings: Settings) -> Iterator[TestClient]:
    """A test client for an app that has no database configured."""
    with TestClient(create_app(offline_settings)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def app_database_url() -> str:
    """The app's own database (DATABASE_URL). Tests may read it, never write to it."""
    url = isolation.app_database_url()
    if not url:
        pytest.skip("DATABASE_URL not set")
    if check_database(url).state != "ok":
        pytest.skip("database not reachable")
    return url


@pytest.fixture(scope="session")
def _test_database(app_database_url: str) -> str:
    url = isolation.database_url_for_tests(app_database_url, os.environ.get("TEST_DATABASE_URL"))
    isolation.ensure_test_database(url)
    migrate(url)
    isolation.empty_test_database(url)  # rows left by an interrupted earlier run
    return url


@pytest.fixture
def pg_url(_test_database: str) -> Iterator[str]:
    """A migrated PostgreSQL test database, emptied again when the test ends."""
    yield _test_database
    isolation.empty_test_database(_test_database)
