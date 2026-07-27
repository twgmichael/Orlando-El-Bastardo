from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


GraphOperation = Literal[
    "add",
    "remove",
    "replace",
    "move",
    "rotate",
    "attach",
    "detach",
    "recolor",
    "resize",
    "group",
    "ungroup",
    "undo",
]

CompilerOutcome = Literal[
    "compiled",
    "needs_repair",
    "needs_clarification",
    "unsupported",
    "invalid",
]


class SemanticTransform(BaseModel):
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])

    @field_validator("location", "rotation", "scale")
    @classmethod
    def vector_must_have_three_numbers(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("transform vectors must contain exactly three numbers")
        return [float(component) for component in value]


class GeometryDefinition(BaseModel):
    type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    operations: list[dict[str, Any]] = Field(default_factory=list)


class SemanticPart(BaseModel):
    id: str
    name: str | None = None
    role: str | None = None
    geometry: GeometryDefinition
    transform: SemanticTransform = Field(default_factory=SemanticTransform)
    material: str | dict[str, Any] | None = None
    construction_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    id: str
    type: str
    subject: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class GraphAttachment(BaseModel):
    id: str
    child: str
    parent: str
    socket: str | None = None
    preserve_world_transform: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class GraphConstraint(BaseModel):
    id: str
    type: str
    targets: list[str]
    required: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class GraphGroup(BaseModel):
    id: str
    members: list[str]
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticAssetGraph(BaseModel):
    schema_version: str = "1.0"
    asset_id: str
    revision: int = Field(ge=0)
    parts: list[SemanticPart] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)
    attachments: list[GraphAttachment] = Field(default_factory=list)
    constraints: list[GraphConstraint] = Field(default_factory=list)
    groups: list[GraphGroup] = Field(default_factory=list)
    construction_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphOperationRequest(BaseModel):
    operation: str
    base_revision: int = Field(ge=0)
    intent: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    preserve: list[str] = Field(default_factory=list)

    @field_validator("operation")
    @classmethod
    def operation_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operation must not be empty")
        return value.strip().lower()


class GraphChange(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class GraphDiff(BaseModel):
    operation: str
    selected_targets: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)
    changes: list[GraphChange] = Field(default_factory=list)


class GraphDiagnostic(BaseModel):
    stage: str
    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GraphOperationResult(BaseModel):
    outcome: CompilerOutcome
    operation: str
    base_revision: int
    proposed_revision: int | None = None
    selected_targets: list[str] = Field(default_factory=list)
    graph_before: SemanticAssetGraph | None = None
    graph_after: SemanticAssetGraph | None = None
    diff: GraphDiff | None = None
    diagnostics: list[GraphDiagnostic] = Field(default_factory=list)


class SemanticAssetGraphResponse(BaseModel):
    graph: SemanticAssetGraph
    summary: dict[str, Any]
    part_catalog: list[dict[str, Any]]
    constraints: list[GraphConstraint]

