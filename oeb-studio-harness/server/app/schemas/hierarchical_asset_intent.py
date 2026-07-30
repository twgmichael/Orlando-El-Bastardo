from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


HIERARCHICAL_ASSET_INTENT_SCHEMA_VERSION = "1.0"
SEMANTIC_PART_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

SemanticDirection = Literal["front", "rear", "left", "right", "up", "down"]
PartRequirement = Literal["required", "optional", "decorative"]
AttachmentAnchor = Literal[
    "center",
    "top_center",
    "bottom_center",
    "front_center",
    "rear_center",
    "left_side",
    "right_side",
    "inside",
    "around",
]
RepetitionMode = Literal["none", "mirror", "linear", "radial"]


def _finite_vector(
    value: list[float] | None,
    *,
    length: int,
    positive: bool,
    field_name: str,
) -> list[float] | None:
    if value is None:
        return None
    if len(value) != length:
        raise ValueError(f"{field_name} must contain exactly {length} numbers")
    normalized = [float(component) for component in value]
    if not all(math.isfinite(component) for component in normalized):
        raise ValueError(f"{field_name} must contain only finite numbers")
    if positive and not all(component > 0 for component in normalized):
        raise ValueError(f"{field_name} must contain only positive numbers")
    return normalized


class HierarchicalDimensions(BaseModel):
    """Resolved or relative full extents in local +X/+Y/+Z axis order."""

    size: list[float] | None = None
    relative_to: str | None = None
    ratio: list[float] | None = None
    minimum: list[float] | None = None
    maximum: list[float] | None = None

    model_config = {"extra": "allow"}

    @field_validator("size", "ratio", "minimum", "maximum")
    @classmethod
    def vectors_must_be_positive_and_finite(
        cls,
        value: list[float] | None,
        info,
    ) -> list[float] | None:
        return _finite_vector(
            value,
            length=3,
            positive=True,
            field_name=info.field_name,
        )


class HierarchicalAttachment(BaseModel):
    parent_id: str
    anchor: AttachmentAnchor
    contact_required: bool = True
    offset: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])

    model_config = {"extra": "allow"}

    @field_validator("offset")
    @classmethod
    def offset_must_be_finite(cls, value: list[float]) -> list[float]:
        normalized = _finite_vector(
            value,
            length=3,
            positive=False,
            field_name="offset",
        )
        return normalized or [0.0, 0.0, 0.0]


class HierarchicalOrientation(BaseModel):
    forward: SemanticDirection
    up: SemanticDirection

    model_config = {"extra": "allow"}


class HierarchicalRepetition(BaseModel):
    mode: RepetitionMode = "none"
    count: int = Field(default=1, ge=1)
    axis: SemanticDirection | None = None
    spacing: float | None = Field(default=None, gt=0)
    instance_role: str | None = None

    model_config = {"extra": "allow"}

    @field_validator("spacing")
    @classmethod
    def spacing_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("spacing must be finite")
        return value


class HierarchicalPart(BaseModel):
    id: str
    name: str
    role: str
    requirement: PartRequirement = "required"
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    shape_family: str | None = None
    geometry_strategy: str | None = None
    dimensions: HierarchicalDimensions
    attachment: HierarchicalAttachment | None = None
    orientation: HierarchicalOrientation
    repetition: HierarchicalRepetition = Field(default_factory=HierarchicalRepetition)
    material: str | dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list)
    construction_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("id")
    @classmethod
    def id_must_be_stable_snake_case(cls, value: str) -> str:
        if not SEMANTIC_PART_ID_PATTERN.fullmatch(value):
            raise ValueError("part id must be stable snake_case")
        return value

    @field_validator("name", "role")
    @classmethod
    def semantic_text_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("semantic part name and role must not be empty")
        return value.strip()


class HierarchicalConstraint(BaseModel):
    id: str
    type: str
    targets: list[str] = Field(min_length=1)
    required: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class HierarchicalAssetIntent(BaseModel):
    schema_version: Literal["1.0"] = HIERARCHICAL_ASSET_INTENT_SCHEMA_VERSION
    object_family: str
    root_part_id: str
    required_roles: list[str] = Field(min_length=1)
    parts: list[HierarchicalPart] = Field(min_length=1)
    constraints: list[HierarchicalConstraint] = Field(default_factory=list)
    construction_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("object_family")
    @classmethod
    def object_family_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("object_family must not be empty")
        return value.strip()

    @field_validator("root_part_id")
    @classmethod
    def root_part_id_must_be_stable_snake_case(cls, value: str) -> str:
        if not SEMANTIC_PART_ID_PATTERN.fullmatch(value):
            raise ValueError("root_part_id must be stable snake_case")
        return value

    @field_validator("required_roles")
    @classmethod
    def required_roles_must_be_unique_and_nonempty(cls, value: list[str]) -> list[str]:
        normalized = [role.strip() for role in value]
        if any(not role for role in normalized):
            raise ValueError("required_roles must not contain empty values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("required_roles must be unique")
        return normalized


class HierarchicalIntentDiagnostic(BaseModel):
    stage: Literal[
        "contract",
        "semantic_completeness",
        "hierarchy",
        "proportions",
        "attachments",
        "orientation",
        "object_family",
    ]
    code: str
    message: str
    path: str | None = None
    part_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HierarchicalIntentValidationResult(BaseModel):
    valid: bool
    outcome: Literal["valid", "invalid", "needs_repair"]
    schema_version: str | None = None
    intent: HierarchicalAssetIntent | None = None
    diagnostics: list[HierarchicalIntentDiagnostic] = Field(default_factory=list)
