"""Stage 2 tables: projects, documents, pages, extracted values, catalogue, matches, estimates, reviews, audit.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06

Mirrors ``backend/app/models.py``; tests/integration/test_migrations.py checks
that the migrated schema and the models agree.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('catalogue_items',
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('rating_a', sa.Integer(), nullable=True),
    sa.Column('poles', sa.Integer(), nullable=True),
    sa.Column('breaking_ka', sa.Integer(), nullable=True),
    sa.Column('ip_rating', sa.String(length=8), nullable=True),
    sa.Column('width_mm', sa.Integer(), nullable=True),
    sa.Column('size', sa.String(length=20), nullable=True),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('unit_price_gbp', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('labour_hours', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    with op.batch_alter_table('catalogue_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_catalogue_items_category'), ['category'], unique=False)

    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor', sa.String(length=60), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('entity', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_project_id'), ['project_id'], unique=False)

    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=64), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('file_type', sa.String(length=8), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documents_sha256'), ['sha256'], unique=False)

    op.create_table('estimates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('labour_rate', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('margin_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('materials', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('labour_hours', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('labour', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('margin', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('problems', sa.JSON(), nullable=False),
    sa.Column('unmatched', sa.JSON(), nullable=False),
    sa.Column('pending', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('estimates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_estimates_project_id'), ['project_id'], unique=False)

    op.create_table('matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('requirement_key', sa.String(length=60), nullable=False),
    sa.Column('requirement', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('review_status', sa.String(length=20), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['code'], ['catalogue_items.code'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_matches_project_id'), ['project_id'], unique=False)

    op.create_table('estimate_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('estimate_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('labour_hours', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('materials', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('basis', sa.JSON(), nullable=False),
    sa.Column('value_ids', sa.JSON(), nullable=False),
    sa.Column('substitute_reasons', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['code'], ['catalogue_items.code'], ),
    sa.ForeignKeyConstraint(['estimate_id'], ['estimates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('estimate_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_estimate_lines_estimate_id'), ['estimate_id'], unique=False)

    op.create_table('extracted_values',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('field', sa.String(length=100), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.Column('unit', sa.String(length=20), nullable=True),
    sa.Column('source_document', sa.String(length=20), nullable=False),
    sa.Column('source_file', sa.String(length=255), nullable=False),
    sa.Column('page', sa.Integer(), nullable=True),
    sa.Column('source_text', sa.Text(), nullable=True),
    sa.Column('regions', sa.JSON(), nullable=False),
    sa.Column('method', sa.String(length=20), nullable=False),
    sa.Column('confidence', sa.String(length=20), nullable=False),
    sa.Column('review_status', sa.String(length=20), nullable=False),
    sa.Column('rule', sa.String(length=60), nullable=True),
    sa.Column('derivation', sa.Text(), nullable=True),
    sa.Column('approved_value', sa.JSON(), nullable=True),
    sa.Column('approved_unit', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('extracted_values', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_extracted_values_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_extracted_values_field'), ['field'], unique=False)
        batch_op.create_index(batch_op.f('ix_extracted_values_project_id'), ['project_id'], unique=False)

    op.create_table('pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('tables', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pages_document_id'), ['document_id'], unique=False)

    op.create_table('reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('value_id', sa.Integer(), nullable=True),
    sa.Column('match_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('old_value', sa.JSON(), nullable=True),
    sa.Column('new_value', sa.JSON(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('actor', sa.String(length=60), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['value_id'], ['extracted_values.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reviews_project_id'), ['project_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reviews_project_id'))

    op.drop_table('reviews')
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pages_document_id'))

    op.drop_table('pages')
    with op.batch_alter_table('extracted_values', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extracted_values_project_id'))
        batch_op.drop_index(batch_op.f('ix_extracted_values_field'))
        batch_op.drop_index(batch_op.f('ix_extracted_values_document_id'))

    op.drop_table('extracted_values')
    with op.batch_alter_table('estimate_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_estimate_lines_estimate_id'))

    op.drop_table('estimate_lines')
    with op.batch_alter_table('matches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_matches_project_id'))

    op.drop_table('matches')
    with op.batch_alter_table('estimates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_estimates_project_id'))

    op.drop_table('estimates')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_sha256'))
        batch_op.drop_index(batch_op.f('ix_documents_project_id'))

    op.drop_table('documents')
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_events_project_id'))

    op.drop_table('audit_events')
    op.drop_table('projects')
    with op.batch_alter_table('catalogue_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_catalogue_items_category'))

    op.drop_table('catalogue_items')
