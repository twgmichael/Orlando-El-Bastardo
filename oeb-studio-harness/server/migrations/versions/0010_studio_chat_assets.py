"""add studio chat assets and revisions

Revision ID: 0010_studio_chat_assets
Revises: 0009_studio_chat_milestones
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0010_studio_chat_assets"
down_revision: str = "0009_studio_chat_milestones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_chat_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.String(255), nullable=False),
        sa.Column("base_builder", sa.String(128), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_blend_path", sa.Text(), nullable=True),
        sa.Column("glb_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["thread_id"], ["studio_chat_threads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_studio_chat_assets_thread_id", "studio_chat_assets", ["thread_id"])
    op.create_index("ix_studio_chat_assets_asset_id", "studio_chat_assets", ["asset_id"])
    op.create_index("ix_studio_chat_assets_created_at", "studio_chat_assets", ["created_at"])
    op.create_index("ix_studio_chat_assets_updated_at", "studio_chat_assets", ["updated_at"])
    op.alter_column("studio_chat_assets", "current_revision", server_default=None)
    op.alter_column("studio_chat_assets", "state_json", server_default=None)

    op.create_table(
        "studio_chat_asset_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_asset_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_revision", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("state_before", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("edit_delta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("state_after", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_blend_path", sa.Text(), nullable=True),
        sa.Column("glb_path", sa.Text(), nullable=True),
        sa.Column("review_artifacts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["chat_asset_id"], ["studio_chat_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["studio_chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_studio_chat_asset_revisions_chat_asset_id", "studio_chat_asset_revisions", ["chat_asset_id"])
    op.create_index("ix_studio_chat_asset_revisions_revision", "studio_chat_asset_revisions", ["revision"])
    op.create_index("ix_studio_chat_asset_revisions_message_id", "studio_chat_asset_revisions", ["message_id"])
    op.create_index("ix_studio_chat_asset_revisions_job_id", "studio_chat_asset_revisions", ["job_id"])
    op.create_index("ix_studio_chat_asset_revisions_status", "studio_chat_asset_revisions", ["status"])
    op.create_index("ix_studio_chat_asset_revisions_created_at", "studio_chat_asset_revisions", ["created_at"])
    op.alter_column("studio_chat_asset_revisions", "state_before", server_default=None)
    op.alter_column("studio_chat_asset_revisions", "edit_delta", server_default=None)
    op.alter_column("studio_chat_asset_revisions", "state_after", server_default=None)
    op.alter_column("studio_chat_asset_revisions", "review_artifacts", server_default=None)
    op.alter_column("studio_chat_asset_revisions", "status", server_default=None)


def downgrade() -> None:
    op.drop_table("studio_chat_asset_revisions")
    op.drop_table("studio_chat_assets")
