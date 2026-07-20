"""add worker update state

Revision ID: 0006_worker_update_state
Revises: 0005
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0006_worker_update_state"
down_revision: str = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workers", sa.Column("git_sha", sa.String(64), nullable=True))
    op.add_column("workers", sa.Column("current_job_id", sa.String(64), nullable=True))
    op.add_column(
        "workers",
        sa.Column("update_state", sa.String(32), nullable=False, server_default="idle"),
    )
    op.add_column("workers", sa.Column("update_mode", sa.String(32), nullable=True))
    op.add_column("workers", sa.Column("update_target_git_sha", sa.String(64), nullable=True))
    op.add_column("workers", sa.Column("update_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workers", sa.Column("update_last_error", sa.String(512), nullable=True))
    op.alter_column("workers", "update_state", server_default=None)


def downgrade() -> None:
    op.drop_column("workers", "update_last_error")
    op.drop_column("workers", "update_requested_at")
    op.drop_column("workers", "update_target_git_sha")
    op.drop_column("workers", "update_mode")
    op.drop_column("workers", "update_state")
    op.drop_column("workers", "current_job_id")
    op.drop_column("workers", "git_sha")
