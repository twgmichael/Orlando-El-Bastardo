from __future__ import annotations

import math

from app.schemas.geometry_recipe import (
    GeometryInspectionFinding,
    GeometryInspectionResult,
    GeometryRecipeCompileResult,
)
from app.schemas.hierarchical_asset_intent import HierarchicalAssetIntent


STANDARD_REVIEW_VIEWS = [
    "top",
    "bottom",
    "left",
    "right",
    "front",
    "rear",
    "action",
]
_ANCHOR_AXIS = {
    "top_center": (2, 1.0),
    "bottom_center": (2, -1.0),
    "front_center": (0, 1.0),
    "rear_center": (0, -1.0),
    "left_side": (1, -1.0),
    "right_side": (1, 1.0),
}


def _inside(
    child_center: list[float],
    child_dimensions: list[float],
    parent_center: list[float],
    parent_dimensions: list[float],
    tolerance: float = 1e-5,
) -> bool:
    return all(
        child_center[axis] - child_dimensions[axis] / 2.0
        >= parent_center[axis] - parent_dimensions[axis] / 2.0 - tolerance
        and child_center[axis] + child_dimensions[axis] / 2.0
        <= parent_center[axis] + parent_dimensions[axis] / 2.0 + tolerance
        for axis in range(3)
    )


def _touches_anchor_axis(
    child_center: list[float],
    child_dimensions: list[float],
    parent_center: list[float],
    parent_dimensions: list[float],
    axis: int,
    sign: float,
    tolerance: float = 1e-4,
) -> bool:
    child_surface = child_center[axis] - sign * child_dimensions[axis] / 2.0
    parent_surface = parent_center[axis] + sign * parent_dimensions[axis] / 2.0
    return abs(child_surface - parent_surface) <= tolerance


def _aabb_overlap(
    first_center: list[float],
    first_dimensions: list[float],
    second_center: list[float],
    second_dimensions: list[float],
    tolerance: float = 1e-5,
) -> bool:
    return all(
        min(
            first_center[axis] + first_dimensions[axis] / 2.0,
            second_center[axis] + second_dimensions[axis] / 2.0,
        )
        - max(
            first_center[axis] - first_dimensions[axis] / 2.0,
            second_center[axis] - second_dimensions[axis] / 2.0,
        )
        > tolerance
        for axis in range(3)
    )


def _resolved_instances_overlap(first, second) -> bool:
    return any(
        _aabb_overlap(
            first_center,
            first.dimensions,
            second_center,
            second.dimensions,
        )
        for first_center in first.centers
        for second_center in second.centers
    )


