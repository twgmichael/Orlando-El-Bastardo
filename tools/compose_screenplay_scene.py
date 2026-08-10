#!/usr/bin/env python3
"""
compose_screenplay_scene.py -- section 6's other "automatic composition"
half, completing screenplay_entity_resolution.py: turn a screenplay
line's *resolved* entities into a scene-scoped Blueprint's "import"
primitives, with plausible spatial/motion relationships via the
animation vocabulary in section 8 -- `set_keyframe`, already
generalized to any object id, not just "camera"
(tools/blueprint_interpreter.py's `_apply_set_keyframe`).

This module does not talk to the registry itself and does not decide
what a line's entities refer to -- that's screenplay_entity_resolution
.py's job. It only takes that module's output (already-resolved
canonical_ids) and assembles a Blueprint dict; running it through
tools/blueprint_interpreter.py is a separate step this module doesn't
perform either.

Deliberately narrow, deterministic motion grammar, not a general
parser -- exactly the plan's own illustrative example ("JB100 flies
past chased by Ellipso Flyers and Ventradi cruiser"):

- A "flyby" verb phrase ("flies past", "flies by", "flying past",
  "passes") marks the line's single subject: the first resolved entity
  mentioned before a "chased by"/"trailed by"/"followed by" marker (or
  the only flyby entity, if there is no chase marker). The subject
  sweeps laterally across the shot, past a static camera, oriented
  toward its direction of travel.
- Entities mentioned after a chase marker become chasers: the same
  sweep, delayed in time and pushed back in depth (and spread slightly
  in altitude so several chasers don't overlap), one after another.
- Anything else placeable but not classified as subject or chaser
  becomes a static import with no motion -- nothing in the line said
  where it belongs, so it is not guessed at.

No lighting/environment/camera-grammar work is attempted here --
out of scope for this composer; see section 8's separate items.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

FLYBY_VERB_PATTERN = re.compile(r"\bfl(?:ies|y|ying)\s+(?:past|by)\b|\bpasses\b", re.IGNORECASE)
CHASE_MARKER_PATTERN = re.compile(r"\b(?:chased|trailed|followed)\s+by\b", re.IGNORECASE)

PLACEABLE_OUTCOMES = ("resolved", "fallback_created")


def classify_entities(line: str, placeable_entities: list[dict]) -> tuple[str | None, list[str], list[str]]:
    """Return (subject_entity_text, chaser_entity_texts, static_entity_texts).

    Both the flyby verb and the chase marker must be present for the
    chaser archetype to activate at all -- entities after a lone
    "chased by" with no flyby subject to trail have nothing to trail,
    so they fall back to static rather than being guessed into motion.
    """
    flyby_match = FLYBY_VERB_PATTERN.search(line)
    chase_match = CHASE_MARKER_PATTERN.search(line) if flyby_match else None

    subject: str | None = None
    chasers: list[str] = []
    static: list[str] = []
    lowered_line = line.lower()

    for entity in placeable_entities:
        text = entity["entity_text"]
        position = lowered_line.find(text.lower())
        if flyby_match and subject is None and (chase_match is None or position < chase_match.start()):
            subject = text
        elif chase_match and position > chase_match.start():
            chasers.append(text)
        else:
            static.append(text)

    return subject, chasers, static


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "entity"


def _forward_aim(start_pos: list[float], end_pos: list[float]) -> list[float]:
    """A point beyond *end_pos*, extrapolated along the start->end
    direction -- so "facing direction of travel" stays well-defined
    (and non-degenerate for _look_at_rotation) at the END keyframe too,
    where aiming literally at end_pos would make position == aim.
    """
    return [end_pos[i] + (end_pos[i] - start_pos[i]) for i in range(3)]


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def compose_screenplay_scene(
    line: str,
    resolved_entities: list[dict],
    *,
    canonical_id: str,
    name: str | None = None,
    frame_start: int = 1,
    frame_end: int = 48,
    lateral_extent: float = 6.0,
    altitude: float = 1.2,
    camera_distance: float = 9.0,
    subject_depth: float = 0.0,
    trail_depth_step: float = 1.5,
    trail_frame_step: int = 6,
    trail_altitude_spread: float = 0.6,
) -> dict:
    """Build a scene-scoped Blueprint from *resolved_entities* (the
    output of screenplay_entity_resolution.resolve_screenplay_line_entities).

    Returns `{"blueprint": ..., "unresolved_entities": [...], "subject":
    ..., "chasers": [...], "static": [...]}` -- entities that never
    resolved to a canonical_id (needs_clarification / no_match) are
    reported, not silently dropped, so a caller can see exactly what
    didn't make it into the Blueprint and why.
    """
    placeable = [
        entity for entity in resolved_entities
        if entity.get("outcome") in PLACEABLE_OUTCOMES and entity.get("resolved")
    ]
    unresolved = [entity for entity in resolved_entities if entity not in placeable]

    subject_text, chaser_texts, static_texts = classify_entities(line, placeable)
    entity_by_text = {entity["entity_text"]: entity for entity in placeable}

    used_ids: set[str] = set()
    primitives: list[dict] = []
    operations: list[dict] = [{
        "op": "set_camera_keyframe",
        "target": "camera",
        "params": {
            "frame": frame_start,
            "position": [0.0, -camera_distance, altitude],
            "aim": [0.0, 0.0, altitude],
        },
    }]

    def add_import(entity_text: str) -> str:
        entity = entity_by_text[entity_text]
        prim_id = _unique_id(_slugify(entity_text), used_ids)
        primitives.append({
            "id": prim_id,
            "type": "import",
            "canonical_id": entity["resolved"]["canonical_id"],
        })
        return prim_id

    if subject_text:
        prim_id = add_import(subject_text)
        start_pos = [-lateral_extent, subject_depth, altitude]
        end_pos = [lateral_extent, subject_depth, altitude]
        forward = _forward_aim(start_pos, end_pos)
        operations.append({"op": "set_keyframe", "target": prim_id,
                            "params": {"frame": frame_start, "position": start_pos, "aim": forward}})
        operations.append({"op": "set_keyframe", "target": prim_id,
                            "params": {"frame": frame_end, "position": end_pos, "aim": forward}})

    for index, chaser_text in enumerate(chaser_texts):
        prim_id = add_import(chaser_text)
        depth = subject_depth + trail_depth_step * (index + 1)
        z = altitude + (trail_altitude_spread if index % 2 == 0 else -trail_altitude_spread) * ((index // 2) + 1)
        chaser_start = min(frame_start + trail_frame_step * (index + 1), frame_end - 1)
        start_pos = [-lateral_extent, depth, z]
        end_pos = [lateral_extent, depth, z]
        forward = _forward_aim(start_pos, end_pos)
        operations.append({"op": "set_keyframe", "target": prim_id,
                            "params": {"frame": chaser_start, "position": start_pos, "aim": forward}})
        operations.append({"op": "set_keyframe", "target": prim_id,
                            "params": {"frame": frame_end, "position": end_pos, "aim": forward}})

    for static_text in static_texts:
        add_import(static_text)

    blueprint = {
        "schema_version": "0.1.0",
        "canonical_id": canonical_id,
        "name": name or canonical_id,
        "kind": "scene",
        "units_per_meter": 1.0,
        "frame_range": {"start": frame_start, "end": frame_end, "fps": 24.0},
        "primitives": primitives,
        "operations": operations,
    }
    return {
        "blueprint": blueprint,
        "unresolved_entities": unresolved,
        "subject": subject_text,
        "chasers": chaser_texts,
        "static": static_texts,
    }


def parse_args():
    parser = argparse.ArgumentParser(prog="compose_screenplay_scene")
    parser.add_argument("--line", required=True, help="screenplay/action line")
    parser.add_argument("--canonical-id", required=True)
    parser.add_argument("--harness-url", default=None)
    parser.add_argument("--admin-token", default=None)
    parser.add_argument(
        "--fallback", action="store_true",
        help="register tier-2 placeholders for unmatched entities before composing",
    )
    return parser.parse_args()


def main() -> int:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from screenplay_entity_resolution import resolve_screenplay_line_entities

    args = parse_args()
    harness_url = args.harness_url or os.environ.get("OEB_HARNESS_URL")
    admin_token = args.admin_token or os.environ.get("API_ADMIN_TOKEN")
    if not harness_url or not admin_token:
        print("[compose_screenplay_scene] ERROR: set OEB_HARNESS_URL and API_ADMIN_TOKEN", file=sys.stderr)
        return 2

    resolved = resolve_screenplay_line_entities(harness_url, admin_token, args.line, fallback=args.fallback)
    result = compose_screenplay_scene(args.line, resolved, canonical_id=args.canonical_id)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
