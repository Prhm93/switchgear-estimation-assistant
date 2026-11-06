"""Database access and the database health check.

The app runs on PostgreSQL with pgvector (Docker, CI). The fast local test
suite runs the same migrations on SQLite, so the engine factory accepts both.
Tables are created only by the Alembic migrations (:func:`migrate`).
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .paths import REPO_ROOT

DatabaseState = Literal["ok", "unavailable", "not_configured"]


class DatabaseStatus(BaseModel):
    """Result of a database health check, safe to show in the UI."""

    state: DatabaseState
    pgvector: str | None = None
    detail: str | None = None


# pg8000 (BSD-3-Clause) is the PostgreSQL driver. psycopg is not used because
# it is LGPL-licensed and the project allows permissive licences only.
DRIVER = "pg8000"

# pg8000's "timeout" is a socket timeout in seconds. It bounds how long the
# health check waits for an unreachable host, and also any single query.
SOCKET_TIMEOUT_SECONDS = 10


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    """Return one pooled engine per URL. A small pool keeps memory low."""
    if database_url.startswith("sqlite"):
        in_memory = database_url in ("sqlite://", "sqlite:///:memory:")
        return create_engine(database_url, connect_args={"check_same_thread": False},
                             poolclass=StaticPool if in_memory else None)
    return create_engine(
        database_url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={"timeout": SOCKET_TIMEOUT_SECONDS},
    )


def check_database(database_url: str | None) -> DatabaseStatus:
    """Check that the database answers and report the pgvector version.

    Never raises: a failure is returned as state "unavailable" with the error
    class name, so the health page can show it without leaking credentials.
    """
    if not database_url:
        return DatabaseStatus(state="not_configured")
    try:
        with get_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
            if connection.dialect.name != "postgresql":
                return DatabaseStatus(state="ok", detail=connection.dialect.name)
            version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    except (SQLAlchemyError, OSError) as error:
        return DatabaseStatus(state="unavailable", detail=type(error).__name__)
    return DatabaseStatus(state="ok", pgvector=version)


def migrate(database_url: str) -> None:
    """Apply every Alembic migration (``alembic upgrade head``) to the database."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    with get_engine(database_url).begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
