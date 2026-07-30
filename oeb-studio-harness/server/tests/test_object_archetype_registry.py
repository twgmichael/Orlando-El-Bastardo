import copy
import json
from pathlib import Path

from app.services.object_archetype_registry import (
    find_object_archetype,
    ground_hierarchy_against_archetype,
    load_object_archetype_registry,
)
from app.services.studio_chat import (
    compile_studio_chat_build_pipeline,
    pipeline_allows_job_submission,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "hierarchical_asset_intents"
    / "valid_tracked_vehicle_v1.json"
)


def _valid_intent():
    return json.loads(FIXTURE_PATH.read_text())


def _codes(result):
    return {diagnostic.code for diagnostic in result.diagnostics}


def _pipeline_response(hierarchy):
    return json.dumps({
        "action": "build_asset",
        "asset_intent": {
            "name": "Army Tank",
            "kind": "vehicle",
            "objects": [
                {
                    "id": "tank_body",
                    "type": "cube",
                    "material": "metal",
                }
            ],
            "hierarchical_asset_intent": hierarchy,
        },
    })


def test_registry_v1_loads_tracked_vehicle_knowledge():
    registry = load_object_archetype_registry()
    archetype = find_object_archetype("tracked_vehicle", registry)

    assert registry.schema_version == "1.0"
    assert registry.registry_version == "1.1.0"
    assert {recipe.status for recipe in registry.geometry_recipes} == {"available"}
    assert all(recipe.compiler for recipe in registry.geometry_recipes)
    assert archetype.id == "tracked_vehicle_v1"
    assert archetype.root_role == "vehicle_root"
    assert {
        "vehicle_root",
        "hull",
        "turret",
        "cannon",
        "track_pair",
        "road_wheel_group",
    }.issubset({role.role for role in archetype.roles})


def test_registry_v11_covers_representative_reusable_families():
    registry = load_object_archetype_registry()

    expected = {
        "tracked_vehicle",
        "wheeled_vehicle",
        "aircraft",
        "chair",
        "table",
        "tower",
        "simple_robot",
    }

    assert expected == {archetype.family for archetype in registry.archetypes}
    assert find_object_archetype("double_decker_bus", registry).family == (
        "wheeled_vehicle"
    )
    assert find_object_archetype("biplane", registry).family == "aircraft"
    assert find_object_archetype("office_chair", registry).family == "chair"
    assert find_object_archetype("castle_tower", registry).family == "tower"


def test_family_and_role_aliases_ground_to_canonical_tracked_vehicle_roles():
    source = _valid_intent()
    source["object_family"] = "army_tank"
    aliases = {
        "vehicle_root": "tank",
        "hull": "tank_body",
        "turret": "gun_platform",
        "cannon": "main_gun",
        "track_pair": "treads",
        "road_wheel_group": "wheels",
    }
    for part in source["parts"]:
        part["role"] = aliases.get(part["role"], part["role"])
    source["required_roles"] = list(aliases.values())

    result = ground_hierarchy_against_archetype(source)

    assert result.valid is True
    assert result.intent.object_family == "tracked_vehicle"
    assert result.intent.required_roles == [
        "vehicle_root",
        "hull",
        "turret",
        "cannon",
        "track_pair",
        "road_wheel_group",
    ]
    assert {part.role for part in result.intent.parts}.issuperset(
        set(result.intent.required_roles)
    )
    assert {
        "object_family_alias_resolved",
        "role_alias_resolved",
        "required_roles_grounded_from_archetype",
    }.issubset({change.code for change in result.changes})
    grounded_again = ground_hierarchy_against_archetype(
        result.intent.model_dump(mode="json")
    )
    assert grounded_again.valid is True
    assert grounded_again.changes == []
    assert (
        grounded_again.intent.model_dump(mode="json")
        == result.intent.model_dump(mode="json")
    )


def test_model_cannot_hide_missing_cannon_by_omitting_it_from_required_roles():
    source = _valid_intent()
    source["required_roles"].remove("cannon")
    source["parts"] = [part for part in source["parts"] if part["id"] != "cannon"]
    turret = next(part for part in source["parts"] if part["id"] == "turret")
    turret["children"].remove("cannon")

    result = ground_hierarchy_against_archetype(source)

    assert result.outcome == "needs_repair"
    assert "archetype_required_roles_missing" in _codes(result)
    diagnostic = next(
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code == "archetype_required_roles_missing"
    )
    assert diagnostic.details["missing_roles"] == ["cannon"]


