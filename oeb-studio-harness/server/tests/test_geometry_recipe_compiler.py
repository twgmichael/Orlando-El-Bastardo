import inspect
import json
import math
from pathlib import Path

import pytest

from app.schemas.hierarchical_asset_intent import HierarchicalAssetIntent
from app.services.geometry_recipe_compiler import (
    SUPPORTED_GEOMETRY_RECIPE_EXECUTORS,
    compile_hierarchical_geometry,
)
from app.services.hierarchical_asset_intent import validate_hierarchical_asset_intent
from app.services.object_archetype_registry import load_object_archetype_registry
import app.services.geometry_recipe_compiler as compiler_module


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "geometry_recipe_intents"
FIXTURES = [
    "tracked_machine.json",
    "double_decker_transit.json",
    "observation_tower.json",
]
EXPECTED_EXECUTORS = {
    "group",
    "compound_body",
    "shaped_shell",
    "mirrored_system",
    "repeated_array",
    "stacked_sections",
    "attached_directional",
}


def _load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.mark.parametrize("fixture_name", FIXTURES)
def test_shared_recipe_layer_compiles_each_unrelated_family(fixture_name):
    source = _load_fixture(fixture_name)
    validation = validate_hierarchical_asset_intent(source)

    assert validation.valid is True

    result = compile_hierarchical_geometry(
        validation.intent,
        load_object_archetype_registry(),
    )

    assert result.outcome == "compiled"
    assert result.valid is True
    assert set(result.used_executors) == EXPECTED_EXECUTORS
    assert len(result.primitives) >= 14
    assert len({primitive.id for primitive in result.primitives}) == len(
        result.primitives
    )
    assert all(
        math.isfinite(value)
        for primitive in result.primitives
        for values in (
            primitive.transform.location,
            primitive.transform.rotation,
            primitive.transform.scale,
        )
        for value in values
    )


def test_recipe_executors_contain_no_named_object_family_branches():
    source = inspect.getsource(compiler_module).lower()

    assert "tank" not in source
    assert "bus" not in source
    assert "tower" not in source
    assert SUPPORTED_GEOMETRY_RECIPE_EXECUTORS == EXPECTED_EXECUTORS


def test_repetition_inherits_mirrored_parent_instances():
    source = _load_fixture("tracked_machine.json")
    intent = HierarchicalAssetIntent.model_validate(source)

    result = compile_hierarchical_geometry(
        intent,
        load_object_archetype_registry(),
    )

    rollers = [
        primitive
        for primitive in result.primitives
        if primitive.params["semantic_part_id"] == "rollers"
    ]
    assert len(rollers) == 12
    assert {math.copysign(1, primitive.transform.location[1]) for primitive in rollers} == {
        -1.0,
        1.0,
    }


def test_linear_radial_and_stacked_expansions_are_all_executable():
    tower = HierarchicalAssetIntent.model_validate(
        _load_fixture("observation_tower.json")
    )
    result = compile_hierarchical_geometry(
        tower,
        load_object_archetype_registry(),
    )

    lights = [
        primitive
        for primitive in result.primitives
        if primitive.params["semantic_part_id"] == "lights"
    ]
    levels = [
        primitive
        for primitive in result.primitives
        if primitive.params["semantic_part_id"] == "levels"
    ]
    assert len(lights) == 12
    assert len(levels) == 4
    assert len({round(item.transform.location[0], 4) for item in lights}) > 2
    assert len({round(item.transform.location[2], 4) for item in levels}) == 4


def test_cross_family_orthographic_silhouette_proportions_remain_distinct():
    extents = {}
    for fixture_name in FIXTURES:
        intent = HierarchicalAssetIntent.model_validate(_load_fixture(fixture_name))
        result = compile_hierarchical_geometry(
            intent,
            load_object_archetype_registry(),
        )
        minimum = [float("inf")] * 3
        maximum = [float("-inf")] * 3
        for primitive in result.primitives:
            for axis in range(3):
                half_extent = primitive.transform.scale[axis]
                minimum[axis] = min(
                    minimum[axis],
                    primitive.transform.location[axis] - half_extent,
                )
                maximum[axis] = max(
                    maximum[axis],
                    primitive.transform.location[axis] + half_extent,
                )
        extents[fixture_name] = [
            maximum[axis] - minimum[axis]
            for axis in range(3)
        ]

    tracked = extents["tracked_machine.json"]
    transit = extents["double_decker_transit.json"]
    tower = extents["observation_tower.json"]
    assert tracked[0] > tracked[2]
    assert transit[0] > transit[2] * 1.5
    assert tower[2] > tower[0] * 1.5


def test_unsupported_recipe_parameters_fail_with_structured_diagnostic():
    source = _load_fixture("double_decker_transit.json")
    body = next(part for part in source["parts"] if part["id"] == "body")
    body["metadata"] = {
        "recipe_parameters": {"primitive_type": "named_object_mesh"}
    }
    intent = HierarchicalAssetIntent.model_validate(source)

    result = compile_hierarchical_geometry(
        intent,
        load_object_archetype_registry(),
    )

    assert result.outcome == "needs_repair"
    assert result.valid is False
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "geometry_recipe_parameters_invalid"
    assert diagnostic.part_id == "body"
    assert diagnostic.recipe_id == "compound_body"
