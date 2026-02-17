"""Add training data quality tables for DQX quality gate integration

Revision ID: v2799r613tt6
Revises: u1688q502ss5
Create Date: 2026-02-17

Creates 2 new tables:
- training_data_quality_checks: Quality check definitions per collection
- training_data_quality_runs: Quality run results with check outcomes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'v2799r613tt6'
down_revision: Union[str, None] = 'u1688q502ss5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # training_data_quality_checks
    op.create_table(
        'training_data_quality_checks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('collection_id', UUID(as_uuid=True), sa.ForeignKey('training_collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('check_name', sa.String(255), nullable=False),
        sa.Column('check_function', sa.String(255), nullable=False),
        sa.Column('column_name', sa.String(255), nullable=True),
        sa.Column('criticality', sa.String(50), nullable=False, server_default='warning'),
        sa.Column('parameters', sa.JSON, nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_quality_checks_collection', 'training_data_quality_checks', ['collection_id'])

    # training_data_quality_runs
    op.create_table(
        'training_data_quality_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('collection_id', UUID(as_uuid=True), sa.ForeignKey('training_collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('source', sa.String(50), nullable=False, server_default='mock'),
        sa.Column('pass_rate', sa.Float, nullable=True),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('check_results', sa.JSON, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_quality_runs_collection', 'training_data_quality_runs', ['collection_id'])
    op.create_index('ix_quality_runs_status', 'training_data_quality_runs', ['status'])


def downgrade() -> None:
    op.drop_table('training_data_quality_runs')
    op.drop_table('training_data_quality_checks')
