"""add studio chat trace events

Revision ID: 0008_studio_chat_trace_events
Revises: 0007_studio_chat_threads
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0008_studio_chat_trace_events"
down_revision: str = "0007_studio_chat_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_chat_trace_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("text_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["studio_chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["studio_chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_studio_chat_trace_events_thread_id", "studio_chat_trace_events", ["thread_id"])
    op.create_index("ix_studio_chat_trace_events_message_id", "studio_chat_trace_events", ["message_id"])
    op.create_index("ix_studio_chat_trace_events_job_id", "studio_chat_trace_events", ["job_id"])
    op.create_index("ix_studio_chat_trace_events_event_type", "studio_chat_trace_events", ["event_type"])
    op.create_index("ix_studio_chat_trace_events_source", "studio_chat_trace_events", ["source"])
    op.create_index("ix_studio_chat_trace_events_created_at", "studio_chat_trace_events", ["created_at"])
    op.alter_column("studio_chat_trace_events", "payload", server_default=None)


def downgrade() -> None:
    op.drop_table("studio_chat_trace_events")
