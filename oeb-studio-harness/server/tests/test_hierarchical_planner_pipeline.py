import copy
import io
import json
from pathlib import Path
import urllib.error

import pytest

from app.schemas.hierarchical_asset_intent import HierarchicalAssetIntent
from app.services.geometry_recipe_compiler import compile_hierarchical_geometry
from app.services.hierarchical_geometry_inspection import (
    inspect_hierarchical_geometry,
)
from app.services.hierarchical_planner import (
    infer_object_archetype,
    repair_hierarchy_against_archetype,
)
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
    / "hierarchy_planner"
    / "tank_aliases_missing_roles.json"
)


def _fixture():
    return json.loads(FIXTURE_PATH.read_text())


def _root_only_hierarchy(archetype):
    root_rule = next(
        role for role in archetype.roles if role.role == archetype.root_role
    )
    return {
        "schema_version": "1.0",
        "object_family": archetype.family,
        "root_part_id": "root",
        "required_roles": [archetype.root_role],
        "parts": [
            {
                "id": "root",
                "name": archetype.family.replace("_", " ").title(),
                "role": archetype.root_role,
                "requirement": "required",
                "parent_id": None,
                "children": [],
                "shape_family": root_rule.allowed_shape_families[0],
                "geometry_strategy": root_rule.supported_geometry_recipes[0],
                "dimensions": {
                    "size": archetype.metadata["canonical_root_size"]
                },
                "orientation": root_rule.default_orientation.model_dump(
                    mode="json"
                ),
                "repetition": {"mode": "none", "count": 1},
            }
        ],
        "constraints": [],
    }


def test_broad_flat_tank_uses_constrained_planner_and_bounded_repair(monkeypatch):
    fixture = _fixture()

    def fake_post_json(url, payload, timeout):
        assert payload["messages"][0]["role"] == "system"
        assert "hierarchical asset planner" in (
            payload["messages"][0]["content"].lower()
        )
        assert payload["messages"][1]["role"] == "user"
        planner_context = json.loads(payload["messages"][1]["content"])
        assert "current_asset_intent" not in planner_context
        assert "current_asset_context" in planner_context
        assert all(
            "orientation" not in hint
            for hint in planner_context["current_asset_context"]["object_hints"]
        )
        assert payload["options"]["num_predict"] == 2048
        return {
            "message": {
                "content": json.dumps(fixture["planner_response"])
            }
        }

    monkeypatch.setattr(
        "app.services.studio_chat.post_json",
        fake_post_json,
    )
    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        json.dumps(fixture["assistant_response"]),
        ollama_url="http://ollama.test",
        model="local-test-model",
    )

    assert result.outcome == "compiled"
    assert result.hierarchy_planner["source"] == "ollama_hierarchical_planner"
    assert result.object_archetype["id"] == "tracked_vehicle_v1"
    assert result.geometry_inspection["valid"] is True
    inserted_roles = {
        repair["after"]["role"]
        for repair in result.structural_repairs
        if repair["code"] == "required_role_inserted"
    }
    assert {"cannon", "track_pair", "road_wheel_group"} <= inserted_roles
    assert pipeline_allows_job_submission(result) is True


def test_failed_hierarchy_planner_is_bounded_and_cannot_submit(monkeypatch):
    fixture = _fixture()
    calls = []

    def fake_post_json(url, payload, timeout):
        calls.append(payload)
        return {"message": {"content": "{\"not_hierarchy\": true}"}}

    monkeypatch.setattr(
        "app.services.studio_chat.post_json",
        fake_post_json,
    )
    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        json.dumps(fixture["assistant_response"]),
        ollama_url="http://ollama.test",
        model="local-test-model",
    )

    assert result.outcome == "needs_repair"
    assert result.diagnostics[0].code == "hierarchical_decomposition_failed"
    assert len(calls) == 2
    assert result.repair_attempt_count == 2
    assert pipeline_allows_job_submission(result) is False


def test_hierarchy_planner_upstream_http_error_is_structured(monkeypatch):
    fixture = _fixture()
    calls = []

    def fake_post_json(url, payload, timeout):
        calls.append(payload)
        raise urllib.error.HTTPError(
            url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":"input exceeds context window"}'),
        )

    monkeypatch.setattr(
        "app.services.studio_chat.post_json",
        fake_post_json,
    )
    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        json.dumps(fixture["assistant_response"]),
        ollama_url="http://ollama.test",
        model="local-test-model",
    )

    assert result.outcome == "needs_repair"
    assert result.diagnostics[0].code == "hierarchical_decomposition_failed"
    assert "upstream HTTP 400" in result.diagnostics[0].reason
    assert "input exceeds context window" in result.diagnostics[0].reason
    assert len(calls) == 2
    assert pipeline_allows_job_submission(result) is False


