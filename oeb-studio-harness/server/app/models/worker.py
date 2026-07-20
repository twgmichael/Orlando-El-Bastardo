from datetime import datetime, timezone
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="offline", nullable=False)
    current_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    update_state: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    update_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    update_target_git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    update_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    update_last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WorkerCapability(Base):
    __tablename__ = "worker_capabilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