def inspect_hierarchical_geometry(
    intent: HierarchicalAssetIntent,
    compiled: GeometryRecipeCompileResult,
) -> GeometryInspectionResult:
    findings: list[GeometryInspectionFinding] = []
    parts = {part.id: part for part in intent.parts}
    resolved = {part.part_id: part for part in compiled.resolved_parts}

    for part in intent.parts:
        resolved_part = resolved.get(part.id)
        if resolved_part is None:
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="required_part_not_resolved",
                message="A semantic part did not resolve through the geometry compiler.",
                part_id=part.id,
            ))
            continue
        if (
            part.requirement == "required"
            and part.geometry_strategy != "group"
            and not resolved_part.primitive_ids
        ):
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="required_part_has_no_geometry",
                message="A required semantic part produced no geometry.",
                part_id=part.id,
            ))
        if not all(
            math.isfinite(value) and value > 0
            for value in resolved_part.dimensions
        ):
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="resolved_dimensions_invalid",
                message="Resolved dimensions must be positive and finite.",
                part_id=part.id,
                details={"dimensions": resolved_part.dimensions},
            ))
        if part.parent_id is None or part.attachment is None:
            continue
        parent = resolved.get(part.parent_id)
        if parent is None:
            continue
        if part.attachment.anchor == "inside":
            if not all(
                any(
                    _inside(
                        child_center,
                        resolved_part.dimensions,
                        parent_center,
                        parent.dimensions,
                    )
                    for parent_center in parent.centers
                )
                for child_center in resolved_part.centers
            ):
                findings.append(GeometryInspectionFinding(
                    severity="error",
                    code="contained_part_outside_parent",
                    message="An inside-anchored part extends beyond its parent envelope.",
                    part_id=part.id,
                    related_part_id=part.parent_id,
                ))
        anchor_axis = _ANCHOR_AXIS.get(part.attachment.anchor)
        if part.attachment.contact_required and anchor_axis is not None:
            axis, sign = anchor_axis
            if not all(
                any(
                    _touches_anchor_axis(
                        child_center,
                        resolved_part.dimensions,
                        parent_center,
                        parent.dimensions,
                        axis,
                        sign,
                    )
                    for parent_center in parent.centers
                )
                for child_center in resolved_part.centers
            ):
                findings.append(GeometryInspectionFinding(
                    severity="error",
                    code="attachment_contact_missing",
                    message="A contact-required part does not touch its declared anchor.",
                    part_id=part.id,
                    related_part_id=part.parent_id,
                    details={"anchor": part.attachment.anchor},
                ))

    for part in intent.parts:
        if part.repetition.mode not in {"mirror", "linear", "radial"}:
            continue
        resolved_part = resolved.get(part.id)
        parent = resolved.get(part.parent_id) if part.parent_id else None
        if resolved_part is None:
            continue
        parent_instances = len(parent.centers) if parent is not None else 1
        minimum_instances = part.repetition.count * parent_instances
        if len(resolved_part.centers) < minimum_instances:
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="repetition_instances_missing",
                message="Compiled repetition produced fewer instances than declared.",
                part_id=part.id,
                details={
                    "expected_at_least": minimum_instances,
                    "actual": len(resolved_part.centers),
                },
            ))
        if part.repetition.mode == "mirror" and part.repetition.axis:
            axis = {
                "front": 0,
                "rear": 0,
                "left": 1,
                "right": 1,
                "up": 2,
                "down": 2,
            }[part.repetition.axis]
            values = [center[axis] for center in resolved_part.centers]
            if not (min(values) < max(values)):
                findings.append(GeometryInspectionFinding(
                    severity="error",
                    code="mirrored_instances_not_separated",
                    message="Mirrored instances are not separated across their axis.",
                    part_id=part.id,
                ))

    for constraint in intent.constraints:
        if not constraint.required or len(constraint.targets) < 2:
            continue
        constraint_type = constraint.type.strip().lower()
        target_parts = [
            resolved.get(target)
            for target in constraint.targets
        ]
        if any(target is None for target in target_parts):
            continue
        if constraint_type in {"no_overlap", "non_intersection"}:
            for first_index, first in enumerate(target_parts[:-1]):
                for second in target_parts[first_index + 1:]:
                    if _resolved_instances_overlap(first, second):
                        findings.append(GeometryInspectionFinding(
                            severity="error",
                            code="constraint_overlap_detected",
                            message=(
                                "Parts governed by a no-overlap constraint "
                                "intersect."
                            ),
                            part_id=first.part_id,
                            related_part_id=second.part_id,
                            details={"constraint_id": constraint.id},
                        ))
        if constraint_type in {"contained", "containment"}:
            child, parent = target_parts[0], target_parts[1]
            if not all(
                any(
                    _inside(
                        child_center,
                        child.dimensions,
                        parent_center,
                        parent.dimensions,
                    )
                    for parent_center in parent.centers
                )
                for child_center in child.centers
            ):
                findings.append(GeometryInspectionFinding(
                    severity="error",
                    code="constraint_containment_failed",
                    message=(
                        "A required containment constraint was not satisfied."
                    ),
                    part_id=child.part_id,
                    related_part_id=parent.part_id,
                    details={"constraint_id": constraint.id},
                ))

    primitive_ids = [primitive.id for primitive in compiled.primitives]
    if len(primitive_ids) != len(set(primitive_ids)):
        findings.append(GeometryInspectionFinding(
            severity="error",
            code="inspection_duplicate_primitive_ids",
            message="Compiled geometry contains duplicate primitive ids.",
        ))
    for primitive in compiled.primitives:
        values = [
            *primitive.transform.location,
            *primitive.transform.rotation,
            *primitive.transform.scale,
        ]
        if not all(math.isfinite(value) for value in values):
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="inspection_non_finite_transform",
                message="Compiled geometry contains a non-finite transform.",
                part_id=str(primitive.params.get("semantic_part_id") or "") or None,
                details={"primitive_id": primitive.id},
            ))
        if any(value <= 0 for value in primitive.transform.scale):
            findings.append(GeometryInspectionFinding(
                severity="error",
                code="inspection_non_positive_scale",
                message="Compiled geometry contains a non-positive scale.",
                part_id=str(primitive.params.get("semantic_part_id") or "") or None,
                details={"primitive_id": primitive.id},
            ))

    root = resolved.get(intent.root_part_id)
    if root is not None:
        dimensions = root.dimensions
        findings.extend([
            GeometryInspectionFinding(
                severity="evidence",
                code="orthographic_silhouette_bounds",
                message="Resolved root bounds are available for deterministic review.",
                view=view,
                details={
                    "root_dimensions": dimensions,
                    "visible_primitive_count": len(compiled.primitives),
                },
            )
            for view in STANDARD_REVIEW_VIEWS
        ])
    return GeometryInspectionResult(
        valid=not any(finding.severity == "error" for finding in findings),
        findings=findings,
        checked_views=STANDARD_REVIEW_VIEWS,
    )