def test_tracked_vehicle_rules_validate_structure_proportions_and_recipes():
    source = _valid_intent()
    tracks = next(part for part in source["parts"] if part["id"] == "tracks")
    tracks["parent_id"] = "turret"
    tracks["attachment"] = {
        "parent_id": "turret",
        "anchor": "top_center",
        "contact_required": False,
    }
    tracks["shape_family"] = "cube"
    tracks["geometry_strategy"] = "generic_box"
    tracks["dimensions"]["relative_to"] = "turret"
    tracks["dimensions"]["ratio"] = [2.0, 2.0, 2.0]
    tracks["orientation"] = {"forward": "rear", "up": "up"}
    tracks["repetition"] = {
        "mode": "linear",
        "count": 3,
        "axis": "front",
    }
    hull = next(part for part in source["parts"] if part["id"] == "hull")
    hull["children"].remove("tracks")
    turret = next(part for part in source["parts"] if part["id"] == "turret")
    turret["children"].append("tracks")

    result = ground_hierarchy_against_archetype(source)

    assert result.outcome == "needs_repair"
    assert {
        "archetype_parent_role_invalid",
        "archetype_shape_family_unsupported",
        "archetype_geometry_recipe_unsupported",
        "archetype_attachment_anchor_invalid",
        "archetype_contact_rule_mismatch",
        "archetype_orientation_mismatch",
        "archetype_repetition_mode_invalid",
        "archetype_repetition_count_invalid",
        "archetype_repetition_axis_invalid",
        "archetype_ratio_out_of_range",
        "archetype_ratio_reference_role_invalid",
    }.issubset(_codes(result))


def test_unregistered_object_family_is_explicitly_unsupported():
    source = _valid_intent()
    source["object_family"] = "hover_dragon"

    result = ground_hierarchy_against_archetype(source)

    assert result.outcome == "unsupported"
    assert _codes(result) == {"object_archetype_not_found"}


def test_pipeline_repairs_deterministic_missing_tracked_vehicle_roles():
    source = _valid_intent()
    source["required_roles"] = ["vehicle_root", "hull", "turret"]
    source["parts"] = [
        part
        for part in source["parts"]
        if part["role"] not in {"cannon", "track_pair", "road_wheel_group"}
    ]
    hull = next(part for part in source["parts"] if part["id"] == "hull")
    hull["children"] = ["turret"]
    turret = next(part for part in source["parts"] if part["id"] == "turret")
    turret["children"] = []

    result = compile_studio_chat_build_pipeline(
        "Build an army tank.",
        _pipeline_response(source),
    )

    assert result.outcome == "compiled"
    assert result.diagnostics[0].code == "build_plan_compiled"
    assert {
        "cannon",
        "track_pair",
        "road_wheel_group",
    }.issubset({
        repair["after"]["role"]
        for repair in result.structural_repairs
        if repair["code"] == "required_role_inserted"
    })
    assert pipeline_allows_job_submission(result) is True


def test_pipeline_compiles_grounded_tracked_vehicle_with_shared_recipes():
    result = compile_studio_chat_build_pipeline(
        "Build an army tank.",
        _pipeline_response(_valid_intent()),
    )

    assert result.outcome == "compiled"
    assert result.diagnostics[0].code == "build_plan_compiled"
    assert result.object_archetype["id"] == "tracked_vehicle_v1"
    assert result.object_archetype["family"] == "tracked_vehicle"
    assert result.resolver["source"] == "hierarchical_geometry_recipe_compiler"
    assert {
        "compound_body",
        "attached_directional",
        "mirrored_system",
        "repeated_array",
    }.issubset(set(result.resolver["used_executors"]))
    assert pipeline_allows_job_submission(result) is True


def test_pipeline_blocks_invalid_recipe_parameters_before_job_submission():
    source = _valid_intent()
    hull = next(part for part in source["parts"] if part["id"] == "hull")
    hull["metadata"] = {
        "recipe_parameters": {"primitive_type": "named_object_mesh"}
    }

    result = compile_studio_chat_build_pipeline(
        "Build an army tank.",
        _pipeline_response(source),
    )

    assert result.outcome == "needs_repair"
    assert (
        result.diagnostics[0].code
        == "hierarchical_geometry_recipe_compile_failed"
    )
    errors = result.diagnostics[0].details["errors"]
    assert errors[0]["code"] == "geometry_recipe_parameters_invalid"
    assert errors[0]["part_id"] == "hull"
    assert pipeline_allows_job_submission(result) is False


def test_pipeline_rejects_unregistered_family_without_job_submission():
    source = copy.deepcopy(_valid_intent())
    source["object_family"] = "hover_dragon"

    result = compile_studio_chat_build_pipeline(
        "Build a hover dragon.",
        _pipeline_response(source),
    )

    assert result.outcome == "unsupported"
    assert result.diagnostics[0].code == "object_archetype_not_found"
    assert pipeline_allows_job_submission(result) is False
