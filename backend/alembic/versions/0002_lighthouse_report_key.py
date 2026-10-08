"""store a reference to the full Lighthouse report of each test

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("performance_results") as batch:
        batch.add_column(sa.Column("report_key", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("performance_results") as batch:
        batch.drop_column("report_key")
