"""add depends_on_job_id to jobs

docs/planning/CASTING-DIRECTOR-PLAN.md's Open Question #1: a Casting
Director job blocked on a scene whose location is *also* unresolved
must not be claimable until the location job it depends on actually
completes. Job.sibling_job_id (0002) is the wrong shape for this -- a
bidirectional, purely informational pairing (preview/final render
jobs), never consulted by the eligibility query. This is a real,
directional, eligibility-gating dependency.

Revision ID: 0012_job_depends_on
Revises: 0011_studio_chat_thread_actor
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0012_job_depends_on"
down_revision: str = "0011_studio_chat_thread_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("depends_on_job_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_jobs_depends_on_job_id",
        "jobs", "jobs",
        ["depends_on_job_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_depends_on_job_id", "jobs", ["depends_on_job_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_depends_on_job_id", table_name="jobs")
    op.drop_constraint("fk_jobs_depends_on_job_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "depends_on_job_id")
