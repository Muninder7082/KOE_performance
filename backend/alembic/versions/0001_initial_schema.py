"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-08 15:33:58.022647
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op



revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table('monitored_websites',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('url_normalized', sa.String(length=2048), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('frequency', sa.String(length=30), nullable=False),
    sa.Column('monitor_time', sa.String(length=5), nullable=False),
    sa.Column('day_of_week', sa.Integer(), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('schedule_updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_scheduled_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url_normalized')
    )
    op.create_table('scheduled_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_by', sa.String(length=100), nullable=True),
    sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.String(length=20), nullable=True),
    sa.Column('last_message', sa.Text(), nullable=True),
    sa.Column('last_occurrence_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('task_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.String(length=40), nullable=False),
    sa.Column('task', sa.String(length=50), nullable=False),
    sa.Column('trigger', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('websites_due', sa.Integer(), nullable=False),
    sa.Column('tests_succeeded', sa.Integer(), nullable=False),
    sa.Column('tests_failed', sa.Integer(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id')
    )
    op.create_index('ix_task_runs_started', 'task_runs', ['started_at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('session_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('email_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email_type', sa.String(length=30), nullable=False),
    sa.Column('recipients', sa.Text(), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('website_id', sa.Integer(), nullable=True),
    sa.Column('website_name', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('has_attachment', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['website_id'], ['monitored_websites.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_email_logs_created', 'email_logs', ['created_at'], unique=False)
    op.create_table('performance_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('website_id', sa.Integer(), nullable=True),
    sa.Column('website_name', sa.String(length=200), nullable=False),
    sa.Column('requested_url', sa.String(length=2048), nullable=False),
    sa.Column('final_url', sa.String(length=2048), nullable=True),
    sa.Column('strategy', sa.String(length=10), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('api_status', sa.String(length=100), nullable=True),
    sa.Column('performance_score', sa.Integer(), nullable=True),
    sa.Column('accessibility_score', sa.Integer(), nullable=True),
    sa.Column('best_practices_score', sa.Integer(), nullable=True),
    sa.Column('seo_score', sa.Integer(), nullable=True),
    sa.Column('fcp_s', sa.Float(), nullable=True),
    sa.Column('lcp_s', sa.Float(), nullable=True),
    sa.Column('tbt_ms', sa.Float(), nullable=True),
    sa.Column('cls', sa.Float(), nullable=True),
    sa.Column('speed_index_s', sa.Float(), nullable=True),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('error_code', sa.String(length=50), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('tested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('run_id', sa.String(length=40), nullable=True),
    sa.Column('excel_appended', sa.Boolean(), nullable=False),
    sa.Column('excel_appended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['website_id'], ['monitored_websites.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_results_excel_pending', 'performance_results', ['excel_appended', 'id'], unique=False)
    op.create_index('ix_results_tested_at', 'performance_results', ['tested_at'], unique=False)
    op.create_index('ix_results_website_strategy_tested', 'performance_results', ['website_id', 'strategy', 'tested_at'], unique=False)
    op.create_table('alert_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('website_id', sa.Integer(), nullable=True),
    sa.Column('website_name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('strategy', sa.String(length=10), nullable=False),
    sa.Column('state', sa.String(length=12), nullable=False),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notify_count', sa.Integer(), nullable=False),
    sa.Column('recovered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('recovered_score', sa.Integer(), nullable=True),
    sa.Column('last_result_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['last_result_id'], ['performance_results.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['website_id'], ['monitored_websites.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_website_strategy_state', 'alert_events', ['website_id', 'strategy', 'state'], unique=False)



def downgrade() -> None:

    op.drop_index('ix_alerts_website_strategy_state', table_name='alert_events')
    op.drop_table('alert_events')
    op.drop_index('ix_results_website_strategy_tested', table_name='performance_results')
    op.drop_index('ix_results_tested_at', table_name='performance_results')
    op.drop_index('ix_results_excel_pending', table_name='performance_results')
    op.drop_table('performance_results')
    op.drop_index('ix_email_logs_created', table_name='email_logs')
    op.drop_table('email_logs')
    op.drop_table('users')
    op.drop_index('ix_task_runs_started', table_name='task_runs')
    op.drop_table('task_runs')
    op.drop_table('system_settings')
    op.drop_table('scheduled_tasks')
    op.drop_table('monitored_websites')

