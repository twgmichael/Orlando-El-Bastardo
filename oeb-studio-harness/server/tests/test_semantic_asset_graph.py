import copy

from app.schemas.semantic_asset_graph import GraphOperationRequest, SemanticAssetGraph
from app.services.semantic_asset_graph import (
    compile_graph_operation,
    graph_from_state,
    graph_summary,
    part_catalog,
    state_from_graph,
    validate_graph,
)


def _graph() -> SemanticAssetGraph:
    return SemanticAssetGraph.model_validate(
        {
            "asset_id": "asset_test_A",
            "revision": 3,
            "parts": [
                {
                    "id": "cone",
                    "geometry": {"type": "cone"},
                    "material": "red",
                    "transform": {"location": [0, 0, 1], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
                },
                {
                    "id": "body",
                    "geometry": {"type": "cylinder"},
                    "material": "blue",
                    "transform": {"location": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 2]},
                },
            ],
            "constraints": [
                {"id": "keep_nose", "type": "connected", "targets": ["cone", "body"], "required": True}
            ],
        }
    )


def test_legacy_state_becomes_canonical_semantic_graph():
    state = {
        "canonical_id": "asset_legacy_A",
        "primitives": [
            {
                "id": "main_cube",
                "type": "cube",
                "material": "orange",
                "transform": {"location": [1, 2, 3], "scale": [2, 2, 2]},
            }
        ],
    }

    graph = graph_from_state(state, revision=4)

    assert graph.asset_id == "asset_legacy_A"
    assert graph.revision == 4
    assert graph.parts[0].id == "main_cube"
    assert graph.parts[0].geometry.type == "box"
    assert graph.parts[0].transform.location == [1.0, 2.0, 3.0]
    assert graph_summary(graph)["part_count"] == 1
    assert part_catalog(graph)[0]["material"] == "orange"


def test_compile_is_pure_and_returns_reviewable_diff():
    graph = _graph()
    before = graph.model_dump(mode="json")

    result = compile_graph_operation(
        graph,
        GraphOperationRequest(
            operation="recolor",
            base_revision=3,
            intent="Recolor the cone yellow",
            target_ids=["cone"],
            parameters={"material": "yellow"},
        ),
    )

    assert result.outcome == "compiled"
    assert result.proposed_revision == 4
    assert result.graph_after.parts[0].material == "yellow"
    assert graph.model_dump(mode="json") == before
    assert result.diff.selected_targets == ["cone"]
    assert any(change.path.endswith(".material") for change in result.diff.changes)


def test_intent_operation_mismatch_is_repaired_before_mutation():
    result = compile_graph_operation(
        _graph(),
        GraphOperationRequest(
            operation="replace",
            base_revision=3,
            intent="Add a tube below the cone",
            target_ids=["cone"],
            parameters={"type": "cylinder"},
        ),
    )

    assert result.outcome == "needs_repair"
    assert result.graph_after is None
    assert result.diagnostics[0].code == "intent_operation_mismatch"
    assert result.diagnostics[0].details == {
        "intended_operation": "add",
        "proposed_operation": "replace",
    }


def test_remove_cannot_violate_preserved_constraint():
    result = compile_graph_operation(
        _graph(),
        GraphOperationRequest(
            operation="remove",
            base_revision=3,
            target_ids=["cone"],
            preserve=["keep_nose"],
        ),
    )

    assert result.outcome == "needs_repair"
    assert result.diagnostics[0].code == "preserved_constraint_violation"


def test_add_attach_group_and_state_projection_share_one_graph_contract():
    graph = _graph()
    added = compile_graph_operation(
        graph,
        GraphOperationRequest(
            operation="add",
            base_revision=3,
            intent="Add a sphere",
            parameters={
                "part": {
                    "id": "globe",
                    "type": "sphere",
                    "material": "green",
                    "transform": {"location": [0, 1, 0]},
                }
            },
        ),
    )
    attached = compile_graph_operation(
        added.graph_after,
        GraphOperationRequest(
            operation="attach",
            base_revision=4,
            target_ids=["globe"],
            parameters={"parent": "body"},
        ),
    )
    grouped = compile_graph_operation(
        attached.graph_after,
        GraphOperationRequest(
            operation="group",
            base_revision=5,
            target_ids=["body", "globe"],
            parameters={"group_id": "engine"},
        ),
    )
    projected = state_from_graph({}, grouped.graph_after)

    assert grouped.outcome == "compiled"
    assert grouped.graph_after.attachments[0].child == "globe"
    assert grouped.graph_after.attachments[0].parent == "body"
    assert grouped.graph_after.groups[0].members == ["body", "globe"]
    assert projected["semantic_graph"]["revision"] == 6
    assert [primitive["id"] for primitive in projected["primitives"]] == ["cone", "body", "globe"]


def test_add_places_new_part_relative_to_selected_reference():
    result = compile_graph_operation(
        _graph(),
        GraphOperationRequest(
            operation="add",
            base_revision=3,
            intent="Add a tube below the cone",
            target_ids=["cone"],
            parameters={
                "id": "lower_tube",
                "type": "tube",
                "material": "red",
                "semantic_direction": "below",
            },
        ),
    )

    assert result.outcome == "compiled"
    added = next(part for part in result.graph_after.parts if part.id == "lower_tube")
    assert added.geometry.type == "cylinder"
    assert added.transform.location == [0.0, 0.0, 0.0]
    assert result.graph_after.relationships[0].subject == "lower_tube"
    assert result.graph_after.relationships[0].target == "cone"


