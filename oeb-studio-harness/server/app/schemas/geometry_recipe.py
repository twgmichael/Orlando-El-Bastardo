from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.conversation import PrimitiveInstance


class GeometryRecipeDiagnostic(BaseModel):
    code: str
    message: str
    recipe_id: str | None = None
    part_id: str | None = None
    path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResolvedRecipePart(BaseModel):
    part_id: str
    recipe_id: str
    executor: str
    dimensions: list[float]
    centers: list[list[float]]
    primitive_ids: list[str] = Field(default_factory=list)


class GeometryRecipeCompileResult(BaseModel):
    valid: bool
    outcome: Literal["compiled", "needs_repair", "unsupported"]
    compiler_version: str = "1.0"
    primitives: list[PrimitiveInstance] = Field(default_factory=list)
    resolved_parts: list[ResolvedRecipePart] = Field(default_factory=list)
    used_recipes: list[str] = Field(default_factory=list)
    used_executors: list[str] = Field(default_factory=list)
    diagnostics: list[GeometryRecipeDiagnostic] = Field(default_factory=list)
