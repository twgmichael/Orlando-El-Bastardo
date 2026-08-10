import importlib.util
import json
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
        "placeholder_blueprint_for_test",
        _find_tool_path("placeholder_blueprint.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_slugify_placeholder_id_is_deterministic_and_reusable():
    module = load_module()
    assert module.slugify_placeholder_id("deep space", "location") == module.slugify_placeholder_id(
        "Deep Space!!", "location",
    )
    assert module.slugify_placeholder_id("deep space", "location") == "placeholder_location_deep_space_A"


def test_default_placeholder_blueprint_has_one_body_primitive_by_default():
    module = load_module()
    bp = module.default_placeholder_blueprint("placeholder_prop_widget_A", "prop", "widget")
    assert len(bp["primitives"]) == 1
    assert bp["primitives"][0]["id"] == "body"
    assert bp["primitives"][0]["type"] == "cylinder"
    assert bp["canonical_id"] == "placeholder_prop_widget_A"
    assert bp["kind"] == "prop"
    assert bp["operations"] == []


def test_default_placeholder_blueprint_unknown_kind_uses_fallback_primitive():
    module = load_module()
    bp = module.default_placeholder_blueprint("placeholder_widget_A", "mystery_kind", "widget")
    assert bp["primitives"][0]["type"] == "cube"


def test_default_placeholder_blueprint_with_location_marks_adds_three_empties():
    module = load_module()
    bp = module.default_placeholder_blueprint(
        "placeholder_location_deep_space_A", "location", "deep space", with_location_marks=True,
    )
    marks = [p for p in bp["primitives"] if p["type"] == "empty"]
    assert len(marks) == 3
    mark_ids = {p["id"] for p in marks}
    assert mark_ids == {
        "placeholder_location_deep_space_A_entry",
        "placeholder_location_deep_space_A_center",
        "placeholder_location_deep_space_A_exit",
    }
    # body (a real primitive), the three marks, and a baked
    # shot_scale-appropriate camera (docs/planning/CAMERA-SHOT-SCALE-PLAN.md)
    cameras = [p for p in bp["primitives"] if p["type"] == "camera"]
    assert len(cameras) == 1
    assert cameras[0]["id"] == "cam_establishing_wide"  # default shot_scale: intimate
    assert len(bp["primitives"]) == 5


def test_default_placeholder_blueprint_without_location_marks_has_no_empties():
    module = load_module()
    bp = module.default_placeholder_blueprint("placeholder_character_orlando_A", "character", "Orlando")
    assert all(p["type"] != "empty" for p in bp["primitives"])


def test_location_mark_name_namespaces_by_canonical_id():
    module = load_module()
    assert module.location_mark_name("placeholder_location_deep_space_A", "entry") == \
        "placeholder_location_deep_space_A_entry"


def test_register_placeholder_asset_writes_config(tmp_path):
    module = load_module()
    config_path = tmp_path / "oeb.config.json"
    config_path.write_text(json.dumps({"assets": {"existing_A": {"file": "x.glb", "node": "existing_A"}}}))

    module.register_placeholder_asset(str(config_path), "placeholder_prop_widget_A", "prop", "assets/placeholders/placeholder_prop_widget_A.glb")

    config = json.loads(config_path.read_text())
    assert "existing_A" in config["assets"]
    entry = config["assets"]["placeholder_prop_widget_A"]
    assert entry["file"] == "assets/placeholders/placeholder_prop_widget_A.glb"
    assert entry["node"] == "placeholder_prop_widget_A"
    assert entry["placeholder"] is True


def test_register_placeholder_location_writes_resolver_map(tmp_path):
    module = load_module()
    rmap_path = tmp_path / "resolver_map.json"
    rmap_path.write_text(json.dumps({"locations": {}, "roles": {}}))

    module.register_placeholder_location(str(rmap_path), "deep_space", "placeholder_location_deep_space_A")

    rmap = json.loads(rmap_path.read_text())
    loc = rmap["locations"]["deep_space"]
    assert loc["set_id"] == "placeholder_location_deep_space_A"
    assert set(loc["marks"]) == {
        "placeholder_location_deep_space_A_entry",
        "placeholder_location_deep_space_A_center",
        "placeholder_location_deep_space_A_exit",
    }
    assert all(tod in loc["variants"] for tod in ("morning", "day", "evening", "night"))
    assert loc["placeholder"] is True


def test_register_placeholder_cast_adds_speaker_to_cast_dict(tmp_path):
    module = load_module()
    standins_path = tmp_path / "standins.json"
    standins_path.write_text(json.dumps({"cast": {"hero": "protagonist"}}))

    module.register_placeholder_cast(str(standins_path), "casey", "casey")

    standins = json.loads(standins_path.read_text())
    assert standins["cast"]["hero"] == "protagonist"
    assert standins["cast"]["casey"] == "casey"


def test_register_placeholder_role_writes_clip_less_entrance(tmp_path):
    module = load_module()
    rmap_path = tmp_path / "resolver_map.json"
    rmap_path.write_text(json.dumps({"locations": {}, "roles": {}}))

    module.register_placeholder_role(
        str(rmap_path), "orlando", "placeholder_character_orlando_A", "deep_space",
        "placeholder_location_deep_space_A",
    )

    rmap = json.loads(rmap_path.read_text())
    role = rmap["roles"]["orlando"]
    assert role["character_id"] == "placeholder_character_orlando_A"
    assert role["spawn_marks"]["deep_space"] == "placeholder_location_deep_space_A_center"
    entrance = role["entrances"]["deep_space"]
    assert entrance["from_mark"] == "placeholder_location_deep_space_A_entry"
    assert entrance["approach_mark"] == "placeholder_location_deep_space_A_center"
    assert "walk_clip" not in entrance
    assert "settle_clip" not in entrance
    assert "stand_clip" not in entrance
    assert "rise_clip" not in entrance
    assert entrance["walk_duration"] > 0
    assert entrance["settle_duration"] > 0
    assert entrance["rise_duration"] > 0
    assert "idle_clip" not in role
    assert "talk_clip" not in role


def test_register_placeholder_role_merges_second_location(tmp_path):
    """A role appearing in a second location must keep its first
    location's spawn_mark/entrance, not lose it -- the whole point of
    the spawn_marks/entrances dicts being keyed by location_tag."""
    module = load_module()
    rmap_path = tmp_path / "resolver_map.json"
    rmap_path.write_text(json.dumps({"locations": {}, "roles": {}}))

    module.register_placeholder_role(
        str(rmap_path), "orlando", "placeholder_character_orlando_A", "deep_space",
        "placeholder_location_deep_space_A",
    )
    module.register_placeholder_role(
        str(rmap_path), "orlando", "placeholder_character_orlando_A", "asteroid_field",
        "placeholder_location_asteroid_field_A",
    )

    rmap = json.loads(rmap_path.read_text())
    role = rmap["roles"]["orlando"]
    assert role["spawn_marks"]["deep_space"] == "placeholder_location_deep_space_A_center"
    assert role["spawn_marks"]["asteroid_field"] == "placeholder_location_asteroid_field_A_center"
    assert role["entrances"]["deep_space"]["from_mark"] == "placeholder_location_deep_space_A_entry"
    assert role["entrances"]["asteroid_field"]["from_mark"] == "placeholder_location_asteroid_field_A_entry"
