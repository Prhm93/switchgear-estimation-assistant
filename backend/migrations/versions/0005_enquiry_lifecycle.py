"""Stage UX part 1: archive, last-updated and sample marks for enquiries; how each file was read.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11

Additive only. ``projects.updated_at`` moves with every upload, reading,
review and quote (existing rows start from ``created_at``);
``projects.archived_at`` hides an enquiry from the list without deleting
anything; ``projects.is_sample`` marks the sample enquiry, the only one that
may use recorded model runs whatever MODEL_MODE says.
``documents.read_method`` records how the file was actually read ("rules",
"ocr" or "rules+model"); it is empty for rows stored before this revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('is_sample', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('documents', sa.Column('read_method', sa.String(length=40), nullable=True))
    op.execute("UPDATE projects SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    op.drop_column('documents', 'read_method')
    op.drop_column('projects', 'is_sample')
    op.drop_column('projects', 'archived_at')
    op.drop_column('projects', 'updated_at')
