import importlib.util
import os
from pathlib import Path


def _find_tool_path(filename: str) -> Path:
    env_override = os.environ.get("OEB_TOOLS_DIR")
    candidates = []
    if env_override:
        candidates.append(Path(env_override) / filename)
    candidates.append(Path("/tools") / filename)
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "tools" / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not locate tools/{filename}. Set OEB_TOOLS_DIR to its "
        "containing directory if running outside the repo checkout or "
        "the oeb-studio-harness-local Docker stack."
    )


def load_module():
    spec = importlib.util.spec_from_file_location(
        "compose_screenplay_scene_for_test",
        _find_tool_path("compose_screenplay_scene.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolved(entity_text, canonical_id, outcome="resolved"):
    return {
        "entity_text": entity_text,
        "outcome": outcome,
        "resolved": {"canonical_id": canonical_id},
        "score": 1.0,
        "fallback_tier": 2 if outcome == "fallback_created" else None,
        "ticket_path": None,
    }


def unresolved(entity_text, outcome="no_match"):
    return {"entity_text": entity_text, "outcome": outcome, "resolved": None, "candidates": []}


LINE = "JB100 flies past chased by Ellipso Flyers and Ventradi cruiser"


def test_classify_entities_matches_plan_example():
    module = load_module()
    entities = [
        resolved("JB100", "prop_jb100_A"),
        resolved("Ellipso Flyers", "prop_ellipso_flyer_A"),
        resolved("Ventradi", "prop_ventradi_cruiser_A"),
    ]
    subject, chasers, static = module.classify_entities(LINE, entities)
    assert subject == "JB100"
    assert chasers == ["Ellipso Flyers", "Ventradi"]
    assert static == []


def test_classify_entities_no_chase_marker_is_static_not_chaser():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    subject, chasers, static = module.classify_entities("JB100 flies past the station.", entities)
    assert subject == "JB100"
    assert chasers == []
    assert static == ["Ellipso Flyers"]


def test_classify_entities_chase_marker_without_flyby_verb_is_all_static():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    subject, chasers, static = module.classify_entities(
        "JB100 sits idle, chased by nothing in particular.", entities,
    )
    assert subject is None
    assert chasers == []
    assert static == ["JB100", "Ellipso Flyers"]


def test_classify_entities_no_flyby_verb_all_static():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A")]
    subject, chasers, static = module.classify_entities("JB100 sits parked in the hangar.", entities)
    assert subject is None
    assert static == ["JB100"]


def test_compose_screenplay_scene_builds_import_primitives_for_all_placeable_entities():
    module = load_module()
    entities = [
        resolved("JB100", "prop_jb100_A"),
        resolved("Ellipso Flyers", "prop_ellipso_flyer_A"),
        resolved("Ventradi", "prop_ventradi_cruiser_A"),
    ]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A")
    blueprint = result["blueprint"]

    import_canonical_ids = {p["canonical_id"] for p in blueprint["primitives"] if p["type"] == "import"}
    assert import_canonical_ids == {"prop_jb100_A", "prop_ellipso_flyer_A", "prop_ventradi_cruiser_A"}
    assert result["subject"] == "JB100"
    assert result["chasers"] == ["Ellipso Flyers", "Ventradi"]
    assert result["unresolved_entities"] == []


def test_compose_screenplay_scene_reports_unresolved_entities_without_dropping_them_silently():
    module = load_module()
    entities = [
        resolved("JB100", "prop_jb100_A"),
        unresolved("Ellipso Flyers", outcome="needs_clarification"),
        unresolved("Meanwhile"),
    ]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A")
    assert len(result["unresolved_entities"]) == 2
    assert {e["entity_text"] for e in result["unresolved_entities"]} == {"Ellipso Flyers", "Meanwhile"}
    import_ids = [p["canonical_id"] for p in result["blueprint"]["primitives"]]
    assert import_ids == ["prop_jb100_A"]


def test_compose_screenplay_scene_every_operation_targets_a_real_primitive_or_camera():
    module = load_module()
    entities = [
        resolved("JB100", "prop_jb100_A"),
        resolved("Ellipso Flyers", "prop_ellipso_flyer_A"),
        resolved("Ventradi", "prop_ventradi_cruiser_A"),
    ]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A")
    blueprint = result["blueprint"]
    primitive_ids = {p["id"] for p in blueprint["primitives"]}
    for op in blueprint["operations"]:
        assert op["target"] == "camera" or op["target"] in primitive_ids


def test_compose_screenplay_scene_chaser_keyframes_start_later_than_subject():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A", frame_start=1, frame_end=48)
    blueprint = result["blueprint"]

    ids_by_prim = {p["canonical_id"]: p["id"] for p in blueprint["primitives"]}
    subject_id = ids_by_prim["prop_jb100_A"]
    chaser_id = ids_by_prim["prop_ellipso_flyer_A"]

    def first_frame(target_id):
        frames = [op["params"]["frame"] for op in blueprint["operations"] if op["target"] == target_id]
        return min(frames)

    assert first_frame(chaser_id) > first_frame(subject_id)


def test_compose_screenplay_scene_chaser_depth_exceeds_subject_depth():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A")
    blueprint = result["blueprint"]
    ids_by_prim = {p["canonical_id"]: p["id"] for p in blueprint["primitives"]}

    def depth_at_start(target_id):
        for op in blueprint["operations"]:
            if op["target"] == target_id:
                return op["params"]["position"][1]
        return None

    subject_depth = depth_at_start(ids_by_prim["prop_jb100_A"])
    chaser_depth = depth_at_start(ids_by_prim["prop_ellipso_flyer_A"])
    assert chaser_depth > subject_depth


def test_compose_screenplay_scene_static_entity_gets_import_but_no_motion_ops():
    module = load_module()
    entities = [resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    result = module.compose_screenplay_scene(
        "A quiet hangar holds Ellipso Flyers.", entities, canonical_id="scene_static_A",
    )
    blueprint = result["blueprint"]
    assert len(blueprint["primitives"]) == 1
    non_camera_ops = [op for op in blueprint["operations"] if op["target"] != "camera"]
    assert non_camera_ops == []


def test_compose_screenplay_scene_blueprint_has_required_top_level_fields():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A")]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A", name="Chase")
    blueprint = result["blueprint"]
    assert blueprint["schema_version"] == "0.1.0"
    assert blueprint["canonical_id"] == "scene_chase_A"
    assert blueprint["name"] == "Chase"
    assert blueprint["kind"] == "scene"
    assert blueprint["frame_range"] == {"start": 1, "end": 48, "fps": 24.0}


def test_compose_screenplay_scene_aim_never_equals_position():
    # Regression: the end keyframe of a straight-line path used to aim
    # literally at its own position (aim == end_pos), which is a
    # zero-length look vector -- _look_at_rotation in
    # blueprint_interpreter.py raises ValueError on exactly this,
    # caught live by actually running the composed Blueprint through
    # headless Blender, not just by reading the code.
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("Ellipso Flyers", "prop_ellipso_flyer_A")]
    result = module.compose_screenplay_scene(LINE, entities, canonical_id="scene_chase_A")
    for op in result["blueprint"]["operations"]:
        params = op["params"]
        if "aim" in params:
            assert params["aim"] != params["position"]


def test_compose_screenplay_scene_duplicate_slugs_get_unique_ids():
    module = load_module()
    entities = [resolved("JB100", "prop_jb100_A"), resolved("JB-100", "prop_jb100_B")]
    result = module.compose_screenplay_scene(
        "JB100 flies past chased by JB-100.", entities, canonical_id="scene_dup_A",
    )
    ids = [p["id"] for p in result["blueprint"]["primitives"]]
    assert len(ids) == len(set(ids))
