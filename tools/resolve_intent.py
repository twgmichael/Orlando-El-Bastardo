#!/usr/bin/env python3
"""resolve_intent.py — Deterministic SceneIntent -> SceneSpec resolver.

Rules R1-R12 per the resolve_intent profile (2026-07-05).
Exit codes: 0 success; 2 input/resolution error; 3 internal validation bug.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import jsonschema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def line_duration(text):
    """R7 duration formula: max(1.5, round(0.9 + 0.3 * word_count, 1))."""
    return max(1.5, round(0.9 + 0.3 * len(text.split()), 1))


# ---------------------------------------------------------------------------
# Resolution core (R2-R12)
# ---------------------------------------------------------------------------

def resolve_intent(intent, rmap, grammar, config):
    """Apply R2-R12. Returns (spec | None, errors_list)."""
    errors = []

    # ------------------------------------------------------------------
    # R2: Set resolution
    # ------------------------------------------------------------------
    loc_tag = intent["location_tag"]
    loc_entry = rmap["locations"].get(loc_tag)
    if loc_entry is None:
        errors.append(
            f"E_UNMAPPED_LOCATION: location_tag '{loc_tag}' not found in resolver map locations"
        )

    tod = intent["time_of_day"]
    variant = None
    if loc_entry is not None:
        if tod not in loc_entry.get("variants", {}):
            errors.append(
                f"E_UNMAPPED_TIME_OF_DAY: time_of_day '{tod}' not found in location '{loc_tag}' variants"
            )
        else:
            variant = loc_entry["variants"][tod]

    # ------------------------------------------------------------------
    # R3: Actor resolution
    # ------------------------------------------------------------------
    intent_actor_ids = [a["actor_id"] for a in intent["actors"]]
    intent_actor_by_id = {a["actor_id"]: a for a in intent["actors"]}
    resolved_roles = {}   # actor_id -> role_entry from map
    seen_char_ids = {}    # character_id -> first actor_id that claimed it

    for actor in intent["actors"]:
        aid = actor["actor_id"]
        role_tag = actor["role_tag"]
        role_entry = rmap["roles"].get(role_tag)
        if role_entry is None:
            errors.append(
                f"E_UNMAPPED_ROLE: role_tag '{role_tag}' for actor '{aid}' not found in resolver map roles"
            )
        else:
            char_id = role_entry["character_id"]
            if char_id in seen_char_ids:
                errors.append(
                    f"E_DUPLICATE_CHARACTER: character_id '{char_id}' resolved for both "
                    f"'{seen_char_ids[char_id]}' and '{aid}'"
                )
            else:
                seen_char_ids[char_id] = aid
                resolved_roles[aid] = role_entry

    # ------------------------------------------------------------------
    # R4: ID sanity
    # ------------------------------------------------------------------

    # Beat order uniqueness
    beat_order_map = {}   # order int -> beat dict
    for beat in intent["beats"]:
        o = beat["order"]
        if o in beat_order_map:
            errors.append(f"E_DUPLICATE_ORDER: duplicate beat order {o}")
        else:
            beat_order_map[o] = beat

    # Shot-intent order uniqueness
    shot_order_seen = set()
    for si in intent["shot_intents"]:
        o = si["order"]
        if o in shot_order_seen:
            errors.append(f"E_DUPLICATE_ORDER: duplicate shot_intent order {o}")
        else:
            shot_order_seen.add(o)

    # Unknown actors referenced in beats
    for beat in intent["beats"]:
        for aid in beat.get("actor_ids", []):
            if aid not in intent_actor_by_id:
                errors.append(
                    f"E_UNKNOWN_ACTOR: actor_id '{aid}' in beat {beat['order']} "
                    f"actor_ids not found in scene actors"
                )
        for dlg in beat.get("dialogue", []):
            aid = dlg["actor_id"]
            if aid not in intent_actor_by_id:
                errors.append(
                    f"E_UNKNOWN_ACTOR: actor_id '{aid}' in beat {beat['order']} "
                    f"dialogue not found in scene actors"
                )

    # Unknown actors in subject_actor_id
    for si in intent["shot_intents"]:
        if "subject_actor_id" in si:
            aid = si["subject_actor_id"]
            if aid not in intent_actor_by_id:
                errors.append(
                    f"E_UNKNOWN_ACTOR: subject_actor_id '{aid}' in shot_intent order "
                    f"{si['order']} not found in scene actors"
                )

    # Bad beat references in shot_intents
    for si in intent["shot_intents"]:
        for bo in si.get("beat_orders", []):
            if bo not in beat_order_map:
                errors.append(
                    f"E_BAD_BEAT_REF: beat_order {bo} in shot_intent order "
                    f"{si['order']} does not match any beat"
                )

    # Asset checks
    config_assets = config.get("assets", {})
    if loc_entry is not None:
        set_id = loc_entry["set_id"]
        if set_id not in config_assets:
            errors.append(
                f"E_UNMAPPED_ASSET: set_id '{set_id}' not found in oeb.config.json assets"
            )
        for prop in loc_entry.get("default_props", []):
            asset_id = prop["asset_id"]
            if asset_id not in config_assets:
                errors.append(
                    f"E_UNMAPPED_ASSET: prop asset_id '{asset_id}' not found in oeb.config.json assets"
                )

    for aid, role_entry in resolved_roles.items():
        char_id = role_entry["character_id"]
        if char_id not in config_assets:
            errors.append(
                f"E_UNMAPPED_ASSET: character_id '{char_id}' not found in oeb.config.json assets"
            )

    # Early exit — cannot safely proceed to camera/shot resolution
    if errors:
        return None, errors

    # ------------------------------------------------------------------
    # R5: Camera resolution
    # ------------------------------------------------------------------
    sorted_shots_intents = sorted(intent["shot_intents"], key=lambda si: si["order"])
    cameras = grammar.get("cameras", [])
    shot_camera_map = []

    for si in sorted_shots_intents:
        framing = si["framing"]
        if framing in ("establishing", "two_shot"):
            matches = [c for c in cameras if c["framing"] == framing]
            if len(matches) != 1:
                errors.append(
                    f"E_NO_CAMERA: framing '{framing}' in shot order {si['order']} "
                    f"matched {len(matches)} cameras, expected exactly 1"
                )
                shot_camera_map.append(None)
            else:
                shot_camera_map.append(matches[0])
        elif framing == "close_on":
            if "subject_actor_id" not in si:
                errors.append(
                    f"E_MISSING_SUBJECT: framing 'close_on' in shot order {si['order']} "
                    f"requires subject_actor_id"
                )
                shot_camera_map.append(None)
            else:
                subj_id = si["subject_actor_id"]
                spawn_mark = resolved_roles[subj_id]["spawn_mark"]
                matches = [
                    c for c in cameras
                    if c["framing"] == "close_on" and c.get("subject_marks") == [spawn_mark]
                ]
                if len(matches) != 1:
                    errors.append(
                        f"E_NO_CAMERA: close_on for actor '{subj_id}' (spawn_mark "
                        f"'{spawn_mark}') matched {len(matches)} cameras, expected exactly 1"
                    )
                    shot_camera_map.append(None)
                else:
                    shot_camera_map.append(matches[0])

    if errors:
        return None, errors

    # ------------------------------------------------------------------
    # R6-R10: Build shots
    # ------------------------------------------------------------------
    global_line_counter = 0
    scene_time = 0.0
    shots = []

    for i, si in enumerate(sorted_shots_intents):
        shot_num = (i + 1) * 10
        framing = si["framing"]
        camera = shot_camera_map[i]

        # R6: shot_id
        if framing == "establishing":
            suffix = "establishing"
        elif framing == "two_shot":
            suffix = "two_shot"
        else:
            suffix = f"close_{si['subject_actor_id']}"
        shot_id = f"shot_{shot_num:03d}_{suffix}"

        # R7: Dialogue scheduling
        beat_orders_for_shot = sorted(si.get("beat_orders", []))
        lines = []   # list of {actor_id, text, start_time, duration}
        cur_start = 1.0
        for bo in beat_orders_for_shot:
            beat = beat_order_map[bo]
            for dlg in beat.get("dialogue", []):
                dur = line_duration(dlg["text"])
                lines.append({
                    "actor_id": dlg["actor_id"],
                    "text": dlg["text"],
                    "start_time": cur_start,
                    "duration": dur,
                })
                cur_start = round(cur_start + dur + 0.5, 1)

        # R8: Shot timing
        if lines:
            last = lines[-1]
            raw = last["start_time"] + last["duration"] + 1.0
            shot_length = max(4.0, math.ceil(raw * 2) / 2)
        else:
            shot_length = 4.0

        start_time = scene_time
        end_time = start_time + shot_length
        scene_time = end_time

        # R9: Present actors
        present_set = set()
        if not beat_orders_for_shot:
            present_set = set(intent_actor_ids)
        else:
            for bo in beat_orders_for_shot:
                beat = beat_order_map[bo]
                if beat.get("actor_ids"):
                    for aid in beat["actor_ids"]:
                        present_set.add(aid)
                elif beat.get("dialogue"):
                    for dlg in beat["dialogue"]:
                        present_set.add(dlg["actor_id"])
                else:
                    present_set.update(intent_actor_ids)

        present_ordered = [aid for aid in intent_actor_ids if aid in present_set]

        # R10: Cues
        cues = []

        # Idle AnimationCue per present actor (intent order)
        for aid in present_ordered:
            cues.append({
                "type": "animation",
                "cue_id": f"{aid}_idle_{shot_num:03d}",
                "start_time": 0.0,
                "actor_id": aid,
                "clip_id": resolved_roles[aid]["idle_clip"],
                "loop": True,
            })

        # Per dialogue line: talk AnimationCue immediately followed by DialogueCue
        for k, line in enumerate(lines, start=1):
            global_line_counter += 1
            act_id = line["actor_id"]
            cues.append({
                "type": "animation",
                "cue_id": f"{act_id}_talk_{shot_num:03d}_{k:02d}",
                "start_time": line["start_time"],
                "actor_id": act_id,
                "clip_id": resolved_roles[act_id]["talk_clip"],
            })
            cues.append({
                "type": "dialogue",
                "cue_id": f"line_{global_line_counter * 10:03d}",
                "start_time": line["start_time"],
                "duration": line["duration"],
                "actor_id": act_id,
                "text": line["text"],
            })

        shots.append({
            "shot_id": shot_id,
            "order": i,
            "start_time": start_time,
            "end_time": end_time,
            "camera_setup": camera["camera_id"],
            "cues": cues,
        })

    # ------------------------------------------------------------------
    # R11: Build envelope
    # ------------------------------------------------------------------

    # Set
    props = []
    for prop in loc_entry.get("default_props", []):
        p = {"prop_id": prop["prop_id"], "asset_id": prop["asset_id"]}
        if "at_mark" in prop:
            p["at_mark"] = prop["at_mark"]
        props.append(p)

    set_spec = {
        "set_id": loc_entry["set_id"],
        "variant": variant,
        "marks": list(loc_entry["marks"]),
        "props": props,
    }

    # Actors
    actors_out = []
    for actor in intent["actors"]:
        aid = actor["actor_id"]
        role_entry = resolved_roles[aid]
        actors_out.append({
            "actor_id": aid,
            "character_id": role_entry["character_id"],
            "spawn_mark": role_entry["spawn_mark"],
            "target_bindings": {
                "usd_path": "/Chars/" + aid.capitalize(),
                "godot_node": "Actors/" + aid.capitalize(),
                "blender_object": role_entry["character_id"],
            },
        })

    # Render (explicit key order to match fixture)
    rd = rmap["defaults"]["render"]
    render_spec = {
        "fps": rd["fps"],
        "resolution": {
            "width": rd["resolution"]["width"],
            "height": rd["resolution"]["height"],
        },
        "engine": rd["engine"],
    }

    export_spec = {
        "targets": list(rmap["defaults"]["export_targets"]),
        "output_dir": intent["scene_id"],
    }

    spec = {
        "schema_version": "1.0.0",
        "scene_id": intent["scene_id"],
        "units": {"length": "meters", "time": "seconds"},
        "set": set_spec,
        "actors": actors_out,
        "shots": shots,
        "render": render_spec,
        "export": export_spec,
    }

    return spec, []


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Resolve SceneIntent JSON to SceneSpec JSON")
    parser.add_argument("--intent", required=True, help="Path to SceneIntent JSON input")
    parser.add_argument("--map", default="data/resolver_map.json", help="Resolver map JSON")
    parser.add_argument("--grammar", default="data/camera_grammar.json", help="Camera grammar JSON")
    parser.add_argument("--config", default="oeb.config.json", help="OEB config JSON")
    parser.add_argument("--schema-dir", default="schemas", help="Directory containing JSON schemas")
    parser.add_argument("--out", default=None, help="Output SceneSpec JSON path")
    args = parser.parse_args()

    # Load intent
    try:
        intent = load_json(args.intent)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"RESOLVE-ERROR E_INTENT_INVALID: cannot load intent file: {exc}", file=sys.stderr)
        sys.exit(2)

    # Load support files
    try:
        rmap = load_json(args.map)
        grammar = load_json(args.grammar)
        config = load_json(args.config)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"RESOLVE-ERROR E_INTENT_INVALID: cannot load support file: {exc}", file=sys.stderr)
        sys.exit(2)

    # Load schemas
    schema_dir = Path(args.schema_dir)
    try:
        intent_schema = load_json(schema_dir / "sceneintent.schema.json")
        spec_schema = load_json(schema_dir / "scenespec.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"RESOLVE-ERROR E_INTENT_INVALID: cannot load schema: {exc}", file=sys.stderr)
        sys.exit(2)

    # R1: Validate intent against schema
    validator = jsonschema.Draft202012Validator(intent_schema)
    schema_errors = sorted(validator.iter_errors(intent), key=lambda e: list(e.path))
    if schema_errors:
        for err in schema_errors:
            print(f"RESOLVE-ERROR E_INTENT_INVALID: {err.message}", file=sys.stderr)
        sys.exit(2)

    # Determine output path (needs scene_id from validated intent)
    scene_id = intent["scene_id"]
    out_path = Path(args.out) if args.out else Path(f"out/{scene_id}.scenespec.json")

    # Run resolution (R2-R12)
    spec, errors = resolve_intent(intent, rmap, grammar, config)

    if errors:
        for err in errors:
            print(f"RESOLVE-ERROR {err}", file=sys.stderr)
        sys.exit(2)

    # R12: Validate produced spec
    try:
        jsonschema.Draft202012Validator(spec_schema).validate(spec)
    except jsonschema.ValidationError as exc:
        print(
            f"Internal error: produced spec failed scenespec schema validation: {exc.message}",
            file=sys.stderr,
        )
        sys.exit(3)

    # R12: Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
