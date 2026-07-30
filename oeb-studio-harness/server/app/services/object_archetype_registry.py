from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.hierarchical_asset_intent import (
    HierarchicalAssetIntent,
    HierarchicalIntentDiagnostic,
)
from app.schemas.object_archetype_registry import (
    ArchetypeGroundingChange,
    ArchetypeGroundingResult,
    ObjectArchetype,
    ObjectArchetypeRegistry,
)
from app.services.geometry_recipe_compiler import (
    SUPPORTED_GEOMETRY_RECIPE_EXECUTORS,
)


DEFAULT_OBJECT_ARCHETYPE_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "registries"
    / "object_archetypes_v1.json"
)


def load_object_archetype_registry(
    path: Path | None = None,
) -> ObjectArchetypeRegistry:
    registry_path = path or DEFAULT_OBJECT_ARCHETYPE_REGISTRY_PATH
    registry = ObjectArchetypeRegistry.model_validate_json(registry_path.read_text())
    _validate_registry_integrity(registry)
    return registry


def _validate_registry_integrity(registry: ObjectArchetypeRegistry) -> None:
    recipe_by_id = {}
    for recipe in registry.geometry_recipes:
        if recipe.id in recipe_by_id:
            raise ValueError(f"duplicate geometry recipe id: {recipe.id}")
        recipe_by_id[recipe.id] = recipe
        if recipe.status == "available" and not recipe.compiler:
            raise ValueError(
                f"available geometry recipe '{recipe.id}' requires a compiler"
            )
        if (
            recipe.status == "available"
            and recipe.compiler not in SUPPORTED_GEOMETRY_RECIPE_EXECUTORS
        ):
            raise ValueError(
                f"geometry recipe '{recipe.id}' references unknown compiler "
                f"'{recipe.compiler}'"
            )

    archetype_ids: set[str] = set()
    family_names: set[str] = set()
    for archetype in registry.archetypes:
        if archetype.id in archetype_ids:
            raise ValueError(f"duplicate archetype id: {archetype.id}")
        archetype_ids.add(archetype.id)
        family_keys = {archetype.family, *archetype.aliases}
        duplicates = family_names.intersection(family_keys)
        if duplicates:
            raise ValueError(
                f"duplicate archetype family or alias: {sorted(duplicates)[0]}"
            )
        family_names.update(family_keys)

        role_by_name = {}
        aliases: set[str] = set()
        for role in archetype.roles:
            if role.role in role_by_name:
                raise ValueError(
                    f"duplicate role '{role.role}' in archetype '{archetype.id}'"
                )
            role_by_name[role.role] = role
            role_keys = {role.role, *role.aliases}
            duplicate_aliases = aliases.intersection(role_keys)
            if duplicate_aliases:
                raise ValueError(
                    f"duplicate role alias '{sorted(duplicate_aliases)[0]}' "
                    f"in archetype '{archetype.id}'"
                )
            aliases.update(role_keys)
            if (
                role.proportion_range is not None
                and any(
                    minimum > maximum
                    for minimum, maximum in zip(
                        role.proportion_range.minimum,
                        role.proportion_range.maximum,
                    )
                )
            ):
                raise ValueError(
                    f"inverted proportion range for role '{role.role}'"
                )
            if role.repetition.minimum_count > role.repetition.maximum_count:
                raise ValueError(
                    f"inverted repetition range for role '{role.role}'"
                )
            unknown_recipes = (
                set(role.supported_geometry_recipes) - set(recipe_by_id)
            )
            if unknown_recipes:
                raise ValueError(
                    f"role '{role.role}' references unknown geometry recipe "
                    f"'{sorted(unknown_recipes)[0]}'"
                )

        if archetype.root_role not in role_by_name:
            raise ValueError(
                f"root role '{archetype.root_role}' is missing from '{archetype.id}'"
            )
        known_roles = set(role_by_name)
        for role in archetype.roles:
            unknown_parents = set(role.allowed_parent_roles) - known_roles
            if unknown_parents:
                raise ValueError(
                    f"role '{role.role}' references unknown parent role "
                    f"'{sorted(unknown_parents)[0]}'"
                )
            if (
                role.proportion_range is not None
                and role.proportion_range.relative_to_role not in known_roles
            ):
                raise ValueError(
                    f"role '{role.role}' references unknown proportion role "
                    f"'{role.proportion_range.relative_to_role}'"
                )


