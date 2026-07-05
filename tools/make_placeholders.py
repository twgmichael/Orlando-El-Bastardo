#!/usr/bin/env python3
"""
make_placeholders.py — Headless Blender script.

Generates grey-box placeholder assets named exactly to canonical IDs in
docs/BAR-SCENE.md and exports them to glTF (GLB) and USD under --output-dir.

Run from repo root:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python tools/make_placeholders.py -- --output-dir assets/placeholders
"""

import sys
import os
import argparse
import math

import bpy
import bmesh


# ---------------------------------------------------------------------------
# Arg parsing — script args come after '--' separator
# ---------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser(
        prog="make_placeholders",
        description="Generate bar-scene placeholder assets (glTF + USD).",
    )
    parser.add_argument(
        "--output-dir",
        default="assets/placeholders",
        help="Output directory for exported files (relative to CWD or absolute).",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Scene reset
# ---------------------------------------------------------------------------

def reset_scene():
    """Remove all existing data, set units to metric/metres."""
    # Remove all objects first
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat, do_unlink=True)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm, do_unlink=True)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam, do_unlink=True)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll, do_unlink=True)

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.frame_start = 1
    scene.frame_end = 250


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def make_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

def make_material(name, rgb=(0.5, 0.5, 0.5)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def assign_material(obj, mat):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(mat)


# ---------------------------------------------------------------------------
# SET — set_bar_small_A: floor + 3 walls
# ---------------------------------------------------------------------------

def make_set(coll):
    mat = make_material("mat_set", (0.42, 0.42, 0.42))

    mesh = bpy.data.meshes.new("set_bar_small_A_mesh")
    bm = bmesh.new()

    W, D, H = 5.0, 4.0, 4.0  # half-width, half-depth, full height

    # Floor — z = 0
    fv = [bm.verts.new(p) for p in [
        (-W, -D, 0.0), (W, -D, 0.0), (W, D, 0.0), (-W, D, 0.0),
    ]]
    bm.faces.new(fv)

    # Back wall — y = +D
    bw = [bm.verts.new(p) for p in [
        (-W, D, 0.0), (W, D, 0.0), (W, D, H), (-W, D, H),
    ]]
    bm.faces.new(bw)

    # Left wall — x = -W
    lw = [bm.verts.new(p) for p in [
        (-W, -D, 0.0), (-W, D, 0.0), (-W, D, H), (-W, -D, H),
    ]]
    bm.faces.new(lw)

    # Right wall — x = +W
    rw = [bm.verts.new(p) for p in [
        (W, -D, 0.0), (W, D, 0.0), (W, D, H), (W, -D, H),
    ]]
    bm.faces.new(rw)

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    obj = bpy.data.objects.new("set_bar_small_A", mesh)
    obj.location = (0.0, 0.0, 0.0)
    coll.objects.link(obj)
    assign_material(obj, mat)
    return obj


# ---------------------------------------------------------------------------
# PROPS
# ---------------------------------------------------------------------------

def _box_mesh(name):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def _cylinder_mesh(name, segs=16):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False,
        segments=segs, radius1=0.5, radius2=0.5, depth=1.0,
    )
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def _sphere_mesh(name, u=12, v=8):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=0.5)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def _make_prop(name, mesh, location, scale, mat, coll):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.scale = scale
    coll.objects.link(obj)
    assign_material(obj, mat)
    return obj


def make_props(coll):
    mat = make_material("mat_prop", (0.50, 0.40, 0.32))

    # Bar counter — box, centred at origin, waist-high
    _make_prop(
        "prop_bar_counter_A",
        _box_mesh("prop_bar_counter_A_mesh"),
        location=(0.0, 0.0, 0.55),
        scale=(3.0, 0.7, 1.1),
        mat=mat, coll=coll,
    )

    # Stool — cylinder, bar-stool height
    _make_prop(
        "prop_stool_A",
        _cylinder_mesh("prop_stool_A_mesh"),
        location=(1.5, -1.2, 0.38),
        scale=(0.4, 0.4, 0.75),
        mat=mat, coll=coll,
    )

    # Tumbler — short cylinder on counter
    _make_prop(
        "prop_glass_tumbler_A",
        _cylinder_mesh("prop_glass_tumbler_A_mesh"),
        location=(0.0, -0.2, 1.16),
        scale=(0.1, 0.1, 0.12),
        mat=mat, coll=coll,
    )

    # Bottle — tall sphere (capsule approximation), sitting on the counter top
    _make_prop(
        "prop_bottle_generic_A",
        _sphere_mesh("prop_bottle_generic_A_mesh"),
        location=(0.4, -0.15, 1.29),
        scale=(0.08, 0.08, 0.38),
        mat=mat, coll=coll,
    )


