#!/usr/bin/env python3
"""Build a smooth, late-1990s Orlando hero and a generic cast stand-in.

The source armature and animation clips come from the project's existing
CC0 Quaternius character stack (see docs/PROVENANCE.md).  All visible mesh,
materials, costume design, look-development, and review staging are built
here from Blender primitives.  The attached design reference is not packed
into the result; this script records the interpreted costume brief instead.

Authoring contract:
  * meters, Z up, character faces +Y, feet at z=0
  * canonical oeb_humanoid_v1 armature and existing hero clips
  * intentionally modest geometry, smooth silhouettes, flat-colour materials
  * separate hero and stand-in exports plus a Blender look-development file

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_orlando_1999.py -- \
    --output-dir assets/concepts/orlando_1999
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


HERO_SOURCE = "assets/characters/char_hero_v1.glb"
IDLE_SOURCE = (
    "assets/Universal Animation Library[Standard]/Unreal-Godot/"
    "UAL1_Standard.glb"
)

CANONICAL_MOTION_CLIPS = (
    "walk_to_stool",
    "sit_barstool",
    "stand_from_stool",
    "idle_standing_relaxed",
    "idle_seated_relaxed",
    "talk_neutral_seated",
    "nod_small",
    "look_down_then_up",
)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_orlando_1999")
    parser.add_argument(
        "--output-dir", default="assets/concepts/orlando_1999"
    )
    parser.add_argument("--resolution", type=int, default=720)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def make_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def move_to_collection(obj, coll):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    coll.objects.link(obj)


def make_material(name, color, roughness=0.72, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.28
    return mat


def smooth_mesh(obj):
    for poly in obj.data.polygons:
        poly.use_smooth = True


def bind_rigid(obj, arm, bone_name):
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = obj.modifiers.new("oeb_humanoid_v1", "ARMATURE")
    mod.object = arm


def apply_object_transform(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)


def ellipsoid(name, center, radii, mat, coll, arm=None, bone=None,
              segments=16, rings=8, smooth=True):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=center
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + "_mesh"
    obj.scale = radii
    apply_object_transform(obj)
    move_to_collection(obj, coll)
    obj.data.materials.append(mat)
    if smooth:
        smooth_mesh(obj)
    if arm and bone:
        bind_rigid(obj, arm, bone)
    return obj


def rounded_box(name, center, dims, mat, coll, arm=None, bone=None,
                rotation=(0.0, 0.0, 0.0), bevel=0.025, smooth=True):
    bpy.ops.mesh.primitive_cube_add(location=center, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + "_mesh"
    obj.dimensions = dims
    apply_object_transform(obj)
    move_to_collection(obj, coll)
    if bevel:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mod = obj.modifiers.new("soft_1999_edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        bpy.ops.object.modifier_apply(modifier=mod.name)
        obj.select_set(False)
    obj.data.materials.append(mat)
    if smooth:
        smooth_mesh(obj)
    if arm and bone:
        bind_rigid(obj, arm, bone)
    return obj


def segment(name, p0, p1, r0, r1, mat, coll, arm=None, bone=None,
            sides=12, squash=(1.0, 0.88), smooth=True):
    p0, p1 = Vector(p0), Vector(p1)
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    axis = p1 - p0
    result = bmesh.ops.create_cone(
        bm, cap_ends=True, segments=sides, radius1=r0, radius2=r1,
        depth=axis.length,
    )
    rotation = axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
    scale = Matrix.Diagonal((squash[0], squash[1], 1.0, 1.0))
    transform = Matrix.Translation((p0 + p1) * 0.5) @ rotation @ scale
    for vert in result["verts"]:
        vert.co = transform @ vert.co
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.data.materials.append(mat)
    if smooth:
        smooth_mesh(obj)
    if arm and bone:
        bind_rigid(obj, arm, bone)
    return obj


def import_rig(source_path, name, coll, keep_animation):
    before_objects = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(source_path))
    imported = list(set(bpy.data.objects) - before_objects)
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    if len(arms) != 1:
        raise RuntimeError(f"Expected one armature in {source_path}, got {len(arms)}")
    arm = arms[0]
    arm.name = name
    arm.data.name = name + "_oeb_humanoid_v1"
    move_to_collection(arm, coll)
    for obj in imported:
        if obj is not arm:
            bpy.data.objects.remove(obj, do_unlink=True)
    if not keep_animation:
        if arm.animation_data:
            arm.animation_data_clear()
        for action in set(bpy.data.actions) - before_actions:
            bpy.data.actions.remove(action)
    arm.data.pose_position = "REST"
    return arm


def bone_points(arm):
    return {
        bone.name: (
            arm.matrix_world @ bone.head_local,
            arm.matrix_world @ bone.tail_local,
        )
        for bone in arm.data.bones
    }


def hero_materials():
    return {
        "skin": make_material("hero_skin_warm", (0.32, 0.12, 0.055, 1), 0.68),
        "skin_light": make_material("hero_skin_highlight", (0.46, 0.22, 0.10, 1), 0.66),
        "hair": make_material("hero_hair_brown", (0.075, 0.035, 0.018, 1), 0.86),
        "navy": make_material("hero_jacket_navy", (0.006, 0.018, 0.055, 1), 0.82),
        "navy_light": make_material("hero_jacket_edge", (0.012, 0.045, 0.13, 1), 0.79),
        "trouser": make_material("hero_trouser_midnight", (0.004, 0.008, 0.025, 1), 0.86),
        "shirt": make_material("hero_shirt_ivory", (0.60, 0.57, 0.48, 1), 0.78),
        "orange": make_material("hero_cap_burnt_orange", (0.48, 0.065, 0.006, 1), 0.74),
        "orange_dark": make_material("hero_cap_seams", (0.12, 0.018, 0.002, 1), 0.82),
        "black": make_material("hero_boot_leather", (0.008, 0.009, 0.012, 1), 0.6),
        "metal": make_material("hero_gunmetal", (0.045, 0.055, 0.065, 1), 0.42, 0.55),
        "eye": make_material("hero_eyes", (0.015, 0.018, 0.014, 1), 0.5),
        "eye_white": make_material("hero_eye_whites", (0.82, 0.80, 0.72, 1), 0.55),
        "steel": make_material("hero_buckle", (0.32, 0.35, 0.37, 1), 0.38, 0.6),
    }


def build_hero(arm, coll):
    """Create Orlando from the supplied front/3-quarter/profile/back brief."""
    mats = hero_materials()
    b = bone_points(arm)
    made = []

    # Torso: a tapered, rounded field-jacket silhouette rather than a box.
    made += [
        segment("orlando_jacket_body", (0, -0.012, 1.055),
                (0, -0.012, 1.535), 0.225, 0.275, mats["navy"], coll,
                arm, "spine_02", sides=18, squash=(1.0, 0.52)),
        ellipsoid("orlando_jacket_opening", (0, 0.137, 1.325),
                  (0.115, 0.025, 0.235), mats["shirt"], coll,
                  arm, "spine_02", 16, 8),
        ellipsoid("orlando_jacket_hem", (0, 0.0, 1.055),
                  (0.235, 0.135, 0.052), mats["navy_light"], coll,
                  arm, "pelvis", 16, 7),
        ellipsoid("orlando_collar_back", (0, -0.028, 1.535),
                  (0.19, 0.09, 0.075), mats["navy_light"], coll,
                  arm, "spine_03", 16, 7),
    ]
    for side, angle in ((-1, -0.16), (1, 0.16)):
        x = 0.108 * side
        made.append(rounded_box(
            f"orlando_jacket_lapel_{'l' if side > 0 else 'r'}",
            (x, 0.157, 1.42), (0.13, 0.026, 0.26), mats["navy_light"],
            coll, arm, "spine_03", rotation=(0, angle, side * 0.14),
            bevel=0.012,
        ))
        made.append(rounded_box(
            f"orlando_shirt_collar_{'l' if side > 0 else 'r'}",
            (0.058 * side, 0.172, 1.49), (0.09, 0.018, 0.13), mats["shirt"],
            coll, arm, "spine_03", rotation=(0, side * 0.18, side * 0.25),
            bevel=0.009,
        ))

    # Jacket pockets and practical 1999 hardware.
    for side in (-1, 1):
        suffix = "l" if side > 0 else "r"
        made.append(rounded_box(
            f"orlando_chest_pocket_{suffix}", (0.15 * side, 0.151, 1.38),
            (0.12, 0.025, 0.075), mats["navy_light"], coll,
            arm, "spine_02", bevel=0.011,
        ))
        made.append(rounded_box(
            f"orlando_cargo_pocket_{suffix}", (0.165 * side, 0.145, 1.17),
            (0.14, 0.028, 0.09), mats["navy_light"], coll,
            arm, "spine_01", bevel=0.012,
        ))
    made.append(rounded_box(
        "orlando_jacket_zipper", (0, 0.159, 1.13), (0.014, 0.012, 0.14),
        mats["steel"], coll, arm, "spine_01", bevel=0.005,
    ))

    # Arms follow the canonical bones; cuffs and sleeve pocket add silhouette.
    for side in ("l", "r"):
        up0, up1 = b[f"upperarm_{side}"]
        lo0, lo1 = b[f"lowerarm_{side}"]
        made.append(segment(f"orlando_upperarm_{side}", up0, up1, 0.086, 0.070,
                            mats["navy"], coll, arm, f"upperarm_{side}"))
        made.append(segment(f"orlando_forearm_{side}", lo0, lo1, 0.074, 0.058,
                            mats["navy"], coll, arm, f"lowerarm_{side}"))
        cuff_center = lo1.lerp(lo0, 0.12)
        made.append(ellipsoid(f"orlando_cuff_{side}", cuff_center,
                              (0.064, 0.057, 0.050), mats["navy_light"], coll,
                              arm, f"lowerarm_{side}", 12, 6))
        hand0, hand1 = b[f"hand_{side}"]
        made.append(ellipsoid(f"orlando_hand_{side}", (hand0 + hand1) * 0.5,
                              (0.058, 0.040, 0.040), mats["skin"], coll,
                              arm, f"hand_{side}", 14, 7))
    up0, up1 = b["upperarm_r"]
    made.append(rounded_box(
        "orlando_sleeve_pocket", up0.lerp(up1, 0.47) + Vector((0, 0.070, 0)),
        (0.10, 0.026, 0.11), mats["navy_light"], coll, arm, "upperarm_r",
        bevel=0.010,
    ))

    # Belt, trousers, boots.
    made.append(ellipsoid("orlando_pelvis", (0, 0.02, 0.98),
                          (0.235, 0.14, 0.145), mats["trouser"], coll,
                          arm, "pelvis", 16, 8))
    made.append(rounded_box("orlando_belt", (0, 0.02, 1.035),
                            (0.47, 0.25, 0.055), mats["black"], coll,
                            arm, "pelvis", bevel=0.016))
    made.append(rounded_box("orlando_belt_buckle", (0, 0.148, 1.035),
                            (0.075, 0.020, 0.065), mats["steel"], coll,
                            arm, "pelvis", bevel=0.008))
    for side in ("l", "r"):
        th0, th1 = b[f"thigh_{side}"]
        ca0, ca1 = b[f"calf_{side}"]
        made.append(segment(f"orlando_thigh_{side}", th0, th1, 0.108, 0.086,
                            mats["trouser"], coll, arm, f"thigh_{side}",
                            squash=(0.9, 0.82)))
        made.append(segment(f"orlando_calf_{side}", ca0, ca1, 0.087, 0.064,
                            mats["trouser"], coll, arm, f"calf_{side}",
                            squash=(0.9, 0.82)))
        ankle = ca1 + Vector((0, 0.01, 0.07))
        made.append(ellipsoid(f"orlando_boot_cuff_{side}", ankle,
                              (0.087, 0.095, 0.115), mats["black"], coll,
                              arm, f"calf_{side}", 14, 7))
        foot0, _foot1 = b[f"foot_{side}"]
        made.append(rounded_box(
            f"orlando_boot_{side}", foot0 + Vector((0, 0.09, -0.005)),
            (0.17, 0.33, 0.145), mats["black"], coll, arm, f"foot_{side}",
            bevel=0.050,
        ))
        for stripe in (0.08, 0.14):
            made.append(rounded_box(
                f"orlando_boot_rib_{side}_{int(stripe*100)}",
                foot0 + Vector((0, stripe, 0.064)), (0.172, 0.016, 0.030),
                mats["metal"], coll, arm, f"foot_{side}", bevel=0.006,
            ))

    # Head, recognisable hair/cap silhouette, and deliberately simple face.
    made += [
        ellipsoid("orlando_neck", (0, 0.018, 1.57), (0.072, 0.068, 0.11),
                  mats["skin"], coll, arm, "neck_01", 14, 7),
        ellipsoid("orlando_hair_mass", (0, -0.025, 1.735), (0.137, 0.116, 0.17),
                  mats["hair"], coll, arm, "Head", 16, 8),
        ellipsoid("orlando_face", (0, 0.020, 1.72), (0.125, 0.108, 0.155),
                  mats["skin_light"], coll, arm, "Head", 18, 10),
        ellipsoid("orlando_left_ear", (0.126, 0.015, 1.72), (0.024, 0.018, 0.045),
                  mats["skin"], coll, arm, "Head", 10, 6),
        ellipsoid("orlando_right_ear", (-0.126, 0.015, 1.72), (0.024, 0.018, 0.045),
                  mats["skin"], coll, arm, "Head", 10, 6),
        segment("orlando_nose", (0, 0.095, 1.735), (0, 0.158, 1.72),
                0.026, 0.010, mats["skin"], coll, arm, "Head", sides=10),
        rounded_box("orlando_mouth", (0, 0.116, 1.657), (0.07, 0.009, 0.008),
                    mats["hair"], coll, arm, "Head", bevel=0.003),
    ]
    for side in (-1, 1):
        suffix = "l" if side > 0 else "r"
        made.append(ellipsoid(f"orlando_eye_white_{suffix}",
                              (0.043 * side, 0.108, 1.755),
                              (0.027, 0.011, 0.017), mats["eye_white"], coll,
                              arm, "Head", 10, 6))
        made.append(ellipsoid(f"orlando_eye_{suffix}",
                              (0.043 * side, 0.119, 1.755),
                              (0.010, 0.007, 0.010), mats["eye"], coll,
                              arm, "Head", 10, 6))
        made.append(rounded_box(f"orlando_brow_{suffix}",
                                (0.045 * side, 0.116, 1.785),
                                (0.062, 0.010, 0.012), mats["hair"], coll,
                                arm, "Head", rotation=(0, side * 0.10, 0),
                                bevel=0.004))

    # Cap: strong orange crown, broad visor, rear strap, simple panel seams.
    made += [
        ellipsoid("orlando_cap_crown", (0, 0.005, 1.845),
                  (0.145, 0.132, 0.095), mats["orange"], coll,
                  arm, "Head", 18, 9),
        ellipsoid("orlando_cap_visor", (0, 0.120, 1.812),
                  (0.155, 0.115, 0.020), mats["orange"], coll,
                  arm, "Head", 18, 6),
        rounded_box("orlando_cap_backstrap", (0, -0.128, 1.812),
                    (0.11, 0.020, 0.028), mats["orange_dark"], coll,
                    arm, "Head", bevel=0.008),
        segment("orlando_cap_center_seam", (0, 0.126, 1.845),
                (0, 0.015, 1.938), 0.0045, 0.0035, mats["orange_dark"],
                coll, arm, "Head", sides=8),
    ]
    for side in (-1, 1):
        made.append(ellipsoid(f"orlando_hair_side_{side}",
                              (0.118 * side, -0.015, 1.68),
                              (0.035, 0.095, 0.09), mats["hair"], coll,
                              arm, "Head", 12, 7))

    # Compact holster and sidearm, read as costume detail rather than focal prop.
    made += [
        rounded_box("orlando_holster", (-0.235, 0.035, 0.91),
                    (0.095, 0.115, 0.26), mats["black"], coll,
                    arm, "thigh_r", rotation=(0.04, -0.10, 0.03), bevel=0.025),
        segment("orlando_sidearm_barrel", (-0.235, 0.085, 1.01),
                (-0.235, 0.085, 0.87), 0.026, 0.023, mats["metal"], coll,
                arm, "thigh_r", sides=10),
        rounded_box("orlando_sidearm_grip", (-0.235, 0.035, 1.0),
                    (0.055, 0.07, 0.115), mats["metal"], coll,
                    arm, "thigh_r", rotation=(-0.25, 0, 0), bevel=0.014),
    ]

    arm["character_id"] = "char_orlando_1999_A"
    arm["skeleton"] = "oeb_humanoid_v1"
    arm["design_reference"] = "Orlando El Bastardo 1999 turnaround"
    arm["style"] = "smooth low-poly late-1990s cinematic stand-in"
    return made


def build_standin(arm, coll):
    mats = {
        "body": make_material("standin_body_teal", (0.06, 0.30, 0.34, 1), 0.84),
        "limb": make_material("standin_limb_bluegray", (0.13, 0.20, 0.25, 1), 0.84),
        "joint": make_material("standin_joint_dark", (0.025, 0.045, 0.055, 1), 0.76),
        "id": make_material("standin_identifier_amber", (0.95, 0.42, 0.035, 1), 0.70),
    }
    b = bone_points(arm)
    made = [
        ellipsoid("standin_torso", (0, 0, 1.30), (0.205, 0.115, 0.285),
                  mats["body"], coll, arm, "spine_02", 18, 9),
        ellipsoid("standin_shoulder_l", (0.205, 0, 1.455),
                  (0.085, 0.095, 0.085), mats["body"], coll,
                  arm, "spine_03", 14, 7),
        ellipsoid("standin_shoulder_r", (-0.205, 0, 1.455),
                  (0.085, 0.095, 0.085), mats["body"], coll,
                  arm, "spine_03", 14, 7),
        ellipsoid("standin_pelvis", (0, 0.02, 0.98), (0.19, 0.12, 0.135),
                  mats["joint"], coll, arm, "pelvis", 14, 7),
        ellipsoid("standin_head", (0, 0.01, 1.73), (0.125, 0.115, 0.16),
                  mats["id"], coll, arm, "Head", 16, 8),
        ellipsoid("standin_eye_l", (0.045, 0.119, 1.755),
                  (0.012, 0.008, 0.014), mats["joint"], coll,
                  arm, "Head", 10, 6),
        ellipsoid("standin_eye_r", (-0.045, 0.119, 1.755),
                  (0.012, 0.008, 0.014), mats["joint"], coll,
                  arm, "Head", 10, 6),
    ]
    for side in ("l", "r"):
        for bone, radii in ((f"upperarm_{side}", (0.080, 0.065)),
                            (f"lowerarm_{side}", (0.065, 0.052)),
                            (f"thigh_{side}", (0.10, 0.08)),
                            (f"calf_{side}", (0.08, 0.058))):
            p0, p1 = b[bone]
            made.append(segment(f"standin_{bone}", p0, p1, radii[0], radii[1],
                                mats["limb"], coll, arm, bone, sides=10))
        h0, h1 = b[f"hand_{side}"]
        made.append(ellipsoid(f"standin_hand_{side}", (h0 + h1) * 0.5,
                              (0.055, 0.038, 0.038), mats["id"], coll,
                              arm, f"hand_{side}", 12, 6))
        f0, _f1 = b[f"foot_{side}"]
        made.append(rounded_box(f"standin_foot_{side}",
                                f0 + Vector((0, 0.075, -0.005)),
                                (0.16, 0.29, 0.13), mats["joint"], coll,
                                arm, f"foot_{side}", bevel=0.042))
    arm["character_id"] = "placeholder_character_generic_1999_A"
    arm["skeleton"] = "oeb_humanoid_v1"
    arm["purpose"] = "shared average-build male stand-in"
    arm["display_label"] = "Average-Build Male Stand-In"
    arm["body_type"] = "average-build"
    arm["gender_presentation"] = "male"
    return made


def configure_motion_clips(arms, existing_sources, idle_source_path):
    """Give each armature its own canonical NLA clip set.

    Blender's ACTIONS glTF mode exports every compatible action in the file,
    which previously cross-labelled the two characters' standing-idle clips.
    Per-armature NLA tracks make clip ownership explicit and let selection-only
    exports carry exactly the eight canonical motions for that character.
    """
    before_objects = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(idle_source_path))
    imported = list(set(bpy.data.objects) - before_objects)
    new_actions = list(set(bpy.data.actions) - before_actions)
    idle = next((a for a in new_actions if a.name.split(".")[0] == "Idle_Loop"), None)
    if idle is None:
        raise RuntimeError(f"Idle_Loop missing from {idle_source_path}")

    sources = dict(existing_sources)
    sources["idle_standing_relaxed"] = idle
    missing = [name for name in CANONICAL_MOTION_CLIPS if name not in sources]
    if missing:
        raise RuntimeError(f"Canonical motion sources missing: {missing}")

    bound_actions = set()
    for arm in arms:
        if arm.animation_data:
            arm.animation_data_clear()
        arm.animation_data_create()
        start = 1
        for clip_name in CANONICAL_MOTION_CLIPS:
            action = sources[clip_name].copy()
            action.name = f"{arm.name}__{clip_name}"
            action.use_fake_user = True
            bound_actions.add(action)
            track = arm.animation_data.nla_tracks.new()
            track.name = clip_name
            length = max(2, int(action.frame_range[1] - action.frame_range[0]) + 1)
            strip = track.strips.new(clip_name, start, action)
            strip.name = clip_name
            strip.frame_start = float(start)
            strip.frame_end = float(start + length - 1)
            strip.extrapolation = "NOTHING"
            start += length + 4
        arm.animation_data.action = None
        arm.data.pose_position = "POSE"

    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        if action not in bound_actions:
            bpy.data.actions.remove(action)
    bpy.context.scene.frame_set(1)


def select_character(arm, coll):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in coll.objects:
        if obj is arm or (obj.type == "MESH" and obj.parent is arm):
            obj.select_set(True)
    bpy.context.view_layer.objects.active = arm


def export_character(arm, coll, path):
    select_character(arm, coll)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_animations=True, export_animation_mode="NLA_TRACKS",
        export_nla_strips=True, export_force_sampling=True, export_extras=True,
    )


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_stage(resolution):
    scene = bpy.context.scene
    # Blender 5.x exposes Eevee under BLENDER_EEVEE (the 4.x NEXT enum was
    # folded back into the stable engine name).
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = int(resolution * 1.16)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.fps = 24
    scene.world.color = (0.004, 0.006, 0.012)
    world = scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.003, 0.006, 0.014, 1)
    bg.inputs["Strength"].default_value = 0.16

    stage = make_collection("LOOKDEV_STAGE")
    floor_mat = make_material("lookdev_floor", (0.012, 0.018, 0.027, 1), 0.88)
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.055))
    floor = bpy.context.object
    floor.name = "lookdev_floor"
    move_to_collection(floor, stage)
    floor.data.materials.append(floor_mat)

    bpy.ops.object.camera_add(location=(0, 5.4, 1.05))
    camera = bpy.context.object
    camera.name = "character_review_camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.18
    camera.data.lens = 70
    look_at(camera, (0, 0, 0.98))
    move_to_collection(camera, stage)
    scene.camera = camera

    lights = [
        ("key_softbox", (3.2, 4.2, 5.1), 520, 4.0, (1.0, 0.72, 0.48)),
        ("fill_softbox", (-3.8, 2.5, 3.0), 320, 3.5, (0.35, 0.55, 1.0)),
        ("rim_softbox", (1.2, -3.5, 4.0), 560, 3.0, (0.20, 0.38, 1.0)),
    ]
    for name, loc, power, size, color in lights:
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy = power
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        look_at(light, (0, 0, 1.0))
        move_to_collection(light, stage)
    bpy.ops.object.light_add(type="AREA", location=(0, 0, -2.5))
    underside = bpy.context.object
    underside.name = "underside_fill"
    underside.data.energy = 0
    underside.data.shape = "DISK"
    underside.data.size = 3.0
    underside.data.color = (0.42, 0.58, 1.0)
    look_at(underside, (0, 0, 0.8))
    move_to_collection(underside, stage)
    return camera, stage


def set_collection_render(coll, visible):
    for obj in coll.objects:
        obj.hide_render = not visible


def render_views(scene, arm, visible_coll, hidden_coll, output_dir, prefix):
    set_collection_render(visible_coll, True)
    set_collection_render(hidden_coll, False)
    distance = 5.4
    views = (
        ("front", (0.0, distance, 1.05), "ORTHO", 2.18, 70),
        ("back", (0.0, -distance, 1.05), "ORTHO", 2.18, 70),
        ("left", (-distance, 0.0, 1.05), "ORTHO", 2.18, 70),
        ("right", (distance, 0.0, 1.05), "ORTHO", 2.18, 70),
        ("top", (0.0, 0.0, 5.8), "ORTHO", 2.18, 70),
        ("bottom", (0.0, 0.0, -4.2), "ORTHO", 2.18, 70),
        ("action", (2.6, 3.5, 1.55), "PERSP", 2.18, 70),
    )
    camera = scene.camera
    original_location = camera.location.copy()
    original_type = camera.data.type
    original_ortho_scale = camera.data.ortho_scale
    original_lens = camera.data.lens
    floor = bpy.data.objects.get("lookdev_floor")
    underside = bpy.data.objects.get("underside_fill")
    for label, location, camera_type, ortho_scale, lens in views:
        camera.location = location
        camera.data.type = camera_type
        camera.data.ortho_scale = ortho_scale
        camera.data.lens = lens
        look_at(camera, (0, 0, 0.98))
        if floor:
            floor.hide_render = label == "bottom"
        if underside:
            underside.data.energy = 650 if label == "bottom" else 0
        scene.render.filepath = str(output_dir / f"{prefix}_{label}.png")
        bpy.ops.render.render(write_still=True)
    if floor:
        floor.hide_render = False
    if underside:
        underside.data.energy = 0
    camera.location = original_location
    camera.data.type = original_type
    camera.data.ortho_scale = original_ortho_scale
    camera.data.lens = original_lens
    look_at(camera, (0, 0, 0.98))


def save_workbench(path, hero_coll, standin_coll):
    set_collection_render(hero_coll, True)
    set_collection_render(standin_coll, False)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)


def main():
    args = parse_args()
    repo = Path.cwd()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    clear_scene()
    hero_coll = make_collection("CHAR_ORLANDO_1999_A")
    standin_coll = make_collection("CHAR_GENERIC_STANDIN_1999_A")
    hero_arm = import_rig(repo / HERO_SOURCE, "char_orlando_1999_A", hero_coll, True)
    motion_sources = {
        name: bpy.data.actions.get(name)
        for name in CANONICAL_MOTION_CLIPS
        if name != "idle_standing_relaxed" and bpy.data.actions.get(name)
    }
    standin_arm = import_rig(
        repo / HERO_SOURCE, "placeholder_character_generic_1999_A",
        standin_coll, False,
    )
    build_hero(hero_arm, hero_coll)
    build_standin(standin_arm, standin_coll)
    configure_motion_clips(
        (hero_arm, standin_arm), motion_sources, repo / IDLE_SOURCE
    )

    export_character(hero_arm, hero_coll, output_dir / "char_orlando_1999_A.glb")
    export_character(
        standin_arm, standin_coll,
        output_dir / "placeholder_character_generic_1999_A.glb",
    )

    # Asset-review renders and the saved workbench use the deformation-safe
    # rest pose. Motion clips remain embedded on the NLA tracks.
    hero_arm.data.pose_position = "REST"
    standin_arm.data.pose_position = "REST"

    _camera, _stage = setup_stage(args.resolution)
    scene = bpy.context.scene
    render_views(scene, hero_arm, hero_coll, standin_coll, output_dir, "orlando_1999")
    render_views(scene, standin_arm, standin_coll, hero_coll, output_dir, "generic_standin")
    hero_arm.rotation_euler.z = 0.0
    standin_arm.rotation_euler.z = 0.0
    save_workbench(
        output_dir / "orlando_1999_character_workbench.blend",
        hero_coll, standin_coll,
    )
    print(f"[build_orlando_1999] Wrote assets and review renders to {output_dir}")


if __name__ == "__main__":
    main()
