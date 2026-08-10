#!/usr/bin/env python3
"""motion_library.py -- consolidated walk-in/walk-out motion grammar.

docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 8: "One
consolidated motion-grammar library. resolve_intent.py's existing
deterministic motion work (walk-in entrances, NLA crossfades) is real,
proven, industry-standard-grade work -- it gets salvaged and pulled
forward as a single shared reference library, not reimplemented, and
applied across all assets where appropriate on both the attended and
unattended ends of section 4's autonomy dial, rather than remaining
specific to the old resolve_intent.py path alone."

This module is that extraction: the pure timing math (R13/R14's
crossfade overlap arithmetic) and SceneSpec move/animation cue
construction that used to live inline inside resolve_intent()'s R13/R14
blocks, with byte-for-byte identical output -- resolve_intent.py now
calls these functions instead of containing the logic itself. Nothing
here is resolve_intent-specific: `entrance`/`departure` dicts are plain
data (from_mark/approach_mark/clip ids/durations, the same shape
data/resolver_map.json's per-role "entrance" block already carries), so
an attended caller (Studio Chat / Producer composing a scene) can drive
the exact same walk-in/walk-out onto an actor without going through the
SceneIntent/resolver-map machinery at all.

Deliberately unchanged from resolve_intent.py's original R13/R14
crossfade constants (0.3s stand->walk blend, 0.3s walk->settle overlap,
0.2s settle->idle overlap, mirrored for rise->walk->idle_out on exit) --
this is a lossless extraction, not a redesign.
"""

from __future__ import annotations


def entrance_times(ent: dict) -> dict:
    """R13 timeline for one entrance. The stand clip exists only as a
    blend source: the walk starts after a 0.3 s standing beat and fades
    in over it; the settle overlaps the walk's end by 0.3 s and the
    idle overlaps the settle's end by 0.2 s (NLA crossfades).
    """
    lead = 0.3 if ent.get("stand_clip") else 0.0
    walk_end = round(lead + ent["walk_duration"], 4)
    settle_start = round(max(lead, walk_end - 0.3), 4)
    settle_end = round(settle_start + ent["settle_duration"], 4)
    return {
        "lead": lead,
        "walk_end": walk_end,
        "settle_start": settle_start,
        "settle_end": settle_end,
        "idle_start": round(max(0.0, settle_end - 0.2), 4),
    }


def departure_times(dep: dict, base: float) -> dict:
    """R14 timeline for one departure, starting at *base* (the scene
    time the actor begins rising from their mark). Mirrors
    entrance_times' crossfade overlaps for the reverse (rise -> walk
    out -> standing idle) direction.
    """
    rise_end = round(base + dep["rise_duration"], 4)
    walk_start = round(rise_end - 0.3, 4)
    walk_end = round(walk_start + dep["walk_duration"], 4)
    return {
        "rise_start": base,
        "walk_start": walk_start,
        "walk_end": walk_end,
        "idle_start": round(walk_end - 0.2, 4),
    }


def build_idle_cue(actor_id: str, clip_id: str, shot_num: int, start_time: float, blend_in: float | None = None) -> dict:
    cue = {
        "type": "animation",
        "cue_id": f"{actor_id}_idle_{shot_num:03d}",
        "start_time": start_time,
        "actor_id": actor_id,
        "clip_id": clip_id,
        "loop": True,
    }
    if blend_in:
        cue["blend_in"] = blend_in
    return cue


def build_entrance_cues(actor_id: str, ent: dict, spawn_mark: str, shot_num: int) -> tuple[list[dict], float, float]:
    """The stand(optional)/walk/settle cues for one actor's walk-in
    entrance (R13). Returns `(cues, idle_start, idle_blend)` -- the
    caller appends its own idle cue via build_idle_cue at that start
    time/blend, exactly as resolve_intent.py's per-actor loop already
    builds one idle cue whether or not the actor has an entrance.
    """
    t = entrance_times(ent)
    cues: list[dict] = []
    if ent.get("stand_clip"):
        cues.append({
            "type": "animation",
            "cue_id": f"{actor_id}_stand_{shot_num:03d}",
            "start_time": 0.0,
            "actor_id": actor_id,
            "clip_id": ent["stand_clip"],
        })
    # Placeholder entrances (tools/placeholder_blueprint.py) have no
    # walk_clip/settle_clip -- a bare primitive has no rig to animate,
    # only a position to move to. export_blender.py/blueprint_
    # interpreter.py's move-cue execution already treats an absent
    # clip_id as "transform-only move", so omitting the key here is
    # enough; nothing downstream needed a change for this.
    walk = {
        "type": "move",
        "cue_id": f"{actor_id}_enter_{shot_num:03d}",
        "start_time": t["lead"],
        "duration": ent["walk_duration"],
        "actor_id": actor_id,
        "from_mark": ent["from_mark"],
        "to_mark": ent["approach_mark"],
        **({"clip_id": ent["walk_clip"]} if ent.get("walk_clip") else {}),
        "loop": True,
    }
    if ent.get("stand_clip") and ent.get("walk_clip"):
        walk["blend_in"] = 0.3
    cues.append(walk)
    settle = {
        "type": "move",
        "cue_id": f"{actor_id}_settle_{shot_num:03d}",
        "start_time": t["settle_start"],
        "duration": ent["settle_duration"],
        "actor_id": actor_id,
        "from_mark": ent["approach_mark"],
        "to_mark": spawn_mark,
        **({"clip_id": ent["settle_clip"]} if ent.get("settle_clip") else {}),
        "facing": "hold",
        **({"blend_in": 0.3} if ent.get("settle_clip") else {}),
    }
    cues.append(settle)
    return cues, t["idle_start"], 0.2


def build_departure_cues(actor_id: str, dep: dict, spawn_mark: str, shot_num: int, dep_time: dict) -> list[dict]:
    """The rise/exit(/idle_out) cues for one actor's walk-out departure
    (R14), given a departure_times() result as *dep_time*.
    """
    rise = {
        "type": "move",
        "cue_id": f"{actor_id}_rise_{shot_num:03d}",
        "start_time": dep_time["rise_start"],
        "duration": dep["rise_duration"],
        "actor_id": actor_id,
        "from_mark": spawn_mark,
        "to_mark": dep["approach_mark"],
        **({"clip_id": dep["rise_clip"]} if dep.get("rise_clip") else {}),
        "facing": "hold",
        **({"blend_in": 0.2} if dep.get("rise_clip") else {}),
    }
    exit_cue = {
        "type": "move",
        "cue_id": f"{actor_id}_exit_{shot_num:03d}",
        "start_time": dep_time["walk_start"],
        "duration": dep["walk_duration"],
        "actor_id": actor_id,
        "from_mark": dep["approach_mark"],
        "to_mark": dep["from_mark"],
        **({"clip_id": dep["walk_clip"]} if dep.get("walk_clip") else {}),
        "loop": True,
        "facing": "travel_hold",
        **({"blend_in": 0.3} if dep.get("walk_clip") else {}),
    }
    cues = [rise, exit_cue]
    if dep.get("stand_clip"):
        cues.append({
            "type": "animation",
            "cue_id": f"{actor_id}_idle_out_{shot_num:03d}",
            "start_time": dep_time["idle_start"],
            "actor_id": actor_id,
            "clip_id": dep["stand_clip"],
            "loop": True,
            "blend_in": 0.2,
        })
    return cues
