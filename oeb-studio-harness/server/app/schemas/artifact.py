from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid


class ArtifactRegisterRequest(BaseModel):
    artifact_type: str
    filename: str
    storage_path: str
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    checksum_sha256: Optional[str] = None
    provenance: str = "inferred"
    attempt_id: Optional[uuid.UUID] = None


class ArtifactSummary(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: str
    artifact_type: str
    filename: str
    storage_path: str
    size_bytes: Optional[int]
    mime_type: Optional[str]
    checksum_sha256: Optional[str]
    provenance: str
    created_at: datetime

    model_config = {"from_attributes": True}