# ---------------------------------------------------------------------------
# CHARACTERS — armature + body mesh + NLA actions
# ---------------------------------------------------------------------------

HERO_ACTIONS = [
    "walk_to_stool",
    "sit_barstool",
    "idle_seated_relaxed",
    "talk_neutral_seated",
    "nod_small",
    "look_down_then_up",
]

BARTENDER_ACTIONS = [
    "idle_standing_relaxed",
    "wipe_glass_loop",
    "talk_friendly_standing",
    "pour_drink_short",
    "lean_forward_counter",
    "shrug_small",
]


def make_character(name, location, body_rgb, action_names, coll):
    """
    Create a character armature (named exactly as `name`) with:
    - 5 bones: root, spine, head, l_arm, r_arm
    - Body mesh child (name + '_body')
    - One NLA track per action, each with minimal keyframes
    """

    # -- Armature data + object --
    arm_data = bpy.data.armatures.new(name + "_armature")
    arm_obj = bpy.data.objects.new(name, arm_data)
    arm_obj.location = location
    coll.objects.link(arm_obj)
    # Also link to scene master collection so view_layer sees it
    bpy.context.scene.collection.objects.link(arm_obj)

    bpy.context.view_layer.update()
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)

    # Enter edit mode to add bones
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones

    root  = eb.new("root");   root.head  = (0, 0, 0.00); root.tail  = (0, 0, 0.30)
    spine = eb.new("spine");  spine.head = (0, 0, 0.30); spine.tail = (0, 0, 0.90)
    spine.parent = root; spine.use_connect = True
    head  = eb.new("head");   head.head  = (0, 0, 0.90); head.tail  = (0, 0, 1.10)
    head.parent = spine; head.use_connect = True
    l_arm = eb.new("l_arm");  l_arm.head = (0, 0, 0.85); l_arm.tail = ( 0.35, 0, 0.60)
    l_arm.parent = spine; l_arm.use_connect = False
    r_arm = eb.new("r_arm");  r_arm.head = (0, 0, 0.85); r_arm.tail = (-0.35, 0, 0.60)
    r_arm.parent = spine; r_arm.use_connect = False

    bpy.ops.object.mode_set(mode='OBJECT')
    arm_obj.select_set(False)

    # -- Body mesh --
    body_mesh = bpy.data.meshes.new(name + "_body_mesh")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.28)
    bm.to_mesh(body_mesh)
    bm.free()
    body_mesh.update()

    body_obj = bpy.data.objects.new(name + "_body", body_mesh)
    body_obj.location = (0.0, 0.0, 0.85)  # relative offset — parented below
    body_obj.scale = (1.0, 0.75, 3.0)     # ~1.7m capsule: reads as a person over the 1.1m counter
    coll.objects.link(body_obj)
    assign_material(body_obj, make_material("mat_" + name, body_rgb))

    # Parent body to armature (object parenting, no deform — placeholder only).
    # No matrix_parent_inverse: body local (0,0,0.55) must land at armature
    # location + offset (setting it to inv(parent world) canceled the parent
    # transform and buried both bodies inside the counter at world origin).
    body_obj.parent = arm_obj
    body_obj.parent_type = 'OBJECT'

    # -- Actions → NLA tracks --
    # Blender 5.x slotted-action API: assign the action to the object FIRST,
    # then use pb.keyframe_insert() — action.fcurves does not exist in 5.x.
    arm_obj.animation_data_create()
    anim_data = arm_obj.animation_data

    # Ensure arm_obj is active for context-sensitive keyframe ops
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)

    # Offset each action along the timeline so strips don't overlap
    start_frame = 1
    strip_len = 24

    for action_name in action_names:
        action = bpy.data.actions.new(action_name)
        action.use_fake_user = True

        # Assign FIRST — Blender 5.x manages slots/channels automatically
        anim_data.action = action

        pb_root  = arm_obj.pose.bones["root"]
        pb_spine = arm_obj.pose.bones["spine"]

        # Root bone: Z rotation bob (2 keyframes)
        pb_root.rotation_euler  = (0.0, 0.0, 0.00)
        pb_root.keyframe_insert("rotation_euler", frame=1)
        pb_root.rotation_euler  = (0.0, 0.0, 0.05)
        pb_root.keyframe_insert("rotation_euler", frame=strip_len)

        # Spine: X lean (2 keyframes)
        pb_spine.rotation_euler = (0.00, 0.0, 0.0)
        pb_spine.keyframe_insert("rotation_euler", frame=1)
        pb_spine.rotation_euler = (0.03, 0.0, 0.0)
        pb_spine.keyframe_insert("rotation_euler", frame=strip_len)

        # Push to NLA
        track = anim_data.nla_tracks.new()
        track.name = action_name
        track.mute = False
        strip = track.strips.new(action_name, start_frame, action)
        strip.action_frame_start = 1.0
        strip.action_frame_end = float(strip_len)
        strip.frame_start = float(start_frame)
        strip.frame_end = float(start_frame + strip_len - 1)

        start_frame += strip_len + 4  # small gap between strips

    # Clear active action so NLA drives playback
    anim_data.action = None

    return arm_obj


