from __future__ import annotations

import copy
import math
import re
from typing import Any

from app.schemas.semantic_asset_graph import (
    GraphChange,
    GraphDiagnostic,
    GraphDiff,
    GraphOperationRequest,
    GraphOperationResult,
    SemanticAssetGraph,
)


OPERATION_ALIASES = {
    "add_part": "add",
    "create_part": "add",
    "append_part": "add",
    "delete": "remove",
    "remove_part": "remove",
    "delete_part": "remove",
    "replace_with": "replace",
    "set_type": "replace",
    "change_type": "replace",
    "translate": "move",
    "adjust_position": "move",
    "move_to": "move",
    "set_location": "move",
    "position": "move",
    "set_rotation": "rotate",
    "rotate_relative": "rotate",
    "adjust_rotation": "rotate",
    "set_material": "recolor",
    "material": "recolor",
    "change_color": "recolor",
    "color": "recolor",
    "set_scale": "resize",
    "scale": "resize",
    "proportional_scale": "resize",
    "scale_relative": "resize",
    "scale_uniform": "resize",
    "scale_axis": "resize",
    "resize_axis": "resize",
    "add_attachment": "attach",
    "remove_attachment": "detach",
    "align_centers": "move",
    "align_objects": "move",
    "center_objects_on_axis": "move",
    "center_group": "move",
    "center_objects": "move",
    "align_center": "move",
    "set_geometry_modifier": "replace",
    "geometry_modifier": "replace",
    "set_shape_modifier": "replace",
    "shape_modifier": "replace",
    "cut": "replace",
    "hemisphere": "replace",
    "half": "replace",
    "set_thickness": "resize",
    "adjust_thickness": "resize",
}

SUPPORTED_OPERATIONS = {
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
}

PRIMITIVE_ALIASES = {
    "cube": "box",
    "cuboid": "box",
    "rectangular_prism": "box",
    "tube": "cylinder",
    "ball": "sphere",
    "triangle": "wedge",
    "triangular_prism": "wedge",
}

INTENT_OPERATIONS = {
    "add": {"add", "create", "append", "insert", "put"},
    "remove": {"remove", "delete", "erase"},
    "replace": {"replace", "swap", "substitute"},
    "move": {"move", "translate", "position"},
    "rotate": {"rotate", "turn", "spin"},
    "attach": {"attach", "connect", "mount", "parent"},
    "detach": {"detach", "disconnect", "unmount", "unparent"},
    "recolor": {"recolor", "color", "paint"},
    "resize": {"resize", "scale", "enlarge", "shrink"},
    "group": {"group"},
    "ungroup": {"ungroup"},
    "undo": {"undo", "revert"},
}


def normalize_operation(value: str) -> str:
    operation = value.strip().lower()
    return OPERATION_ALIASES.get(operation, operation)


def _vector(value: Any, default: list[float]) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        return default.copy()
    if not all(isinstance(component, int | float) and math.isfinite(component) for component in value):
        return default.copy()
    return [float(component) for component in value]


def _slug(value: Any, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug or fallback


def _part_id(entry: dict[str, Any], index: int) -> str:
    return _slug(entry.get("id") or entry.get("label") or entry.get("name"), f"part_{index + 1}")


def _repair_graph_data_references(graph_data: dict[str, Any]) -> dict[str, Any]:
    """Remove references to geometry that never compiled, recording every repair."""
    repairs: list[dict[str, Any]] = []
    known = {
        str(part.get("id"))
        for part in graph_data.get("parts", [])
        if isinstance(part, dict) and part.get("id")
    }

    def retain(collection: str, predicate) -> None:
        entries = graph_data.get(collection)
        if not isinstance(entries, list):
            graph_data[collection] = []
            return
        kept = []
        for entry in entries:
            if isinstance(entry, dict) and predicate(entry):
                kept.append(entry)
            else:
                repairs.append({
                    "code": "dropped_dangling_graph_reference",
                    "collection": collection,
                    "id": entry.get("id") if isinstance(entry, dict) else None,
                })
        graph_data[collection] = kept

    retain("relationships", lambda entry: entry.get("subject") in known and entry.get("target") in known)
    retain("attachments", lambda entry: entry.get("child") in known and entry.get("parent") in known)
    retain(
        "constraints",
        lambda entry: isinstance(entry.get("targets"), list)
        and all(target in known for target in entry["targets"]),
    )
    groups = graph_data.get("groups")
    if isinstance(groups, list):
        repaired_groups = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            original = list(group.get("members") or [])
            group["members"] = [member for member in original if member in known]
            if group["members"]:
                repaired_groups.append(group)
            if group["members"] != original:
                repairs.append({
                    "code": "dropped_dangling_group_member",
                    "collection": "groups",
                    "id": group.get("id"),
                })
        graph_data["groups"] = repaired_groups
    else:
        graph_data["groups"] = []
    if repairs:
        metadata = graph_data.setdefault("metadata", {})
        existing = metadata.get("normalization_diagnostics")
        metadata["normalization_diagnostics"] = [
            *(existing if isinstance(existing, list) else []),
            *repairs,
        ]
    return graph_data


def graph_from_state(
    state: dict[str, Any],
    *,
    asset_id: str | None = None,
    revision: int | None = None,
) -> SemanticAssetGraph:
    existing = state.get("semantic_graph")
    if isinstance(existing, dict):
        graph_data = copy.deepcopy(existing)
        if asset_id:
            graph_data["asset_id"] = asset_id
        if revision is not None:
            graph_data["revision"] = revision
        return SemanticAssetGraph.model_validate(_repair_graph_data_references(graph_data))

    primitives = state.get("primitives")
    parts = []
    if isinstance(primitives, list):
        for index, primitive in enumerate(primitives):
            if not isinstance(primitive, dict):
                continue
            transform = primitive.get("transform") if isinstance(primitive.get("transform"), dict) else {}
            parameters = copy.deepcopy(primitive.get("params")) if isinstance(primitive.get("params"), dict) else {}
            construction_element = primitive.get("construction_element")
            if isinstance(construction_element, dict):
                parameters["construction_element"] = copy.deepcopy(construction_element)
            parts.append(
                {
                    "id": _part_id(primitive, index),
                    "name": primitive.get("label") or primitive.get("name"),
                    "role": primitive.get("role"),
                    "geometry": {
                        "type": PRIMITIVE_ALIASES.get(
                            str(primitive.get("type") or "box").lower(),
                            str(primitive.get("type") or "box").lower(),
                        ),
                        "parameters": parameters,
                    },
                    "transform": {
                        "location": _vector(transform.get("location"), [0.0, 0.0, 0.0]),
                        "rotation": _vector(transform.get("rotation"), [0.0, 0.0, 0.0]),
                        "scale": _vector(transform.get("scale"), [1.0, 1.0, 1.0]),
                    },
                    "material": primitive.get("material"),
                    "metadata": {
                        key: copy.deepcopy(value)
                        for key, value in primitive.items()
                        if key not in {"id", "label", "name", "role", "type", "params", "transform", "material", "construction_element"}
                    },
                }
            )

    intent = state.get("asset_intent") if isinstance(state.get("asset_intent"), dict) else {}
    scene_plan = state.get("scene_plan") if isinstance(state.get("scene_plan"), dict) else {}
    raw_relationships = intent.get("relationships")
    if not isinstance(raw_relationships, list):
        raw_relationships = scene_plan.get("relationships")
    relationships = []
    attachments = []
    for index, item in enumerate(raw_relationships or []):
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "")
        target = str(item.get("target") or "")
        relation = str(item.get("relation") or item.get("type") or "related_to")
        if not subject or not target:
            continue
        if relation in {"attached_to", "mounted_on", "parented_to"}:
            attachments.append(
                {
                    "id": _slug(item.get("id"), f"attachment_{subject}_{target}_{index + 1}"),
                    "child": subject,
                    "parent": target,
                    "socket": item.get("socket"),
                    "parameters": {
                        key: copy.deepcopy(value)
                        for key, value in item.items()
                        if key not in {"id", "subject", "target", "relation", "type", "socket"}
                    },
                }
            )
        else:
            relationships.append(
                {
                    "id": _slug(item.get("id"), f"relationship_{subject}_{relation}_{target}_{index + 1}"),
                    "type": relation,
                    "subject": subject,
                    "target": target,
                    "parameters": {
                        key: copy.deepcopy(value)
                        for key, value in item.items()
                        if key not in {"id", "subject", "target", "relation", "type"}
                    },
                }
            )

    notes = intent.get("construction_notes")
    if isinstance(notes, str):
        notes = [notes]
    if not isinstance(notes, list):
        notes = []
    resolved_asset_id = asset_id or state.get("canonical_id") or state.get("asset_id") or "unnamed_asset"
    return SemanticAssetGraph.model_validate(
        _repair_graph_data_references({
            "asset_id": str(resolved_asset_id),
            "revision": revision if revision is not None else int(state.get("revision") or 0),
            "parts": parts,
            "relationships": relationships,
            "attachments": attachments,
            "constraints": copy.deepcopy(state.get("constraints") or []),
            "groups": copy.deepcopy(state.get("groups") or []),
            "construction_notes": [str(note) for note in notes],
            "metadata": {
                "name": state.get("name"),
                "kind": state.get("kind"),
                "style": state.get("style"),
                "legacy_projection": True,
            },
        })
    )


