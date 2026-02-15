"""Add ML lifecycle tables for training jobs, DSPy runs, feedback, and gaps

Revision ID: u1688q502ss5
Revises: t0577p491rr4
Create Date: 2026-02-13

Creates 4 new tables:
- training_jobs: Fine-tuning job tracking
- dspy_optimization_runs: DSPy prompt optimization runs
- ml_feedback_items: User feedback on model predictions
- ml_identified_gaps: Systematic gaps in model coverage
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


# revision identifiers, used by Alembic.
revision: str = 'u1688q502ss5'
down_revision: Union[str, None] = 't0577p491rr4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE trainingjobstatus AS ENUM ('pending', 'queued', 'running', 'succeeded', 'failed', 'cancelled')")
    op.execute("CREATE TYPE dspyrunstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE gapseverity AS ENUM ('low', 'medium', 'high', 'critical')")
    op.execute("CREATE TYPE gapstatus AS ENUM ('identified', 'in_progress', 'resolved', 'wont_fix')")

    # training_jobs
    op.create_table(
        'training_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('collection_id', UUID(as_uuid=True), sa.ForeignKey('training_collections.id', ondelete='SET NULL'), nullable=True),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('base_model', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('pending', 'queued', 'running', 'succeeded', 'failed', 'cancelled', name='trainingjobstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('training_config', sa.JSON, nullable=True),
        sa.Column('train_val_split', sa.Float, nullable=True),
        sa.Column('total_pairs', sa.Integer, nullable=True),
        sa.Column('train_pairs', sa.Integer, nullable=True),
        sa.Column('val_pairs', sa.Integer, nullable=True),
        sa.Column('progress_percent', sa.Float, nullable=True, server_default='0'),
        sa.Column('current_epoch', sa.Integer, nullable=True),
        sa.Column('total_epochs', sa.Integer, nullable=True),
        sa.Column('best_metric', sa.Float, nullable=True),
        sa.Column('metric_name', sa.String(100), nullable=True),
        sa.Column('fmapi_job_id', sa.String(255), nullable=True),
        sa.Column('mlflow_run_id', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('updated_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_training_jobs_status', 'training_jobs', ['status'])
    op.create_index('ix_training_jobs_collection', 'training_jobs', ['collection_id'])
    op.create_index('ix_training_jobs_fmapi', 'training_jobs', ['fmapi_job_id'])

    # dspy_optimization_runs
    op.create_table(
        'dspy_optimization_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('prompt_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('program_name', sa.String(255), nullable=False),
        sa.Column('signature_name', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', name='dspyrunstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('optimizer_type', sa.String(100), nullable=True),
        sa.Column('config', sa.JSON, nullable=True),
        sa.Column('trials_completed', sa.Integer, nullable=True, server_default='0'),
        sa.Column('trials_total', sa.Integer, nullable=True),
        sa.Column('best_score', sa.Float, nullable=True),
        sa.Column('results', sa.JSON, nullable=True),
        sa.Column('top_example_ids', ARRAY(sa.String), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('updated_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_dspy_runs_status', 'dspy_optimization_runs', ['status'])
    op.create_index('ix_dspy_runs_template', 'dspy_optimization_runs', ['template_id'])

    # ml_feedback_items
    op.create_table(
        'ml_feedback_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('endpoint_name', sa.String(255), nullable=True),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('response', sa.Text, nullable=False),
        sa.Column('rating', sa.Integer, nullable=True),
        sa.Column('feedback_type', sa.String(100), nullable=True),
        sa.Column('category', sa.String(255), nullable=True),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('is_converted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('converted_to_pair_id', UUID(as_uuid=True), sa.ForeignKey('qa_pairs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_feedback_model', 'ml_feedback_items', ['model_name'])
    op.create_index('ix_feedback_rating', 'ml_feedback_items', ['rating'])
    op.create_index('ix_feedback_converted', 'ml_feedback_items', ['is_converted'])

    # ml_identified_gaps
    op.create_table(
        'ml_identified_gaps',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('gap_type', sa.String(100), nullable=False),
        sa.Column('severity', sa.Enum('low', 'medium', 'high', 'critical', name='gapseverity', create_type=False), nullable=False, server_default='medium'),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('model_name', sa.String(255), nullable=True),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('prompt_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('affected_queries_count', sa.Integer, nullable=True),
        sa.Column('error_rate', sa.Float, nullable=True),
        sa.Column('suggested_action', sa.Text, nullable=True),
        sa.Column('estimated_records_needed', sa.Integer, nullable=True),
        sa.Column('status', sa.Enum('identified', 'in_progress', 'resolved', 'wont_fix', name='gapstatus', create_type=False), nullable=False, server_default='identified'),
        sa.Column('priority', sa.Integer, nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_gaps_severity', 'ml_identified_gaps', ['severity'])
    op.create_index('ix_gaps_status', 'ml_identified_gaps', ['status'])
    op.create_index('ix_gaps_model', 'ml_identified_gaps', ['model_name'])


def downgrade() -> None:
    op.drop_table('ml_identified_gaps')
    op.drop_table('ml_feedback_items')
    op.drop_table('dspy_optimization_runs')
    op.drop_table('training_jobs')

    op.execute("DROP TYPE IF EXISTS gapstatus")
    op.execute("DROP TYPE IF EXISTS gapseverity")
    op.execute("DROP TYPE IF EXISTS dspyrunstatus")
    op.execute("DROP TYPE IF EXISTS trainingjobstatus")
