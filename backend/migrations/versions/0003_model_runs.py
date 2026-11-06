"""Stage 3: the model run that read a document, and rules/LLM agreement per value.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

``documents.model_run`` holds the label of the recorded or live model run used
for the document (for example "gemma4:e2b, 2026-11-07"); it is empty in rules
mode. ``extracted_values.agreement`` is set in combined mode only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('model_run', sa.String(length=200), nullable=True))
    op.add_column('extracted_values', sa.Column('agreement', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('extracted_values', 'agreement')
    op.drop_column('documents', 'model_run')
