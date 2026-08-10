#!/usr/bin/env python3
"""placeholder_blueprint.py -- deterministic, offline crude-primitive
placeholder generation for tools/producer.py's --primitive-fallback
(docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7).

Deliberately a separate, small implementation from
oeb-studio-harness/server/app/services/missing_asset_fallback.py's
tier-2 fallback, not a shared import: that one registers into the
server's Postgres-backed Asset registry for the chat/registry-
resolution path (a live harness + DB dependency); this one writes
into the SAME local, file-based registry
(oeb.config.json/data/resolver_map.json) the deterministic pipeline
already reads -- per section 7's "no separate placeholder-specific
store" decision, extended here rather than duplicated, since the two
registries are genuinely different systems (DB vs. file) serving
different callers. Keeping this pure/stdlib-only (no bpy, no FastAPI/
SQLAlchemy imports) keeps producer.py's deterministic pipeline
offline -- no live harness needed, unlike --studio-chat-fallback.

Placeholder locations get auto-generated mark objects (entry/center/
exit, as new Blueprint "empty" primitives) so a placeholder actor has
somewhere to move from/to even when the whole location is placeholder-
tier too -- confirmed live 2026-08-09 against the real bar-scene
walk-in that a transform-only move (no clip_id) between two named
marks is exactly what the "oblong crosses the room and stops at the
mark" rough-blocking look needs; export_blender.py/blueprint_
interpreter.py's move-cue execution already treats a missing clip_id
as "transform-only move", nothing new needed there.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BLENDER = "blender"

_DEFAULT_PRIMITIVE_BY_KIND = {
    "prop": {"type": "cylinder", "transform": {"location": [0, 0, 0.25], "scale": [0.2, 0.2, 0.5]}},
    "character": {"type": "cylinder", "transform": {"location": [0, 0, 0.9], "scale": [0.25, 0.25, 1.8]}},
    "vehicle": {"type": "cube", "transform": {"location": [0, 0, 0.5], "scale": [1.5, 0.8, 0.8]}},
    "set": {"type": "cube", "transform": {"location": [0, 0, 0.1], "scale": [3.0, 3.0, 0.1]}},
    "location": {"type": "cube", "transform": {"location": [0, 0, 0.1], "scale": [3.0, 3.0, 0.1]}},
}
_DEFAULT_PRIMITIVE_FALLBACK = {"type": "cube", "transform": {"location": [0, 0, 0.5], "scale": [0.5, 0.5, 0.5]}}

# Deliberately crude, symmetric, fixed offsets -- not measured against
# any real geometry, just enough for a transform-only move to have a
# start and an end. See module docstring.
LOCATION_MARK_OFFSETS = {
    "entry": [-2.0, 0.0, 0.0],
    "center": [0.0, 0.0, 0.0],
    "exit": [2.0, 0.0, 0.0],
}


def slugify_placeholder_id(query: str, kind: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", query.strip().lower()).strip("_")
    return f"placeholder_{kind}_{slug}_A"


def location_mark_name(canonical_id: str, mark: str) -> str:
    return f"{canonical_id}_{mark}"


def default_placeholder_blueprint(
    canonical_id: str, kind: str, name: str, *, with_location_marks: bool = False,
) -> dict:
    primitive = dict(_DEFAULT_PRIMITIVE_BY_KIND.get(kind, _DEFAULT_PRIMITIVE_FALLBACK))
    primitive["id"] = "body"
    primitives = [primitive]
    if with_location_marks:
        for mark, offset in LOCATION_MARK_OFFSETS.items():
            primitives.append({
                "id": location_mark_name(canonical_id, mark),
                "type": "empty",
                "transform": {"location": offset},
            })
    return {
        "schema_version": "0.1.0",
        "canonical_id": canonical_id,
        "name": name,
        "kind": kind,
        "units_per_meter": 1.0,
        "primitives": primitives,
        "operations": [],
    }


def build_placeholder_glb(blueprint: dict, glb_output: str, blend_output: str, manifest_output: str) -> None:
    """Run *blueprint* through the real Blender translator
    (tools/blueprint_interpreter.py) to produce an actual .glb -- a
    placeholder is a Blueprint definition, not a pre-built asset file,
    so it needs to be built once before oeb.config.json can reference
    it the same way every other asset does.
    """
    tools_dir = Path(__file__).resolve().parent
    Path(glb_output).parent.mkdir(parents=True, exist_ok=True)
    Path(blend_output).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_output).parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [BLENDER, "--background", "--factory-startup", "--python",
         str(tools_dir / "blueprint_interpreter.py"), "--",
         "--blueprint-json", json.dumps(blueprint),
         "--glb-output", glb_output,
         "--blend-output", blend_output,
         "--manifest-output", manifest_output],
        capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"blueprint_interpreter.py failed building placeholder {blueprint['canonical_id']!r} "
            f"(exit {result.returncode}): {(result.stdout + result.stderr)[-1500:]}"
        )


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def register_placeholder_asset(config_path: str, canonical_id: str, kind: str, glb_relpath: str) -> None:
    """Add *canonical_id* to oeb.config.json's assets map, pointing at
    the freshly-built placeholder .glb -- node name is the Blueprint's
    own root object name, which tools/blueprint_interpreter.py's
    parent_to_root() always names after canonical_id.
    """
    config = _load_json(config_path)
    assets = config.setdefault("assets", {})
    assets[canonical_id] = {
        "file": glb_relpath,
        "node": canonical_id,
        "kind": kind,
        "placeholder": True,
        "source": "producer --primitive-fallback",
    }
    _write_json(config_path, config)


def register_placeholder_location(resolver_map_path: str, location_tag: str, canonical_id: str) -> None:
    rmap = _load_json(resolver_map_path)
    locations = rmap.setdefault("locations", {})
    locations[location_tag] = {
        "set_id": canonical_id,
        # A real set's variants pick between actually-different lit/dressed
        # collections (day vs night); export_blender.py never reads this
        # field at all today (only carried through the SceneSpec), so a
        # single placeholder variant covering every time_of_day is safe --
        # nothing downstream currently depends on the string's meaning.
        "variants": {"morning": "placeholder", "day": "placeholder",
                     "evening": "placeholder", "night": "placeholder"},
        "marks": [location_mark_name(canonical_id, mark) for mark in LOCATION_MARK_OFFSETS],
        "default_props": [],
        "placeholder": True,
        "source": "producer --primitive-fallback",
    }
    _write_json(resolver_map_path, rmap)


def register_placeholder_cast(standins_path: str, speaker_name: str, role_tag: str) -> None:
    """producer.py only ever considers a speaker an "actor" at all if
    `data/standins.json`'s cast dict maps their lowercased dialogue-cue
    name to a role_tag (tools/producer.py:152-157) -- a resolver_map.json
    roles entry alone is never reached without this mapping existing
    first. *speaker_name* must already be lowercased, matching how
    producer.py itself looks it up.
    """
    standins = _load_json(standins_path)
    cast = standins.setdefault("cast", {})
    cast[speaker_name] = role_tag
    _write_json(standins_path, standins)


def register_placeholder_role(
    resolver_map_path: str, role_tag: str, canonical_id: str, location_tag: str,
    location_canonical_id: str,
) -> None:
    """A placeholder role gets a synthesized, clip-less entrance --
    from the location's own entry mark, settling at its center mark,
    with no walk_clip/settle_clip/stand_clip/idle_clip/talk_clip keys
    at all. tools/motion_library.py and tools/resolve_intent.py treat
    a missing clip key as "transform-only" (no NLA strip attempted),
    the same convention export_blender.py's cue execution already
    uses for a move cue with no clip_id.

    A role's spawn_mark/entrance are per-location (keyed by
    *location_tag*, the resolver_map.json locations key -- NOT
    *location_canonical_id*, that location's set_id, which is only
    used to build this location's own mark names): the same character
    or vehicle can recur across multiple different placeholder
    locations in one script (e.g. a hero appearing in both a cockpit
    and an asteroid-field scene), and each occurrence needs its own
    marks. Calling this again for an already-registered role_tag MERGES
    a new location's entry into that role's spawn_marks/entrances
    dicts rather than overwriting the whole role -- see
    docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7's
    spawn_mark limitation writeup.
    """
    rmap = _load_json(resolver_map_path)
    roles = rmap.setdefault("roles", {})
    spawn_mark = location_mark_name(location_canonical_id, "center")
    entrance = {
        "from_mark": location_mark_name(location_canonical_id, "entry"),
        "approach_mark": spawn_mark,
        "walk_duration": 2.0,
        "settle_duration": 0.5,
        "rise_duration": 0.5,
    }
    role = roles.setdefault(role_tag, {
        "character_id": canonical_id,
        "spawn_marks": {},
        "entrances": {},
        "placeholder": True,
        "source": "producer --primitive-fallback",
    })
    role["character_id"] = canonical_id
    role.setdefault("spawn_marks", {})[location_tag] = spawn_mark
    role.setdefault("entrances", {})[location_tag] = entrance
    role["placeholder"] = True
    role["source"] = "producer --primitive-fallback"
    _write_json(resolver_map_path, rmap)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="placeholder_blueprint")
    parser.add_argument("--query", required=True, help="what's missing, e.g. a location_tag or role_tag")
    parser.add_argument("--kind", required=True, choices=sorted(_DEFAULT_PRIMITIVE_BY_KIND))
    parser.add_argument("--with-location-marks", action="store_true")
    parser.add_argument("--assets-root", default="assets/placeholders")
    args = parser.parse_args()

    canonical_id = slugify_placeholder_id(args.query, args.kind)
    blueprint = default_placeholder_blueprint(
        canonical_id, args.kind, args.query, with_location_marks=args.with_location_marks,
    )
    glb_output = f"{args.assets_root}/{canonical_id}.glb"
    build_placeholder_glb(
        blueprint, glb_output,
        f"out/blueprint_builds/{canonical_id}.blend",
        f"out/blueprint_builds/{canonical_id}.manifest.json",
    )
    print(json.dumps({"canonical_id": canonical_id, "glb": glb_output}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