def find_object_archetype(
    family: str,
    registry: ObjectArchetypeRegistry | None = None,
) -> ObjectArchetype | None:
    selected_registry = registry or load_object_archetype_registry()
    normalized = family.strip().lower().replace("-", "_").replace(" ", "_")
    for archetype in selected_registry.archetypes:
        if normalized in {archetype.family, *archetype.aliases}:
            return archetype
    return None


def unavailable_geometry_recipes(
    intent: HierarchicalAssetIntent,
    registry: ObjectArchetypeRegistry | None = None,
) -> list[str]:
    selected_registry = registry or load_object_archetype_registry()
    recipe_by_id = {
        recipe.id: recipe
        for recipe in selected_registry.geometry_recipes
    }
    unavailable = {
        part.geometry_strategy
        for part in intent.parts
        if (
            part.geometry_strategy
            and (
                part.geometry_strategy not in recipe_by_id
                or recipe_by_id[part.geometry_strategy].status != "available"
                or not recipe_by_id[part.geometry_strategy].compiler
                or recipe_by_id[part.geometry_strategy].compiler
                not in SUPPORTED_GEOMETRY_RECIPE_EXECUTORS
            )
        )
    }
    return sorted(unavailable)


def _diagnostic(
    stage: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    part_id: str | None = None,
    details: dict | None = None,
) -> HierarchicalIntentDiagnostic:
    return HierarchicalIntentDiagnostic(
        stage=stage,
        code=code,
        message=message,
        path=path,
        part_id=part_id,
        details=details or {},
    )


def _change(
    path: str,
    code: str,
    before,
    after,
) -> ArchetypeGroundingChange:
    return ArchetypeGroundingChange(
        path=path,
        code=code,
        before=before,
        after=after,
    )


