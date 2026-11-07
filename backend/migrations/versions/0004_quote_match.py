"""Stage 3c: how a model value's quote was found, and value flags for the engineer.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08

``extracted_values.quote_match`` is "exact" (one continuous span of the page)
or "words_on_page" (every word on the page, the relaxed quote check); it is
empty for rules values and for rows stored before this revision.
``extracted_values.flags`` lists things to check, for example
"poles_from_cable_cores".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('extracted_values', sa.Column('quote_match', sa.String(length=20), nullable=True))
    op.add_column('extracted_values', sa.Column('flags', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('extracted_values', 'flags')
    op.drop_column('extracted_values', 'quote_match')
