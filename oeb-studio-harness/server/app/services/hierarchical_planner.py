from __future__ import annotations

import json
import re
from typing import Any
import urllib.error

from pydantic import ValidationError

from app.schemas.hierarchical_asset_intent import HierarchicalAssetIntent
from app.schemas.object_archetype_registry import (
    ArchetypeGroundingChange,
    ObjectArchetype,
    ObjectArchetypeRegistry,
)


HIERARCHICAL_DECOMPOSITION_PROMPT = """You are the OEB hierarchical asset planner.
Convert one broad named-object request into versioned hierarchical_asset_intent.
You propose semantic structure only. Do not emit Blender code, primitive
coordinates, Euler rotations, or worker jobs.

Return JSON only:
{
  "hierarchical_asset_intent": {
    "schema_version": "1.0",
    "object_family": "registered family or explicit unknown family",
    "root_part_id": "stable_snake_case_id",
    "required_roles": ["roles believed required"],
    "parts": [{
      "id": "stable_snake_case_id",
      "name": "human name",
      "role": "semantic role or alias",
      "requirement": "required|optional|decorative",
      "parent_id": null,
      "children": [],
      "shape_family": "semantic shape family",
      "geometry_strategy": "registered recipe",
      "dimensions": {
        "size": [x, y, z]
      },
      "attachment": null,
      "orientation": {"forward": "front", "up": "up"},
      "repetition": {"mode": "none", "count": 1}
    }],
    "constraints": [],
    "construction_notes": []
  },
  "clarification_question": null
}

For non-root parts, use dimensions.relative_to plus a three-axis ratio instead
of final coordinates. Attach every child to its declared parent with a semantic
anchor. Use only the supplied family, role, shape, recipe, anchor, orientation,
and repetition vocabulary. Preserve uncertainty by asking one clarification
question rather than guessing materially different interpretations."""


class HierarchyClarificationRequired(ValueError):
    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


def _normalized_name(value: Any) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def infer_object_archetype(
    creative_request: str,
    asset_intent: dict[str, Any],
    registry: ObjectArchetypeRegistry,
) -> ObjectArchetype | None:
    explicit = _normalized_name(
        asset_intent.get("object_family")
        or asset_intent.get("family")
        or ""
    )
    if explicit:
        for archetype in registry.archetypes:
            if explicit in {archetype.family, *archetype.aliases}:
                return archetype
    text = " ".join(
        str(value)
        for value in (
            creative_request,
            asset_intent.get("name"),
            asset_intent.get("description"),
            asset_intent.get("kind"),
        )
        if value
    ).lower()
    normalized_text = f"_{_normalized_name(text)}_"
    candidates: list[tuple[int, ObjectArchetype]] = []
    for archetype in registry.archetypes:
        for name in (archetype.family, *archetype.aliases):
            marker = f"_{_normalized_name(name)}_"
            if marker in normalized_text:
                candidates.append((len(marker), archetype))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def hierarchy_planner_payload(
    creative_request: str,
    asset_intent: dict[str, Any],
    archetype: ObjectArchetype,
    *,
    model: str,
    validation_error: str | None = None,
    previous_response: str | None = None,
) -> dict[str, Any]:
    role_contract = [
        {
            "role": role.role,
            "requirement": role.requirement,
            "aliases": role.aliases,
            "allowed_parent_roles": role.allowed_parent_roles,
            "allowed_shape_families": role.allowed_shape_families,
            "allowed_attachment_anchors": role.allowed_attachment_anchors,
            "contact_required": role.contact_required,
            "default_orientation": role.default_orientation.model_dump(mode="json"),
            "proportion_range": (
                role.proportion_range.model_dump(mode="json")
                if role.proportion_range is not None
                else None
            ),
            "repetition": role.repetition.model_dump(mode="json"),
            "supported_geometry_recipes": role.supported_geometry_recipes,
        }
        for role in archetype.roles
    ]
    object_hints = [
        {
            key: item[key]
            for key in ("id", "type", "material", "count", "description")
            if item.get(key) is not None
        }
        for item in asset_intent.get("objects", [])[:24]
        if isinstance(item, dict)
    ]
    relationship_hints = [
        {
            key: item[key]
            for key in ("subject", "relation", "target")
            if item.get(key) is not None
        }
        for item in asset_intent.get("relationships", [])[:32]
        if isinstance(item, dict)
    ]
    current_asset_context = {
        key: asset_intent[key]
        for key in ("name", "kind", "description", "style")
        if asset_intent.get(key) is not None
    }
    if object_hints:
        current_asset_context["object_hints"] = object_hints
    if relationship_hints:
        current_asset_context["relationship_hints"] = relationship_hints
    user_content: dict[str, Any] = {
        "creative_request": creative_request,
        "current_asset_context": current_asset_context,
        "registered_archetype": {
            "id": archetype.id,
            "family": archetype.family,
            "aliases": archetype.aliases,
            "root_role": archetype.root_role,
            "canonical_root_size": archetype.metadata.get(
                "canonical_root_size",
                [4.0, 3.0, 3.0],
            ),
            "roles": role_contract,
        },
    }
    if validation_error:
        user_content["validation_error"] = validation_error
    if previous_response:
        user_content["previous_response"] = previous_response
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": HIERARCHICAL_DECOMPOSITION_PROMPT},
            {"role": "user", "content": json.dumps(user_content, indent=2)},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
    }


