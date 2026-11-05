"""Tests for backend.app.db that need no running database."""

from backend.app.db import DRIVER, check_database, get_engine


def test_no_url_means_not_configured() -> None:
    status = check_database(None)
    assert status.state == "not_configured"
    assert status.pgvector is None


def test_engine_uses_the_permissively_licensed_driver() -> None:
    """Licence rule: the driver must be pg8000 (BSD), not psycopg (LGPL)."""
    engine = get_engine("postgresql+pg8000://u:p@127.0.0.1:1/none")
    assert engine.dialect.driver == DRIVER == "pg8000"


def test_failure_detail_does_not_leak_credentials() -> None:
    status = check_database("postgresql+pg8000://user:secret-password@127.0.0.1:1/none")
    assert status.state == "unavailable"
    assert "secret-password" not in (status.detail or "")