def make_characters(coll):
    make_character(
        "char_hero_v1",
        location=(1.5, -1.0, 0.0),
        body_rgb=(0.32, 0.42, 0.55),   # blue-grey
        action_names=HERO_ACTIONS,
        coll=coll,
    )
    make_character(
        "char_bartender_v1",
        location=(-0.5, 0.5, 0.0),
        body_rgb=(0.55, 0.44, 0.32),   # warm ochre-grey
        action_names=BARTENDER_ACTIONS,
        coll=coll,
    )


# ---------------------------------------------------------------------------
# MARKS — plain-axes empties at floor level
# ---------------------------------------------------------------------------

MARK_DEFS = [
    ("hero_entry_A",        (-3.5, -3.0, 0.0)),
    ("hero_barstool_A",     ( 1.5, -1.0, 0.0)),
    ("bartender_idle_A",    (-0.5,  0.5, 0.0)),
    ("bartender_backbar_A", (-0.5,  2.5, 0.0)),
]


def make_marks(coll):
    for name, loc in MARK_DEFS:
        obj = bpy.data.objects.new(name, None)   # None → empty object
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = 0.3
        obj.location = loc
        coll.objects.link(obj)


# ---------------------------------------------------------------------------
# CAMERAS
# ---------------------------------------------------------------------------

CAM_DEFS = [
    ("cam_establishing_wide",
     ( 0.0, -7.0, 2.5), (math.radians(75), 0.0, 0.0)),
    ("cam_two_shot_bar",
     (-2.5, -4.5, 1.9), (math.radians(78), 0.0, math.radians(-20))),
    ("cam_close_hero",
     ( 2.5, -3.0, 1.5), (math.radians(80), 0.0, math.radians( 30))),
    ("cam_close_bartender",
     (-2.0, -2.0, 1.5), (math.radians(80), 0.0, math.radians(-30))),
]


def make_cameras(coll):
    for name, loc, rot in CAM_DEFS:
        cam_data = bpy.data.cameras.new(name + "_data")
        cam_data.lens = 35.0
        obj = bpy.data.objects.new(name, cam_data)
        obj.location = loc
        obj.rotation_euler = rot
        coll.objects.link(obj)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_gltf(output_dir):
    filepath = os.path.join(output_dir, "bar_scene_placeholders.glb")
    print(f"[make_placeholders] Exporting GLB → {filepath}")
    # Try with animation export params; fall back to minimal params on TypeError
    try:
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=False,
            export_cameras=True,
            export_animations=True,
            export_nla_strips=True,
            export_force_sampling=True,
        )
    except TypeError as exc:
        print(f"[make_placeholders] WARNING: gltf param error ({exc}); retrying minimal params")
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=False,
            export_cameras=True,
        )
    print(f"[make_placeholders] GLB written.")


def export_usd(output_dir):
    filepath = os.path.join(output_dir, "bar_scene_placeholders.usdc")
    print(f"[make_placeholders] Exporting USDC → {filepath}")
    try:
        bpy.ops.wm.usd_export(
            filepath=filepath,
            export_animation=True,
            export_hair=False,
            export_uvmaps=True,
            export_normals=True,
            export_materials=True,
            export_armatures=True,
        )
    except TypeError as exc:
        print(f"[make_placeholders] WARNING: usd_export param error ({exc}); retrying minimal params")
        bpy.ops.wm.usd_export(filepath=filepath)
    print(f"[make_placeholders] USDC written.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.getcwd(), output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"[make_placeholders] Output dir: {output_dir}")
    print(f"[make_placeholders] Blender version: {bpy.app.version_string}")

    reset_scene()

    set_coll  = make_collection("SET")
    prop_coll = make_collection("PROPS")
    char_coll = make_collection("CHARS")
    mark_coll = make_collection("MARKS")
    cam_coll  = make_collection("CAMS")

    print("[make_placeholders] Building set...")
    make_set(set_coll)

    print("[make_placeholders] Building props...")
    make_props(prop_coll)

    print("[make_placeholders] Building characters...")
    make_characters(char_coll)

    print("[make_placeholders] Building marks...")
    make_marks(mark_coll)

    print("[make_placeholders] Building cameras...")
    make_cameras(cam_coll)

    print("[make_placeholders] Exporting...")
    export_gltf(output_dir)
    export_usd(output_dir)

    print("[make_placeholders] All done — success.")


if __name__ == "__main__":
    main()
