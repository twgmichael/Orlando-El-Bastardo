from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
import uuid


class JobCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    llm_response: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    required_capabilities: list[str] = []
    policy: str = "run_anywhere"
    preferred_worker_id: Optional[str] = None
    priority: int = 0
    payload: dict = {}
    is_idempotent: bool = True
    depends_on_job_id: Optional[uuid.UUID] = None


ASSET_REVIEW_VIEWS = {"top", "bottom", "left", "right", "front", "back", "action"}


class AssetReviewRenderRequest(BaseModel):
    asset_path: Optional[str] = None
    asset_id: Optional[str] = None
    asset_name: Optional[str] = None
    views: list[str] = Field(default_factory=lambda: [
        "top", "bottom", "left", "right", "front", "back", "action"
    ])
    quality: str = "preview"
    output_namespace: Optional[str] = None
    artifact_prefix: Optional[str] = None
    priority: int = 10
    preferred_worker_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    samples: Optional[int] = None
    output_path: Optional[str] = None
    require_gpu_cycles: bool = False

    @field_validator("views")
    @classmethod
    def validate_views(cls, views: list[str]) -> list[str]:
        if not views:
            raise ValueError("views must contain at least one view")
        invalid = [view for view in views if view not in ASSET_REVIEW_VIEWS]
        if invalid:
            raise ValueError(f"views contains unsupported values: {invalid}")
        return views

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, quality: str) -> str:
        if quality not in {"draft", "preview", "final"}:
            raise ValueError("quality must be draft, preview, or final")
        return quality


class KitbashBuildRequest(BaseModel):
    """Kicks off the set designer kitbash tier's human-approval flow
    (docs/planning/PRODUCTION-DESIGNER-PLAN.md): a worker runs
    tools/build_set.py against *spec_path*, then post_build_review
    auto-follows with turntable renders and lands the set as a
    kitbash_pending Asset row for /review/kitbash to show.
    """
    canonical_id: str
    spec_path: str
    location_tag: Optional[str] = None
    name: Optional[str] = None
    ticket_ref: Optional[str] = None
    priority: int = 10
    preferred_worker_id: Optional[str] = None


class JobSummary(BaseModel):
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
    payload: dict = {}
    is_idempotent: bool
    sibling_job_id: Optional[uuid.UUID]
    depends_on_job_id: Optional[uuid.UUID] = None
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
    output_summary: Optional[dict] = None


class JobProgressRequest(BaseModel):
    progress: dict = Field(default_factory=dict)


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
