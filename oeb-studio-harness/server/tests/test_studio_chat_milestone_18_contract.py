import copy
import json
from pathlib import Path

from app.services.hierarchical_asset_intent import (
    validate_hierarchical_asset_intent,
)
from app.services.studio_chat import (
    compile_studio_chat_build_pipeline,
    pipeline_allows_job_submission,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "hierarchical_asset_intents"


def _valid_intent():
    return json.loads((FIXTURE_ROOT / "valid_tracked_vehicle_v1.json").read_text())


def _diagnostic_codes(result):
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_versioned_hierarchical_asset_intent_accepts_coherent_tracked_vehicle():
    source = _valid_intent()

    result = validate_hierarchical_asset_intent(source)

    assert result.valid is True
    assert result.outcome == "valid"
    assert result.schema_version == "1.0"
    assert result.intent.object_family == "tracked_vehicle"
    assert result.intent.model_dump()["future_family_extension"] == {"preserve": True}
    normalized = result.intent.model_dump(mode="json")
    assert (
        validate_hierarchical_asset_intent(normalized).intent.model_dump(mode="json")
        == normalized
    )


def test_unknown_hierarchy_schema_version_is_invalid():
    source = _valid_intent()
    source["schema_version"] = "2.0"

    result = validate_hierarchical_asset_intent(source)

    assert result.valid is False
    assert result.outcome == "invalid"
    assert _diagnostic_codes(result) == {"hierarchical_contract_invalid"}


def test_hierarchy_requires_declared_semantic_roles():
    source = _valid_intent()
    source["required_roles"].append("commander_hatch")

    result = validate_hierarchical_asset_intent(source)

    assert result.outcome == "needs_repair"
    assert "required_roles_missing" in _diagnostic_codes(result)


def test_hierarchy_rejects_duplicate_ids_and_disconnected_parts():
    source = _valid_intent()
    orphan = copy.deepcopy(source["parts"][-1])
    orphan["id"] = "orphan_wheel"
    orphan["parent_id"] = None
    orphan["attachment"] = None
    source["parts"].append(orphan)
    source["parts"].append(copy.deepcopy(source["parts"][1]))

    result = validate_hierarchical_asset_intent(source)

    assert result.outcome == "needs_repair"
    assert {
        "duplicate_hierarchical_part_id",
        "hierarchy_root_not_unique",
        "hierarchy_disconnected",
    }.issubset(_diagnostic_codes(result))


def test_parent_children_and_attachment_parent_must_agree():
    source = _valid_intent()
    cannon = next(part for part in source["parts"] if part["id"] == "cannon")
    cannon["parent_id"] = "hull"

    result = validate_hierarchical_asset_intent(source)

    assert result.outcome == "needs_repair"
    assert {
        "attachment_parent_mismatch",
        "hierarchy_parent_child_mismatch",
        "hierarchy_child_not_owned",
    }.issubset(_diagnostic_codes(result))


def test_dimensions_orientation_and_repetition_are_validated():
    source = _valid_intent()
    cannon = next(part for part in source["parts"] if part["id"] == "cannon")
    cannon["dimensions"] = {}
    cannon["orientation"] = {"forward": "front", "up": "rear"}
    cannon["repetition"] = {"mode": "mirror", "count": 3}

    result = validate_hierarchical_asset_intent(source)

    assert result.outcome == "needs_repair"
    assert {
        "part_dimensions_unresolved",
        "orientation_axes_not_orthogonal",
        "repetition_axis_missing",
        "mirror_count_invalid",
    }.issubset(_diagnostic_codes(result))


def test_declared_dimension_bounds_must_be_coherent_and_contain_size():
    source = _valid_intent()
    source["parts"][0]["dimensions"] = {
        "size": [4.8, 3.2, 2.4],
        "minimum": [5.0, 1.0, 1.0],
        "maximum": [4.0, 4.0, 4.0],
    }

    result = validate_hierarchical_asset_intent(source)

    assert result.outcome == "needs_repair"
    assert {
        "dimension_bounds_inverted",
        "dimension_size_out_of_bounds",
    }.issubset(_diagnostic_codes(result))


def test_pipeline_blocks_invalid_hierarchy_even_when_flat_primitives_are_executable():
    source = _valid_intent()
    cannon = next(part for part in source["parts"] if part["id"] == "cannon")
    cannon["attachment"]["parent_id"] = "hull"
    assistant_response = json.dumps({
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
            "hierarchical_asset_intent": source,
        },
    })

    result = compile_studio_chat_build_pipeline(
        "Build an army tank.",
        assistant_response,
    )

    assert result.outcome == "needs_repair"
    assert result.diagnostics[0].code == "hierarchical_asset_intent_needs_repair"
    hierarchy_errors = {
        error["code"] for error in result.diagnostics[0].details["errors"]
    }
    assert "attachment_parent_mismatch" in hierarchy_errors
    assert pipeline_allows_job_submission(result) is False


def test_pipeline_preserves_and_compiles_valid_hierarchy_with_recipe_executors():
    source = _valid_intent()
    assistant_response = json.dumps({
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
            "hierarchical_asset_intent": source,
        },
    })

    result = compile_studio_chat_build_pipeline(
        "Build an army tank.",
        assistant_response,
    )

    assert result.outcome == "compiled"
    assert result.diagnostics[0].code == "build_plan_compiled"
    assert result.normalized_hierarchical_asset_intent["schema_version"] == "1.0"
    assert result.normalized_hierarchical_asset_intent["future_family_extension"] == {
        "preserve": True
    }
    assert pipeline_allows_job_submission(result) is True
