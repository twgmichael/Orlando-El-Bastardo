"""Assets table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("canonical_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("node_name", sa.String(256), nullable=True),
        sa.Column("format", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_canonical_id", "assets", ["canonical_id"], unique=True)
    op.create_index("ix_assets_kind", "assets", ["kind"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])


def downgrade() -> None:
    op.drop_table("assets")
