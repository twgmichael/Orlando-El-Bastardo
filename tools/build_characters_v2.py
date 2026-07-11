#!/usr/bin/env python3
"""
build_characters_v2.py — Headless Blender: assemble pipeline characters v2
from the Quaternius CC0 stack (docs/PROVENANCE.md) on the `oeb_humanoid_v1`
skeleton (docs/RIGGING.md).

Superhero Male → `char_hero_v1`, Superhero Female → `char_bartender_v1`
(textures kept). The Universal Animation Library's clips are copied and
RENAMED to the canonical clip IDs (RIGGING.md §4 remap-at-build-time), then
pushed as NLA strips on the owning character. UAL source clips are in-place;
both source stacks share the skeleton, so no retargeting occurs.

v0 remap notes: no literal nod/shrug/wipe clips exist in UAL Standard —
nearest pose-correct sources are duplicated under the canonical names (see
REMAP tables). Revisit when custom clips are authored.

Run from repo root:
  blender --background --factory-startup \
    --python tools/build_characters_v2.py -- \
    --output assets/characters/oeb_ubc_characters
"""

import sys
import os
import argparse

import bpy

UBC_DIR = "assets/Universal Base Characters[Standard]/GLB"
UAL = "assets/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb"

HERO_REMAP = [
    ("walk_to_stool",       "Walk_Loop"),
    ("sit_barstool",        "Sitting_Enter"),
    ("idle_seated_relaxed", "Sitting_Idle_Loop"),
    ("talk_neutral_seated", "Sitting_Talking_Loop"),
    ("nod_small",           "Sitting_Talking_Loop"),   # v0: no nod clip
    ("look_down_then_up",   "Sitting_Idle_Loop"),      # v0: no glance clip
]
BARTENDER_REMAP = [
    ("idle_standing_relaxed", "Idle_Loop"),
    ("wipe_glass_loop",       "Idle_Torch_Loop"),      # v0: raised-arm hold
    ("talk_friendly_standing", "Idle_Talking_Loop"),
    ("pour_drink_short",      "Interact"),
    ("lean_forward_counter",  "PickUp_Table"),
    ("shrug_small",           "Idle_Talking_Loop"),    # v0: no shrug clip
]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_characters_v2")
    p.add_argument("--output", default="assets/characters/oeb_ubc_characters")
    return p.parse_args(argv)


def import_character(glb_path, canonical_name, face_z_deg=0.0):
    """face_z_deg: object-level Z rotation baked into the asset so the
    character faces the right way at its mark (clips are pose-local and ride
    along). Hero: -90° turns the UAL seated clips to face the bar (+Y)."""
    import math
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), glb_path))
    imported = list(set(bpy.data.objects) - before)
    arms = [o for o in imported if o.type == 'ARMATURE']
    if len(arms) != 1:
        print(f"[build_characters_v2] ERROR: {glb_path} has {len(arms)} armatures")
        sys.exit(1)
    arm = arms[0]
    arm.name = canonical_name
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_mode = 'XYZ'
    arm.rotation_euler.z += math.radians(face_z_deg)
    if arm.animation_data:
        arm.animation_data_clear()
    return arm


def attach_clips(arm, remap, source_actions):
    arm.animation_data_create()
    anim = arm.animation_data
    start = 1
    for canonical, source in remap:
        src = source_actions.get(source)
        if src is None:
            print(f"[build_characters_v2] ERROR: UAL clip missing: {source}")
            sys.exit(1)
        action = src.copy()
        action.name = canonical
        action.use_fake_user = True
        track = anim.nla_tracks.new()
        track.name = canonical
        length = max(2, int(action.frame_range[1] - action.frame_range[0]) + 1)
        strip = track.strips.new(canonical, start, action)
        strip.frame_start = float(start)
        strip.frame_end = float(start + length - 1)
        start += length + 4
    anim.action = None


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)

    # UAL clips' base facing is -Y (toward camera); 180° turns the hero to
    # face the bar (+Y). (First attempt -90° sent him to the left wall.)
    hero = import_character(f"{UBC_DIR}/Superhero_Male_FullBody.glb",
                            "char_hero_v1", face_z_deg=180.0)
    bartender = import_character(f"{UBC_DIR}/Superhero_Female_FullBody.glb",
                                 "char_bartender_v1")

    # Pull the clip library in, keep only its actions
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), UAL))
    for o in set(bpy.data.objects) - before:
        bpy.data.objects.remove(o, do_unlink=True)
    source_actions = {a.name.split(".")[0]: a for a in bpy.data.actions}
    print(f"[build_characters_v2] UAL actions available: {len(source_actions)}")

    attach_clips(hero, HERO_REMAP, source_actions)
    attach_clips(bartender, BARTENDER_REMAP, source_actions)

    # Drop every action that isn't one of the 12 canonical copies
    canonical = {c for c, _s in HERO_REMAP} | {c for c, _s in BARTENDER_REMAP}
    for act in list(bpy.data.actions):
        if act.name not in canonical:
            bpy.data.actions.remove(act)
    print(f"[build_characters_v2] canonical clips kept: "
          f"{sorted(a.name for a in bpy.data.actions)}")

    glb = out_stem + ".glb"
    print(f"[build_characters_v2] Exporting {glb}")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=False,
        export_animations=True, export_nla_strips=True,
        export_force_sampling=True,
    )
    usdc = out_stem + ".usdc"
    print(f"[build_characters_v2] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=True,
                              export_armatures=True, export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)
    print("[build_characters_v2] Done.")


if __name__ == "__main__":
    main()
