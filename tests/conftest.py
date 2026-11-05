"""Shared pytest fixtures.

Tests in this repo run without a database or a model server by default.
Tests that need PostgreSQL are marked ``database`` and skip themselves when
``DATABASE_URL`` is not set or the server cannot be reached.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def offline_settings() -> Settings:
    """Settings with no database configured, as in CI."""
    return Settings(database_url=None, environment="test")


@pytest.fixture
def client(offline_settings: Settings) -> Iterator[TestClient]:
    """A test client for an app that has no database configured."""
    with TestClient(create_app(offline_settings)) as test_client:
        yield test_client
