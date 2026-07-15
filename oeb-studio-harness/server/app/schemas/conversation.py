from typing import Optional
import uuid

from pydantic import BaseModel, Field

from app.schemas.job import JobSummary


class PrimitiveBuildSpec(BaseModel):
    canonical_id: str
    name: str
    kind: str = "asset"
    style: str
    build_method: str = "blender_primitives"
    components: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=lambda: ["glb", "preview_render", "review_page"])


class ConversationProposalRequest(BaseModel):
    creative_request: str


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
