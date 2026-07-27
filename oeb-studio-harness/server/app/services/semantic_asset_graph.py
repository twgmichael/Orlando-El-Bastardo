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
        return SemanticAssetGraph.model_validate(graph_data)

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
        {
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
        }
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


def compile_graph_operation(
    graph: SemanticAssetGraph,
    request: GraphOperationRequest,
) -> GraphOperationResult:
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

    preserved_constraints = [
        constraint["id"]
        for constraint in data["constraints"]
        if constraint["id"] in request.preserve or constraint["type"] in request.preserve
    ]

    if operation == "add":
        part = copy.deepcopy(parameters.get("part") or {})
        part_id = _slug(part.get("id") or parameters.get("id"), "new_part")
        if any(existing["id"] == part_id for existing in data["parts"]):
            return _failure("needs_repair", operation, request, graph, "duplicate_part_id", f"Part id {part_id} already exists.")
        geometry_type = part.get("geometry", {}).get("type") if isinstance(part.get("geometry"), dict) else None
        geometry_type = geometry_type or part.get("type") or parameters.get("type") or parameters.get("primitive_type")
        if not geometry_type:
            return _failure("needs_clarification", operation, request, graph, "missing_geometry", "Add requires a part geometry type.")
        transform = copy.deepcopy(part.get("transform") or {})
        requested_location = transform.get("location") or parameters.get("location")
        placement = str(
            parameters.get("placement")
            or parameters.get("semantic_direction")
            or parameters.get("relation")
            or ""
        ).lower()
        if requested_location is None and selected:
            reference = selected[0]
            reference_location = reference["transform"]["location"]
            reference_scale = reference["transform"]["scale"]
            added_scale = _vector(transform.get("scale") or parameters.get("scale"), [1.0, 1.0, 1.0])
            offset = {
                "below": [0.0, 0.0, -((reference_scale[2] + added_scale[2]) / 2)],
                "down": [0.0, 0.0, -((reference_scale[2] + added_scale[2]) / 2)],
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
        data["parts"].append(
            {
                "id": part_id,
                "name": part.get("name") or part.get("label"),
                "role": part.get("role"),
                "geometry": {
                    "type": PRIMITIVE_ALIASES.get(str(geometry_type).lower(), str(geometry_type).lower()),
                    "parameters": copy.deepcopy(part.get("parameters") or parameters.get("geometry_parameters") or {}),
                    "operations": copy.deepcopy(part.get("operations") or []),
                },
                "transform": {
                    "location": _vector(requested_location, [0.0, 0.0, 0.0]),
                    "rotation": _vector(transform.get("rotation") or parameters.get("rotation"), [0.0, 0.0, 0.0]),
                    "scale": _vector(transform.get("scale") or parameters.get("scale"), [1.0, 1.0, 1.0]),
                },
                "material": part.get("material") or parameters.get("material") or parameters.get("color"),
                "construction_notes": copy.deepcopy(part.get("construction_notes") or []),
                "metadata": copy.deepcopy(part.get("metadata") or {}),
            }
        )
        if selected and placement:
            reference_id = selected[0]["id"]
            data["relationships"].append(
                {
                    "id": _slug(None, f"relationship_{part_id}_{placement}_{reference_id}"),
                    "type": placement,
                    "subject": part_id,
                    "target": reference_id,
                    "parameters": {},
                }
            )
        selected_ids = [part_id]
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
            return _failure("needs_clarification", operation, request, graph, "missing_translation", "Move requires a location or translation delta.")
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
