#!/usr/bin/env python3
"""
convert_legacy_dxf.py — Headless Blender: 1999-era Infini-D DXF → pipeline
characters.

Parses an Infini-D 3DFACE DXF (classic-Mac CR line endings, per-body-part
layers), normalizes it (recenter, feet to z=0, scale to target height),
mirrors the right hand to the left when the source lacks one, and builds TWO
pipeline-ready characters from the same geometry — `char_hero_v1` (blue
tint) and `char_bartender_v1` (green tint) — each with the standard 5-bone
armature and its 6 canonical keyed actions, exported to GLB + USDC.

Run from repo root:
  blender --background --factory-startup \
    --python tools/convert_legacy_dxf.py -- \
    --dxf "models/mƒ jb5k/guy.dxf" \
    --output assets/characters/oeb_guy_characters
"""

import sys
import os
import argparse
import math

import bpy
import bmesh

HERO_ACTIONS = [
    "walk_to_stool", "sit_barstool", "idle_seated_relaxed",
    "talk_neutral_seated", "nod_small", "look_down_then_up",
]
BARTENDER_ACTIONS = [
    "idle_standing_relaxed", "wipe_glass_loop", "talk_friendly_standing",
    "pour_drink_short", "lean_forward_counter", "shrug_small",
]
TARGET_HEIGHT = 1.7  # meters


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="convert_legacy_dxf")
    p.add_argument("--dxf", required=True)
    p.add_argument("--output", required=True,
                   help="Output path stem (.glb and .usdc are appended)")
    return p.parse_args(argv)


