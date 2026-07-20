from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class SceneRenderRequest(BaseModel):
    scene_name: str = Field(min_length=1)
    script_path: str = Field(min_length=1)
    quality: str = "preview"
    width: Optional[int] = Field(default=None, gt=0)
    height: Optional[int] = Field(default=None, gt=0)
    preferred_worker_id: Optional[str] = None
    priority: int = 10
    require_gpu_cycles: bool = False
    mode: Optional[str] = None
    expected_frames: Optional[int] = Field(default=None, gt=0)
    blender_timeout_seconds: Optional[int] = Field(default=None, gt=0)

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, quality: str) -> str:
        if quality not in {"draft", "preview", "final"}:
            raise ValueError("quality must be draft, preview, or final")
        return quality

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, mode: Optional[str]) -> Optional[str]:
        if mode is not None and mode not in {"preview", "blocking"}:
            raise ValueError("mode must be preview or blocking")
        return mode


class SceneRenderResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    review_url: str
    trace_url: str
    scene_name: str
    script_path: str
    quality: str
    created_at: datetime