def test_hierarchy_planner_clarification_stops_after_one_attempt(monkeypatch):
    fixture = _fixture()
    calls = []

    def fake_post_json(url, payload, timeout):
        calls.append(payload)
        return {
            "message": {
                "content": json.dumps({
                    "hierarchical_asset_intent": None,
                    "clarification_question": (
                        "Should this be a tracked battle tank or a wheeled "
                        "armored vehicle?"
                    ),
                })
            }
        }

    monkeypatch.setattr(
        "app.services.studio_chat.post_json",
        fake_post_json,
    )
    result = compile_studio_chat_build_pipeline(
        fixture["creative_request"],
        json.dumps(fixture["assistant_response"]),
        ollama_url="http://ollama.test",
        model="local-test-model",
    )

    assert result.outcome == "needs_clarification"
    assert result.diagnostics[0].code == (
        "hierarchical_decomposition_clarification_required"
    )
    assert len(calls) == 1
    assert result.repair_attempt_count == 0
    assert pipeline_allows_job_submission(result) is False


@pytest.mark.parametrize(
    ("prompt", "expected_family"),
    [
        ("Build an army tank.", "tracked_vehicle"),
        ("Build a double decker bus.", "wheeled_vehicle"),
        ("Build a biplane.", "aircraft"),
        ("Build an office chair.", "chair"),
        ("Build a dining table.", "table"),
        ("Build a castle tower.", "tower"),
        ("Build a simple robot.", "simple_robot"),
    ],
)
def test_prompt_family_inference_uses_reusable_archetypes(
    prompt,
    expected_family,
):
    registry = load_object_archetype_registry()

    archetype = infer_object_archetype(
        prompt,
        {"name": prompt, "kind": "asset"},
        registry,
    )

    assert archetype.family == expected_family


@pytest.mark.parametrize(
    "family",
    [
        "tracked_vehicle",
        "wheeled_vehicle",
        "aircraft",
        "chair",
        "table",
        "tower",
        "simple_robot",
    ],
)
def test_bounded_required_role_repair_compiles_each_registered_family(family):
    registry = load_object_archetype_registry()
    archetype = find_object_archetype(family, registry)
    source = _root_only_hierarchy(archetype)
    initial = ground_hierarchy_against_archetype(source, registry)

    assert initial.outcome == "needs_repair"

    repaired, changes = repair_hierarchy_against_archetype(
        initial.intent.model_dump(mode="json"),
        archetype,
    )
    grounded = ground_hierarchy_against_archetype(repaired, registry)
    compiled = compile_hierarchical_geometry(grounded.intent, registry)
    inspection = inspect_hierarchical_geometry(grounded.intent, compiled)

    assert grounded.valid is True
    assert compiled.valid is True
    assert inspection.valid is True
    assert any(change.code == "required_role_inserted" for change in changes)


@pytest.mark.parametrize(
    "family",
    [
        "tracked_vehicle",
        "wheeled_vehicle",
        "aircraft",
        "chair",
        "table",
        "tower",
        "simple_robot",
    ],
)
def test_pipeline_compiles_repaired_hierarchy_for_each_registered_family(family):
    registry = load_object_archetype_registry()
    archetype = find_object_archetype(family, registry)
    response = {
        "action": "build_asset",
        "confidence": 1,
        "clarification_question": None,
        "escalation_reason": None,
        "asset_intent": {
            "name": family.replace("_", " ").title(),
            "kind": "vehicle" if "vehicle" in family else "asset",
            "description": f"A representative {family}.",
            "hierarchical_asset_intent": _root_only_hierarchy(archetype),
        },
    }

    result = compile_studio_chat_build_pipeline(
        f"Build a {family.replace('_', ' ')}.",
        json.dumps(response),
    )

    assert result.outcome == "compiled"
    assert result.geometry_inspection["valid"] is True
    assert result.object_archetype["family"] == family
    assert pipeline_allows_job_submission(result) is True


