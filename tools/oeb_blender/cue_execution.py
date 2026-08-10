"""oeb_blender/cue_execution.py -- shared move/animation-cue Blender
execution, extracted from tools/export_blender.py so
tools/blueprint_interpreter.py's play_move_cue/play_animation_cue
Blueprint operations (docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 11 item 3 / section 3's fixed-vocabulary decision) can drive
the exact same NLA-strip/facing-turn machinery export_blender.py
already proved against real SceneSpec scenes, instead of a second
implementation. Lossless extraction, not a redesign -- see
export_blender.py's own R7/R8/R12 rule-number comments this preserves.
"""

from __future__ import annotations

import math
import re


def to_frame(t_seconds: float, fps: float) -> int:
    """R3: convert absolute seconds to a Blender 1-based frame number."""
    return round(t_seconds * fps) + 1


def find_action(clip_id: str):
    """R7: resolve *clip_id* to exactly one bpy.data.actions entry.
    Candidate = exact name match OR name with trailing .NNN suffix
    stripped. Exactly one candidate -> return it; otherwise -> raise.
    """
    import bpy  # noqa

    candidates = []
    seen_ptr = set()
    for action in bpy.data.actions:
        nm = action.name
        match = (nm == clip_id) or (re.sub(r"\.\d+$", "", nm) == clip_id)
        if match and id(action) not in seen_ptr:
            candidates.append(action)
            seen_ptr.add(id(action))

    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"clip {clip_id!r} resolved to {len(candidates)} actions")


def apply_move(obj, cue: dict, start_frame: int, end_frame: int, fps: float) -> None:
    """R12: keyframe *obj* location from from_mark to to_mark across the cue.

    Facing convention: OEB character assets face -Y at object rotation 0
    (UAL clip baseline), so the absolute heading that faces travel
    direction (dx, dy) is atan2(dx, -dy). facing='travel' keys that
    heading for the journey and turns back to the asset's resting
    rotation over the final ~0.4 s; facing='hold' leaves rotation alone.
    """
    import bpy  # noqa

    from_obj = bpy.data.objects.get(cue["from_mark"])
    to_obj = bpy.data.objects.get(cue["to_mark"])
    cue_id = cue.get("cue_id", "<no-id>")
    if from_obj is None:
        raise ValueError(f"move cue {cue_id!r} from_mark {cue['from_mark']!r} not found in scene")
    if to_obj is None:
        raise ValueError(f"move cue {cue_id!r} to_mark {cue['to_mark']!r} not found in scene")

    src = from_obj.location.copy()
    dst = to_obj.location.copy()

    # glTF-imported objects arrive in QUATERNION rotation mode; convert so
    # z-euler keyframes apply.
    if obj.rotation_mode != "XYZ":
        eul = (obj.rotation_quaternion.to_euler("XYZ")
               if obj.rotation_mode == "QUATERNION"
               else obj.rotation_euler.to_quaternion().to_euler("XYZ"))
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = eul
    base_rz = obj.rotation_euler.z

    obj.location = src
    obj.keyframe_insert("location", frame=start_frame)
    obj.location = dst
    obj.keyframe_insert("location", frame=end_frame)

    facing = cue.get("facing", "travel")
    if facing in ("travel", "travel_hold"):
        dx, dy = dst.x - src.x, dst.y - src.y
        if (dx * dx + dy * dy) > 1e-8:
            heading = math.atan2(dx, -dy)
            turn_frames = max(2, int(round(0.4 * fps)))
            if facing == "travel":
                # Arrive: enter already facing travel, turn back to the
                # resting facing (expressed nearest the heading -- no
                # long-way spins) over the final ~0.4 s.
                delta = (base_rz - heading + math.pi) % (2 * math.pi) - math.pi
                rest_rz = heading + delta
                obj.rotation_euler.z = heading
                obj.keyframe_insert("rotation_euler", index=2, frame=start_frame)
                obj.keyframe_insert(
                    "rotation_euler", index=2,
                    frame=max(start_frame + 1, end_frame - turn_frames),
                )
                obj.rotation_euler.z = rest_rz
                obj.keyframe_insert("rotation_euler", index=2, frame=end_frame)
            else:
                # Exit: anchor the CURRENT resting facing at move start,
                # turn INTO travel over ~0.4 s, and keep facing it
                # (constant extrapolation).
                heading_n = base_rz + ((heading - base_rz + math.pi) % (2 * math.pi) - math.pi)
                obj.rotation_euler.z = base_rz
                obj.keyframe_insert("rotation_euler", index=2, frame=start_frame)
                obj.rotation_euler.z = heading_n
                obj.keyframe_insert(
                    "rotation_euler", index=2,
                    frame=min(end_frame, start_frame + turn_frames),
                )
            obj.rotation_euler.z = base_rz


def apply_nla_clip(
    obj,
    cue_id: str,
    clip_id: str,
    frame_num: int,
    fps: float,
    *,
    blend_in: float = 0.0,
    loop: bool = False,
    available_frames: float | None = None,
) -> None:
    """R8: create one NLA track/strip playing *clip_id* on *obj* starting
    at *frame_num*, with HOLD_FORWARD extrapolation (a lone strip's
    first frame must not project backward over the whole timeline at
    REPLACE priority), an optional crossfade (*blend_in*, in seconds --
    the strip fades in over the pose held by the previous track's
    strip), and looping to fill *available_frames* seconds when *loop*
    is set (repeat = max(1, ceil(available_frames / action_frames))).
    """
    action = find_action(clip_id)

    if obj.animation_data is None:
        obj.animation_data_create()

    track = obj.animation_data.nla_tracks.new()
    track.name = cue_id

    strip = track.strips.new(cue_id, frame_num, action)
    strip.extrapolation = "HOLD_FORWARD"
    if blend_in:
        strip.blend_in = blend_in * fps

    if loop:
        action_frames = max(1.0, action.frame_range[1] - action.frame_range[0])
        available = available_frames if available_frames is not None else action_frames
        strip.repeat = max(1, math.ceil(available / action_frames))


def apply_fx_cue(root_obj, target_obj, frame_num: int, fps: float) -> None:
    """R13 (docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 7
    item 7): trigger a multi-object effect-rig asset -- several
    separately-animated objects under one root (e.g. the Hyperspace
    Effect: HYPERSPACE_EVENT_ROOT plus an ignition/engulfment/cloud/
    residue stage each with their own scale/rotation action), not one
    object with one action like apply_nla_clip() alone covers.

    Parents *root_obj* to *target_obj* (the actor/ship it travels with)
    at *target_obj*'s local origin, then walks every object in the
    rig -- root plus all descendants -- looking for an action named
    Blender's own default `f"{obj.name}Action"`. Objects with a match
    get a fresh NLA strip via apply_nla_clip(), all anchored at the same
    *frame_num* so the rig's stages stay in sync; objects with no match
    are static geometry riding along with an animated parent (true for
    most of a rig like this one) and are silently skipped -- not an
    error, and not a hardcoded per-asset table of which objects to
    expect.
    """
    root_obj.parent = target_obj
    root_obj.location = (0.0, 0.0, 0.0)

    for obj in [root_obj] + root_obj.children_recursive:
        clip_id = f"{obj.name}Action"
        try:
            apply_nla_clip(obj, clip_id, clip_id, frame_num, fps)
        except ValueError:
            continue
