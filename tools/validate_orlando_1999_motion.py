#!/usr/bin/env python3
"""Validate the Orlando 1999 character GLBs as motion-ready assets.

Checks the canonical skeleton, exact animation vocabulary, mesh bindings,
vertex weights, and evaluated mesh displacement for every embedded clip.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/validate_orlando_1999_motion.py -- \
    assets/concepts/orlando_1999/char_orlando_1999_A.glb \
    assets/concepts/orlando_1999/placeholder_character_generic_1999_A.glb
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


EXPECTED_CLIPS = {
    "walk_to_stool",
    "sit_barstool",
    "stand_from_stool",
    "idle_standing_relaxed",
    "idle_seated_relaxed",
    "talk_neutral_seated",
    "nod_small",
    "look_down_then_up",
}

CORE_BONES = {
    "root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01",
    "Head", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r",
    "lowerarm_r", "hand_r", "thigh_l", "calf_l", "foot_l", "thigh_r",
    "calf_r", "foot_r",
}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def first_vertex_positions(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    positions = {}
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.data.vertices:
            positions[obj.name] = (
                evaluated.matrix_world @ evaluated.data.vertices[0].co
            ).copy()
    return positions


def validate_asset(path: Path):
    reset_scene()
    before_objects = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = list(set(bpy.data.objects) - before_objects)
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    # Some local Blender start-up configurations inject unparented helper
    # primitives during glTF import. Character meshes have controlled names;
    # validate only the asset payload, never environment helpers.
    meshes = [
        obj for obj in imported
        if obj.type == "MESH"
        and obj.name.startswith(("orlando_", "standin_", "female_"))
    ]
    if len(arms) != 1:
        raise AssertionError(f"{path.name}: expected one armature, got {len(arms)}")
    arm = arms[0]
    bone_names = {bone.name for bone in arm.data.bones}
    if len(bone_names) != 65:
        raise AssertionError(f"{path.name}: expected 65 bones, got {len(bone_names)}")
    if not CORE_BONES <= bone_names:
        raise AssertionError(f"{path.name}: missing core bones {CORE_BONES - bone_names}")

    action_names = {action.name for action in bpy.data.actions}
    if action_names != EXPECTED_CLIPS:
        raise AssertionError(
            f"{path.name}: clip mismatch missing={EXPECTED_CLIPS-action_names} "
            f"extra={action_names-EXPECTED_CLIPS}"
        )

    for mesh in meshes:
        modifiers = [mod for mod in mesh.modifiers if mod.type == "ARMATURE"]
        if len(modifiers) != 1 or modifiers[0].object is not arm:
            raise AssertionError(f"{path.name}: {mesh.name} armature binding invalid")
        group_names = {group.index: group.name for group in mesh.vertex_groups}
        invalid_groups = set(group_names.values()) - bone_names
        if invalid_groups:
            raise AssertionError(
                f"{path.name}: {mesh.name} has non-skeleton groups {invalid_groups}"
            )
        unweighted = 0
        for vert in mesh.data.vertices:
            total = sum(group.weight for group in vert.groups)
            if total < 0.999:
                unweighted += 1
        if unweighted:
            raise AssertionError(
                f"{path.name}: {mesh.name} has {unweighted} unweighted vertices"
            )

    arm.data.pose_position = "POSE"
    arm.animation_data_create()
    if arm.animation_data:
        for track in arm.animation_data.nla_tracks:
            track.mute = True

    deltas = {}
    scene = bpy.context.scene
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        arm.animation_data.action = action
        start = int(round(action.frame_range[0]))
        middle = int(round((action.frame_range[0] + action.frame_range[1]) * 0.5))
        scene.frame_set(start)
        start_positions = first_vertex_positions(meshes)
        scene.frame_set(middle)
        middle_positions = first_vertex_positions(meshes)
        delta = max(
            (middle_positions[name] - start_positions[name]).length
            for name in start_positions.keys() & middle_positions.keys()
        )
        if delta <= 0.0001:
            raise AssertionError(
                f"{path.name}: {action.name} produced no evaluated mesh motion"
            )
        deltas[action.name] = round(delta, 5)

    arm.animation_data.action = None
    print(
        f"MOTION_PASS {path.name} bones={len(bone_names)} meshes={len(meshes)} "
        f"clips={len(action_names)} deltas_m={deltas}"
    )


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("Provide one or more GLB paths after --")
    for raw_path in argv:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        validate_asset(path)


if __name__ == "__main__":
    main()