def graph_summary(graph: SemanticAssetGraph) -> dict[str, Any]:
    return {
        "asset_id": graph.asset_id,
        "revision": graph.revision,
        "part_count": len(graph.parts),
        "relationship_count": len(graph.relationships),
        "attachment_count": len(graph.attachments),
        "constraint_count": len(graph.constraints),
        "group_count": len(graph.groups),
    }


def part_catalog(graph: SemanticAssetGraph) -> list[dict[str, Any]]:
    return [
        {
            "id": part.id,
            "name": part.name,
            "role": part.role,
            "geometry_type": part.geometry.type,
            "material": part.material,
            "groups": [group.id for group in graph.groups if part.id in group.members],
        }
        for part in graph.parts
    ]


def validate_graph(graph: SemanticAssetGraph) -> list[GraphDiagnostic]:
    diagnostics: list[GraphDiagnostic] = []
    part_ids = [part.id for part in graph.parts]
    known = set(part_ids)
    if len(part_ids) != len(known):
        diagnostics.append(GraphDiagnostic(
            stage="validate",
            code="duplicate_part_id",
            message="Every semantic part must have a unique id.",
            path="parts",
        ))
    for index, part in enumerate(graph.parts):
        if any(component <= 0 for component in part.transform.scale):
            diagnostics.append(GraphDiagnostic(
                stage="validate",
                code="invalid_scale",
                message=f"Part {part.id} has a non-positive scale component.",
                path=f"parts.{index}.transform.scale",
            ))
        if not part.geometry.type.strip():
            diagnostics.append(GraphDiagnostic(
                stage="validate",
                code="missing_geometry_type",
                message=f"Part {part.id} has no geometry definition.",
                path=f"parts.{index}.geometry.type",
            ))
    for collection_name, entries, reference_fields in (
        ("relationships", graph.relationships, ("subject", "target")),
        ("attachments", graph.attachments, ("child", "parent")),
    ):
        for index, entry in enumerate(entries):
            for field in reference_fields:
                target = getattr(entry, field)
                if target not in known:
                    diagnostics.append(GraphDiagnostic(
                        stage="validate",
                        code="unknown_part_reference",
                        message=f"{collection_name[:-1].title()} {entry.id} references unknown part {target}.",
                        path=f"{collection_name}.{index}.{field}",
                    ))
    for index, constraint in enumerate(graph.constraints):
        missing = [target for target in constraint.targets if target not in known]
        if missing:
            diagnostics.append(GraphDiagnostic(
                stage="validate",
                code="unknown_constraint_target",
                message=f"Constraint {constraint.id} references unknown parts.",
                path=f"constraints.{index}.targets",
                details={"missing": missing},
            ))
    for index, group in enumerate(graph.groups):
        missing = [member for member in group.members if member not in known]
        if missing:
            diagnostics.append(GraphDiagnostic(
                stage="validate",
                code="unknown_group_member",
                message=f"Group {group.id} references unknown parts.",
                path=f"groups.{index}.members",
                details={"missing": missing},
            ))
    attachment_parent = {attachment.child: attachment.parent for attachment in graph.attachments}
    for child in attachment_parent:
        visited = {child}
        parent = attachment_parent.get(child)
        while parent is not None:
            if parent in visited:
                diagnostics.append(GraphDiagnostic(
                    stage="validate",
                    code="attachment_cycle",
                    message=f"Attachment hierarchy contains a cycle involving {parent}.",
                    path="attachments",
                ))
                break
            visited.add(parent)
            parent = attachment_parent.get(parent)
    return diagnostics


