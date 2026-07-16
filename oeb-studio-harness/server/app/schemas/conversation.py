from typing import Any, Optional
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from app.schemas.job import JobSummary


class SceneObject(BaseModel):
    id: str
    label: str
    category: str = "unknown"
    count: int = 1
    size: Optional[str] = None
    placement: Optional[str] = None
    mounting: Optional[str] = None
    shape: dict[str, Any] = Field(default_factory=dict)
    required_features: list[str] = Field(default_factory=list)
    source_phrases: list[str] = Field(default_factory=list)
    materials: dict[str, Any] = Field(default_factory=dict)
    style_details: list[str] = Field(default_factory=list)
    parts: list[dict[str, Any]] = Field(default_factory=list)
    orientation: dict[str, Any] = Field(default_factory=dict)


class SpatialRelationship(BaseModel):
    subject: str
    relation: str
    target: str


class ScenePlan(BaseModel):
    scene_type: str = "asset"
    style: Optional[str] = None
    objects: list[SceneObject] = Field(default_factory=list)
    relationships: list[SpatialRelationship] = Field(default_factory=list)


class PrimitiveBuildSpec(BaseModel):
    canonical_id: str
    name: str
    kind: str = "asset"
    style: str
    creative_request: Optional[str] = None
    build_method: str = "blender_primitives"
    components: list[str] = Field(default_factory=list)
    scene_plan: Optional[ScenePlan] = None
    repaired_scene_plan: Optional[ScenePlan] = None
    deliverables: list[str] = Field(default_factory=lambda: ["glb", "preview_render", "review_page"])


class ConversationProposalRequest(BaseModel):
    creative_request: str


class ConversationAcceptRequest(BaseModel):
    creative_request: str


class ConversationAcceptResponse(BaseModel):
    accepted: bool = True
    status: str = "accepted"
    creative_request: str
    accepted_at: datetime


class ConversationProposalResponse(BaseModel):
    creative_request: str
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    spec: PrimitiveBuildSpec
    job_payload: dict
    review_url: Optional[str] = None


class ConversationJobRequest(BaseModel):
    creative_request: str
    spec: PrimitiveBuildSpec
    llm_response: Optional[str] = None
    llm_prompt: Optional[str] = None
    scene_plan_prompt: Optional[str] = None
    scene_plan_response: Optional[str] = None
    repair_prompt: Optional[str] = None
    repair_response: Optional[str] = None
    scene_plan: Optional[ScenePlan] = None
    repaired_scene_plan: Optional[ScenePlan] = None
    detail_validation_warnings: list[str] = Field(default_factory=list)
    priority: int = 0
    policy: str = "run_anywhere"


class ConversationJobResponse(BaseModel):
    job: JobSummary
    review_url: str
    spec: PrimitiveBuildSpec


class ReviewArtifact(BaseModel):
    id: uuid.UUID
    artifact_type: str
    filename: str
    storage_path: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    url: str

    model_config = {"from_attributes": True}
