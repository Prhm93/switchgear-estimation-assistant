"""Keep the tests out of the app's database.

Tests marked ``database`` need a real PostgreSQL. ``DATABASE_URL`` says where
the server is, but it is also the database the running app uses, so no test
may write to it. The tests use a second database on the same server instead,
named after the app's with ``_test`` added (``sea`` -> ``sea_test``), or the
one in ``TEST_DATABASE_URL``. It is created on first use, migrated like the
app's, and emptied after every test.

Every write helper here refuses a database whose name does not end in
``_test``, so a wrong URL fails loudly instead of touching real data.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

SUFFIX = "_test"
KEPT_TABLES = {"alembic_version"}  # the schema version is not test data


class UnsafeTestDatabase(RuntimeError):
    """The test database would be the app's database, or is not named as a test database."""


def app_database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def _same_database(a: URL, b: URL) -> bool:
    return (a.host, a.port or 5432, a.database) == (b.host, b.port or 5432, b.database)


def database_url_for_tests(app_url: str, explicit: str | None = None) -> str:
    """The URL the database tests use: ``explicit`` (TEST_DATABASE_URL) or the app's name plus ``_test``."""
    app = make_url(app_url)
    test = make_url(explicit) if explicit else app.set(database=f"{app.database}{SUFFIX}")
    if _same_database(app, test):
        raise UnsafeTestDatabase("TEST_DATABASE_URL points at the app's database; tests must use their own.")
    if not (test.database or "").endswith(SUFFIX):
        raise UnsafeTestDatabase(f"The test database must be named *{SUFFIX}, not {test.database!r}.")
    return test.render_as_string(hide_password=False)


def _require_test_name(url: str) -> URL:
    parsed = make_url(url)
    if not (parsed.database or "").endswith(SUFFIX):
        raise UnsafeTestDatabase(f"Refusing to change {parsed.database!r}: not a test database.")
    return parsed


def ensure_test_database(test_url: str) -> None:
    """Create the test database if the server does not have it yet (through the ``postgres`` database)."""
    parsed = _require_test_name(test_url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT",
                          connect_args={"timeout": 10})
    try:
        with admin.connect() as connection:
            exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                                        {"n": parsed.database}).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        admin.dispose()


def empty_test_database(test_url: str) -> None:
    """Remove every row the tests wrote (all tables but the schema version), restarting the id counters."""
    from backend.app.db import get_engine

    _require_test_name(test_url)
    engine = get_engine(test_url)
    tables = [t for t in inspect(engine).get_table_names() if t not in KEPT_TABLES]
    if tables:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))


def row_counts(url: str) -> dict[str, int]:
    """Rows per table, read only: used to prove the app's database is the same before and after."""
    engine = create_engine(url, connect_args={"timeout": 10})
    try:
        with engine.connect() as connection:
            tables = [t for t in inspect(connection).get_table_names() if t not in KEPT_TABLES]
            return {t: connection.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in sorted(tables)}
    finally:
        engine.dispose()
