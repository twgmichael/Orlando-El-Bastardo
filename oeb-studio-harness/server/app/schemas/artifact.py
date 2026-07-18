from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


class ArtifactRegisterRequest(BaseModel):
    artifact_type: str
    filename: str
    storage_path: str
    public_url: Optional[str] = None
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    checksum_sha256: Optional[str] = None
    provenance: str = "inferred"
    review_metadata: dict = Field(default_factory=dict)
    attempt_id: Optional[uuid.UUID] = None


class ArtifactSummary(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    artifact_type: str
    filename: str
    storage_path: str
    public_url: Optional[str]
    size_bytes: Optional[int]
    mime_type: Optional[str]
    checksum_sha256: Optional[str]
    provenance: str
    review_metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}
