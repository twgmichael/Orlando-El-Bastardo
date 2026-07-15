from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field


class AssetBase(BaseModel):
    name: Optional[str] = None
    file_path: Optional[str] = None
    node_name: Optional[str] = None
    format: Optional[str] = None
    status: str = "available"
    provenance: Optional[dict[str, Any]] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetCreate(AssetBase):
    canonical_id: str
    kind: str


class AssetUpdate(BaseModel):
    canonical_id: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    file_path: Optional[str] = None
    node_name: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    provenance: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class AssetRead(AssetBase):
    id: uuid.UUID
    canonical_id: str
    kind: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="asset_metadata")

    model_config = {"from_attributes": True}


class AssetSeedResponse(BaseModel):
    created: int
    skipped: int
    errors: list[str]
