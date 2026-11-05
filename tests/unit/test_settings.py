"""Tests for backend.app.config."""

import pytest

from backend.app.config import Settings


def test_defaults_need_no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app starts with sensible defaults when no variables are set."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = Settings()
    assert settings.app_name == "Switchgear Estimation Assistant"
    assert settings.environment == "development"
    assert settings.database_url is None


def test_values_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployment settings are read from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+pg8000://u:p@db:5432/sea")
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings()
    assert settings.database_url == "postgresql+pg8000://u:p@db:5432/sea"
    assert settings.environment == "production"


def test_empty_database_url_means_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty DATABASE_URL is treated as no database, not as a broken one."""
    monkeypatch.setenv("DATABASE_URL", "")
    assert Settings().database_url is None
