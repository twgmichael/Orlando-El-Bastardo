#!/usr/bin/env python3
"""
build_characters_v3.py — Headless Blender: v2 characters + COSTUME
TRANSPLANT (docs/PROVENANCE.md; RIGGING.md).

Keeps the UBC bodies on `oeb_humanoid_v1` with the UAL clip remap (as v2),
then dresses them with Modular Men/Women garment parts (legacy-rig meshes):
per part — drop the vendor Icosphere helper, bake world transform, strip
legacy rig data; then height-match the assembled stack to the UBC body,
weight-transfer from it (nearest-vertex), and bind to our armature.
Hero: SpaceSuit (pilot flight gear). Bartender: Worker. `_Head` parts bring
the vendor face + hair (REPLACEMENT approach — the UBC meshes are removed).

Vendor gotcha (found 2026-07-08, the "garments don't deform" bug): every
Modular part GLB ships an `Icosphere.00x` helper mesh spanning z -1..+1. It
poisons any bbox height measurement — the old code scaled garments to 64%,
landing the helmet at chest height, so nearest-vertex weights bound the
whole suit to pelvis/spine and nothing visibly deformed.

Run from repo root:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/build_characters_v3.py -- \
    --output assets/characters/oeb_dressed_characters
"""

import sys
import os
import argparse
import math

import bpy
from mathutils import Matrix, Vector

UBC_DIR = "assets/Universal Base Characters[Standard]/GLB"
UAL = "assets/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb"
MEN = "assets/Ultimate Modular Men- Feb 2022/GLB"
WOMEN = "assets/Ultimate Modular Women - April 2022/GLB"

HERO_REMAP = [
    ("walk_to_stool",       "Walk_Loop"),
    ("sit_barstool",        "Sitting_Enter"),
    ("stand_from_stool",    "Sitting_Exit"),
    ("idle_seated_relaxed", "Sitting_Idle_Loop"),
    ("talk_neutral_seated", "Sitting_Talking_Loop"),
    ("nod_small",           "Sitting_Talking_Loop"),
    ("look_down_then_up",   "Sitting_Idle_Loop"),
]
BARTENDER_REMAP = [
    ("idle_standing_relaxed", "Idle_Loop"),
    ("wipe_glass_loop",       "Idle_Torch_Loop"),
    ("talk_friendly_standing", "Idle_Talking_Loop"),
    ("pour_drink_short",      "Interact"),
    ("lean_forward_counter",  "PickUp_Table"),
    ("shrug_small",           "Idle_Talking_Loop"),
]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_characters_v3")
    p.add_argument("--output", default="assets/characters/oeb_dressed_characters")
    return p.parse_args(argv)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), path))
    return list(set(bpy.data.objects) - before)


def bake_and_strip(objs):
    """World-bake mesh transforms; drop non-meshes, rigs, legacy vgroups."""
    meshes = []
    for o in objs:
        if o.type == 'MESH':
            o.data.transform(o.matrix_world)
            o.matrix_world = Matrix.Identity(4)
            o.parent = None
            for mod in list(o.modifiers):
                o.modifiers.remove(mod)
            o.vertex_groups.clear()
            meshes.append(o)
    for o in objs:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    return meshes


def bbox_height(objs):
    zs = []
    for o in objs:
        for c in o.bound_box:
            zs.append((o.matrix_world @ Vector(c)).z)
    return max(zs) - min(zs) if zs else 0.0


def import_character(glb_path, canonical_name, face_z_deg=0.0):
    objs = import_glb(glb_path)
    arms = [o for o in objs if o.type == 'ARMATURE']
    if len(arms) != 1:
        print(f"[v3] ERROR: {glb_path} has {len(arms)} armatures")
        sys.exit(1)
    arm = arms[0]
    arm.name = canonical_name
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_mode = 'XYZ'
    arm.rotation_euler.z += math.radians(face_z_deg)
    if arm.animation_data:
        arm.animation_data_clear()
    body = max((o for o in objs if o.type == 'MESH'),
               key=lambda o: len(o.data.vertices))
    return arm, body, objs


