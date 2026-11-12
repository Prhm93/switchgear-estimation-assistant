"""Stage UX visual pass V4: notes typed about an enquiry.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12

Additive only: one new table, ``enquiry_notes``. Text the engineer types on
the start page is kept here, so an enquiry may start before any file
arrives. A note is never read for values and never priced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'enquiry_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_enquiry_notes_project_id'), 'enquiry_notes', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_enquiry_notes_project_id'), table_name='enquiry_notes')
    op.drop_table('enquiry_notes')
