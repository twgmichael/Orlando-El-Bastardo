from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid


class JobCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    required_capabilities: list[str] = []
    policy: str = "run_anywhere"
    preferred_worker_id: Optional[str] = None
    priority: int = 0
    payload: dict = {}
    is_idempotent: bool = True


class JobSummary(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    required_capabilities: list
    policy: str
    preferred_worker_id: Optional[str]
    assigned_worker_id: Optional[str]
    priority: int
    payload: dict = {}
    is_idempotent: bool
    sibling_job_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeaseDetail(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    attempt_id: uuid.UUID
    worker_id: str
    granted_at: datetime
    expires_at: datetime
    last_renewed_at: datetime

    model_config = {"from_attributes": True}


class ClaimResponse(BaseModel):
    job: JobSummary
    lease: LeaseDetail


class JobCompleteRequest(BaseModel):
    log_output: Optional[str] = None
    output_summary: Optional[dict] = None


class JobFailRequest(BaseModel):
    reason: str
    log_output: Optional[str] = None


class AttemptSummary(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    output_summary: Optional[dict]

    model_config = {"from_attributes": True}