def ground_hierarchy_against_archetype(
    value: dict,
    registry: ObjectArchetypeRegistry | None = None,
) -> ArchetypeGroundingResult:
    selected_registry = registry or load_object_archetype_registry()
    try:
        intent = HierarchicalAssetIntent.model_validate(value)
    except ValidationError as exc:
        return ArchetypeGroundingResult(
            valid=False,
            outcome="invalid",
            registry_version=selected_registry.registry_version,
            diagnostics=[
                _diagnostic(
                    "contract",
                    "hierarchical_contract_invalid",
                    str(error.get("msg") or "Invalid hierarchical asset intent."),
                    path="$.hierarchical_asset_intent"
                    + "".join(
                        f"[{segment}]" if isinstance(segment, int) else f".{segment}"
                        for segment in error.get("loc", ())
                    ),
                )
                for error in exc.errors(include_url=False)
            ],
        )

    archetype = find_object_archetype(intent.object_family, selected_registry)
    if archetype is None:
        return ArchetypeGroundingResult(
            valid=False,
            outcome="unsupported",
            registry_version=selected_registry.registry_version,
            intent=intent,
            diagnostics=[_diagnostic(
                "object_family",
                "object_archetype_not_found",
                f"No registered object archetype matches '{intent.object_family}'.",
                path="$.hierarchical_asset_intent.object_family",
                details={"object_family": intent.object_family},
            )],
        )

    grounded = intent.model_dump(mode="json")
    changes: list[ArchetypeGroundingChange] = []
    if grounded["object_family"] != archetype.family:
        changes.append(_change(
            "$.hierarchical_asset_intent.object_family",
            "object_family_alias_resolved",
            grounded["object_family"],
            archetype.family,
        ))
        grounded["object_family"] = archetype.family

    role_by_name = {role.role: role for role in archetype.roles}
    role_aliases = {
        alias: role.role
        for role in archetype.roles
        for alias in [role.role, *role.aliases]
    }
    for index, part in enumerate(grounded["parts"]):
        before = part["role"]
        normalized_role = role_aliases.get(before)
        if normalized_role and normalized_role != before:
            part["role"] = normalized_role
            changes.append(_change(
                f"$.hierarchical_asset_intent.parts[{index}].role",
                "role_alias_resolved",
                before,
                normalized_role,
            ))

    canonical_required_roles = [
        role.role for role in archetype.roles if role.requirement == "required"
    ]
    if grounded["required_roles"] != canonical_required_roles:
        changes.append(_change(
            "$.hierarchical_asset_intent.required_roles",
            "required_roles_grounded_from_archetype",
            grounded["required_roles"],
            canonical_required_roles,
        ))
    grounded["required_roles"] = canonical_required_roles
    grounded_intent = HierarchicalAssetIntent.model_validate(grounded)

    diagnostics: list[HierarchicalIntentDiagnostic] = []
    parts_by_id = {part.id: part for part in grounded_intent.parts}
    roles_to_parts: dict[str, list] = {}
    for part in grounded_intent.parts:
        roles_to_parts.setdefault(part.role, []).append(part)

    missing_required_roles = [
        role for role in canonical_required_roles if role not in roles_to_parts
    ]
    if missing_required_roles:
        diagnostics.append(_diagnostic(
            "object_family",
            "archetype_required_roles_missing",
            "The hierarchy is missing roles required by its registered object family.",
            path="$.hierarchical_asset_intent.parts",
            details={"missing_roles": missing_required_roles},
        ))

    root = parts_by_id.get(grounded_intent.root_part_id)
    if root is not None and root.role != archetype.root_role:
        diagnostics.append(_diagnostic(
            "object_family",
            "archetype_root_role_mismatch",
            "The hierarchy root does not use the archetype root role.",
            part_id=root.id,
            details={
                "actual_role": root.role,
                "expected_role": archetype.root_role,
            },
        ))

    for index, part in enumerate(grounded_intent.parts):
        path = f"$.hierarchical_asset_intent.parts[{index}]"
        rule = role_by_name.get(part.role)
        if rule is None:
            diagnostics.append(_diagnostic(
                "object_family",
                "archetype_role_unknown",
                f"Role '{part.role}' is not registered for this object family.",
                path=f"{path}.role",
                part_id=part.id,
            ))
            continue

        parent = parts_by_id.get(part.parent_id) if part.parent_id else None
        parent_role = parent.role if parent is not None else None
        if parent_role not in rule.allowed_parent_roles:
            if not (part.role == archetype.root_role and parent_role is None):
                diagnostics.append(_diagnostic(
                    "hierarchy",
                    "archetype_parent_role_invalid",
                    "The part is attached beneath a role not allowed by its archetype.",
                    path=f"{path}.parent_id",
                    part_id=part.id,
                    details={
                        "parent_role": parent_role,
                        "allowed_parent_roles": rule.allowed_parent_roles,
                    },
                ))

        if part.shape_family not in rule.allowed_shape_families:
            diagnostics.append(_diagnostic(
                "object_family",
                "archetype_shape_family_unsupported",
                "The part shape family is not supported for its archetype role.",
                path=f"{path}.shape_family",
                part_id=part.id,
                details={
                    "shape_family": part.shape_family,
                    "allowed_shape_families": rule.allowed_shape_families,
                },
            ))
        if part.geometry_strategy not in rule.supported_geometry_recipes:
            diagnostics.append(_diagnostic(
                "object_family",
                "archetype_geometry_recipe_unsupported",
                "The part geometry strategy is not supported for its archetype role.",
                path=f"{path}.geometry_strategy",
                part_id=part.id,
                details={
                    "geometry_strategy": part.geometry_strategy,
                    "supported_geometry_recipes": rule.supported_geometry_recipes,
                },
            ))

        if part.role != archetype.root_role:
            if (
                part.attachment is not None
                and part.attachment.anchor not in rule.allowed_attachment_anchors
            ):
                diagnostics.append(_diagnostic(
                    "attachments",
                    "archetype_attachment_anchor_invalid",
                    "The semantic attachment anchor is not allowed for this role.",
                    path=f"{path}.attachment.anchor",
                    part_id=part.id,
                    details={
                        "anchor": part.attachment.anchor,
                        "allowed_anchors": rule.allowed_attachment_anchors,
                    },
                ))
            if (
                part.attachment is not None
                and rule.contact_required is not None
                and part.attachment.contact_required != rule.contact_required
            ):
                diagnostics.append(_diagnostic(
                    "attachments",
                    "archetype_contact_rule_mismatch",
                    "The part contact requirement does not match its archetype role.",
                    path=f"{path}.attachment.contact_required",
                    part_id=part.id,
                    details={
                        "contact_required": part.attachment.contact_required,
                        "expected_contact_required": rule.contact_required,
                    },
                ))

        expected_orientation = rule.default_orientation
        if (
            part.orientation.forward != expected_orientation.forward
            or part.orientation.up != expected_orientation.up
        ):
            diagnostics.append(_diagnostic(
                "orientation",
                "archetype_orientation_mismatch",
                "The part orientation does not match its archetype role.",
                path=f"{path}.orientation",
                part_id=part.id,
                details={
                    "expected": expected_orientation.model_dump(mode="json"),
                    "actual": part.orientation.model_dump(mode="json"),
                },
            ))

        repetition = rule.repetition
        if part.repetition.mode not in repetition.allowed_modes:
            diagnostics.append(_diagnostic(
                "object_family",
                "archetype_repetition_mode_invalid",
                "The repetition mode is not allowed for this archetype role.",
                path=f"{path}.repetition.mode",
                part_id=part.id,
                details={
                    "mode": part.repetition.mode,
                    "allowed_modes": repetition.allowed_modes,
                },
            ))
        if not (
            repetition.minimum_count
            <= part.repetition.count
            <= repetition.maximum_count
        ):
            diagnostics.append(_diagnostic(
                "object_family",
                "archetype_repetition_count_invalid",
                "The repetition count is outside the archetype range.",
                path=f"{path}.repetition.count",
                part_id=part.id,
                details={
                    "count": part.repetition.count,
                    "minimum": repetition.minimum_count,
                    "maximum": repetition.maximum_count,
                },
            ))
        if repetition.axis is not None and part.repetition.axis != repetition.axis:
            diagnostics.append(_diagnostic(
                "orientation",
                "archetype_repetition_axis_invalid",
                "The repetition axis does not match the archetype role.",
                path=f"{path}.repetition.axis",
                part_id=part.id,
                details={
                    "axis": part.repetition.axis,
                    "expected_axis": repetition.axis,
                },
            ))

        proportion = rule.proportion_range
        if proportion is not None:
            if part.dimensions.ratio is None:
                diagnostics.append(_diagnostic(
                    "proportions",
                    "archetype_ratio_missing",
                    "This archetype role requires a parent-relative proportion.",
                    path=f"{path}.dimensions.ratio",
                    part_id=part.id,
                    details={
                        "relative_to_role": proportion.relative_to_role,
                    },
                ))
            else:
                invalid_axes = [
                    axis
                    for axis, (ratio, minimum, maximum) in enumerate(zip(
                        part.dimensions.ratio,
                        proportion.minimum,
                        proportion.maximum,
                    ))
                    if ratio < minimum or ratio > maximum
                ]
                if invalid_axes:
                    diagnostics.append(_diagnostic(
                        "proportions",
                        "archetype_ratio_out_of_range",
                        "The part proportion is outside its archetype range.",
                        path=f"{path}.dimensions.ratio",
                        part_id=part.id,
                        details={
                            "axis_indices": invalid_axes,
                            "minimum": proportion.minimum,
                            "maximum": proportion.maximum,
                            "actual": part.dimensions.ratio,
                        },
                    ))
                if parent_role != proportion.relative_to_role:
                    diagnostics.append(_diagnostic(
                        "proportions",
                        "archetype_ratio_reference_role_invalid",
                        "The part ratio is not relative to the archetype's expected role.",
                        path=f"{path}.dimensions.relative_to",
                        part_id=part.id,
                        details={
                            "parent_role": parent_role,
                            "expected_role": proportion.relative_to_role,
                        },
                    ))

    return ArchetypeGroundingResult(
        valid=not diagnostics,
        outcome="valid" if not diagnostics else "needs_repair",
        registry_version=selected_registry.registry_version,
        archetype_id=archetype.id,
        archetype=archetype,
        intent=grounded_intent,
        changes=changes,
        diagnostics=diagnostics,
    )
