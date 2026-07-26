"""add studio chat milestones

Revision ID: 0009_studio_chat_milestones
Revises: 0008_studio_chat_trace_events
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0009_studio_chat_milestones"
down_revision: str = "0008_studio_chat_trace_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_chat_milestones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("asset_id", sa.String(255), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("bundle_path", sa.Text(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["studio_chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["studio_chat_messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_studio_chat_milestones_thread_id", "studio_chat_milestones", ["thread_id"])
    op.create_index("ix_studio_chat_milestones_message_id", "studio_chat_milestones", ["message_id"])
    op.create_index("ix_studio_chat_milestones_asset_id", "studio_chat_milestones", ["asset_id"])
    op.create_index("ix_studio_chat_milestones_created_at", "studio_chat_milestones", ["created_at"])
    op.alter_column("studio_chat_milestones", "manifest_json", server_default=None)


def downgrade() -> None:
    op.drop_table("studio_chat_milestones")
