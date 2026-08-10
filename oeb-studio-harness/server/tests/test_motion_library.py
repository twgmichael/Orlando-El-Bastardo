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
        "motion_library_for_test",
        _find_tool_path("motion_library.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENTRANCE = {
    "from_mark": "hero_entry_A",
    "approach_mark": "hero_stool_front_A",
    "stand_clip": "idle_standing_relaxed",
    "walk_clip": "walk_to_stool",
    "walk_duration": 2.6667,
    "settle_clip": "sit_barstool",
    "settle_duration": 1.3,
    "rise_clip": "stand_from_stool",
    "rise_duration": 1.3,
}

ENTRANCE_NO_STAND = {
    "from_mark": "hero_entry_A",
    "approach_mark": "hero_stool_front_A",
    "walk_clip": "walk_to_stool",
    "walk_duration": 2.0,
    "settle_clip": "sit_barstool",
    "settle_duration": 1.0,
}


def test_entrance_times_applies_030_lead_when_stand_clip_present():
    module = load_module()
    times = module.entrance_times(ENTRANCE)
    assert times["lead"] == 0.3
    assert times["walk_end"] == round(0.3 + 2.6667, 4)
    assert times["settle_start"] == round(times["walk_end"] - 0.3, 4)
    assert times["settle_end"] == round(times["settle_start"] + 1.3, 4)
    assert times["idle_start"] == round(times["settle_end"] - 0.2, 4)


def test_entrance_times_no_lead_without_stand_clip():
    module = load_module()
    times = module.entrance_times(ENTRANCE_NO_STAND)
    assert times["lead"] == 0.0
    assert times["walk_end"] == 2.0


def test_entrance_times_idle_start_never_negative():
    module = load_module()
    tiny = {"walk_duration": 0.01, "settle_duration": 0.01}
    times = module.entrance_times(tiny)
    assert times["idle_start"] >= 0.0


def test_departure_times_mirrors_entrance_crossfade_offsets():
    module = load_module()
    dep = {"rise_duration": 1.3, "walk_duration": 2.5}
    times = module.departure_times(dep, base=5.0)
    assert times["rise_start"] == 5.0
    assert times["walk_start"] == round(5.0 + 1.3 - 0.3, 4)
    assert times["walk_end"] == round(times["walk_start"] + 2.5, 4)
    assert times["idle_start"] == round(times["walk_end"] - 0.2, 4)


def test_build_idle_cue_omits_blend_in_when_none():
    module = load_module()
    cue = module.build_idle_cue("hero", "idle_seated", 10, 0.0)
    assert cue == {
        "type": "animation", "cue_id": "hero_idle_010", "start_time": 0.0,
        "actor_id": "hero", "clip_id": "idle_seated", "loop": True,
    }


def test_build_idle_cue_includes_blend_in_when_given():
    module = load_module()
    cue = module.build_idle_cue("hero", "idle_seated", 10, 2.5, blend_in=0.2)
    assert cue["blend_in"] == 0.2


def test_build_entrance_cues_includes_stand_walk_settle_in_order():
    module = load_module()
    cues, idle_start, idle_blend = module.build_entrance_cues("hero", ENTRANCE, "hero_barstool_A", 10)
    assert [c["type"] for c in cues] == ["animation", "move", "move"]
    assert cues[0]["clip_id"] == "idle_standing_relaxed"
    walk = cues[1]
    assert walk["from_mark"] == "hero_entry_A"
    assert walk["to_mark"] == "hero_stool_front_A"
    assert walk["blend_in"] == 0.3
    settle = cues[2]
    assert settle["from_mark"] == "hero_stool_front_A"
    assert settle["to_mark"] == "hero_barstool_A"
    assert idle_blend == 0.2
    assert idle_start == module.entrance_times(ENTRANCE)["idle_start"]


def test_build_entrance_cues_omits_stand_cue_and_walk_blend_without_stand_clip():
    module = load_module()
    cues, _idle_start, _idle_blend = module.build_entrance_cues(
        "hero", ENTRANCE_NO_STAND, "hero_barstool_A", 10,
    )
    assert [c["type"] for c in cues] == ["move", "move"]
    assert "blend_in" not in cues[0]


def test_build_departure_cues_includes_rise_and_exit():
    module = load_module()
    dep = {**ENTRANCE, "approach_mark": "hero_stool_front_A"}
    dep_time = module.departure_times(dep, base=5.0)
    cues = module.build_departure_cues("hero", dep, "hero_barstool_A", 10, dep_time)
    assert [c["type"] for c in cues] == ["move", "move", "animation"]
    rise, exit_cue, idle_out = cues
    assert rise["from_mark"] == "hero_barstool_A"
    assert rise["to_mark"] == "hero_stool_front_A"
    assert exit_cue["from_mark"] == "hero_stool_front_A"
    assert exit_cue["to_mark"] == dep["from_mark"]
    assert idle_out["clip_id"] == dep["stand_clip"]


PLACEHOLDER_ENTRANCE = {
    "from_mark": "loc_entry", "approach_mark": "loc_center",
    "walk_duration": 2.0, "settle_duration": 0.5, "rise_duration": 0.5,
}


def test_build_entrance_cues_omits_clip_id_for_placeholder_entrance():
    module = load_module()
    cues, idle_start, idle_blend = module.build_entrance_cues(
        "actor1", PLACEHOLDER_ENTRANCE, "loc_center", 10,
    )
    assert [c["type"] for c in cues] == ["move", "move"]
    walk, settle = cues
    assert "clip_id" not in walk
    assert "blend_in" not in walk
    assert "clip_id" not in settle
    assert "blend_in" not in settle
    assert walk["from_mark"] == "loc_entry"
    assert settle["to_mark"] == "loc_center"


def test_build_departure_cues_omits_clip_id_for_placeholder_departure():
    module = load_module()
    dep_time = module.departure_times(PLACEHOLDER_ENTRANCE, base=5.0)
    cues = module.build_departure_cues("actor1", PLACEHOLDER_ENTRANCE, "loc_center", 10, dep_time)
    assert [c["type"] for c in cues] == ["move", "move"]
    rise, exit_cue = cues
    assert "clip_id" not in rise
    assert "blend_in" not in rise
    assert "clip_id" not in exit_cue
    assert "blend_in" not in exit_cue


def test_build_departure_cues_omits_idle_out_without_stand_clip():
    module = load_module()
    dep = {**ENTRANCE_NO_STAND, "rise_clip": "stand_from_stool", "rise_duration": 1.0}
    dep_time = module.departure_times(dep, base=5.0)
    cues = module.build_departure_cues("hero", dep, "hero_barstool_A", 10, dep_time)
    assert [c["type"] for c in cues] == ["move", "move"]
