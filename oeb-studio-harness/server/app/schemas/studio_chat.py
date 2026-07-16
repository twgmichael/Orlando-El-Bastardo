from typing import Optional
import uuid

from pydantic import BaseModel

from app.schemas.conversation import PrimitiveBuildSpec
from app.schemas.job import JobSummary


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
