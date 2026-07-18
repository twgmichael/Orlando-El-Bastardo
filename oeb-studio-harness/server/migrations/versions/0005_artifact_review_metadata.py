"""add artifact public urls and review metadata

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("public_url", sa.Text(), nullable=True))
    op.add_column(
        "artifacts",
        sa.Column("review_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("artifacts", "review_metadata")
    op.drop_column("artifacts", "public_url")
