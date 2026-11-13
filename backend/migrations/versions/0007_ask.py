"""Stage 9: the question box (passages with embeddings, and every question with its answer).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13

Additive only: two new tables.

- ``ask_passages``: short passages of an enquiry's page text, each with its file, page, the embedder's name and its
  vector (pgvector ``vector`` on PostgreSQL, JSON on SQLite). Made again from the stored page text whenever needed,
  so they can be dropped and rebuilt without losing anything.
- ``ask_questions``: every question asked about an enquiry, with the answer shown, its sources, whether it was a
  refusal, the number check, the embedder and the actor (also written to the audit log).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        'ask_passages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedder', sa.String(length=60), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),  # replaced by a vector column on PostgreSQL below
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    if bind.dialect.name == 'postgresql':
        op.execute('ALTER TABLE ask_passages DROP COLUMN embedding')
        op.execute('ALTER TABLE ask_passages ADD COLUMN embedding vector')
    op.create_index(op.f('ix_ask_passages_project_id'), 'ask_passages', ['project_id'], unique=False)
    op.create_index(op.f('ix_ask_passages_document_id'), 'ask_passages', ['document_id'], unique=False)
    op.create_table(
        'ask_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('refused', sa.Boolean(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('numbers', sa.JSON(), nullable=False),
        sa.Column('embedder', sa.String(length=60), nullable=False),
        sa.Column('actor', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ask_questions_project_id'), 'ask_questions', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ask_questions_project_id'), table_name='ask_questions')
    op.drop_table('ask_questions')
    op.drop_index(op.f('ix_ask_passages_document_id'), table_name='ask_passages')
    op.drop_index(op.f('ix_ask_passages_project_id'), table_name='ask_passages')
    op.drop_table('ask_passages')
