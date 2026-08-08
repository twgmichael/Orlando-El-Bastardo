#!/usr/bin/env python3
"""
scenespec_to_blueprint.py -- derive a scene-scoped Blueprint from a
resolved SceneSpec.

Phase 3 of docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 2/12:
"tools/resolve_intent.py is retargeted universally to SceneIntent ->
Blueprint". Implemented here as a derivation layer over the existing,
proven, unchanged `resolve_intent()` resolver
(tools/resolve_intent.py:35-598, ~560 lines of deterministic camera
grammar / motion cue / mark handling, shipped and tested since Phase 6)
rather than rewriting that function's internals to emit Blueprint
natively. `resolve_intent()` itself is untouched by this change --
this module consumes its SceneSpec *output* and derives a Blueprint
from it. This is a deliberate, narrower scope than a literal internal
rewrite: gutting proven, shipped resolver logic in one pass is exactly
the kind of risk REVIEW-AUDIT.md's own Phase 3 discussion (section 10)
warned against for a structurally similar case. The functional outcome
the plan calls for -- "every scene goes through Blueprint... no
separate SceneSpec-authoring path left standing" -- is delivered
end-to-end (SceneIntent -> resolve_intent() -> SceneSpec -> this module
-> Blueprint); a future pass MAY fold this derivation directly into
resolve_intent() once it's proven, per the same incremental discipline
used throughout this plan.

What this derives:
  - The set becomes the first `"type": "import"` primitive (its glTF is
    what carries every mark object everything else resolves against --
    see blueprint_interpreter.py's `mark` field).
  - Each prop becomes an import primitive; `at_mark`, if present, maps
    to `mark` + `mark_mode: "prop"` (R6: keep the prop's own z, take
    the mark's x/y). Props without `at_mark` import at the origin,
    matching the resolver's own SceneSpec shape (not every prop is
    mark-placed today).
  - Each actor becomes an import primitive; `spawn_mark` maps to
    `mark` + `mark_mode: "actor"` (R12: copy the mark's full location).
  - Each shot's `camera_setup` resolves against data/camera_grammar.json
    to a `scene_object` name, emitted as a `set_camera_keyframe`
    operation with `camera_mark` at the shot's start frame (fps from
    SceneSpec.render.fps, default 24). Cue-level motion (R12 move
    cues, NLA crossfades) is NOT yet derived -- open item, see
    UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 11 item 1 (motion-grammar
    mapping onto the generalized set_keyframe vocabulary).
  - `frame_range` spans from frame 1 to the last shot's end_time,
    converted at the render fps.

Run standalone:
  python3 tools/scenespec_to_blueprint.py \\
    --scenespec fixtures/bar_scene.scenespec.json \\
    --camera-grammar data/camera_grammar.json \\
    --output out/blueprints/sc_bar_intro_001.blueprint.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "0.1.0"
DEFAULT_FPS = 24


def parse_args():
    parser = argparse.ArgumentParser(prog="scenespec_to_blueprint")
    parser.add_argument("--scenespec", required=True)
    parser.add_argument(
        "--camera-grammar",
        default=str(PROJECT_ROOT / "data" / "camera_grammar.json"),
    )
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _camera_scene_object(camera_setup_id: str, camera_grammar: dict) -> str:
    for camera in camera_grammar.get("cameras", []):
        if camera.get("camera_id") == camera_setup_id:
            scene_object = camera.get("scene_object")
            if not scene_object:
                raise ValueError(f"camera_grammar entry {camera_setup_id!r} has no scene_object")
            return scene_object
    raise ValueError(f"Unknown camera_setup {camera_setup_id!r} -- not found in camera_grammar.json's cameras list")


def scenespec_to_blueprint(scene_spec: dict, camera_grammar: dict) -> dict:
    fps = int((scene_spec.get("render") or {}).get("fps") or DEFAULT_FPS)
    set_spec = scene_spec["set"]

    primitives = [
        {"id": set_spec["set_id"], "type": "import", "canonical_id": set_spec["set_id"]},
    ]

    for prop in set_spec.get("props", []):
        prim = {"id": prop["prop_id"], "type": "import", "canonical_id": prop["asset_id"]}
        at_mark = prop.get("at_mark")
        if at_mark:
            prim["mark"] = at_mark
            prim["mark_mode"] = "prop"
        primitives.append(prim)

    for actor in scene_spec.get("actors", []):
        primitives.append({
            "id": actor["actor_id"],
            "type": "import",
            "canonical_id": actor["character_id"],
            "mark": actor["spawn_mark"],
            "mark_mode": "actor",
        })

    operations = []
    last_end_time = 0.0
    for shot in sorted(scene_spec.get("shots", []), key=lambda s: s["order"]):
        scene_object = _camera_scene_object(shot["camera_setup"], camera_grammar)
        frame = int(round(shot["start_time"] * fps)) + 1
        operations.append({
            "op": "set_camera_keyframe",
            "target": "camera",
            "params": {"frame": frame, "camera_mark": scene_object},
        })
        last_end_time = max(last_end_time, shot["end_time"])

    frame_end = max(int(round(last_end_time * fps)) + 1, 2)

    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_id": scene_spec["scene_id"],
        "name": scene_spec["scene_id"],
        "kind": "scene",
        "units_per_meter": 1.0,
        "frame_range": {"start": 1, "end": frame_end, "fps": float(fps)},
        "primitives": primitives,
        "operations": operations,
    }


def main():
    args = parse_args()
    scene_spec = json.loads(Path(args.scenespec).read_text())
    camera_grammar = json.loads(Path(args.camera_grammar).read_text())
    blueprint = scenespec_to_blueprint(scene_spec, camera_grammar)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(blueprint, indent=2) + "\n")
    print(f"Blueprint derived from {scene_spec['scene_id']}: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
