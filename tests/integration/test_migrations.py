"""The Alembic migrations create exactly the tables the models describe."""

from __future__ import annotations

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from backend.app.db import check_database, get_engine, migrate
from backend.app.models import Base

TABLES = {"projects", "documents", "pages", "extracted_values", "catalogue_items", "matches", "estimates",
          "estimate_lines", "reviews", "audit_events"}


def _check(url: str) -> None:
    migrate(url)
    engine = get_engine(url)
    assert TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    migrate(url)  # running again is a no-op


def test_migrations_match_the_models_on_sqlite(tmp_path):
    _check(f"sqlite:///{tmp_path / 'migrate.db'}")


@pytest.mark.database
def test_migrations_match_the_models_on_postgres():
    url = os.environ.get("DATABASE_URL")
    if not url or check_database(url).state != "ok":
        pytest.skip("DATABASE_URL not set or database not reachable")
    _check(url)