def test_repair_clamps_proportions_and_restores_anchor_orientation_repetition():
    registry = load_object_archetype_registry()
    archetype = find_object_archetype("tracked_vehicle", registry)
    fixture = _fixture()["planner_response"]["hierarchical_asset_intent"]
    repaired, _ = repair_hierarchy_against_archetype(fixture, archetype)
    cannon = next(part for part in repaired["parts"] if part["role"] == "cannon")
    cannon["dimensions"]["ratio"] = [99.0, 99.0, 99.0]
    cannon["attachment"]["anchor"] = "rear_center"
    cannon["orientation"] = {"forward": "rear", "up": "up"}
    cannon["repetition"] = {"mode": "radial", "count": 9, "axis": "up"}

    repaired_again, changes = repair_hierarchy_against_archetype(
        cannon_parent_consistent(repaired),
        archetype,
    )
    cannon = next(
        part for part in repaired_again["parts"] if part["role"] == "cannon"
    )

    assert cannon["dimensions"]["ratio"] == [2.0, 0.25, 0.25]
    assert cannon["attachment"]["anchor"] == "front_center"
    assert cannon["orientation"] == {"forward": "front", "up": "up"}
    assert cannon["repetition"]["mode"] == "none"
    assert {
        "proportion_repaired",
        "attachment_repaired",
        "orientation_repaired",
        "repetition_repaired",
    } <= {change.code for change in changes}


def test_grounding_and_repair_preserve_novel_optional_extension():
    registry = load_object_archetype_registry()
    archetype = find_object_archetype("tracked_vehicle", registry)
    source = _fixture()["planner_response"]["hierarchical_asset_intent"]
    repaired, _ = repair_hierarchy_against_archetype(source, archetype)
    turret = next(part for part in repaired["parts"] if part["role"] == "turret")
    antenna = {
        "id": "command_antenna",
        "name": "Command Antenna",
        "role": "command_antenna",
        "requirement": "optional",
        "parent_id": turret["id"],
        "children": [],
        "shape_family": "mast",
        "geometry_strategy": "attached_directional_v1",
        "dimensions": {
            "relative_to": turret["id"],
            "ratio": [0.1, 0.1, 0.8],
        },
        "attachment": {
            "parent_id": turret["id"],
            "anchor": "top_center",
            "contact_required": True,
            "offset": [0.0, 0.0, 0.0],
        },
        "orientation": {"forward": "front", "up": "up"},
        "repetition": {"mode": "none", "count": 1},
        "metadata": {"user_extension": True},
    }
    repaired["parts"].append(antenna)
    turret["children"].append(antenna["id"])

    repaired_again, _ = repair_hierarchy_against_archetype(
        repaired,
        archetype,
    )
    grounded = ground_hierarchy_against_archetype(repaired_again, registry)
    preserved = next(
        part for part in repaired_again["parts"] if part["id"] == "command_antenna"
    )

    assert grounded.valid is True
    assert preserved["role"] == antenna["role"]
    assert preserved["parent_id"] == antenna["parent_id"]
    assert preserved["geometry_strategy"] == antenna["geometry_strategy"]
    assert preserved["dimensions"]["ratio"] == antenna["dimensions"]["ratio"]
    assert preserved["metadata"] == antenna["metadata"]


def cannon_parent_consistent(value):
    repaired = copy.deepcopy(value)
    cannon = next(part for part in repaired["parts"] if part["role"] == "cannon")
    turret = next(part for part in repaired["parts"] if part["role"] == "turret")
    cannon["parent_id"] = turret["id"]
    return repaired


def test_inspection_detects_containment_failure_with_part_diagnostic():
    source = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "geometry_recipe_intents"
            / "tracked_machine.json"
        ).read_text()
    )
    intent = HierarchicalAssetIntent.model_validate(source)
    compiled = compile_hierarchical_geometry(
        intent,
        load_object_archetype_registry(),
    )
    rollers = next(
        part for part in compiled.resolved_parts if part.part_id == "rollers"
    )
    rollers.centers[0][1] = 999.0

    inspection = inspect_hierarchical_geometry(intent, compiled)

    assert inspection.valid is False
    finding = next(
        finding
        for finding in inspection.findings
        if finding.code == "contained_part_outside_parent"
    )
    assert finding.part_id == "rollers"
    assert finding.related_part_id == "side_system"


def test_inspection_enforces_explicit_no_overlap_constraint():
    source = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "geometry_recipe_intents"
            / "tracked_machine.json"
        ).read_text()
    )
    source.setdefault("constraints", []).append({
        "id": "rollers_must_not_intersect_side_system",
        "type": "no_overlap",
        "targets": ["rollers", "side_system"],
        "required": True,
    })
    intent = HierarchicalAssetIntent.model_validate(source)
    compiled = compile_hierarchical_geometry(
        intent,
        load_object_archetype_registry(),
    )

    inspection = inspect_hierarchical_geometry(intent, compiled)

    assert inspection.valid is False
    finding = next(
        finding
        for finding in inspection.findings
        if finding.code == "constraint_overlap_detected"
    )
    assert finding.part_id == "rollers"
    assert finding.related_part_id == "side_system"
