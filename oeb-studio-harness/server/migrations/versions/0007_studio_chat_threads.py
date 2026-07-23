"""add studio chat threads

Revision ID: 0007_studio_chat_threads
Revises: 0006_worker_update_state
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0007_studio_chat_threads"
down_revision: str = "0006_worker_update_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_chat_threads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False, server_default="local"),
        sa.Column("default_model", sa.String(255), nullable=True),
        sa.Column("default_preset_id", sa.String(128), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("review_views", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_chat_threads_environment", "studio_chat_threads", ["environment"])
    op.create_index("ix_studio_chat_threads_created_at", "studio_chat_threads", ["created_at"])
    op.create_index("ix_studio_chat_threads_updated_at", "studio_chat_threads", ["updated_at"])
    op.create_index("ix_studio_chat_threads_archived_at", "studio_chat_threads", ["archived_at"])
    op.alter_column("studio_chat_threads", "environment", server_default=None)
    op.alter_column("studio_chat_threads", "review_views", server_default=None)

    op.create_table(
        "studio_chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["studio_chat_threads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_studio_chat_messages_thread_id", "studio_chat_messages", ["thread_id"])
    op.create_index("ix_studio_chat_messages_created_at", "studio_chat_messages", ["created_at"])
    op.alter_column("studio_chat_messages", "raw", server_default=None)

    op.create_table(
        "studio_chat_build_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("asset_id", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["studio_chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["studio_chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_studio_chat_build_events_thread_id", "studio_chat_build_events", ["thread_id"])
    op.create_index("ix_studio_chat_build_events_message_id", "studio_chat_build_events", ["message_id"])
    op.create_index("ix_studio_chat_build_events_job_id", "studio_chat_build_events", ["job_id"])
    op.create_index("ix_studio_chat_build_events_asset_id", "studio_chat_build_events", ["asset_id"])
    op.create_index("ix_studio_chat_build_events_event_type", "studio_chat_build_events", ["event_type"])
    op.create_index("ix_studio_chat_build_events_created_at", "studio_chat_build_events", ["created_at"])
    op.alter_column("studio_chat_build_events", "payload", server_default=None)


def downgrade() -> None:
    op.drop_table("studio_chat_build_events")
    op.drop_table("studio_chat_messages")
    op.drop_table("studio_chat_threads")
