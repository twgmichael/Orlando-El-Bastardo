"""add actor_type/actor_id to studio chat threads

docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 4: Producer is a
literal Studio Chat client, tagged as an agent actor in the same
conversational audit trail a human uses -- this is that tag.

Revision ID: 0011_studio_chat_thread_actor
Revises: 0010_studio_chat_assets
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0011_studio_chat_thread_actor"
down_revision: str = "0010_studio_chat_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "studio_chat_threads",
        sa.Column("actor_type", sa.String(32), nullable=False, server_default="human"),
    )
    op.add_column(
        "studio_chat_threads",
        sa.Column("actor_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_studio_chat_threads_actor_type", "studio_chat_threads", ["actor_type"])
    op.alter_column("studio_chat_threads", "actor_type", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_studio_chat_threads_actor_type", table_name="studio_chat_threads")
    op.drop_column("studio_chat_threads", "actor_id")
    op.drop_column("studio_chat_threads", "actor_type")
