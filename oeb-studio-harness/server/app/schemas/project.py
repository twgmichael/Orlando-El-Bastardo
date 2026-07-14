from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid


class ProjectCreateRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
