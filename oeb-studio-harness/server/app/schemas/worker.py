from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class WorkerRegisterRequest(BaseModel):
    worker_id: str
    platform: str
    agent_version: str
    git_sha: Optional[str] = None
    capabilities: list[str]
    resources: Optional[dict] = None


class WorkerRegisterResponse(BaseModel):
    worker_id: str
    worker_token: str
    registered_at: datetime


class WorkerHeartbeatRequest(BaseModel):
    status: str  # online | busy | idle
    current_job_id: Optional[str] = None
    git_sha: Optional[str] = None
    update_state: Optional[str] = None
    update_last_error: Optional[str] = None
    cpu_load_percent: Optional[float] = None
    gpu_load_percent: Optional[float] = None
    free_ram_gb: Optional[float] = None
    free_vram_gb: Optional[float] = None


class WorkerHeartbeatResponse(BaseModel):
    acknowledged: bool
    server_time: datetime
    update_state: str = "idle"
    update_mode: Optional[str] = None
    update_target_git_sha: Optional[str] = None


class WorkerUpdateRequest(BaseModel):
    target_git_sha: Optional[str] = None
    mode: str = "drain_then_update"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, mode: str) -> str:
        allowed = {"drain_then_update", "update_if_idle", "force_update"}
        if mode not in allowed:
            raise ValueError(f"mode must be one of {sorted(allowed)}")
        return mode


class WorkerUpdateResponse(BaseModel):
    worker_id: str
    update_state: str
    update_mode: str
    update_target_git_sha: Optional[str]
    current_job_id: Optional[str]
    message: str


class WorkerCapabilitySummary(BaseModel):
    capability: str

    model_config = {"from_attributes": True}


class WorkerDetail(BaseModel):
    id: str
    platform: str
    agent_version: str
    git_sha: Optional[str]
    status: str
    current_job_id: Optional[str]
    update_state: str
    update_mode: Optional[str]
    update_target_git_sha: Optional[str]
    update_requested_at: Optional[datetime]
    update_last_error: Optional[str]
    capabilities: list[str]
    resources: Optional[dict]
    last_heartbeat_at: Optional[datetime]
    registered_at: datetime

    model_config = {"from_attributes": True}
