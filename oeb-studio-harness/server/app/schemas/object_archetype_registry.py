from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.hierarchical_asset_intent import (
    AttachmentAnchor,
    HierarchicalAssetIntent,
    HierarchicalIntentDiagnostic,
    PartRequirement,
    RepetitionMode,
    SemanticDirection,
)


OBJECT_ARCHETYPE_REGISTRY_SCHEMA_VERSION = "1.0"
ARCHETYPE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _positive_finite_vector(value: list[float], field_name: str) -> list[float]:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three numbers")
    normalized = [float(component) for component in value]
    if not all(math.isfinite(component) and component > 0 for component in normalized):
        raise ValueError(f"{field_name} must contain positive finite numbers")
    return normalized


class ArchetypeProportionRange(BaseModel):
    minimum: list[float]
    maximum: list[float]
    relative_to_role: str

    @field_validator("minimum", "maximum")
    @classmethod
    def ranges_must_be_positive_and_finite(
        cls,
        value: list[float],
        info,
    ) -> list[float]:
        return _positive_finite_vector(value, info.field_name)


class ArchetypeOrientationRule(BaseModel):
    forward: SemanticDirection
    up: SemanticDirection


class ArchetypeRepetitionRule(BaseModel):
    allowed_modes: list[RepetitionMode] = Field(min_length=1)
    minimum_count: int = Field(default=1, ge=1)
    maximum_count: int = Field(default=1, ge=1)
    axis: SemanticDirection | None = None

    @field_validator("allowed_modes")
    @classmethod
    def modes_must_be_unique(cls, value: list[RepetitionMode]) -> list[RepetitionMode]:
        if len(value) != len(set(value)):
            raise ValueError("allowed repetition modes must be unique")
        return value


class ArchetypeRoleRule(BaseModel):
    role: str
    requirement: PartRequirement
    aliases: list[str] = Field(default_factory=list)
    allowed_parent_roles: list[str] = Field(default_factory=list)
    allowed_shape_families: list[str] = Field(min_length=1)
    allowed_attachment_anchors: list[AttachmentAnchor] = Field(default_factory=list)
    contact_required: bool | None = None
    default_orientation: ArchetypeOrientationRule
    proportion_range: ArchetypeProportionRange | None = None
    repetition: ArchetypeRepetitionRule
    supported_geometry_recipes: list[str] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("role")
    @classmethod
    def role_must_be_stable(cls, value: str) -> str:
        if not ARCHETYPE_ID_PATTERN.fullmatch(value):
            raise ValueError("archetype role must be stable snake_case")
        return value


class ArchetypeGeometryRecipe(BaseModel):
    id: str
    status: Literal["planned", "available"]
    compiler: str | None = None
    description: str
    defaults: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("id")
    @classmethod
    def id_must_be_stable(cls, value: str) -> str:
        if not ARCHETYPE_ID_PATTERN.fullmatch(value):
            raise ValueError("geometry recipe id must be stable snake_case")
        return value


class ObjectArchetype(BaseModel):
    id: str
    family: str
    aliases: list[str] = Field(default_factory=list)
    root_role: str
    roles: list[ArchetypeRoleRule] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("id", "family", "root_role")
    @classmethod
    def ids_must_be_stable(cls, value: str) -> str:
        if not ARCHETYPE_ID_PATTERN.fullmatch(value):
            raise ValueError("archetype identifiers must be stable snake_case")
        return value


class ObjectArchetypeRegistry(BaseModel):
    schema_version: Literal["1.0"] = OBJECT_ARCHETYPE_REGISTRY_SCHEMA_VERSION
    registry_version: str
    geometry_recipes: list[ArchetypeGeometryRecipe] = Field(default_factory=list)
    archetypes: list[ObjectArchetype] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("registry_version")
    @classmethod
    def registry_version_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("registry_version must not be empty")
        return value.strip()


class ArchetypeGroundingChange(BaseModel):
    path: str
    code: str
    before: Any = None
    after: Any = None


class ArchetypeGroundingResult(BaseModel):
    valid: bool
    outcome: Literal["valid", "invalid", "needs_repair", "unsupported"]
    registry_version: str
    archetype_id: str | None = None
    archetype: ObjectArchetype | None = None
    intent: HierarchicalAssetIntent | None = None
    changes: list[ArchetypeGroundingChange] = Field(default_factory=list)
    diagnostics: list[HierarchicalIntentDiagnostic] = Field(default_factory=list)