def _hierarchy_from_planner_response(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, count=1)
        normalized = re.sub(r"\s*```$", "", normalized, count=1)
    first_brace = normalized.find("{")
    last_brace = normalized.rfind("}")
    if first_brace >= 0 and last_brace >= first_brace:
        normalized = normalized[first_brace:last_brace + 1]
    parsed = json.loads(normalized)
    if not isinstance(parsed, dict):
        raise ValueError("hierarchy planner response must be a JSON object")
    if parsed.get("clarification_question"):
        raise HierarchyClarificationRequired(
            str(parsed["clarification_question"])
        )
    hierarchy = parsed.get("hierarchical_asset_intent")
    if hierarchy is None and parsed.get("schema_version") == "1.0":
        hierarchy = parsed
    if not isinstance(hierarchy, dict):
        raise ValueError(
            "hierarchy planner response must include hierarchical_asset_intent"
        )
    return hierarchy


def resolve_hierarchical_decomposition(
    ollama_url: str,
    model: str,
    creative_request: str,
    asset_intent: dict[str, Any],
    archetype: ObjectArchetype,
    post_json,
    *,
    max_attempts: int = 2,
) -> dict[str, Any]:
    attempts = []
    validation_error = None
    previous_response = None
    for attempt_index in range(max(1, min(max_attempts, 2))):
        payload = hierarchy_planner_payload(
            creative_request,
            asset_intent,
            archetype,
            model=model,
            validation_error=validation_error,
            previous_response=previous_response,
        )
        try:
            raw = post_json(
                f"{ollama_url.rstrip('/')}/api/chat",
                payload,
                timeout=120,
            )
        except urllib.error.HTTPError as exc:
            try:
                upstream_detail = exc.read().decode("utf-8", errors="replace")
            except (AttributeError, OSError):
                upstream_detail = ""
            validation_error = (
                f"hierarchy planner upstream HTTP {exc.code}"
                + (f": {upstream_detail}" if upstream_detail else "")
            )
            attempts.append({
                "attempt": attempt_index + 1,
                "request": payload,
                "error": validation_error,
                "upstream_status": exc.code,
            })
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            validation_error = (
                f"hierarchy planner upstream unavailable: {exc}"
            )
            attempts.append({
                "attempt": attempt_index + 1,
                "request": payload,
                "error": validation_error,
            })
            continue
        message = raw.get("message") if isinstance(raw, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            validation_error = "planner response did not include message.content"
            attempts.append({
                "attempt": attempt_index + 1,
                "request": payload,
                "raw": raw,
                "error": validation_error,
            })
            continue
        try:
            hierarchy = _hierarchy_from_planner_response(content)
            intent = HierarchicalAssetIntent.model_validate(hierarchy)
        except HierarchyClarificationRequired as exc:
            attempts.append({
                "attempt": attempt_index + 1,
                "request": payload,
                "raw": raw,
                "content": content,
                "clarification_question": exc.question,
            })
            return {
                "ok": False,
                "source": "ollama_hierarchical_planner",
                "attempts": attempts,
                "clarification_question": exc.question,
                "error": "hierarchical decomposition requires clarification",
            }
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            validation_error = str(exc)
            previous_response = content
            attempts.append({
                "attempt": attempt_index + 1,
                "request": payload,
                "raw": raw,
                "content": content,
                "error": validation_error,
            })
            continue
        attempts.append({
            "attempt": attempt_index + 1,
            "request": payload,
            "raw": raw,
            "content": content,
            "hierarchical_asset_intent": intent.model_dump(mode="json"),
        })
        return {
            "ok": True,
            "source": "ollama_hierarchical_planner",
            "attempts": attempts,
            "hierarchical_asset_intent": intent.model_dump(mode="json"),
        }
    return {
        "ok": False,
        "source": "ollama_hierarchical_planner",
        "attempts": attempts,
        "error": validation_error or "hierarchical decomposition failed",
    }


def _midpoint(minimum: list[float], maximum: list[float]) -> list[float]:
    return [
        (minimum[index] + maximum[index]) / 2.0
        for index in range(3)
    ]


def _record_change(
    changes: list[ArchetypeGroundingChange],
    path: str,
    code: str,
    before: Any,
    after: Any,
) -> None:
    if before != after:
        changes.append(ArchetypeGroundingChange(
            path=path,
            code=code,
            before=before,
            after=after,
        ))


def repair_hierarchy_against_archetype(
    value: dict[str, Any],
    archetype: ObjectArchetype,
) -> tuple[dict[str, Any], list[ArchetypeGroundingChange]]:
    intent = HierarchicalAssetIntent.model_validate(value)
    repaired = intent.model_dump(mode="json")
    changes: list[ArchetypeGroundingChange] = []
    role_aliases = {
        alias: role.role
        for role in archetype.roles
        for alias in (role.role, *role.aliases)
    }
    rules = {role.role: role for role in archetype.roles}

    before_family = repaired["object_family"]
    repaired["object_family"] = archetype.family
    _record_change(
        changes,
        "$.object_family",
        "object_family_repaired",
        before_family,
        archetype.family,
    )
    for index, part in enumerate(repaired["parts"]):
        before_role = part["role"]
        part["role"] = role_aliases.get(before_role, before_role)
        _record_change(
            changes,
            f"$.parts[{index}].role",
            "role_alias_repaired",
            before_role,
            part["role"],
        )

    parts_by_role = {
        part["role"]: part
        for part in repaired["parts"]
        if part["role"] in rules
    }
    root = next(
        (
            part
            for part in repaired["parts"]
            if part["id"] == repaired["root_part_id"]
        ),
        None,
    )
    if root is None:
        raise ValueError("deterministic repair requires an existing root part")
    root_rule = rules[archetype.root_role]
    before_root_role = root["role"]
    root["role"] = archetype.root_role
    before_root_requirement = root.get("requirement")
    root["requirement"] = root_rule.requirement
    before_root_shape = root.get("shape_family")
    if before_root_shape not in root_rule.allowed_shape_families:
        root["shape_family"] = root_rule.allowed_shape_families[0]
    before_root_recipe = root.get("geometry_strategy")
    if before_root_recipe not in root_rule.supported_geometry_recipes:
        root["geometry_strategy"] = root_rule.supported_geometry_recipes[0]
    before_root_parent = root.get("parent_id")
    root["parent_id"] = None
    before_root_attachment = root.get("attachment")
    root["attachment"] = None
    expected_root_orientation = root_rule.default_orientation.model_dump(
        mode="json"
    )
    before_root_orientation = root.get("orientation")
    if before_root_orientation != expected_root_orientation:
        root["orientation"] = expected_root_orientation
    before_root_repetition = root.get("repetition")
    root_repetition_valid = (
        isinstance(before_root_repetition, dict)
        and before_root_repetition.get("mode")
        in root_rule.repetition.allowed_modes
        and root_rule.repetition.minimum_count
        <= int(before_root_repetition.get("count", 0))
        <= root_rule.repetition.maximum_count
        and (
            root_rule.repetition.axis is None
            or before_root_repetition.get("axis") == root_rule.repetition.axis
        )
    )
    if not root_repetition_valid:
        root["repetition"] = {
            "mode": root_rule.repetition.allowed_modes[0],
            "count": root_rule.repetition.minimum_count,
            "axis": root_rule.repetition.axis,
        }
    before_root_dimensions = dict(root.get("dimensions") or {})
    if root.get("dimensions", {}).get("size") is None:
        root["dimensions"] = {
            "size": archetype.metadata.get(
                "canonical_root_size",
                [4.0, 3.0, 3.0],
            )
        }
    _record_change(
        changes,
        f"$.parts[{repaired['parts'].index(root)}].role",
        "root_role_repaired",
        before_root_role,
        archetype.root_role,
    )
    root_index = repaired["parts"].index(root)
    for suffix, code, before, after in (
        ("requirement", "root_requirement_repaired", before_root_requirement,
         root["requirement"]),
        ("shape_family", "root_shape_family_repaired", before_root_shape,
         root["shape_family"]),
        ("geometry_strategy", "root_geometry_recipe_repaired",
         before_root_recipe, root["geometry_strategy"]),
        ("parent_id", "root_parent_repaired", before_root_parent, None),
        ("attachment", "root_attachment_repaired", before_root_attachment, None),
        ("orientation", "root_orientation_repaired", before_root_orientation,
         root["orientation"]),
        ("repetition", "root_repetition_repaired", before_root_repetition,
         root["repetition"]),
        ("dimensions", "root_dimensions_repaired", before_root_dimensions,
         root["dimensions"]),
    ):
        _record_change(
            changes,
            f"$.parts[{root_index}].{suffix}",
            code,
            before,
            after,
        )
    parts_by_role[archetype.root_role] = root

    for rule in archetype.roles:
        if rule.requirement != "required" or rule.role in parts_by_role:
            continue
        if not rule.allowed_parent_roles:
            raise ValueError(
                f"cannot deterministically insert missing root role '{rule.role}'"
            )
        parent = next(
            (
                parts_by_role[parent_role]
                for parent_role in rule.allowed_parent_roles
                if parent_role in parts_by_role
            ),
            None,
        )
        if parent is None:
            raise ValueError(
                f"cannot determine parent for missing role '{rule.role}'"
            )
        part_id = rule.role
        existing_ids = {part["id"] for part in repaired["parts"]}
        suffix = 2
        while part_id in existing_ids:
            part_id = f"{rule.role}_{suffix}"
            suffix += 1
        proportion = rule.proportion_range
        new_part = {
            "id": part_id,
            "name": rule.role.replace("_", " ").title(),
            "role": rule.role,
            "requirement": "required",
            "parent_id": parent["id"],
            "children": [],
            "shape_family": rule.allowed_shape_families[0],
            "geometry_strategy": rule.supported_geometry_recipes[0],
            "dimensions": (
                {
                    "relative_to": parent["id"],
                    "ratio": _midpoint(
                        proportion.minimum,
                        proportion.maximum,
                    ),
                }
                if proportion is not None
                else {"ratio": [0.5, 0.5, 0.5], "relative_to": parent["id"]}
            ),
            "attachment": {
                "parent_id": parent["id"],
                "anchor": rule.allowed_attachment_anchors[0],
                "contact_required": (
                    rule.contact_required
                    if rule.contact_required is not None
                    else True
                ),
                "offset": [0.0, 0.0, 0.0],
            },
            "orientation": rule.default_orientation.model_dump(mode="json"),
            "repetition": {
                "mode": rule.repetition.allowed_modes[0],
                "count": rule.repetition.minimum_count,
                "axis": rule.repetition.axis,
            },
            "material": "neutral",
            "metadata": {"deterministically_inserted": True},
        }
        repaired["parts"].append(new_part)
        parts_by_role[rule.role] = new_part
        _record_change(
            changes,
            "$.parts",
            "required_role_inserted",
            None,
            new_part,
        )

    parts_by_id = {part["id"]: part for part in repaired["parts"]}
    for index, part in enumerate(repaired["parts"]):
        rule = rules.get(part["role"])
        if rule is None:
            continue
        part["requirement"] = rule.requirement
        if part["role"] == archetype.root_role:
            continue
        parent = parts_by_id.get(part.get("parent_id"))
        parent_role = parent.get("role") if parent else None
        if parent_role not in rule.allowed_parent_roles:
            parent = next(
                (
                    parts_by_role[parent_role]
                    for parent_role in rule.allowed_parent_roles
                    if parent_role in parts_by_role
                ),
                None,
            )
            if parent is None:
                raise ValueError(
                    f"cannot deterministically repair parent for '{part['id']}'"
                )
            before_parent = part.get("parent_id")
            part["parent_id"] = parent["id"]
            _record_change(
                changes,
                f"$.parts[{index}].parent_id",
                "parent_repaired",
                before_parent,
                parent["id"],
            )
        else:
            parent = parent
        before_shape = part.get("shape_family")
        if before_shape not in rule.allowed_shape_families:
            part["shape_family"] = rule.allowed_shape_families[0]
            _record_change(
                changes,
                f"$.parts[{index}].shape_family",
                "shape_family_repaired",
                before_shape,
                part["shape_family"],
            )
        before_recipe = part.get("geometry_strategy")
        if before_recipe not in rule.supported_geometry_recipes:
            part["geometry_strategy"] = rule.supported_geometry_recipes[0]
            _record_change(
                changes,
                f"$.parts[{index}].geometry_strategy",
                "geometry_recipe_repaired",
                before_recipe,
                part["geometry_strategy"],
            )
        if rule.proportion_range is not None:
            dimensions = part.get("dimensions") or {}
            ratio = dimensions.get("ratio")
            if not isinstance(ratio, list) or len(ratio) != 3:
                repaired_ratio = _midpoint(
                    rule.proportion_range.minimum,
                    rule.proportion_range.maximum,
                )
            else:
                repaired_ratio = [
                    min(
                        max(
                            float(ratio[axis]),
                            rule.proportion_range.minimum[axis],
                        ),
                        rule.proportion_range.maximum[axis],
                    )
                    for axis in range(3)
                ]
            before_dimensions = dict(dimensions)
            part["dimensions"] = {
                **dimensions,
                "size": None,
                "relative_to": parent["id"],
                "ratio": repaired_ratio,
            }
            _record_change(
                changes,
                f"$.parts[{index}].dimensions",
                "proportion_repaired",
                before_dimensions,
                part["dimensions"],
            )
        before_attachment = part.get("attachment")
        part["attachment"] = {
            "parent_id": parent["id"],
            "anchor": (
                before_attachment.get("anchor")
                if isinstance(before_attachment, dict)
                and before_attachment.get("anchor")
                in rule.allowed_attachment_anchors
                else rule.allowed_attachment_anchors[0]
            ),
            "contact_required": (
                rule.contact_required
                if rule.contact_required is not None
                else bool(
                    before_attachment.get("contact_required", True)
                    if isinstance(before_attachment, dict)
                    else True
                )
            ),
            "offset": (
                [0.0, 0.0, 0.0]
                if rule.contact_required
                else (
                    before_attachment.get("offset", [0.0, 0.0, 0.0])
                    if isinstance(before_attachment, dict)
                    else [0.0, 0.0, 0.0]
                )
            ),
        }
        _record_change(
            changes,
            f"$.parts[{index}].attachment",
            "attachment_repaired",
            before_attachment,
            part["attachment"],
        )
        before_orientation = part.get("orientation")
        part["orientation"] = rule.default_orientation.model_dump(mode="json")
        _record_change(
            changes,
            f"$.parts[{index}].orientation",
            "orientation_repaired",
            before_orientation,
            part["orientation"],
        )
        before_repetition = part.get("repetition")
        repetition_is_valid = (
            isinstance(before_repetition, dict)
            and before_repetition.get("mode")
            in rule.repetition.allowed_modes
            and rule.repetition.minimum_count
            <= int(before_repetition.get("count", 0))
            <= rule.repetition.maximum_count
            and (
                rule.repetition.axis is None
                or before_repetition.get("axis") == rule.repetition.axis
            )
        )
        if repetition_is_valid:
            part["repetition"] = before_repetition
        else:
            part["repetition"] = {
                "mode": rule.repetition.allowed_modes[0],
                "count": rule.repetition.minimum_count,
                "axis": rule.repetition.axis,
                **(
                    {"instance_role": before_repetition.get("instance_role")}
                    if isinstance(before_repetition, dict)
                    and before_repetition.get("instance_role")
                    else {}
                ),
            }
        _record_change(
            changes,
            f"$.parts[{index}].repetition",
            "repetition_repaired",
            before_repetition,
            part["repetition"],
        )

    children_by_parent = {part["id"]: [] for part in repaired["parts"]}
    for part in repaired["parts"]:
        if part.get("parent_id") in children_by_parent:
            children_by_parent[part["parent_id"]].append(part["id"])
    for index, part in enumerate(repaired["parts"]):
        before_children = part.get("children", [])
        part["children"] = children_by_parent[part["id"]]
        _record_change(
            changes,
            f"$.parts[{index}].children",
            "children_rebuilt",
            before_children,
            part["children"],
        )
    required_roles = [
        rule.role
        for rule in archetype.roles
        if rule.requirement == "required"
    ]
    _record_change(
        changes,
        "$.required_roles",
        "required_roles_repaired",
        repaired["required_roles"],
        required_roles,
    )
    repaired["required_roles"] = required_roles
    existing_ids = {part["id"] for part in repaired["parts"]}
    required_part_ids = [
        part["id"]
        for part in repaired["parts"]
        if part["role"] in required_roles
    ]
    for index, constraint in enumerate(repaired.get("constraints", [])):
        before_targets = list(constraint.get("targets", []))
        if constraint.get("type") == "connected" and constraint.get(
            "required",
            True,
        ):
            constraint["targets"] = required_part_ids
        else:
            constraint["targets"] = [
                target
                for target in before_targets
                if target in existing_ids
            ]
        _record_change(
            changes,
            f"$.constraints[{index}].targets",
            "constraint_targets_repaired",
            before_targets,
            constraint["targets"],
        )
    validated = HierarchicalAssetIntent.model_validate(repaired)
    return validated.model_dump(mode="json"), changes
