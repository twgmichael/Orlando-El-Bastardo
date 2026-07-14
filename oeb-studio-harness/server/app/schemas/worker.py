from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class WorkerRegisterRequest(BaseModel):
    worker_id: str
    platform: str
    agent_version: str
    capabilities: list[str]
    resources: Optional[dict] = None


class WorkerRegisterResponse(BaseModel):
    worker_id: str
    worker_token: str
    registered_at: datetime


class WorkerHeartbeatRequest(BaseModel):
    status: str  # online | busy | idle
    current_job_id: Optional[str] = None
    cpu_load_percent: Optional[float] = None
    gpu_load_percent: Optional[float] = None
    free_ram_gb: Optional[float] = None
    free_vram_gb: Optional[float] = None


class WorkerHeartbeatResponse(BaseModel):
    acknowledged: bool
    server_time: datetime


class WorkerCapabilitySummary(BaseModel):
    capability: str

    model_config = {"from_attributes": True}


class WorkerDetail(BaseModel):
    id: str
    platform: str
    agent_version: str
    status: str
    capabilities: list[str]
    resources: Optional[dict]
    last_heartbeat_at: Optional[datetime]
    registered_at: datetime

    model_config = {"from_attributes": True}
