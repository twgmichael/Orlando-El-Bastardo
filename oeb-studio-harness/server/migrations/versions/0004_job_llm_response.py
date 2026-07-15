"""Add job LLM response

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("llm_response", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "llm_response")
