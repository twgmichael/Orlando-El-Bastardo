from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel


class DebugJobRecord(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    llm_response: Optional[str]
    status: str
    required_capabilities: list
    policy: str
    preferred_worker_id: Optional[str]
    assigned_worker_id: Optional[str]
    priority: int
    payload: dict
    is_idempotent: bool
    sibling_job_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DebugAttemptRecord(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    log_output: Optional[str]
    output_summary: Optional[dict]

    model_config = {"from_attributes": True}


class DebugArtifactRecord(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    attempt_id: Optional[uuid.UUID]
    worker_id: str
    artifact_type: str
    filename: str
    storage_path: str
    size_bytes: Optional[int]
    mime_type: Optional[str]
    checksum_sha256: Optional[str]
    provenance: str
    created_at: datetime
    review_url: str

    model_config = {"from_attributes": True}


class DebugPromptLoop(BaseModel):
    creative_request: Optional[str]
    llm_prompt: Optional[str]
    llm_response: Optional[str]
    scene_plan_prompt: Optional[str]
    scene_plan_response: Optional[str]
    scene_plan: Optional[dict]
    repair_prompt: Optional[str]
    repair_response: Optional[str]
    repaired_scene_plan: Optional[dict]
    primitive_spec: Optional[dict]
    script_file: Optional[str]
    script_args: list


class DebugJobTrace(BaseModel):
    job: DebugJobRecord
    prompt_loop: DebugPromptLoop
    conversation: dict
    attempts: list[DebugAttemptRecord]
    artifacts: list[DebugArtifactRecord]
    review_url: str


class StudioProjectState(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StudioWorkerState(BaseModel):
    id: str
    platform: str
    agent_version: str
    status: str
    capabilities: list[str]
    resources: Optional[dict]
    current_job_id: Optional[uuid.UUID]
    last_heartbeat_at: Optional[datetime]
    registered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StudioJobState(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    project_id: Optional[uuid.UUID]
    canonical_id: Optional[str]
    creative_request: Optional[str]
    assigned_worker_id: Optional[str]
    preferred_worker_id: Optional[str]
    required_capabilities: list
    priority: int
    created_at: datetime
    updated_at: datetime
    last_attempt_status: Optional[str]
    last_failure_reason: Optional[str]
    review_url: str
    trace_url: str


class StudioAttemptState(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    failure_reason: Optional[str]
    trace_url: str


class StudioArtifactState(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    attempt_id: Optional[uuid.UUID]
    worker_id: str
    artifact_type: str
    filename: str
    size_bytes: Optional[int]
    mime_type: Optional[str]
    created_at: datetime
    review_url: str
    trace_url: str


class StudioJobBuckets(BaseModel):
    queued: list[StudioJobState]
    running: list[StudioJobState]
    recent_completed: list[StudioJobState]
    recent_failed: list[StudioJobState]


class StudioStateResponse(BaseModel):
    generated_at: datetime
    projects: list[StudioProjectState]
    workers: list[StudioWorkerState]
    jobs: StudioJobBuckets
    recent_attempts: list[StudioAttemptState]
    recent_artifacts: list[StudioArtifactState]
    review_links: list[str]
    debug_links: list[str]