def parse_dxf_faces(path):
    """Return list of (layer, [4 corner triples]) from 3DFACE entities."""
    raw = open(path, "rb").read()
    lines = [l.strip() for l in
             raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")]
    pairs = list(zip(lines[::2], lines[1::2]))
    faces = []
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if val == b"3DFACE":
            layer, corners = "?", {}
            j = i + 1
            while j < len(pairs) and pairs[j][1] != b"3DFACE" and pairs[j][0] != b"0":
                c, v = pairs[j]
                if c == b"8":
                    layer = v.decode("latin-1")
                else:
                    try:
                        gc = int(c)
                    except ValueError:
                        gc = -1
                    if 10 <= gc <= 33:
                        corners[gc] = float(v)
                j += 1
            quad = []
            for k in range(4):
                if 10 + k in corners:
                    quad.append((corners[10 + k], corners[20 + k], corners[30 + k]))
            if len(quad) >= 3:
                faces.append((layer, quad))
            i = j
        else:
            i += 1
    return faces


def normalize(faces):
    """Recenter x/y, drop feet to z=0, scale to TARGET_HEIGHT."""
    pts = [p for _, quad in faces for p in quad]
    xs, ys, zs = zip(*pts)
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    z0, height = min(zs), max(zs) - min(zs)
    s = TARGET_HEIGHT / height
    out = [(layer, [((x - cx) * s, (y - cy) * s, (z - z0) * s) for x, y, z in quad])
           for layer, quad in faces]
    return out


def facing_rotation(faces):
    """Infer native facing from L/R shoe lateral offset; return z-rotation
    (radians) that turns the model to face +Y. A person facing +Y has their
    left side at -X."""
    def centroid(prefix):
        pts = [p for layer, quad in faces if layer.startswith(prefix) for p in quad]
        if not pts:
            return None
        xs, ys, _ = zip(*pts)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    l, r = centroid("LSHOE"), centroid("RSHOE")
    if not l or not r:
        return 0.0
    dx, dy = l[0] - r[0], l[1] - r[1]
    if abs(dx) >= abs(dy):          # lateral axis is X
        return 0.0 if dx < 0 else math.pi          # L at -X → already faces +Y
    else:                           # lateral axis is Y → rotate 90°
        return -math.pi / 2 if dy < 0 else math.pi / 2


def has_left_hand(faces):
    return any(layer.startswith(("LHAND", "LMITT", "MITT")) for layer, _ in faces)


def mirror_right_hand(faces):
    """Duplicate RHAND* mirrored across X (model is recentered)."""
    extra = []
    for layer, quad in faces:
        if layer.startswith("RHAND"):
            extra.append(("LHANDM" + layer[5:],
                          [(-x, y, z) for x, y, z in reversed(quad)]))
    return extra


def build_body_mesh(name, faces, rot_z):
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    cos_r, sin_r = math.cos(rot_z), math.sin(rot_z)
    cache = {}

    def vert(p):
        x, y, z = p
        rx, ry = x * cos_r - y * sin_r, x * sin_r + y * cos_r
        key = (round(rx, 6), round(ry, 6), round(z, 6))
        if key not in cache:
            cache[key] = bm.verts.new(key)
        return cache[key]

    for _, quad in faces:
        vs = []
        for p in quad:
            v = vert(p)
            if v not in vs:               # 3DFACE triangles repeat corner 4
                vs.append(v)
        if len(vs) >= 3:
            try:
                bm.faces.new(vs)
            except ValueError:            # duplicate face in source; skip
                pass
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def make_material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.8
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def make_character(name, mesh_faces, rot_z, rgb, action_names, location):
    arm_data = bpy.data.armatures.new(name + "_armature")
    arm_obj = bpy.data.objects.new(name, arm_data)
    arm_obj.location = location
    bpy.context.scene.collection.objects.link(arm_obj)

    bpy.context.view_layer.update()
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones
    root = eb.new("root");   root.head = (0, 0, 0.00); root.tail = (0, 0, 0.30)
    spine = eb.new("spine"); spine.head = (0, 0, 0.30); spine.tail = (0, 0, 0.90)
    spine.parent = root; spine.use_connect = True
    head = eb.new("head");   head.head = (0, 0, 0.90); head.tail = (0, 0, 1.10)
    head.parent = spine; head.use_connect = True
    l_arm = eb.new("l_arm"); l_arm.head = (0, 0, 0.85); l_arm.tail = (0.35, 0, 0.60)
    l_arm.parent = spine; l_arm.use_connect = False
    r_arm = eb.new("r_arm"); r_arm.head = (0, 0, 0.85); r_arm.tail = (-0.35, 0, 0.60)
    r_arm.parent = spine; r_arm.use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    arm_obj.select_set(False)

    body = bpy.data.objects.new(name + "_body",
                                build_body_mesh(name + "_body", mesh_faces, rot_z))
    bpy.context.scene.collection.objects.link(body)
    body.data.materials.append(make_material("mat_" + name, rgb))
    body.parent = arm_obj
    body.parent_type = 'OBJECT'

    # Actions → NLA (Blender 5.x slotted: assign action FIRST, then keyframe)
    arm_obj.animation_data_create()
    anim = arm_obj.animation_data
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    start, strip_len = 1, 24
    for action_name in action_names:
        action = bpy.data.actions.new(action_name)
        action.use_fake_user = True
        anim.action = action
        pb_root, pb_spine = arm_obj.pose.bones["root"], arm_obj.pose.bones["spine"]
        pb_root.rotation_euler = (0.0, 0.0, 0.00)
        pb_root.keyframe_insert("rotation_euler", frame=1)
        pb_root.rotation_euler = (0.0, 0.0, 0.05)
        pb_root.keyframe_insert("rotation_euler", frame=strip_len)
        pb_spine.rotation_euler = (0.00, 0.0, 0.0)
        pb_spine.keyframe_insert("rotation_euler", frame=1)
        pb_spine.rotation_euler = (0.03, 0.0, 0.0)
        pb_spine.keyframe_insert("rotation_euler", frame=strip_len)
        track = anim.nla_tracks.new()
        track.name = action_name
        strip = track.strips.new(action_name, start, action)
        strip.action_frame_start, strip.action_frame_end = 1.0, float(strip_len)
        start += strip_len + 4
    anim.action = None
    arm_obj.select_set(False)
    return arm_obj


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)

    faces = normalize(parse_dxf_faces(args.dxf))
    print(f"[convert_legacy_dxf] {len(faces)} faces, "
          f"{len({l for l, _ in faces})} layers")
    if not has_left_hand(faces):
        mirrored = mirror_right_hand(faces)
        faces += mirrored
        print(f"[convert_legacy_dxf] no left hand in source — mirrored "
              f"{len(mirrored)} right-hand faces")
    rot = facing_rotation(faces)
    print(f"[convert_legacy_dxf] facing rotation: {math.degrees(rot):.0f}°")

    # Hero faces +Y (toward the counter); bartender faces -Y (toward hero).
    make_character("char_hero_v1", faces, rot, (0.30, 0.42, 0.58),
                   HERO_ACTIONS, location=(0.0, 0.0, 0.0))
    make_character("char_bartender_v1", faces, rot + math.pi, (0.32, 0.52, 0.34),
                   BARTENDER_ACTIONS, location=(0.0, 0.0, 0.0))

    glb = out_stem + ".glb"
    print(f"[convert_legacy_dxf] Exporting {glb}")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=False,
        export_animations=True, export_nla_strips=True,
        export_force_sampling=True,
    )
    usdc = out_stem + ".usdc"
    print(f"[convert_legacy_dxf] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=True,
                              export_armatures=True, export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)
    print("[convert_legacy_dxf] Done.")


if __name__ == "__main__":
    main()