def dress(arm, body, pack_dir, archetype, parts=("Body", "Legs", "Feet"),
          part_prefix=None, part_overrides=None):
    """Transplant garment parts onto `arm`, weights copied from `body`.
    part_prefix: vendor casing quirk — e.g. full char `Spacesuit.glb` but
    parts `SpaceSuit_Body.glb`. part_overrides: {part: (pack_dir, prefix)}
    to mix archetypes — e.g. hero wears the SpaceSuit but keeps the bare
    Casual head (helmet off, 2026-07-11)."""
    part_prefix = part_prefix or archetype
    part_overrides = part_overrides or {}
    dressed = []
    for part in parts:
        src_dir, src_prefix = part_overrides.get(part,
                                                 (pack_dir, part_prefix))
        objs = import_glb(f"{src_dir}/{src_prefix}_{part}.glb")
        # Drop the vendor Icosphere helper (z -1..+1 — see module docstring)
        # before it reaches any measurement or the export.
        for o in list(objs):
            if o.type == 'MESH' and o.name.startswith("Icosphere"):
                bpy.data.objects.remove(o, do_unlink=True)
                objs.remove(o)
        meshes = bake_and_strip(objs)
        for m in meshes:
            # Vendor materials arrive alpha-MASK with alpha 0 (invisible —
            # same bug as the sci-fi kit). Force opaque.
            for slot in m.material_slots:
                mat = slot.material
                if not mat:
                    continue
                if hasattr(mat, "blend_method"):
                    mat.blend_method = 'OPAQUE'
                if mat.use_nodes:
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf and "Alpha" in bsdf.inputs:
                        for link in list(bsdf.inputs["Alpha"].links):
                            mat.node_tree.links.remove(link)
                        bsdf.inputs["Alpha"].default_value = 1.0
            m.name = f"{arm.name}_{archetype}_{part}".lower()
            dressed.append(m)

    # Height-match the assembled garment stack to the UBC body (both stand
    # on z=0), then bind. Parts are positioned in-file to assemble a full
    # character, so one uniform scale keeps them aligned to each other AND
    # to the body — which the nearest-vertex weight lookup depends on.
    src_h = bbox_height(dressed)
    dst_h = bbox_height([body])
    s = dst_h / src_h if src_h > 0 else 1.0
    print(f"[v3] {archetype}: stack {src_h:.2f} → body {dst_h:.2f}, scale {s:.3f}")
    for m in dressed:
        m.data.transform(Matrix.Scale(s, 4))
        # Weight transfer: manual nearest-vertex copy. (The data_transfer
        # OPERATOR silently no-ops headless — found 2026-07-07: garments
        # exported as skins with zero weights.)
        transfer_weights(body, m)
        m.parent = arm
        mod = m.modifiers.new(name="Armature", type='ARMATURE')
        mod.object = arm
    return dressed


def transfer_weights(body, garment):
    """Copy each garment vertex's weights from the nearest body vertex.
    Both meshes must be in the SAME space (dress before rotating the
    armature). Pure API — no operators."""
    from mathutils import kdtree
    bw = body.matrix_world
    kd = kdtree.KDTree(len(body.data.vertices))
    for i, v in enumerate(body.data.vertices):
        kd.insert(bw @ v.co, i)
    kd.balance()
    idx_to_name = {g.index: g.name for g in body.vertex_groups}
    for name in idx_to_name.values():
        if name not in garment.vertex_groups:
            garment.vertex_groups.new(name=name)
    gw = garment.matrix_world
    for gv in garment.data.vertices:
        _co, near, _d = kd.find(gw @ gv.co)
        for ge in body.data.vertices[near].groups:
            garment.vertex_groups[idx_to_name[ge.group]].add(
                [gv.index], ge.weight, 'REPLACE')


def absorb(body, extra_meshes):
    """REPLACEMENT step: the modular parts ARE the clothed body, so once
    weights are copied the UBC meshes (body + face/eye extras) go away."""
    for o in [body, *extra_meshes]:
        bpy.data.objects.remove(o, do_unlink=True)


def attach_clips(arm, remap, source_actions):
    arm.animation_data_create()
    anim = arm.animation_data
    start = 1
    for canonical, source in remap:
        src = source_actions.get(source)
        if src is None:
            print(f"[v3] ERROR: UAL clip missing: {source}")
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

    # Import UNROTATED (facing applied after dressing so body and garment
    # occupy the same space during the nearest-vertex weight lookup).
    hero, hero_body, hero_objs = import_character(
        f"{UBC_DIR}/Superhero_Male_FullBody.glb", "char_hero_v1")
    bartender, bar_body, bartender_objs = import_character(
        f"{UBC_DIR}/Superhero_Female_FullBody.glb", "char_bartender_v1")

    # REPLACEMENT, not overlay (2026-07-07): modular parts ARE the body
    # wearing clothes — the muscular UBC meshes swallow them (suit torso is
    # half the body's depth). Weights transfer FROM the UBC body (correct
    # oeb_humanoid_v1 binding), then the UBC meshes are removed. `Head`
    # included — brings the face + hair.
    hero_garms = dress(hero, hero_body, MEN, "Spacesuit",
                       part_prefix="SpaceSuit",
                       parts=("Body", "Legs", "Feet", "Head"),
                       part_overrides={"Head": (MEN, "Casual")})
    bar_garms = dress(bartender, bar_body, WOMEN, "Worker",
                      parts=("Body", "Legs", "Feet", "Head"))
    print(f"[v3] hero garments: {[m.name for m in hero_garms]}")
    print(f"[v3] bartender garments: {[m.name for m in bar_garms]}")
    absorb(hero_body,
           [o for o in hero_objs if o.type == 'MESH' and o is not hero_body])
    absorb(bar_body,
           [o for o in bartender_objs if o.type == 'MESH' and o is not bar_body])

    # Hero faces the bar (+Y); garments are parented, they rotate along.
    hero.rotation_euler.z += math.radians(180.0)

    ual_objs = import_glb(UAL)
    for o in ual_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    source_actions = {a.name.split(".")[0]: a for a in bpy.data.actions}
    attach_clips(hero, HERO_REMAP, source_actions)
    attach_clips(bartender, BARTENDER_REMAP, source_actions)

    canonical = {c for c, _s in HERO_REMAP} | {c for c, _s in BARTENDER_REMAP}
    for act in list(bpy.data.actions):
        if act.name not in canonical:
            bpy.data.actions.remove(act)

    glb = out_stem + ".glb"
    print(f"[v3] Exporting {glb}")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=False,
        export_animations=True, export_nla_strips=True,
        export_force_sampling=True)
    usdc = out_stem + ".usdc"
    print(f"[v3] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=True,
                              export_armatures=True, export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)
    print("[v3] Done.")


if __name__ == "__main__":
    main()
