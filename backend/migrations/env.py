"""Alembic migration environment.

Reads the database URL from the app settings (DATABASE_URL), so migrations
and the app always target the same database. A caller (the tests, or the app
at start-up) may instead pass an open connection in
``config.attributes["connection"]``.
"""

from alembic import context
from sqlalchemy import create_engine, pool

from backend.app.config import Settings
from backend.app.models import Base

target_metadata = Base.metadata


def _database_url() -> str:
    url = Settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set; cannot run migrations.")
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (alembic upgrade --sql)."""
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    given = context.config.attributes.get("connection")
    if given is not None:
        context.configure(connection=given, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
