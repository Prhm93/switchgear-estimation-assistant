"""Baseline: enable the pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgres() -> bool:
    # The local test suite also runs the migrations on SQLite, which has no extensions.
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # pgvector stores embeddings for note search (Stage 9).
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP EXTENSION IF EXISTS vector")
