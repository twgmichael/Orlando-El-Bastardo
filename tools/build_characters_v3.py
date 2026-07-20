#!/usr/bin/env python3
"""
build_characters_v3.py — Headless Blender: v2 characters + COSTUME
TRANSPLANT (docs/PROVENANCE.md; RIGGING.md).

Keeps the UBC armatures on `oeb_humanoid_v1` with the UAL clip remap (as v2).
The hero is dressed with Modular Men garment parts (legacy-rig meshes):
per part — drop the vendor Icosphere helper, bake world transform, strip
legacy rig data; then height-match the assembled stack to the UBC body,
weight-transfer from it (nearest-vertex), and bind to our armature.
Hero: SpaceSuit (pilot flight gear). `_Head` parts bring the vendor face +
hair (REPLACEMENT approach — the UBC meshes are removed).

The bartender keeps the same canonical armature and clip table, but replaces
the vendor body with a primitive-built, faceted, late-1990s low-poly skin:
tapered limb cylinders, ellipsoid head/hands/shoes, wedge-like torso, apron
panel, and pixel-scale face marks. Pieces are rigid-weighted to their named
deforming bones so key riggers can pose with the normal `oeb_humanoid_v1`
controls while preserving a period-correct, non-rubber deformation style.

Vendor gotcha (found 2026-07-08, the "garments don't deform" bug): every
Modular part GLB ships an `Icosphere.00x` helper mesh spanning z -1..+1. It
poisons any bbox height measurement — the old code scaled garments to 64%,
landing the helmet at chest height, so nearest-vertex weights bound the
whole suit to pelvis/spine and nothing visibly deformed.

Run from repo root:
  blender --background --factory-startup \
    --python tools/build_characters_v3.py -- \
    --output-dir assets/characters
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
    p.add_argument("--output-dir", default=None)
    p.add_argument("--output", default=None,
                   help="Legacy combined-output stem; dirname is used for separate assets.")
    p.add_argument("--combined-output", default=None,
                   help="Optional debug bundle stem containing both characters.")
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


def make_mat(name, color, roughness=0.78):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.28
        elif "Specular" in bsdf.inputs:
            bsdf.inputs["Specular"].default_value = 0.28
    return mat


def bone_midpoints(arm):
    return {b.name: (arm.matrix_world @ b.head_local,
                     arm.matrix_world @ b.tail_local)
            for b in arm.data.bones}


def assign_to_bone(obj, arm, bone_name):
    vg = obj.vertex_groups.new(name=bone_name)
    vg.add(range(len(obj.data.vertices)), 1.0, 'REPLACE')
    obj.parent = arm
    mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm


def create_segment(name, arm, bone_name, p0, p1, r0, r1, mat,
                   segments=7, squash=(1.0, 0.74), z_pad=0.0):
    import bmesh
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    axis = p1 - p0
    depth = axis.length + z_pad
    res = bmesh.ops.create_cone(
        bm, cap_ends=True, segments=segments, radius1=r0, radius2=r1,
        depth=depth)
    rot = axis.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    scale = Matrix.Diagonal((squash[0], squash[1], 1.0, 1.0))
    loc = Matrix.Translation((p0 + p1) * 0.5)
    xform = loc @ rot @ scale
    for v in res["verts"]:
        v.co = xform @ v.co
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    assign_to_bone(obj, arm, bone_name)
    return obj


def create_ellipsoid(name, arm, bone_name, center, scale, mat,
                     segments=8, rings=4):
    import bmesh
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    res = bmesh.ops.create_uvsphere(
        bm, u_segments=segments, v_segments=rings, radius=1.0)
    xform = Matrix.Translation(center) @ Matrix.Diagonal(
        (scale[0], scale[1], scale[2], 1.0))
    for v in res["verts"]:
        v.co = xform @ v.co
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    assign_to_bone(obj, arm, bone_name)
    return obj


def create_box(name, arm, bone_name, center, scale, mat):
    import bmesh
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    res = bmesh.ops.create_cube(bm, size=1.0)
    xform = Matrix.Translation(center) @ Matrix.Diagonal(
        (scale[0], scale[1], scale[2], 1.0))
    for v in res["verts"]:
        v.co = xform @ v.co
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    assign_to_bone(obj, arm, bone_name)
    return obj


def build_primitive_bartender(arm):
    """Late-1990s primitive character skin on oeb_humanoid_v1.

    Meshes stay separate and named by body part so key riggers can isolate
    silhouette problems quickly. Weights are intentionally rigid-per-part:
    faceted deformation is period-correct and avoids modern rubber bending.
    """
    bones = bone_midpoints(arm)
    mat_skin = make_mat("mat_bartender_skin_lowpoly", (0.62, 0.44, 0.34, 1))
    mat_hair = make_mat("mat_bartender_hair_lowpoly", (0.07, 0.055, 0.045, 1))
    mat_shirt = make_mat("mat_bartender_black_shirt_lowpoly",
                         (0.025, 0.028, 0.032, 1))
    mat_vest = make_mat("mat_bartender_oxblood_vest_lowpoly",
                        (0.30, 0.045, 0.055, 1))
    mat_apron = make_mat("mat_bartender_worn_apron_lowpoly",
                         (0.62, 0.60, 0.54, 1))
    mat_pants = make_mat("mat_bartender_charcoal_pants_lowpoly",
                         (0.075, 0.08, 0.09, 1))
    mat_shoe = make_mat("mat_bartender_black_shoes_lowpoly",
                        (0.018, 0.016, 0.014, 1))
    mat_eye = make_mat("mat_bartender_face_pixels", (0.02, 0.018, 0.015, 1))

    made = []
    pelvis_h, pelvis_t = bones["pelvis"]
    spine_h, spine_t = bones["spine_03"]
    neck_h, neck_t = bones["neck_01"]
    head_h, head_t = bones["Head"]

    made.append(create_segment(
        "char_bartender_v1_lowpoly_torso_vest", arm, "spine_02",
        pelvis_t + Vector((0, 0, -0.03)), spine_t + Vector((0, 0, 0.02)),
        0.25, 0.34, mat_vest, segments=7, squash=(0.86, 0.58)))
    made.append(create_box(
        "char_bartender_v1_lowpoly_apron_panel", arm, "spine_01",
        (pelvis_t + spine_h) * 0.5 + Vector((0, -0.105, -0.02)),
        (0.34, 0.018, 0.46), mat_apron))
    made.append(create_ellipsoid(
        "char_bartender_v1_lowpoly_pelvis", arm, "pelvis",
        pelvis_h + Vector((0, 0, 0.03)), (0.27, 0.18, 0.15),
        mat_pants, segments=8, rings=4))
    made.append(create_segment(
        "char_bartender_v1_lowpoly_neck", arm, "neck_01",
        neck_h, neck_t, 0.065, 0.06, mat_skin, segments=7,
        squash=(0.85, 0.75)))
    made.append(create_ellipsoid(
        "char_bartender_v1_lowpoly_head", arm, "Head",
        (head_h + head_t) * 0.5 + Vector((0, 0.015, 0.035)),
        (0.13, 0.105, 0.17), mat_skin, segments=8, rings=5))
    made.append(create_ellipsoid(
        "char_bartender_v1_lowpoly_hair_cap", arm, "Head",
        (head_h + head_t) * 0.5 + Vector((0, 0.012, 0.105)),
        (0.135, 0.112, 0.075), mat_hair, segments=8, rings=3))
    made.append(create_segment(
        "char_bartender_v1_lowpoly_nose", arm, "Head",
        (head_h + head_t) * 0.5 + Vector((0, -0.09, 0.035)),
        (head_h + head_t) * 0.5 + Vector((0, -0.16, 0.025)),
        0.026, 0.004, mat_skin, segments=5, squash=(0.75, 0.75)))
    for x in (-0.045, 0.045):
        made.append(create_box(
            f"char_bartender_v1_lowpoly_eye_{'l' if x > 0 else 'r'}",
            arm, "Head",
            (head_h + head_t) * 0.5 + Vector((x, -0.105, 0.062)),
            (0.018, 0.006, 0.010), mat_eye))

    limb_specs = [
        ("upperarm_l", 0.072, 0.058, mat_shirt),
        ("lowerarm_l", 0.056, 0.045, mat_skin),
        ("upperarm_r", 0.072, 0.058, mat_shirt),
        ("lowerarm_r", 0.056, 0.045, mat_skin),
        ("thigh_l", 0.086, 0.067, mat_pants),
        ("calf_l", 0.064, 0.050, mat_pants),
        ("thigh_r", 0.086, 0.067, mat_pants),
        ("calf_r", 0.064, 0.050, mat_pants),
    ]
    for bone, r0, r1, mat in limb_specs:
        p0, p1 = bones[bone]
        made.append(create_segment(
            f"char_bartender_v1_lowpoly_{bone}", arm, bone, p0, p1,
            r0, r1, mat, segments=7, squash=(0.82, 0.70)))
    for side in ("l", "r"):
        hand_h, hand_t = bones[f"hand_{side}"]
        made.append(create_ellipsoid(
            f"char_bartender_v1_lowpoly_hand_{side}", arm, f"hand_{side}",
            (hand_h + hand_t) * 0.5, (0.055, 0.035, 0.035),
            mat_skin, segments=7, rings=3))
        foot_h, foot_t = bones[f"foot_{side}"]
        made.append(create_ellipsoid(
            f"char_bartender_v1_lowpoly_shoe_{side}", arm, f"foot_{side}",
            (foot_h + foot_t) * 0.5 + Vector((0, -0.025, -0.025)),
            (0.060, 0.140, 0.045), mat_shoe, segments=7, rings=3))

    for obj in made:
        for poly in obj.data.polygons:
            poly.use_smooth = False
    return made


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


def selected_character_objects(arm):
    objs = [arm]
    objs.extend(o for o in bpy.data.objects
                if o.type == 'MESH' and o.parent is arm
                and o.name.startswith(arm.name))
    return objs


def export_character_asset(arm, out_stem):
    for obj in bpy.data.objects:
        obj.select_set(False)
    for obj in selected_character_objects(arm):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm

    glb = out_stem + ".glb"
    print(f"[v3] Exporting {arm.name} GLB: {glb}")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=True,
        export_animations=True, export_animation_mode='NLA_TRACKS',
        export_nla_strips=True,
        export_force_sampling=True)

    usdc = out_stem + ".usdc"
    print(f"[v3] Exporting {arm.name} USDC: {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, selected_objects_only=True,
                              export_animation=True, export_armatures=True,
                              export_materials=True)
    except TypeError:
        try:
            bpy.ops.wm.usd_export(filepath=usdc, selected=True,
                                  export_animation=True, export_armatures=True,
                                  export_materials=True)
        except TypeError:
            bpy.ops.wm.usd_export(filepath=usdc)


def export_combined_bundle(out_stem):
    for obj in bpy.data.objects:
        obj.select_set(False)
    glb = out_stem + ".glb"
    print(f"[v3] Exporting debug combined GLB: {glb}")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=False,
        export_animations=True, export_animation_mode='NLA_TRACKS',
        export_nla_strips=True,
        export_force_sampling=True)
    usdc = out_stem + ".usdc"
    print(f"[v3] Exporting debug combined USDC: {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=True,
                              export_armatures=True, export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)


def main():
    args = parse_args()
    if args.output_dir:
        out_dir = args.output_dir
    elif args.output:
        out_dir = os.path.dirname(args.output)
    else:
        out_dir = "assets/characters"
    out_dir = out_dir if os.path.isabs(out_dir) else os.path.join(os.getcwd(), out_dir)
    os.makedirs(out_dir, exist_ok=True)

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
    bar_garms = build_primitive_bartender(bartender)
    print(f"[v3] hero garments: {[m.name for m in hero_garms]}")
    print(f"[v3] bartender low-poly parts: {[m.name for m in bar_garms]}")
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

    export_character_asset(hero, os.path.join(out_dir, "char_hero_v1"))
    export_character_asset(bartender, os.path.join(out_dir, "char_bartender_v1"))
    if args.combined_output:
        combined_stem = args.combined_output if os.path.isabs(args.combined_output) \
            else os.path.join(os.getcwd(), args.combined_output)
        os.makedirs(os.path.dirname(combined_stem), exist_ok=True)
        export_combined_bundle(combined_stem)
    print("[v3] Done.")


if __name__ == "__main__":
    main()