def _failure(
    outcome: str,
    operation: str,
    request: GraphOperationRequest,
    graph: SemanticAssetGraph | None,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> GraphOperationResult:
    return GraphOperationResult(
        outcome=outcome,
        operation=operation,
        base_revision=request.base_revision,
        selected_targets=request.target_ids,
        graph_before=graph,
        diagnostics=[
            GraphDiagnostic(
                stage="compile",
                code=code,
                message=message,
                details=details or {},
            )
        ],
    )


def _intent_operation(intent: str | None) -> str | None:
    if not intent:
        return None
    words = set(re.findall(r"[a-z]+", intent.lower()))
    for operation, verbs in INTENT_OPERATIONS.items():
        if words & verbs:
            return operation
    return None


def _diff(before: Any, after: Any, path: str = "") -> list[GraphChange]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            next_path = f"{path}.{key}" if path else key
            if key not in before:
                changes.append(GraphChange(path=next_path, after=after[key]))
            elif key not in after:
                changes.append(GraphChange(path=next_path, before=before[key]))
            else:
                changes.extend(_diff(before[key], after[key], next_path))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        if all(isinstance(item, dict) and item.get("id") for item in before + after):
            before_by_id = {str(item["id"]): item for item in before}
            after_by_id = {str(item["id"]): item for item in after}
            changes = []
            for item_id in sorted(set(before_by_id) | set(after_by_id)):
                next_path = f"{path}[{item_id}]"
                if item_id not in before_by_id:
                    changes.append(GraphChange(path=next_path, after=after_by_id[item_id]))
                elif item_id not in after_by_id:
                    changes.append(GraphChange(path=next_path, before=before_by_id[item_id]))
                else:
                    changes.extend(_diff(before_by_id[item_id], after_by_id[item_id], next_path))
            return changes
        return [GraphChange(path=path, before=before, after=after)]
    if before != after:
        return [GraphChange(path=path, before=before, after=after)]
    return []


def _targets(graph_data: dict[str, Any], request: GraphOperationRequest) -> list[dict[str, Any]]:
    target_ids = set(request.target_ids)
    if target_ids & {"asset", "whole_asset", "*"}:
        return graph_data["parts"]
    return [part for part in graph_data["parts"] if part["id"] in target_ids]


def _rotation_amount(parameters: dict[str, Any]) -> tuple[int | None, float | None]:
    axis = str(parameters.get("axis") or "").lower()
    view = str(parameters.get("view") or "").lower()
    axis_index = {
        "x": 0, "+x": 0, "-x": 0, "front": 0, "rear": 0, "back": 0,
        "y": 1, "+y": 1, "-y": 1, "left": 1, "right": 1,
        "z": 2, "+z": 2, "-z": 2, "top": 2, "bottom": 2,
    }.get(axis or view)
    value = parameters.get("radians")
    if value is None:
        value = parameters.get("degrees")
    if value is None:
        value = parameters.get("amount")
    if not isinstance(value, int | float):
        return axis_index, None
    amount = float(value)
    if parameters.get("degrees") is not None or abs(amount) > math.tau:
        amount = math.radians(amount)
    return axis_index, amount


def _vertical_half_extent(part: dict[str, Any]) -> float:
    geometry = part.get("geometry") if isinstance(part.get("geometry"), dict) else {}
    parameters = geometry.get("parameters") if isinstance(geometry.get("parameters"), dict) else {}
    scale = part.get("transform", {}).get("scale", [1.0, 1.0, 1.0])
    scale_z = abs(float(scale[2])) if isinstance(scale, list) and len(scale) == 3 else 1.0
    geometry_type = str(geometry.get("type") or "").lower()
    if geometry_type == "sphere":
        return abs(float(parameters.get("radius", 0.5))) * scale_z
    if geometry_type in {"cylinder", "cone"}:
        return abs(float(parameters.get("depth", 1.0))) * scale_z / 2.0
    return scale_z / 2.0


def _horizontal_diameter(part: dict[str, Any]) -> float:
    geometry = part.get("geometry") if isinstance(part.get("geometry"), dict) else {}
    parameters = geometry.get("parameters") if isinstance(geometry.get("parameters"), dict) else {}
    scale = part.get("transform", {}).get("scale", [1.0, 1.0, 1.0])
    scale_x = abs(float(scale[0])) if isinstance(scale, list) and len(scale) == 3 else 1.0
    scale_y = abs(float(scale[1])) if isinstance(scale, list) and len(scale) == 3 else 1.0
    geometry_type = str(geometry.get("type") or "").lower()
    if geometry_type == "sphere":
        return 2.0 * abs(float(parameters.get("radius", 0.5))) * max(scale_x, scale_y)
    if geometry_type in {"cylinder", "cone"}:
        default_radius = 0.35 if geometry_type == "cylinder" else 0.4
        return 2.0 * abs(float(parameters.get("radius", default_radius))) * max(scale_x, scale_y)
    return max(scale_x, scale_y)


def _upsert_spatial_relationship(
    graph_data: dict[str, Any],
    *,
    subject: str,
    relation: str,
    target: str,
) -> None:
    spatial_types = {
        "above", "below", "on_top_of", "under", "left_of", "right_of",
        "in_front_of", "behind", "aligned_with",
    }
    graph_data["relationships"] = [
        item
        for item in graph_data["relationships"]
        if not (item["subject"] == subject and item["type"] in spatial_types)
    ]
    graph_data["relationships"].append({
        "id": _slug(None, f"relationship_{subject}_{relation}_{target}"),
        "type": relation,
        "subject": subject,
        "target": target,
        "parameters": {},
    })


def _solve_spatial_relationships(graph_data: dict[str, Any], changed_ids: set[str]) -> None:
    parts = {part["id"]: part for part in graph_data["parts"]}
    for relationship in graph_data["relationships"]:
        subject = parts.get(relationship["subject"])
        target = parts.get(relationship["target"])
        if subject is None or target is None:
            continue
        if subject["id"] not in changed_ids and target["id"] not in changed_ids:
            continue
        relation = relationship["type"]
        target_location = target["transform"]["location"]
        if relation in {"on_top_of", "above"}:
            subject["transform"]["location"] = [
                target_location[0],
                target_location[1],
                round(
                    target_location[2]
                    + _vertical_half_extent(target)
                    + _vertical_half_extent(subject),
                    9,
                ),
            ]
        elif relation in {"below", "under"}:
            subject["transform"]["location"] = [
                target_location[0],
                target_location[1],
                target_location[2] - _vertical_half_extent(target) - _vertical_half_extent(subject),
            ]


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = 0
    differences = 0
    for character in longer:
        if short_index < len(shorter) and shorter[short_index] == character:
            short_index += 1
        else:
            differences += 1
            if differences > 1:
                return False
    return True


def _part_terms(part: Any) -> set[str]:
    values = [
        getattr(part, "id", None),
        getattr(part, "name", None),
        getattr(part, "role", None),
        getattr(getattr(part, "geometry", None), "type", None),
    ]
    terms = {
        token
        for value in values
        if value
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
    }
    geometry_type = str(getattr(getattr(part, "geometry", None), "type", "")).lower()
    if geometry_type == "cylinder":
        terms.add("tube")
    elif geometry_type == "box":
        terms.add("cube")
    elif geometry_type == "sphere":
        terms.add("ball")
    return terms


def _unique_part_for_term(graph: SemanticAssetGraph, term: str) -> str | None:
    normalized = _slug(term, "")
    exact = [part.id for part in graph.parts if normalized in _part_terms(part)]
    if len(exact) == 1:
        return exact[0]
    fuzzy = [
        part.id
        for part in graph.parts
        if any(_edit_distance_at_most_one(normalized, candidate) for candidate in _part_terms(part))
    ]
    return fuzzy[0] if len(fuzzy) == 1 else None


def _normalize_relational_move_intent(
    graph: SemanticAssetGraph,
    request: GraphOperationRequest,
) -> tuple[GraphOperationRequest, GraphDiagnostic | None]:
    intent = str(request.intent or "").strip().lower()
    match = re.search(
        r"\bmove\s+(?:the\s+)?([a-z0-9_-]+)\s+"
        r"(?:to|onto)\s+(?:the\s+)?(top|bottom)\s+of\s+(?:the\s+)?([a-z0-9_-]+)",
        intent,
    )
    if not match:
        return request, None
    moving_term, side, reference_term = match.groups()
    moving_id = _unique_part_for_term(graph, moving_term)
    reference_id = _unique_part_for_term(graph, reference_term)
    if not moving_id or not reference_id or moving_id == reference_id:
        return request, None
    relation = "on_top_of" if side == "top" else "below"
    normalized = request.model_copy(
        update={
            "operation": "move",
            "target_ids": [moving_id],
            "parameters": {
                **request.parameters,
                "relation": relation,
                "reference_id": reference_id,
            },
        }
    )
    return normalized, GraphDiagnostic(
        stage="normalize",
        code="relational_move_normalized",
        message=f"Normalized relational move: {moving_id} {relation} {reference_id}.",
        details={
            "original_operation": request.operation,
            "moving_term": moving_term,
            "reference_term": reference_term,
            "target": moving_id,
            "reference_id": reference_id,
        },
    )


def _normalize_match_width_resize_intent(
    graph: SemanticAssetGraph,
    request: GraphOperationRequest,
) -> tuple[GraphOperationRequest, GraphDiagnostic | None]:
    intent = str(request.intent or "").strip().lower()
    match = re.search(
        r"\b(?:reduce|resize|scale|shrink)\s+(?:the\s+)?([a-z0-9_-]+)"
        r".*?\bmatch\s+(?:the\s+)?([a-z0-9_-]+)(?:'s)?\s+width\b",
        intent,
    )
    if not match:
        return request, None
    target_term, reference_term = match.groups()
    target_id = _unique_part_for_term(graph, target_term)
    reference_id = _unique_part_for_term(graph, reference_term)
    if not target_id or not reference_id or target_id == reference_id:
        return request, None
    normalized = request.model_copy(
        update={
            "operation": "resize",
            "target_ids": [target_id],
            "parameters": {
                **request.parameters,
                "mode": "match_reference_width",
                "reference_id": reference_id,
                "proportional": True,
            },
        }
    )
    return normalized, GraphDiagnostic(
        stage="normalize",
        code="match_width_resize_normalized",
        message=f"Normalized proportional resize: match {target_id} width to {reference_id}.",
        details={
            "original_operation": request.operation,
            "target": target_id,
            "reference_id": reference_id,
        },
    )


def _normalize_relational_add_intent(
    graph: SemanticAssetGraph,
    request: GraphOperationRequest,
) -> tuple[GraphOperationRequest, GraphDiagnostic | None]:
    if normalize_operation(request.operation) != "add":
        return request, None
    intent = str(request.intent or "").strip().lower()
    if not intent:
        return request, None

    reference_match = re.search(
        r"\b(top|bottom|base)\s+of\s+(?:the\s+)?([a-z0-9_-]+)",
        intent,
    )
    if reference_match:
        placement, reference_term = reference_match.groups()
        placement = "bottom" if placement in {"bottom", "base"} else "above"
    else:
        reference_match = re.search(
            r"\b(below|under|underneath|above|over|near|beside)\s+(?:the\s+)?([a-z0-9_-]+)",
            intent,
        )
        if not reference_match:
            return request, None
        placement, reference_term = reference_match.groups()
        placement = {
            "under": "below",
            "underneath": "below",
            "over": "above",
            "beside": "near",
        }.get(placement, placement)

    reference_id = _unique_part_for_term(graph, reference_term)
    if not reference_id:
        return request, None

    parameters = copy.deepcopy(request.parameters)
    part = copy.deepcopy(parameters.get("part") or {})
    geometry_type = (
        part.get("type")
        or parameters.get("type")
        or parameters.get("primitive_type")
    )
    if not geometry_type:
        geometry_terms = [
            ("triangle", "triangle"),
            ("triangular", "triangle"),
            ("triangular prism", "triangle"),
            ("wedge", "wedge"),
            ("cone", "cone"),
            ("tube", "cylinder"),
            ("cylinder", "cylinder"),
            ("sphere", "sphere"),
            ("ball", "sphere"),
            ("cube", "box"),
            ("box", "box"),
            ("torus", "torus"),
            ("ring", "torus"),
            ("plane", "plane"),
        ]
        geometry_type = next(
            (canonical for phrase, canonical in geometry_terms if re.search(rf"\b{phrase}\b", intent)),
            None,
        )
    if geometry_type:
        part["type"] = geometry_type

    material = part.get("material") or parameters.get("material") or parameters.get("color")
    if not material:
        material = next(
            (
                name
                for name in (
                    "neutral", "blue", "red", "green", "yellow", "orange",
                    "purple", "black", "white", "gray", "metal", "wood", "glass",
                )
                if re.search(rf"\b{name}\b", intent)
            ),
            "neutral",
        )
    part["material"] = material

    if not part.get("id") and not parameters.get("id"):
        part["id"] = f"added_{geometry_type or 'part'}"
    parameters["placement"] = placement
    parameters["part"] = part

    normalized = request.model_copy(
        update={
            "target_ids": [reference_id],
            "parameters": parameters,
        }
    )
    return normalized, GraphDiagnostic(
        stage="normalize",
        code="relational_add_normalized",
        message=f"Normalized add relative to existing part {reference_id}.",
        details={
            "original_targets": request.target_ids,
            "reference_term": reference_term,
            "target": reference_id,
            "placement": placement,
            "geometry_type": geometry_type,
            "count": parameters.get("count", 1),
        },
    )


def compile_graph_operation(
    graph: SemanticAssetGraph,
    request: GraphOperationRequest,
) -> GraphOperationResult:
    normalization_diagnostics: list[GraphDiagnostic] = []
    request, diagnostic = _normalize_relational_move_intent(graph, request)
    if diagnostic:
        normalization_diagnostics.append(diagnostic)
    request, diagnostic = _normalize_match_width_resize_intent(graph, request)
    if diagnostic:
        normalization_diagnostics.append(diagnostic)
    request, diagnostic = _normalize_relational_add_intent(graph, request)
    if diagnostic:
        normalization_diagnostics.append(diagnostic)
    source_operation = request.operation.strip().lower()
    operation = normalize_operation(request.operation)
    if operation not in SUPPORTED_OPERATIONS:
        return _failure("unsupported", operation, request, graph, "unsupported_operation", f"Unsupported graph operation: {request.operation}")
    if request.base_revision != graph.revision:
        return _failure(
            "invalid",
            operation,
            request,
            graph,
            "revision_conflict",
            "The operation base revision does not match the graph revision.",
            details={"current_revision": graph.revision, "requested_base_revision": request.base_revision},
        )
    graph_diagnostics = validate_graph(graph)
    if graph_diagnostics:
        return GraphOperationResult(
            outcome="invalid",
            operation=operation,
            base_revision=request.base_revision,
            graph_before=graph,
            diagnostics=graph_diagnostics,
        )
    intended = _intent_operation(request.intent)
    if intended and intended != operation:
        return _failure(
            "needs_repair",
            operation,
            request,
            graph,
            "intent_operation_mismatch",
            f"Requested intent implies {intended}, but the proposed operation is {operation}.",
            details={"intended_operation": intended, "proposed_operation": operation},
        )

    data = graph.model_dump(mode="python")
    selected = _targets(data, request)
    selected_ids = [part["id"] for part in selected]
    parameters = copy.deepcopy(request.parameters)
    needs_target = operation not in {"add", "undo", "ungroup"}
    if needs_target and not request.target_ids:
        return _failure("needs_clarification", operation, request, graph, "missing_target", f"{operation} requires at least one target id.")
    if needs_target and not selected:
        return _failure("needs_clarification", operation, request, graph, "target_not_found", "No requested target exists in the graph.")
    if operation == "add" and request.target_ids and not selected:
        return _failure(
            "needs_repair",
            operation,
            request,
            graph,
            "reference_target_not_found",
            "The add reference target does not exist in the graph.",
        )

    preserved_constraints = [
        constraint["id"]
        for constraint in data["constraints"]
        if constraint["id"] in request.preserve or constraint["type"] in request.preserve
    ]

    if operation == "add":
        raw_parts = parameters.get("parts")
        part_definitions = (
            [copy.deepcopy(part) for part in raw_parts if isinstance(part, dict)]
            if isinstance(raw_parts, list) and raw_parts
            else [copy.deepcopy(parameters.get("part") or {})]
        )
        reference = selected[0] if selected else None
        reference_location = reference["transform"]["location"] if reference else [0.0, 0.0, 0.0]
        reference_scale = reference["transform"]["scale"] if reference else [1.0, 1.0, 1.0]
        existing_ids = {existing["id"] for existing in data["parts"]}
        added_ids: list[str] = []

        for definition_index, part in enumerate(part_definitions):
            geometry_type = part.get("geometry", {}).get("type") if isinstance(part.get("geometry"), dict) else None
            geometry_type = geometry_type or part.get("type") or parameters.get("type") or parameters.get("primitive_type")
            if not geometry_type:
                return _failure("needs_clarification", operation, request, graph, "missing_geometry", "Every added part requires a geometry type.")
            geometry_type = PRIMITIVE_ALIASES.get(str(geometry_type).lower(), str(geometry_type).lower())
            fallback_id = f"added_{geometry_type}_{definition_index + 1}" if len(part_definitions) > 1 else f"added_{geometry_type}"
            part_id = _slug(part.get("id") or parameters.get("id"), fallback_id)
            transform = copy.deepcopy(part.get("transform") or {})
            requested_location = transform.get("location") or part.get("position") or parameters.get("location")
            placement = str(
                part.get("placement")
                or parameters.get("placement")
                or parameters.get("semantic_direction")
                or parameters.get("relation")
                or ""
            ).lower()
            arrangement = str(part.get("arrangement") or parameters.get("arrangement") or "").lower()
            raw_count = part.get("count") or parameters.get("count") or 1
            try:
                count = max(1, min(int(raw_count), 32))
            except (TypeError, ValueError):
                count = 1
            if placement and not reference and requested_location is None:
                return _failure(
                    "needs_clarification",
                    operation,
                    request,
                    graph,
                    "missing_reference_target",
                    "Relative add placement requires an existing reference target.",
                )
            added_scale = _vector(transform.get("scale") or part.get("scale") or parameters.get("scale"), [1.0, 1.0, 1.0])
            if requested_location is None and reference:
                offset = {
                    "below": [0.0, 0.0, -((reference_scale[2] + added_scale[2]) / 2)],
                    "down": [0.0, 0.0, -((reference_scale[2] + added_scale[2]) / 2)],
                    "bottom": [0.0, 0.0, -(reference_scale[2] / 2) + (added_scale[2] / 2)],
                    "at_bottom_of": [0.0, 0.0, -(reference_scale[2] / 2) + (added_scale[2] / 2)],
                    "above": [0.0, 0.0, (reference_scale[2] + added_scale[2]) / 2],
                    "up": [0.0, 0.0, (reference_scale[2] + added_scale[2]) / 2],
                    "left": [0.0, -((reference_scale[1] + added_scale[1]) / 2), 0.0],
                    "left_of": [0.0, -((reference_scale[1] + added_scale[1]) / 2), 0.0],
                    "right": [0.0, (reference_scale[1] + added_scale[1]) / 2, 0.0],
                    "right_of": [0.0, (reference_scale[1] + added_scale[1]) / 2, 0.0],
                    "front": [(reference_scale[0] + added_scale[0]) / 2, 0.0, 0.0],
                    "in_front_of": [(reference_scale[0] + added_scale[0]) / 2, 0.0, 0.0],
                    "behind": [-((reference_scale[0] + added_scale[0]) / 2), 0.0, 0.0],
                    "rear": [-((reference_scale[0] + added_scale[0]) / 2), 0.0, 0.0],
                }.get(placement, [0.0, (reference_scale[1] + added_scale[1]) / 2, 0.0])
                requested_location = [
                    reference_location[index] + offset[index]
                    for index in range(3)
                ]
            base_location = _vector(requested_location, [0.0, 0.0, 0.0])
            base_rotation = _vector(transform.get("rotation") or part.get("rotation") or parameters.get("rotation"), [0.0, 0.0, 0.0])
            material = part.get("material") or parameters.get("material") or parameters.get("color") or "neutral"
            instance_ids = [part_id] if count == 1 else [part_id, *[f"{part_id}_{index}" for index in range(2, count + 1)]]
            duplicate_id = next((instance_id for instance_id in instance_ids if instance_id in existing_ids), None)
            if duplicate_id:
                return _failure("needs_repair", operation, request, graph, "duplicate_part_id", f"Part id {duplicate_id} already exists.")

            for index, instance_id in enumerate(instance_ids):
                location = list(base_location)
                rotation = list(base_rotation)
                if arrangement == "radial" and reference:
                    angle = (2 * math.pi * index) / count
                    radius = (max(reference_scale[0], reference_scale[1]) + max(added_scale[0], added_scale[1])) / 2
                    location[0] = reference_location[0] + math.cos(angle) * radius
                    location[1] = reference_location[1] + math.sin(angle) * radius
                    rotation[2] += angle
                elif count > 1:
                    axis_name = str(part.get("repeat_axis") or parameters.get("repeat_axis") or "y").lower()
                    axis = {"x": 0, "y": 1, "z": 2}.get(axis_name, 1)
                    spacing = part.get("spacing") or parameters.get("spacing") or abs(added_scale[axis]) * 1.25
                    location[axis] += (index - ((count - 1) / 2)) * float(spacing)
                metadata = copy.deepcopy(part.get("metadata") or {})
                if count > 1:
                    metadata.update({
                        "arrangement": arrangement or "linear",
                        "instance_index": index,
                        "instance_count": count,
                    })
                data["parts"].append({
                    "id": instance_id,
                    "name": part.get("name") or part.get("label"),
                    "role": part.get("role"),
                    "geometry": {
                        "type": geometry_type,
                        "parameters": copy.deepcopy(part.get("parameters") or parameters.get("geometry_parameters") or {}),
                        "operations": copy.deepcopy(part.get("operations") or []),
                    },
                    "transform": {
                        "location": location,
                        "rotation": rotation,
                        "scale": added_scale,
                    },
                    "material": material,
                    "construction_notes": copy.deepcopy(part.get("construction_notes") or []),
                    "metadata": metadata,
                })
                existing_ids.add(instance_id)
                added_ids.append(instance_id)
                if reference and placement:
                    data["relationships"].append({
                        "id": _slug(None, f"relationship_{instance_id}_{placement}_{reference['id']}"),
                        "type": placement,
                        "subject": instance_id,
                        "target": reference["id"],
                        "parameters": {},
                    })
        selected_ids = added_ids
    elif operation == "remove":
        blocked = [
            constraint
            for constraint in data["constraints"]
            if constraint["required"] and any(target in selected_ids for target in constraint["targets"])
            and (constraint["id"] in request.preserve or constraint["type"] in request.preserve)
        ]
        if blocked:
            return _failure(
                "needs_repair",
                operation,
                request,
                graph,
                "preserved_constraint_violation",
                "Removing the selected part would violate a preserved constraint.",
                details={"constraints": [constraint["id"] for constraint in blocked]},
            )
        selected_set = set(selected_ids)
        data["parts"] = [part for part in data["parts"] if part["id"] not in selected_set]
        data["relationships"] = [item for item in data["relationships"] if item["subject"] not in selected_set and item["target"] not in selected_set]
        data["attachments"] = [item for item in data["attachments"] if item["child"] not in selected_set and item["parent"] not in selected_set]
        data["constraints"] = [item for item in data["constraints"] if not any(target in selected_set for target in item["targets"])]
        for group in data["groups"]:
            group["members"] = [member for member in group["members"] if member not in selected_set]
        data["groups"] = [group for group in data["groups"] if group["members"]]
    elif operation == "replace":
        modifier_mode = (
            parameters.get("mode") == "geometry_modifier"
            or source_operation in {
                "set_geometry_modifier", "geometry_modifier", "set_shape_modifier",
                "shape_modifier", "cut", "hemisphere", "half",
            }
            or isinstance(parameters.get("shape_modifiers"), list)
        )
        if modifier_mode:
            requested_modifiers = [
                str(item).strip().lower()
                for item in parameters.get("shape_modifiers", [])
                if str(item).strip()
            ]
            if source_operation in {"cut", "hemisphere", "half"} and "half" not in requested_modifiers:
                requested_modifiers.append("half")
            if "half" in requested_modifiers and "flat" not in requested_modifiers:
                requested_modifiers.append("flat")
            for part in selected:
                if part["geometry"]["type"] != "sphere":
                    return _failure(
                        "needs_repair",
                        operation,
                        request,
                        graph,
                        "geometry_modifier_target_mismatch",
                        "Half/hemisphere modifiers require a sphere target.",
                    )
                existing = part["geometry"]["parameters"].get("shape_modifiers")
                existing = existing if isinstance(existing, list) else []
                part["geometry"]["parameters"]["shape_modifiers"] = list(dict.fromkeys(existing + requested_modifiers))
                direction = str(parameters.get("hemisphere_direction") or parameters.get("direction") or "up").lower()
                if direction in {"down", "-z", "bottom", "flat_up", "flat-top"}:
                    part["transform"]["rotation"] = [math.pi, 0.0, 0.0]
                elif direction in {"up", "+z", "top", "flat_down", "flat-bottom"}:
                    part["transform"]["rotation"] = [0.0, 0.0, 0.0]
                else:
                    return _failure(
                        "needs_clarification",
                        operation,
                        request,
                        graph,
                        "invalid_hemisphere_direction",
                        "Hemisphere direction must be up or down.",
                    )
        else:
            geometry_type = parameters.get("type") or parameters.get("primitive_type") or parameters.get("replacement_type") or parameters.get("replace_with")
            if not geometry_type:
                return _failure("needs_clarification", operation, request, graph, "missing_geometry", "Replace requires a replacement geometry type.")
            for part in selected:
                part["geometry"]["type"] = PRIMITIVE_ALIASES.get(str(geometry_type).lower(), str(geometry_type).lower())
                if isinstance(parameters.get("geometry_parameters"), dict):
                    part["geometry"]["parameters"] = copy.deepcopy(parameters["geometry_parameters"])
                if parameters.get("material") or parameters.get("color"):
                    part["material"] = parameters.get("material") or parameters.get("color")
    elif operation == "move":
        move_mode = str(parameters.get("mode") or "").lower()
        if source_operation in {"align_centers", "align_objects", "center_objects_on_axis"}:
            move_mode = "align_centers_xy"
        elif source_operation in {"center_group", "center_objects", "align_center"}:
            move_mode = "center_group"
        relation = str(parameters.get("relation") or parameters.get("placement") or "").lower()
        reference_id = str(
            parameters.get("reference_id")
            or parameters.get("reference")
            or parameters.get("anchor")
            or ""
        )
        if relation in {"top", "above"}:
            relation = "on_top_of"
        elif relation in {"bottom", "below"}:
            relation = "below"
        if relation:
            reference = next((part for part in data["parts"] if part["id"] == reference_id), None)
            if reference is None:
                return _failure(
                    "needs_clarification",
                    operation,
                    request,
                    graph,
                    "reference_not_found",
                    "Relational move requires a known reference_id.",
                    details={"reference_id": reference_id},
                )
            for part in selected:
                reference_location = reference["transform"]["location"]
                location = list(part["transform"]["location"])
                if relation in {"on_top_of", "above"}:
                    location = [
                        reference_location[0],
                        reference_location[1],
                        reference_location[2] + _vertical_half_extent(reference) + _vertical_half_extent(part),
                    ]
                elif relation in {"below", "under"}:
                    location = [
                        reference_location[0],
                        reference_location[1],
                        reference_location[2] - _vertical_half_extent(reference) - _vertical_half_extent(part),
                    ]
                elif relation == "left_of":
                    location[1] = reference_location[1] - 1.0
                elif relation == "right_of":
                    location[1] = reference_location[1] + 1.0
                elif relation == "in_front_of":
                    location[0] = reference_location[0] + 1.0
                elif relation == "behind":
                    location[0] = reference_location[0] - 1.0
                elif relation == "aligned_with":
                    location[0:2] = reference_location[0:2]
                else:
                    return _failure(
                        "needs_clarification",
                        operation,
                        request,
                        graph,
                        "unsupported_spatial_relation",
                        f"Unsupported relational move: {relation}",
                    )
                part["transform"]["location"] = location
                _upsert_spatial_relationship(
                    data,
                    subject=part["id"],
                    relation=relation,
                    target=reference_id,
                )
        elif move_mode == "align_centers_xy":
            if len(selected) < 2:
                return _failure(
                    "needs_clarification",
                    operation,
                    request,
                    graph,
                    "insufficient_alignment_targets",
                    "Center alignment requires at least two selected parts.",
                )
            center_x = sum(part["transform"]["location"][0] for part in selected) / len(selected)
            center_y = sum(part["transform"]["location"][1] for part in selected) / len(selected)
            for part in selected:
                part["transform"]["location"][0:2] = [center_x, center_y]
        elif move_mode == "center_group":
            centroid = [
                sum(part["transform"]["location"][index] for part in selected) / len(selected)
                for index in range(3)
            ]
            for part in selected:
                part["transform"]["location"] = [
                    part["transform"]["location"][index] - centroid[index]
                    for index in range(3)
                ]
        else:
            absolute = parameters.get("location") or parameters.get("position")
            delta = parameters.get("location_delta") or parameters.get("delta_location")
            if absolute is None and delta is None and isinstance(parameters.get("amount"), int | float):
                amount = float(parameters["amount"])
                direction = str(parameters.get("semantic_direction") or parameters.get("direction") or "").lower()
                delta = {
                    "front": [amount, 0, 0], "forward": [amount, 0, 0],
                    "rear": [-amount, 0, 0], "back": [-amount, 0, 0],
                    "left": [0, -amount, 0], "right": [0, amount, 0],
                    "up": [0, 0, amount], "down": [0, 0, -amount],
                }.get(direction)
            if absolute is None and delta is None:
                return _failure("needs_clarification", operation, request, graph, "missing_translation", "Move requires a location, translation delta, or relation plus reference_id.")
            for part in selected:
                current = part["transform"]["location"]
                part["transform"]["location"] = _vector(absolute, current) if absolute is not None else [
                    current[index] + _vector(delta, [0, 0, 0])[index] for index in range(3)
                ]
    elif operation == "rotate":
        absolute = parameters.get("rotation")
        if absolute is not None:
            for part in selected:
                part["transform"]["rotation"] = _vector(absolute, part["transform"]["rotation"])
        else:
            axis, amount = _rotation_amount(parameters)
            if axis is None or amount is None:
                return _failure("needs_clarification", operation, request, graph, "missing_rotation", "Rotate requires a rotation vector or axis/view plus amount.")
            for part in selected:
                part["transform"]["rotation"][axis] += amount
    elif operation == "recolor":
        material = parameters.get("material") or parameters.get("color")
        if material is None:
            return _failure("needs_clarification", operation, request, graph, "missing_material", "Recolor requires a material or color.")
        for part in selected:
            part["material"] = copy.deepcopy(material)
    elif operation == "resize":
        changed_ids = set(selected_ids)
        if parameters.get("mode") == "match_reference_width":
            reference_id = str(parameters.get("reference_id") or "")
            reference = next((part for part in data["parts"] if part["id"] == reference_id), None)
            if reference is None:
                return _failure(
                    "needs_clarification",
                    operation,
                    request,
                    graph,
                    "reference_not_found",
                    "Match-width resize requires a known reference_id.",
                    details={"reference_id": reference_id},
                )
            reference_width = _horizontal_diameter(reference)
            for part in selected:
                current_width = _horizontal_diameter(part)
                if current_width <= 0 or reference_width <= 0:
                    return _failure(
                        "invalid",
                        operation,
                        request,
                        graph,
                        "invalid_geometry_width",
                        "Cannot derive a positive width for proportional matching.",
                    )
                factor = round(reference_width / current_width, 9)
                part["transform"]["scale"] = [
                    round(component * factor, 9)
                    for component in part["transform"]["scale"]
                ]
            _solve_spatial_relationships(data, changed_ids)
        elif source_operation in {"set_thickness", "adjust_thickness"} or parameters.get("mode") == "thickness":
            amount = parameters.get("amount")
            if not isinstance(amount, int | float):
                return _failure("needs_clarification", operation, request, graph, "missing_thickness", "Thickness resize requires a numeric amount.")
            for part in selected:
                current = part["transform"]["scale"]
                thickness = float(amount) if source_operation != "adjust_thickness" else current[0] + float(amount)
                if not 0.01 <= thickness <= 20.0:
                    return _failure("invalid", operation, request, graph, "invalid_thickness", "Thickness must resolve between 0.01 and 20.")
                part["transform"]["scale"][0:2] = [thickness, thickness]
            scale = None
            factor = None
        else:
            scale = parameters.get("scale")
            factor = parameters.get("factor") or parameters.get("scale_factor")
            if factor is None and normalize_operation(request.operation) == "resize":
                factor = parameters.get("amount")
            if scale is None and not isinstance(factor, int | float):
                return _failure("needs_clarification", operation, request, graph, "missing_scale", "Resize requires a scale vector or numeric factor.")
            if isinstance(factor, int | float) and not 0.01 <= float(factor) <= 20:
                return _failure("invalid", operation, request, graph, "invalid_scale_factor", "Resize factor must be between 0.01 and 20.")
            for part in selected:
                if scale is not None:
                    part["transform"]["scale"] = _vector(scale, part["transform"]["scale"])
                else:
                    part["transform"]["scale"] = [component * float(factor) for component in part["transform"]["scale"]]
                    if set(request.target_ids) & {"asset", "whole_asset", "*"}:
                        part["transform"]["location"] = [component * float(factor) for component in part["transform"]["location"]]
    elif operation == "attach":
        parent = str(parameters.get("parent") or parameters.get("target") or "")
        children = selected_ids
        if not parent or parent not in {part["id"] for part in data["parts"]}:
            return _failure("needs_clarification", operation, request, graph, "missing_parent", "Attach requires a known parent part.")
        for child in children:
            if child == parent:
                return _failure("invalid", operation, request, graph, "self_attachment", "A part cannot attach to itself.")
            data["attachments"] = [item for item in data["attachments"] if item["child"] != child]
            data["attachments"].append({
                "id": _slug(parameters.get("id"), f"attachment_{child}_{parent}"),
                "child": child,
                "parent": parent,
                "socket": parameters.get("socket"),
                "preserve_world_transform": bool(parameters.get("preserve_world_transform", True)),
                "parameters": {},
            })
    elif operation == "detach":
        before_count = len(data["attachments"])
        selected_set = set(selected_ids)
        data["attachments"] = [item for item in data["attachments"] if item["child"] not in selected_set]
        if len(data["attachments"]) == before_count:
            return _failure("needs_repair", operation, request, graph, "attachment_not_found", "Selected parts are not attached.")
    elif operation == "group":
        group_id = _slug(parameters.get("group_id") or parameters.get("id"), "group")
        if len(selected_ids) < 2:
            return _failure("needs_clarification", operation, request, graph, "insufficient_group_members", "Group requires at least two selected parts.")
        existing = next((group for group in data["groups"] if group["id"] == group_id), None)
        if existing:
            existing["members"] = list(dict.fromkeys(existing["members"] + selected_ids))
        else:
            data["groups"].append({"id": group_id, "members": selected_ids, "name": parameters.get("name"), "metadata": {}})
    elif operation == "ungroup":
        group_ids = set(request.target_ids)
        before_count = len(data["groups"])
        data["groups"] = [group for group in data["groups"] if group["id"] not in group_ids]
        if len(data["groups"]) == before_count:
            return _failure("needs_clarification", operation, request, graph, "group_not_found", "No requested group exists.")
        selected_ids = sorted(group_ids)
    elif operation == "undo":
        previous = parameters.get("previous_graph")
        if not isinstance(previous, dict):
            return _failure("needs_clarification", operation, request, graph, "missing_previous_graph", "Undo requires the previous graph revision.")
        try:
            previous_graph = SemanticAssetGraph.model_validate(previous)
        except Exception as exc:
            return _failure("invalid", operation, request, graph, "invalid_previous_graph", "Undo graph is invalid.", details={"error": str(exc)})
        if previous_graph.asset_id != graph.asset_id:
            return _failure("invalid", operation, request, graph, "asset_mismatch", "Undo graph belongs to a different asset.")
        data = previous_graph.model_dump(mode="python")
        selected_ids = [part["id"] for part in data["parts"]]

    data["revision"] = graph.revision + 1
    try:
        after = SemanticAssetGraph.model_validate(data)
    except Exception as exc:
        return _failure("invalid", operation, request, graph, "schema_validation_failed", "Proposed graph does not satisfy the graph schema.", details={"error": str(exc)})
    diagnostics = validate_graph(after)
    if diagnostics:
        return GraphOperationResult(
            outcome="invalid",
            operation=operation,
            base_revision=request.base_revision,
            selected_targets=selected_ids,
            graph_before=graph,
            graph_after=after,
            diagnostics=diagnostics,
        )
    changes = _diff(graph.model_dump(mode="json"), after.model_dump(mode="json"))
    return GraphOperationResult(
        outcome="compiled",
        operation=operation,
        base_revision=request.base_revision,
        proposed_revision=after.revision,
        selected_targets=selected_ids,
        graph_before=graph,
        graph_after=after,
        diff=GraphDiff(
            operation=operation,
            selected_targets=selected_ids,
            preserved_constraints=preserved_constraints,
            changes=changes,
        ),
        diagnostics=[
            *normalization_diagnostics,
            GraphDiagnostic(
                stage="compile",
                code="compiled",
                message=f"Compiled {operation} for {len(selected_ids)} selected target(s).",
            )
        ],
    )


def state_from_graph(state: dict[str, Any], graph: SemanticAssetGraph) -> dict[str, Any]:
    """Persist the graph as authority and refresh the primitive builder projection."""
    result = copy.deepcopy(state)
    result["semantic_graph"] = graph.model_dump(mode="json")
    result["revision"] = graph.revision
    result["primitives"] = [
        {
            **copy.deepcopy(part.metadata),
            "id": part.id,
            "type": part.geometry.type,
            "label": part.name or part.id,
            "material": copy.deepcopy(part.material),
            "transform": part.transform.model_dump(mode="json"),
            "params": copy.deepcopy(part.geometry.parameters),
        }
        for part in graph.parts
    ]
    result["constraints"] = [constraint.model_dump(mode="json") for constraint in graph.constraints]
    result["groups"] = [group.model_dump(mode="json") for group in graph.groups]
    result["last_graph_revision"] = graph.revision
    result["pending_edit"] = False
    result["source"] = "semantic_asset_graph"
    return result
