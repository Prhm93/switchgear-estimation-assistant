"""Database access and the database health check.

Stage 0 only needs to know whether PostgreSQL is reachable and whether the
pgvector extension is installed. Tables arrive with Alembic migrations in
later stages.
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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
            version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    except (SQLAlchemyError, OSError) as error:
        return DatabaseStatus(state="unavailable", detail=type(error).__name__)
    return DatabaseStatus(state="ok", pgvector=version)
