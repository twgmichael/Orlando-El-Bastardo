from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.conversation import PrimitiveBuildSpec
from app.schemas.job import JobSummary

STANDARD_REVIEW_VIEWS = ["top", "bottom", "left", "right", "front", "rear", "action"]
VALID_REVIEW_VIEWS = set(STANDARD_REVIEW_VIEWS)


class StudioChatRequest(BaseModel):
    prompt: str
    priority: int = 0
    policy: str = "run_anywhere"
    target_harness_url: Optional[str] = None


class StudioChatResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    canonical_id: str
    review_url: str
    trace_url: str
    saved_llm_response: bool
    target_harness_url: Optional[str] = None
    job: JobSummary | dict
    spec: PrimitiveBuildSpec | dict


class StudioChatModelList(BaseModel):
    models: list[str]
    default_model: str
    ollama_base_url: str


class StudioChatPreset(BaseModel):
    id: str
    label: str
    description: str
    system_prompt: str
    temperature: float = 0.2
    max_tokens: int = 2048


class StudioChatPresetList(BaseModel):
    presets: list[StudioChatPreset]


class StudioChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be empty")
        return value


class StudioChatOllamaRequest(BaseModel):
    model: str
    system_prompt: str = ""
    messages: list[StudioChatMessage]
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    stream: bool = False
    preset_id: str | None = None
    review_views: list[str] = Field(default_factory=list)

    @field_validator("review_views")
    @classmethod
    def review_views_must_be_known(cls, value: list[str]) -> list[str]:
        normalized = []
        for view in value:
            view_name = view.strip().lower()
            if view_name == "back":
                view_name = "rear"
            if view_name not in VALID_REVIEW_VIEWS:
                allowed = ", ".join(STANDARD_REVIEW_VIEWS)
                raise ValueError(f"review view must be one of: {allowed}")
            if view_name not in normalized:
                normalized.append(view_name)
        return normalized


class StudioChatOllamaMessage(BaseModel):
    role: Literal["assistant"]
    content: str


class StudioChatOllamaResponse(BaseModel):
    model: str
    message: StudioChatOllamaMessage
    done: bool
    raw: dict[str, Any]


class StudioChatBuildJobRequest(BaseModel):
    model: str | None = None
    creative_request: str
    assistant_response: str
    messages: list[StudioChatMessage] = Field(default_factory=list)
    review_views: list[str] = Field(default_factory=lambda: STANDARD_REVIEW_VIEWS.copy())
    priority: int = 0
    policy: str = "run_anywhere"

    @field_validator("review_views")
    @classmethod
    def build_review_views_must_be_known(cls, value: list[str]) -> list[str]:
        return StudioChatOllamaRequest.review_views_must_be_known(value)


class StudioChatBuildJobResponse(BaseModel):
    job: JobSummary
    review_url: str
    asset_review_url: str
    spec: PrimitiveBuildSpec
    review_views: list[str]
    resolver: dict[str, Any] | None = None
    review_render_requested: bool = True


class StudioChatPrimitiveResolveRequest(BaseModel):
    model: str | None = None
    creative_request: str
    assistant_response: str = ""
    max_retries: int = Field(default=1, ge=0, le=2)


class StudioChatPrimitiveResolveResponse(BaseModel):
    resolved: dict[str, Any]
    registry: dict[str, Any]


class StudioChatReviewArtifact(BaseModel):
    view: str
    filename: str
    url: str


class StudioChatBuildJobStatusResponse(BaseModel):
    build_job: JobSummary
    build_review_url: str
    asset_review_url: str
    review_job: JobSummary | None = None
    gallery_ready: bool = False
    missing_views: list[str] = Field(default_factory=list)
    artifacts: list[StudioChatReviewArtifact] = Field(default_factory=list)
    phase: str = "queued"
