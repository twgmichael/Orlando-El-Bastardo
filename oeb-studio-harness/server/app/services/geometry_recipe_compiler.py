from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from app.schemas.conversation import PrimitiveInstance
from app.schemas.geometry_recipe import (
    GeometryRecipeCompileResult,
    GeometryRecipeDiagnostic,
    ResolvedRecipePart,
)
from app.schemas.hierarchical_asset_intent import (
    HierarchicalAssetIntent,
    HierarchicalPart,
)
from app.schemas.object_archetype_registry import ObjectArchetypeRegistry


GEOMETRY_RECIPE_COMPILER_VERSION = "1.0"
SUPPORTED_PRIMITIVE_TYPES = {"box", "cylinder", "sphere"}
_DIRECTION_VECTORS = {
    "front": [1.0, 0.0, 0.0],
    "rear": [-1.0, 0.0, 0.0],
    "left": [0.0, -1.0, 0.0],
    "right": [0.0, 1.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "down": [0.0, 0.0, -1.0],
}
_DIRECTION_AXIS = {
    "front": 0,
    "rear": 0,
    "left": 1,
    "right": 1,
    "up": 2,
    "down": 2,
}


def _add(left: list[float], right: list[float]) -> list[float]:
    return [left[index] + right[index] for index in range(3)]


def _multiply(vector: list[float], scalar: float) -> list[float]:
    return [component * scalar for component in vector]


def _box_scale(dimensions: list[float]) -> list[float]:
    return [component / 2.0 for component in dimensions]


def _primitive(
    *,
    primitive_id: str,
    primitive_type: str,
    material: str,
    location: list[float],
    dimensions: list[float],
    rotation: list[float] | None,
    recipe_id: str,
    part: HierarchicalPart,
    modifiers: list[str] | None = None,
    cylinder_axis: str = "front",
) -> PrimitiveInstance:
    if primitive_type == "cylinder":
        length_axis = _DIRECTION_AXIS[cylinder_axis]
        radial_axes = [axis for axis in range(3) if axis != length_axis]
        scale = [
            dimensions[radial_axes[0]] / 2.0,
            dimensions[radial_axes[1]] / 2.0,
            dimensions[length_axis] / 2.0,
        ]
    else:
        scale = _box_scale(dimensions)
    return PrimitiveInstance.model_validate({
        "id": primitive_id,
        "type": primitive_type,
        "label": part.name,
        "material": material,
        "transform": {
            "location": location,
            "rotation": rotation or [0.0, 0.0, 0.0],
            "scale": scale,
        },
        "params": {
            "geometry_recipe": recipe_id,
            "semantic_part_id": part.id,
            "semantic_role": part.role,
            "shape_description": part.shape_family or part.name,
            "shape_modifiers": modifiers or [],
        },
    })


def _material(part: HierarchicalPart) -> str:
    if isinstance(part.material, str) and part.material.strip():
        return part.material.strip()
    if isinstance(part.material, dict):
        for key in ("primary", "name", "type"):
            value = part.material.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "neutral"


def _recipe_parameters(part: HierarchicalPart, defaults: dict[str, Any]) -> dict[str, Any]:
    metadata = part.metadata if isinstance(part.metadata, dict) else {}
    supplied = metadata.get("recipe_parameters")
    return {
        **defaults,
        **(supplied if isinstance(supplied, dict) else {}),
    }


def _primitive_type(
    parameters: dict[str, Any],
    *,
    fallback: str,
) -> str:
    value = str(parameters.get("primitive_type") or fallback).strip().lower()
    if value not in SUPPORTED_PRIMITIVE_TYPES:
        raise ValueError(
            f"primitive_type must be one of {sorted(SUPPORTED_PRIMITIVE_TYPES)}"
        )
    return value


def _direction_rotation(direction: str) -> list[float]:
    return {
        "up": [0.0, 0.0, 0.0],
        "down": [math.pi, 0.0, 0.0],
        "front": [0.0, math.pi / 2.0, 0.0],
        "rear": [0.0, -math.pi / 2.0, 0.0],
        "right": [-math.pi / 2.0, 0.0, 0.0],
        "left": [math.pi / 2.0, 0.0, 0.0],
    }[direction]


def _group_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    return [], centers


def _compound_body_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    primitive_type = _primitive_type(parameters, fallback="box")
    lower_fraction = float(parameters.get("lower_height_fraction", 0.58))
    if not 0.2 <= lower_fraction <= 0.8:
        raise ValueError("lower_height_fraction must be between 0.2 and 0.8")
    taper = float(parameters.get("upper_taper", 0.82))
    if not 0.4 <= taper <= 1.0:
        raise ValueError("upper_taper must be between 0.4 and 1.0")
    material = _material(part)
    primitives = []
    lower_height = dimensions[2] * lower_fraction
    upper_height = dimensions[2] - lower_height
    for index, center in enumerate(centers, start=1):
        lower_center = _add(
            center,
            [0.0, 0.0, -(dimensions[2] - lower_height) / 2.0],
        )
        upper_center = _add(
            center,
            [0.0, 0.0, (dimensions[2] - upper_height) / 2.0],
        )
        prefix = f"{part.id}_{index}" if len(centers) > 1 else part.id
        primitives.extend([
            _primitive(
                primitive_id=f"{prefix}_lower",
                primitive_type=primitive_type,
                material=material,
                location=lower_center,
                dimensions=[dimensions[0], dimensions[1], lower_height],
                rotation=None,
                recipe_id=recipe_id,
                part=part,
                modifiers=["beveled"],
                cylinder_axis="up",
            ),
            _primitive(
                primitive_id=f"{prefix}_upper",
                primitive_type=primitive_type,
                material=material,
                location=upper_center,
                dimensions=[
                    dimensions[0] * taper,
                    dimensions[1] * taper,
                    upper_height,
                ],
                rotation=None,
                recipe_id=recipe_id,
                part=part,
                modifiers=["tapered"],
                cylinder_axis="up",
            ),
        ])
    return primitives, centers


def _shaped_shell_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    primitive_type = _primitive_type(parameters, fallback="sphere")
    material = _material(part)
    modifiers = [
        str(value)
        for value in parameters.get("shape_modifiers", ["rounded"])
        if str(value).strip()
    ]
    primitives = [
        _primitive(
            primitive_id=(
                f"{part.id}_{index}" if len(centers) > 1 else part.id
            ),
            primitive_type=primitive_type,
            material=material,
            location=center,
            dimensions=dimensions,
            rotation=None,
            recipe_id=recipe_id,
            part=part,
            modifiers=modifiers,
            cylinder_axis="up",
        )
        for index, center in enumerate(centers, start=1)
    ]
    return primitives, centers


def _mirrored_system_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    if part.repetition.mode != "mirror" or part.repetition.count != 2:
        raise ValueError("mirrored_system requires repetition mode mirror and count 2")
    direction = part.repetition.axis
    if direction not in _DIRECTION_VECTORS:
        raise ValueError("mirrored_system requires a semantic repetition axis")
    primitive_type = _primitive_type(parameters, fallback="box")
    thickness_fraction = float(parameters.get("thickness_fraction", 0.18))
    if not 0.05 <= thickness_fraction <= 0.45:
        raise ValueError("thickness_fraction must be between 0.05 and 0.45")
    axis = _DIRECTION_AXIS[direction]
    item_dimensions = list(dimensions)
    item_dimensions[axis] *= thickness_fraction
    distance = (dimensions[axis] - item_dimensions[axis]) / 2.0
    vector = _DIRECTION_VECTORS[direction]
    expanded_centers = []
    for center in centers:
        expanded_centers.extend([
            _add(center, _multiply(vector, -distance)),
            _add(center, _multiply(vector, distance)),
        ])
    material = _material(part)
    rotation = (
        _direction_rotation(direction)
        if primitive_type == "cylinder"
        else [0.0, 0.0, 0.0]
    )
    primitives = [
        _primitive(
            primitive_id=f"{part.id}_{index}",
            primitive_type=primitive_type,
            material=material,
            location=center,
            dimensions=item_dimensions,
            rotation=rotation,
            recipe_id=recipe_id,
            part=part,
            modifiers=["mirrored"],
            cylinder_axis=direction,
        )
        for index, center in enumerate(expanded_centers, start=1)
    ]
    return primitives, expanded_centers


def _repeated_array_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    if part.repetition.mode not in {"linear", "radial"}:
        raise ValueError("repeated_array requires linear or radial repetition")
    count = part.repetition.count
    if count < 2:
        raise ValueError("repeated_array requires at least two instances")
    primitive_type = _primitive_type(parameters, fallback="cylinder")
    direction = part.repetition.axis
    if direction not in _DIRECTION_VECTORS:
        raise ValueError("repeated_array requires a semantic repetition axis")
    expanded_centers = []
    if part.repetition.mode == "linear":
        vector = _DIRECTION_VECTORS[direction]
        axis = _DIRECTION_AXIS[direction]
        spacing = (
            part.repetition.spacing
            or float(parameters.get("spacing", dimensions[axis] * 1.2))
        )
        for center in centers:
            expanded_centers.extend([
                _add(
                    center,
                    _multiply(vector, (index - (count - 1) / 2.0) * spacing),
                )
                for index in range(count)
            ])
    else:
        axis = _DIRECTION_AXIS[direction]
        radius = float(
            parameters.get(
                "radius",
                max(dimensions[(axis + 1) % 3], dimensions[(axis + 2) % 3]) * 1.5,
            )
        )
        if radius <= 0:
            raise ValueError("radial array radius must be positive")
        plane_axes = [candidate for candidate in range(3) if candidate != axis]
        for center in centers:
            for index in range(count):
                angle = 2.0 * math.pi * index / count
                offset = [0.0, 0.0, 0.0]
                offset[plane_axes[0]] = math.cos(angle) * radius
                offset[plane_axes[1]] = math.sin(angle) * radius
                expanded_centers.append(_add(center, offset))
    material = _material(part)
    item_axis = str(parameters.get("item_axis") or direction)
    if item_axis not in _DIRECTION_VECTORS:
        raise ValueError("item_axis must be a semantic direction")
    rotation = (
        _direction_rotation(item_axis)
        if primitive_type == "cylinder"
        else [0.0, 0.0, 0.0]
    )
    primitives = [
        _primitive(
            primitive_id=f"{part.id}_{index}",
            primitive_type=primitive_type,
            material=material,
            location=center,
            dimensions=dimensions,
            rotation=rotation,
            recipe_id=recipe_id,
            part=part,
            modifiers=[part.repetition.mode],
            cylinder_axis=item_axis,
        )
        for index, center in enumerate(expanded_centers, start=1)
    ]
    return primitives, expanded_centers


def _stacked_sections_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    primitive_type = _primitive_type(parameters, fallback="box")
    count = int(parameters.get("sections", part.repetition.count))
    if count < 2 or count > 32:
        raise ValueError("stacked_sections requires between 2 and 32 sections")
    gap_fraction = float(parameters.get("gap_fraction", 0.04))
    if not 0.0 <= gap_fraction <= 0.25:
        raise ValueError("gap_fraction must be between 0 and 0.25")
    section_height = dimensions[2] / count
    visible_height = section_height * (1.0 - gap_fraction)
    expanded_centers = []
    primitives = []
    material = _material(part)
    for parent_index, center in enumerate(centers, start=1):
        for section_index in range(count):
            section_center = _add(center, [
                0.0,
                0.0,
                -dimensions[2] / 2.0
                + section_height * (section_index + 0.5),
            ])
            expanded_centers.append(section_center)
            primitives.append(_primitive(
                primitive_id=(
                    f"{part.id}_{parent_index}_{section_index + 1}"
                    if len(centers) > 1
                    else f"{part.id}_{section_index + 1}"
                ),
                primitive_type=primitive_type,
                material=material,
                location=section_center,
                dimensions=[dimensions[0], dimensions[1], visible_height],
                rotation=None,
                recipe_id=recipe_id,
                part=part,
                modifiers=["stacked"],
                cylinder_axis="up",
            ))
    return primitives, expanded_centers


def _attached_directional_executor(
    part: HierarchicalPart,
    recipe_id: str,
    dimensions: list[float],
    centers: list[list[float]],
    parameters: dict[str, Any],
) -> tuple[list[PrimitiveInstance], list[list[float]]]:
    primitive_type = _primitive_type(parameters, fallback="cylinder")
    direction = part.orientation.forward
    material = _material(part)
    rotation = (
        _direction_rotation(direction)
        if primitive_type == "cylinder"
        else [0.0, 0.0, 0.0]
    )
    primitives = [
        _primitive(
            primitive_id=(
                f"{part.id}_{index}" if len(centers) > 1 else part.id
            ),
            primitive_type=primitive_type,
            material=material,
            location=center,
            dimensions=dimensions,
            rotation=rotation,
            recipe_id=recipe_id,
            part=part,
            modifiers=["directional"],
            cylinder_axis=direction,
        )
        for index, center in enumerate(centers, start=1)
    ]
    return primitives, centers


RecipeExecutor = Callable[
    [
        HierarchicalPart,
        str,
        list[float],
        list[list[float]],
        dict[str, Any],
    ],
    tuple[list[PrimitiveInstance], list[list[float]]],
]

GEOMETRY_RECIPE_EXECUTORS: dict[str, RecipeExecutor] = {
    "group": _group_executor,
    "compound_body": _compound_body_executor,
    "shaped_shell": _shaped_shell_executor,
    "mirrored_system": _mirrored_system_executor,
    "repeated_array": _repeated_array_executor,
    "stacked_sections": _stacked_sections_executor,
    "attached_directional": _attached_directional_executor,
}
SUPPORTED_GEOMETRY_RECIPE_EXECUTORS = frozenset(GEOMETRY_RECIPE_EXECUTORS)


def _resolve_dimensions(
    part: HierarchicalPart,
    dimensions_by_part: dict[str, list[float]],
) -> list[float]:
    if part.dimensions.size is not None:
        return list(part.dimensions.size)
    reference_id = part.dimensions.relative_to or part.parent_id
    if (
        reference_id is None
        or reference_id not in dimensions_by_part
        or part.dimensions.ratio is None
    ):
        raise ValueError("part dimensions are not resolvable from its parent")
    return [
        dimensions_by_part[reference_id][index] * part.dimensions.ratio[index]
        for index in range(3)
    ]


def _anchor_center(
    parent_center: list[float],
    parent_dimensions: list[float],
    child_dimensions: list[float],
    part: HierarchicalPart,
) -> list[float]:
    attachment = part.attachment
    if attachment is None:
        return list(parent_center)
    anchor = attachment.anchor
    offset = list(attachment.offset)
    center = list(parent_center)
    if anchor == "top_center":
        center[2] += parent_dimensions[2] / 2.0 + child_dimensions[2] / 2.0
    elif anchor == "bottom_center":
        center[2] -= parent_dimensions[2] / 2.0 + child_dimensions[2] / 2.0
    elif anchor == "front_center":
        center[0] += parent_dimensions[0] / 2.0 + child_dimensions[0] / 2.0
    elif anchor == "rear_center":
        center[0] -= parent_dimensions[0] / 2.0 + child_dimensions[0] / 2.0
    elif anchor == "left_side":
        center[1] -= parent_dimensions[1] / 2.0 + child_dimensions[1] / 2.0
    elif anchor == "right_side":
        center[1] += parent_dimensions[1] / 2.0 + child_dimensions[1] / 2.0
    return _add(center, offset)


def _ordered_parts(intent: HierarchicalAssetIntent) -> list[HierarchicalPart]:
    parts_by_id = {part.id: part for part in intent.parts}
    ordered = []

    def visit(part_id: str) -> None:
        part = parts_by_id[part_id]
        ordered.append(part)
        for child_id in part.children:
            visit(child_id)

    visit(intent.root_part_id)
    return ordered


def compile_hierarchical_geometry(
    intent: HierarchicalAssetIntent,
    registry: ObjectArchetypeRegistry,
) -> GeometryRecipeCompileResult:
    recipe_by_id = {recipe.id: recipe for recipe in registry.geometry_recipes}
    dimensions_by_part: dict[str, list[float]] = {}
    centers_by_part: dict[str, list[list[float]]] = {}
    primitives: list[PrimitiveInstance] = []
    resolved_parts: list[ResolvedRecipePart] = []
    diagnostics: list[GeometryRecipeDiagnostic] = []
    used_recipes: list[str] = []
    used_executors: list[str] = []

    for part in _ordered_parts(intent):
        recipe_id = part.geometry_strategy or ""
        recipe = recipe_by_id.get(recipe_id)
        if (
            recipe is None
            or recipe.status != "available"
            or not recipe.compiler
            or recipe.compiler not in GEOMETRY_RECIPE_EXECUTORS
        ):
            diagnostics.append(GeometryRecipeDiagnostic(
                code="geometry_recipe_unavailable",
                message="The semantic part has no available deterministic executor.",
                recipe_id=recipe_id or None,
                part_id=part.id,
                path=f"parts.{part.id}.geometry_strategy",
            ))
            continue
        try:
            dimensions = _resolve_dimensions(part, dimensions_by_part)
            if part.parent_id is None:
                base_centers = [[0.0, 0.0, dimensions[2] / 2.0]]
            else:
                parent_dimensions = dimensions_by_part[part.parent_id]
                parent_centers = centers_by_part[part.parent_id]
                base_centers = [
                    _anchor_center(
                        parent_center,
                        parent_dimensions,
                        dimensions,
                        part,
                    )
                    for parent_center in parent_centers
                ]
            parameters = _recipe_parameters(part, recipe.defaults)
            executor = GEOMETRY_RECIPE_EXECUTORS[recipe.compiler]
            compiled, logical_centers = executor(
                part,
                recipe_id,
                dimensions,
                base_centers,
                parameters,
            )
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append(GeometryRecipeDiagnostic(
                code="geometry_recipe_parameters_invalid",
                message=str(exc),
                recipe_id=recipe_id,
                part_id=part.id,
                path=f"parts.{part.id}.metadata.recipe_parameters",
            ))
            continue

        dimensions_by_part[part.id] = dimensions
        centers_by_part[part.id] = logical_centers
        primitives.extend(compiled)
        resolved_parts.append(ResolvedRecipePart(
            part_id=part.id,
            recipe_id=recipe_id,
            executor=recipe.compiler,
            dimensions=dimensions,
            centers=logical_centers,
            primitive_ids=[primitive.id for primitive in compiled],
        ))
        if recipe_id not in used_recipes:
            used_recipes.append(recipe_id)
        if recipe.compiler not in used_executors:
            used_executors.append(recipe.compiler)

    primitive_ids = [primitive.id for primitive in primitives]
    if len(primitive_ids) != len(set(primitive_ids)):
        diagnostics.append(GeometryRecipeDiagnostic(
            code="compiled_primitive_ids_duplicate",
            message="Geometry recipe expansion produced duplicate primitive ids.",
        ))
    if diagnostics:
        unavailable = any(
            diagnostic.code == "geometry_recipe_unavailable"
            for diagnostic in diagnostics
        )
        return GeometryRecipeCompileResult(
            valid=False,
            outcome="unsupported" if unavailable else "needs_repair",
            compiler_version=GEOMETRY_RECIPE_COMPILER_VERSION,
            diagnostics=diagnostics,
            primitives=primitives,
            resolved_parts=resolved_parts,
            used_recipes=used_recipes,
            used_executors=used_executors,
        )
    return GeometryRecipeCompileResult(
        valid=True,
        outcome="compiled",
        compiler_version=GEOMETRY_RECIPE_COMPILER_VERSION,
        primitives=primitives,
        resolved_parts=resolved_parts,
        used_recipes=used_recipes,
        used_executors=used_executors,
    )