def test_validator_rejects_dangling_graph_references():
    graph = _graph()
    data = graph.model_dump(mode="python")
    data["relationships"] = [
        {"id": "bad_relation", "type": "left_of", "subject": "cone", "target": "missing"}
    ]
    invalid = SemanticAssetGraph.model_validate(data)

    diagnostics = validate_graph(invalid)

    assert diagnostics[0].code == "unknown_part_reference"


def test_validator_rejects_attachment_cycles():
    graph = _graph()
    data = graph.model_dump(mode="python")
    data["attachments"] = [
        {"id": "cone_to_body", "child": "cone", "parent": "body"},
        {"id": "body_to_cone", "child": "body", "parent": "cone"},
    ]
    invalid = SemanticAssetGraph.model_validate(data)

    assert any(diagnostic.code == "attachment_cycle" for diagnostic in validate_graph(invalid))


def test_existing_graph_drops_references_to_parts_that_never_compiled():
    state = {
        "semantic_graph": {
            "asset_id": "rocket_A",
            "revision": 2,
            "parts": [
                {"id": "cone", "geometry": {"type": "cone"}},
                {"id": "tube", "geometry": {"type": "cylinder"}},
            ],
            "relationships": [
                {"id": "cone_on_tube", "type": "on_top_of", "subject": "cone", "target": "tube"},
            ],
            "attachments": [
                {"id": "tube_to_missing_fin", "child": "tube", "parent": "missing_fin"},
            ],
        }
    }

    graph = graph_from_state(state)

    assert [relationship.id for relationship in graph.relationships] == ["cone_on_tube"]
    assert graph.attachments == []
    assert graph.metadata["normalization_diagnostics"][0]["id"] == "tube_to_missing_fin"


def test_relational_move_places_cone_on_top_of_tube():
    graph = SemanticAssetGraph.model_validate(
        {
            "asset_id": "rocket_A",
            "revision": 2,
            "parts": [
                {
                    "id": "cone",
                    "geometry": {"type": "cone", "parameters": {"depth": 1.0}},
                    "transform": {"location": [0, 0, 0], "scale": [1, 1, 1]},
                },
                {
                    "id": "tube",
                    "geometry": {"type": "cylinder", "parameters": {"depth": 1.0}},
                    "transform": {"location": [0, 0, 0], "scale": [0.4, 0.4, 1.4]},
                },
            ],
        }
    )

    result = compile_graph_operation(
        graph,
        GraphOperationRequest(
            operation="move",
            base_revision=2,
            intent="Move the cone to the top of the tube.",
            target_ids=["cone"],
            parameters={"relation": "on_top_of", "reference_id": "tube"},
        ),
    )

    assert result.outcome == "compiled"
    cone = next(part for part in result.graph_after.parts if part.id == "cone")
    assert cone.transform.location == [0.0, 0.0, 1.2]
    assert result.graph_after.relationships[0].type == "on_top_of"
    assert result.graph_after.relationships[0].subject == "cone"
    assert result.graph_after.relationships[0].target == "tube"


def test_relational_intent_repairs_legacy_operation_and_unique_cone_typo():
    graph = SemanticAssetGraph.model_validate(
        {
            "asset_id": "rocket_A",
            "revision": 2,
            "parts": [
                {
                    "id": "rocket_top_cone",
                    "geometry": {"type": "cone"},
                    "transform": {"location": [0, 0, 0], "scale": [1, 1, 1]},
                },
                {
                    "id": "rocket_body_tube",
                    "geometry": {"type": "cylinder"},
                    "transform": {"location": [0, 0, 0], "scale": [0.4, 0.4, 1.4]},
                },
            ],
        }
    )

    result = compile_graph_operation(
        graph,
        GraphOperationRequest(
            operation="align_centers",
            base_revision=2,
            intent="Move the code to the top of the tube.",
            target_ids=["rocket_body_tube"],
            parameters={"semantic_direction": "down", "amount": 0.25},
        ),
    )

    assert result.outcome == "compiled"
    assert result.operation == "move"
    assert result.selected_targets == ["rocket_top_cone"]
    cone = next(part for part in result.graph_after.parts if part.id == "rocket_top_cone")
    assert cone.transform.location == [0.0, 0.0, 1.2]
    assert result.diagnostics[0].code == "relational_move_normalized"
    assert result.diagnostics[0].details["original_operation"] == "align_centers"


def test_legacy_align_centers_with_one_target_requests_clarification():
    result = compile_graph_operation(
        _graph(),
        GraphOperationRequest(
            operation="align_centers",
            base_revision=3,
            target_ids=["body"],
        ),
    )

    assert result.outcome == "needs_clarification"
    assert result.operation == "move"
    assert result.diagnostics[0].code == "insufficient_alignment_targets"


def test_failed_compile_does_not_change_input_state():
    graph = _graph()
    before = copy.deepcopy(graph.model_dump(mode="json"))

    result = compile_graph_operation(
        graph,
        GraphOperationRequest(
            operation="move",
            base_revision=3,
            target_ids=["cone"],
            parameters={},
        ),
    )

    assert result.outcome == "needs_clarification"
    assert graph.model_dump(mode="json") == before
