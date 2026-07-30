from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.hierarchical_asset_intent import (
    HierarchicalAssetIntent,
    HierarchicalIntentDiagnostic,
    HierarchicalIntentValidationResult,
)


_DIRECTION_AXIS = {
    "front": (1, 0, 0),
    "rear": (-1, 0, 0),
    "left": (0, -1, 0),
    "right": (0, 1, 0),
    "up": (0, 0, 1),
    "down": (0, 0, -1),
}


def _diagnostic(
    stage: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    part_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> HierarchicalIntentDiagnostic:
    return HierarchicalIntentDiagnostic(
        stage=stage,
        code=code,
        message=message,
        path=path,
        part_id=part_id,
        details=details or {},
    )


def _contract_diagnostics(exc: ValidationError) -> list[HierarchicalIntentDiagnostic]:
    diagnostics = []
    for error in exc.errors(include_url=False):
        path = "$.hierarchical_asset_intent"
        if error.get("loc"):
            path += "".join(
                f"[{segment}]" if isinstance(segment, int) else f".{segment}"
                for segment in error["loc"]
            )
        diagnostics.append(_diagnostic(
            "contract",
            "hierarchical_contract_invalid",
            str(error.get("msg") or "Invalid hierarchical asset intent."),
            path=path,
            details={"type": error.get("type")},
        ))
    return diagnostics


def validate_hierarchical_asset_intent(
    value: dict[str, Any],
) -> HierarchicalIntentValidationResult:
    """Validate schema plus deterministic internal hierarchy invariants."""

    try:
        intent = HierarchicalAssetIntent.model_validate(value)
    except ValidationError as exc:
        return HierarchicalIntentValidationResult(
            valid=False,
            outcome="invalid",
            schema_version=str(value.get("schema_version")) if value.get("schema_version") else None,
            diagnostics=_contract_diagnostics(exc),
        )

    diagnostics: list[HierarchicalIntentDiagnostic] = []
    part_by_id = {}
    for index, part in enumerate(intent.parts):
        if part.id in part_by_id:
            diagnostics.append(_diagnostic(
                "hierarchy",
                "duplicate_hierarchical_part_id",
                f"Part id '{part.id}' is duplicated.",
                path=f"$.hierarchical_asset_intent.parts[{index}].id",
                part_id=part.id,
            ))
        else:
            part_by_id[part.id] = part

    root = part_by_id.get(intent.root_part_id)
    if root is None:
        diagnostics.append(_diagnostic(
            "hierarchy",
            "hierarchy_root_missing",
            f"Root part '{intent.root_part_id}' does not exist.",
            path="$.hierarchical_asset_intent.root_part_id",
        ))
    elif root.parent_id is not None:
        diagnostics.append(_diagnostic(
            "hierarchy",
            "hierarchy_root_has_parent",
            "The root part cannot have a parent.",
            path=f"$.hierarchical_asset_intent.parts[{intent.parts.index(root)}].parent_id",
            part_id=root.id,
        ))

    roots = [part.id for part in intent.parts if part.parent_id is None]
    if len(roots) != 1 or (roots and roots[0] != intent.root_part_id):
        diagnostics.append(_diagnostic(
            "hierarchy",
            "hierarchy_root_not_unique",
            "A hierarchical asset must contain exactly one declared root.",
            path="$.hierarchical_asset_intent.parts",
            details={"root_ids": roots, "declared_root_id": intent.root_part_id},
        ))

    role_ids: dict[str, list[str]] = {}
    for part in intent.parts:
        role_ids.setdefault(part.role, []).append(part.id)
    missing_roles = [role for role in intent.required_roles if role not in role_ids]
    if missing_roles:
        diagnostics.append(_diagnostic(
            "semantic_completeness",
            "required_roles_missing",
            "The hierarchy does not cover every declared required role.",
            path="$.hierarchical_asset_intent.required_roles",
            details={"missing_roles": missing_roles},
        ))

    for index, part in enumerate(intent.parts):
        base_path = f"$.hierarchical_asset_intent.parts[{index}]"
        dimensions = part.dimensions
        if dimensions.minimum is not None and dimensions.maximum is not None:
            invalid_axes = [
                axis
                for axis, (minimum, maximum) in enumerate(
                    zip(dimensions.minimum, dimensions.maximum)
                )
                if minimum > maximum
            ]
            if invalid_axes:
                diagnostics.append(_diagnostic(
                    "proportions",
                    "dimension_bounds_inverted",
                    "Minimum dimensions cannot exceed maximum dimensions.",
                    path=f"{base_path}.dimensions",
                    part_id=part.id,
                    details={"axis_indices": invalid_axes},
                ))
        if dimensions.size is not None:
            below_minimum = (
                dimensions.minimum is not None
                and any(
                    size < minimum
                    for size, minimum in zip(dimensions.size, dimensions.minimum)
                )
            )
            above_maximum = (
                dimensions.maximum is not None
                and any(
                    size > maximum
                    for size, maximum in zip(dimensions.size, dimensions.maximum)
                )
            )
            if below_minimum or above_maximum:
                diagnostics.append(_diagnostic(
                    "proportions",
                    "dimension_size_out_of_bounds",
                    "Resolved part size must remain within its declared bounds.",
                    path=f"{base_path}.dimensions.size",
                    part_id=part.id,
                ))
        if part.id == intent.root_part_id:
            if part.dimensions.size is None:
                diagnostics.append(_diagnostic(
                    "proportions",
                    "root_dimensions_missing",
                    "The root part requires an absolute positive size.",
                    path=f"{base_path}.dimensions.size",
                    part_id=part.id,
                ))
            if part.attachment is not None:
                diagnostics.append(_diagnostic(
                    "attachments",
                    "root_attachment_forbidden",
                    "The root part cannot attach to another part.",
                    path=f"{base_path}.attachment",
                    part_id=part.id,
                ))
        else:
            if not part.parent_id or part.parent_id not in part_by_id:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_parent_missing",
                    f"Part '{part.id}' references a missing parent.",
                    path=f"{base_path}.parent_id",
                    part_id=part.id,
                    details={"parent_id": part.parent_id},
                ))
            if part.dimensions.size is None and part.dimensions.ratio is None:
                diagnostics.append(_diagnostic(
                    "proportions",
                    "part_dimensions_unresolved",
                    "A non-root part requires an absolute size or a parent-relative ratio.",
                    path=f"{base_path}.dimensions",
                    part_id=part.id,
                ))
            if part.dimensions.ratio is not None:
                relative_to = part.dimensions.relative_to or part.parent_id
                if relative_to != part.parent_id:
                    diagnostics.append(_diagnostic(
                        "proportions",
                        "dimension_reference_not_parent",
                        "Parent-relative dimensions must reference the owning parent.",
                        path=f"{base_path}.dimensions.relative_to",
                        part_id=part.id,
                        details={
                            "relative_to": relative_to,
                            "parent_id": part.parent_id,
                        },
                    ))
            if part.attachment is None:
                diagnostics.append(_diagnostic(
                    "attachments",
                    "attachment_missing",
                    "Every non-root part requires a semantic attachment.",
                    path=f"{base_path}.attachment",
                    part_id=part.id,
                ))
            elif part.attachment.parent_id != part.parent_id:
                diagnostics.append(_diagnostic(
                    "attachments",
                    "attachment_parent_mismatch",
                    "Attachment parent must match hierarchy ownership.",
                    path=f"{base_path}.attachment.parent_id",
                    part_id=part.id,
                    details={
                        "attachment_parent_id": part.attachment.parent_id,
                        "parent_id": part.parent_id,
                    },
                ))

        if not part.shape_family:
            diagnostics.append(_diagnostic(
                "semantic_completeness",
                "shape_family_missing",
                "Every planned part requires a semantic shape family.",
                path=f"{base_path}.shape_family",
                part_id=part.id,
            ))
        if not part.geometry_strategy:
            diagnostics.append(_diagnostic(
                "semantic_completeness",
                "geometry_strategy_missing",
                "Every planned part requires a declared geometry strategy.",
                path=f"{base_path}.geometry_strategy",
                part_id=part.id,
            ))

        forward = _DIRECTION_AXIS[part.orientation.forward]
        up = _DIRECTION_AXIS[part.orientation.up]
        if sum(a * b for a, b in zip(forward, up)) != 0:
            diagnostics.append(_diagnostic(
                "orientation",
                "orientation_axes_not_orthogonal",
                "Forward and up directions must be perpendicular.",
                path=f"{base_path}.orientation",
                part_id=part.id,
            ))

        repetition = part.repetition
        if repetition.mode == "none" and repetition.count != 1:
            diagnostics.append(_diagnostic(
                "semantic_completeness",
                "repetition_none_count_invalid",
                "A non-repeated part must have count 1.",
                path=f"{base_path}.repetition.count",
                part_id=part.id,
            ))
        if repetition.mode != "none":
            if repetition.count < 2:
                diagnostics.append(_diagnostic(
                    "semantic_completeness",
                    "repetition_count_invalid",
                    "A repeated part requires at least two instances.",
                    path=f"{base_path}.repetition.count",
                    part_id=part.id,
                ))
            if repetition.axis is None:
                diagnostics.append(_diagnostic(
                    "orientation",
                    "repetition_axis_missing",
                    "A repeated part requires a semantic repetition axis.",
                    path=f"{base_path}.repetition.axis",
                    part_id=part.id,
                ))
            if repetition.mode == "mirror" and repetition.count != 2:
                diagnostics.append(_diagnostic(
                    "semantic_completeness",
                    "mirror_count_invalid",
                    "Mirror repetition creates exactly two instances.",
                    path=f"{base_path}.repetition.count",
                    part_id=part.id,
                ))

        for child_id in part.children:
            if child_id == part.id:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_self_reference",
                    "A part cannot own itself.",
                    path=f"{base_path}.children",
                    part_id=part.id,
                ))
                continue
            child = part_by_id.get(child_id)
            if child is None:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_child_missing",
                    f"Child part '{child_id}' does not exist.",
                    path=f"{base_path}.children",
                    part_id=part.id,
                    details={"child_id": child_id},
                ))
            elif child.parent_id != part.id:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_parent_child_mismatch",
                    "Parent children and child parent_id must agree.",
                    path=f"{base_path}.children",
                    part_id=part.id,
                    details={
                        "child_id": child_id,
                        "child_parent_id": child.parent_id,
                    },
                ))
        if len(part.children) != len(set(part.children)):
            diagnostics.append(_diagnostic(
                "hierarchy",
                "hierarchy_child_duplicated",
                "A parent cannot list the same child more than once.",
                path=f"{base_path}.children",
                part_id=part.id,
            ))

    for part in intent.parts:
        if part.parent_id and part.parent_id in part_by_id:
            parent = part_by_id[part.parent_id]
            if part.id not in parent.children:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_child_not_owned",
                    "A child's parent must list the child in its owned children.",
                    part_id=part.id,
                    details={"parent_id": part.parent_id},
                ))

    if root is not None:
        visited: set[str] = set()
        active: set[str] = set()

        def walk(part_id: str) -> None:
            if part_id in active:
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "hierarchy_cycle_detected",
                    "The part hierarchy contains a cycle.",
                    part_id=part_id,
                ))
                return
            if part_id in visited or part_id not in part_by_id:
                return
            active.add(part_id)
            for child_id in part_by_id[part_id].children:
                walk(child_id)
            active.remove(part_id)
            visited.add(part_id)

        walk(root.id)
        unreachable = sorted(set(part_by_id) - visited)
        if unreachable:
            diagnostics.append(_diagnostic(
                "hierarchy",
                "hierarchy_disconnected",
                "Every part must be reachable from the declared root.",
                path="$.hierarchical_asset_intent.parts",
                details={"unreachable_part_ids": unreachable},
            ))

    seen_constraint_ids: set[str] = set()
    for index, constraint in enumerate(intent.constraints):
        if constraint.id in seen_constraint_ids:
            diagnostics.append(_diagnostic(
                "hierarchy",
                "constraint_id_duplicated",
                "Hierarchy constraint ids must be unique.",
                path=f"$.hierarchical_asset_intent.constraints[{index}].id",
                details={"constraint_id": constraint.id},
            ))
        seen_constraint_ids.add(constraint.id)
        unknown_targets = [target for target in constraint.targets if target not in part_by_id]
        if unknown_targets:
            diagnostics.append(_diagnostic(
                "hierarchy",
                "constraint_target_missing",
                "A hierarchy constraint references an unknown part.",
                path=f"$.hierarchical_asset_intent.constraints[{index}].targets",
                details={"unknown_target_ids": unknown_targets},
            ))

    return HierarchicalIntentValidationResult(
        valid=not diagnostics,
        outcome="valid" if not diagnostics else "needs_repair",
        schema_version=intent.schema_version,
        intent=intent,
        diagnostics=diagnostics,
    )
