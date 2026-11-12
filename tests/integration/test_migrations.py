"""The Alembic migrations create exactly the tables the models describe."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from backend.app.db import get_engine, migrate
from backend.app.models import Base
from backend.app.paths import REPO_ROOT

TABLES = {"projects", "documents", "pages", "extracted_values", "catalogue_items", "matches", "estimates",
          "estimate_lines", "reviews", "audit_events", "enquiry_notes"}


def upgrade_to(url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    with get_engine(url).begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


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
def test_migrations_match_the_models_on_postgres(pg_url):
    _check(pg_url)  # the tests' own database, never the app's


def test_migration_0005_only_adds_and_keeps_every_row(tmp_path):
    """Upgrading a Stage 4 database keeps its enquiries and gives each a "last updated" time."""
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    upgrade_to(url, "0004")
    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO projects (name, reference, created_at) "
                          "VALUES ('Old board', 'ENQ-1', '2026-11-01 09:00:00')"))
        before = {t: set(c["name"] for c in inspect(conn).get_columns(t)) for t in inspect(conn).get_table_names()}
    upgrade_to(url, "0005")
    with engine.connect() as conn:
        after = {t: set(c["name"] for c in inspect(conn).get_columns(t)) for t in inspect(conn).get_table_names()}
        row = conn.execute(text("SELECT name, updated_at, archived_at, is_sample FROM projects")).one()
    assert all(before[t] <= after[t] for t in before)  # nothing dropped or renamed
    assert after["projects"] - before["projects"] == {"updated_at", "archived_at", "is_sample"}
    assert after["documents"] - before["documents"] == {"read_method"}
    assert row[0] == "Old board" and row[1] is not None and row[2] is None and not row[3]


def test_migration_0006_only_adds_the_notes_table_and_keeps_every_row(tmp_path):
    """V4: typed notes get their own table; nothing else changes and every enquiry is kept."""
    url = f"sqlite:///{(tmp_path / 'm6.db').as_posix()}"
    upgrade_to(url, "0005")
    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO projects (name, created_at, updated_at, is_sample) "
                          "VALUES ('Kept board', '2026-11-01 09:00:00', '2026-11-01 09:00:00', 0)"))
        before = {t: set(c["name"] for c in inspect(conn).get_columns(t)) for t in inspect(conn).get_table_names()}
    upgrade_to(url, "0006")
    with engine.connect() as conn:
        after = {t: set(c["name"] for c in inspect(conn).get_columns(t)) for t in inspect(conn).get_table_names()}
        assert conn.execute(text("SELECT name FROM projects")).scalar_one() == "Kept board"
    assert set(after) - set(before) == {"enquiry_notes"}
    assert all(after[t] == before[t] for t in before)  # no column added, dropped or renamed elsewhere
    assert after["enquiry_notes"] == {"id", "project_id", "text", "actor", "created_at"}
    migration = (REPO_ROOT / "backend" / "migrations" / "versions" / "0006_enquiry_notes.py").read_text(encoding="utf-8")
    upgrade = migration.split("def upgrade")[1].split("def downgrade")[0]
    assert "drop" not in upgrade.lower() and "alter_column" not in upgrade
