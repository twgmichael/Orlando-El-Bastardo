#!/usr/bin/env python3
"""Build the additive female stand-in v0.0.1 character asset.

The figure deliberately stays close to the neutral male stand-in language:
smooth primitive construction, restrained average proportions, and a single
horizontal pill-shaped chest form.  It uses the canonical 65-bone humanoid
rig and the same eight embedded motion clips as the other 1999 stand-ins.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_female_standin_1999.py -- \
    --output-dir assets/concepts/orlando_1999
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_orlando_1999 import (  # noqa: E402
    CANONICAL_MOTION_CLIPS,
    HERO_SOURCE,
    IDLE_SOURCE,
    bind_rigid,
    bone_points,
    clear_scene,
    configure_motion_clips,
    ellipsoid,
    export_character,
    import_rig,
    make_collection,
    make_material,
    render_views,
    rounded_box,
    save_workbench,
    segment,
    smooth_mesh,
    setup_stage,
)


ASSET_ID = "female-stand-in_v0.0.2"
DISPLAY_LABEL = "Female Stand-In"
VERSION = "0.0.2"


def profiled_torso(name, profiles, mat, coll, arm, bone, sides=24):
    """Create one smooth torso from a restrained waist-and-ribcage profile."""
    vertices = []
    faces = []
    for z, radius_x, radius_y in profiles:
        for index in range(sides):
            angle = (2.0 * math.pi * index) / sides
            vertices.append(
                (radius_x * math.cos(angle), radius_y * math.sin(angle), z)
            )
    for ring in range(len(profiles) - 1):
        current = ring * sides
        following = (ring + 1) * sides
        for index in range(sides):
            next_index = (index + 1) % sides
            faces.append(
                (
                    current + index,
                    current + next_index,
                    following + next_index,
                    following + index,
                )
            )
    bottom_center = len(vertices)
    vertices.append((0, 0, profiles[0][0]))
    top_center = len(vertices)
    vertices.append((0, 0, profiles[-1][0]))
    top_ring = (len(profiles) - 1) * sides
    for index in range(sides):
        next_index = (index + 1) % sides
        faces.append((bottom_center, next_index, index))
        faces.append((top_center, top_ring + index, top_ring + next_index))

    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.data.materials.append(mat)
    smooth_mesh(obj)
    bind_rigid(obj, arm, bone)
    return obj


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_female_standin_1999")
    parser.add_argument(
        "--output-dir", default="assets/concepts/orlando_1999"
    )
    parser.add_argument("--resolution", type=int, default=640)
    return parser.parse_args(argv)


def build_female_standin(arm, coll):
    """Build a restrained abstract female silhouette on the shared rig."""
    mats = {
        "body": make_material(
            "female_standin_body_plum", (0.24, 0.075, 0.22, 1), 0.84
        ),
        "limb": make_material(
            "female_standin_limb_bluegray", (0.13, 0.18, 0.25, 1), 0.84
        ),
        "joint": make_material(
            "female_standin_joint_dark", (0.030, 0.040, 0.060, 1), 0.76
        ),
        "id": make_material(
            "female_standin_identifier_amber", (0.90, 0.34, 0.045, 1), 0.70
        ),
    }
    b = bone_points(arm)
    made = [
        # One continuous profile avoids stacked cones and keeps the waist and
        # ribcage transition readable from every review angle.
        profiled_torso(
            "female_torso",
            (
                (1.035, 0.188, 0.103),
                (1.105, 0.196, 0.108),
                (1.255, 0.166, 0.094),
                (1.385, 0.190, 0.104),
                (1.485, 0.213, 0.106),
                (1.525, 0.188, 0.090),
            ),
            mats["body"], coll, arm, "spine_02",
        ),
        # One modest horizontal capsule: the deliberately simple "uni-boob"
        # read requested for this early silhouette test.
        rounded_box(
            "female_chest_pill", (0, 0.096, 1.392),
            (0.285, 0.094, 0.096), mats["body"], coll, arm, "spine_03",
            bevel=0.046,
        ),
        ellipsoid(
            "female_pelvis", (0, 0.006, 0.985), (0.205, 0.094, 0.14),
            mats["joint"], coll, arm, "pelvis", 16, 8,
        ),
        ellipsoid(
            "female_shoulder_l", (0.197, 0, 1.455), (0.071, 0.078, 0.071),
            mats["body"], coll, arm, "spine_03", 14, 7,
        ),
        ellipsoid(
            "female_shoulder_r", (-0.197, 0, 1.455), (0.071, 0.078, 0.071),
            mats["body"], coll, arm, "spine_03", 14, 7,
        ),
        ellipsoid(
            "female_neck", (0, 0.01, 1.57), (0.064, 0.061, 0.095),
            mats["id"], coll, arm, "neck_01", 14, 7,
        ),
        ellipsoid(
            "female_head", (0, 0.01, 1.73), (0.119, 0.108, 0.155),
            mats["id"], coll, arm, "Head", 16, 8,
        ),
        ellipsoid(
            "female_eye_l", (0.047, 0.120, 1.755),
            (0.011, 0.008, 0.013), mats["joint"], coll, arm, "Head", 10, 6,
        ),
        ellipsoid(
            "female_eye_r", (-0.047, 0.120, 1.755),
            (0.011, 0.008, 0.013), mats["joint"], coll, arm, "Head", 10, 6,
        ),
    ]

    for side in ("l", "r"):
        for bone, radii in (
            (f"upperarm_{side}", (0.073, 0.058)),
            (f"lowerarm_{side}", (0.058, 0.047)),
            (f"thigh_{side}", (0.096, 0.077)),
            (f"calf_{side}", (0.076, 0.055)),
        ):
            p0, p1 = b[bone]
            made.append(
                segment(
                    f"female_{bone}", p0, p1, radii[0], radii[1],
                    mats["limb"], coll, arm, bone, sides=12,
                    squash=(1.0, 0.86),
                )
            )
        hand0, hand1 = b[f"hand_{side}"]
        made.append(
            ellipsoid(
                f"female_hand_{side}", (hand0 + hand1) * 0.5,
                (0.050, 0.035, 0.036), mats["id"], coll, arm,
                f"hand_{side}", 12, 6,
            )
        )
        foot0, _foot1 = b[f"foot_{side}"]
        made.append(
            rounded_box(
                f"female_foot_{side}", foot0 + Vector((0, 0.068, -0.004)),
                (0.145, 0.265, 0.12), mats["joint"], coll, arm,
                f"foot_{side}", bevel=0.040,
            )
        )

    arm["character_id"] = ASSET_ID
    arm["asset_version"] = VERSION
    arm["display_label"] = DISPLAY_LABEL
    arm["purpose"] = "shared average-build female stand-in"
    arm["body_type"] = "average-build"
    arm["gender_presentation"] = "female"
    arm["chest_design"] = "single modest horizontal pill form"
    arm["skeleton"] = "oeb_humanoid_v1"
    return made


def main():
    args = parse_args()
    repo = Path.cwd()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    clear_scene()
    female_coll = make_collection("FEMALE_STAND_IN_V0_0_1")
    empty_coll = make_collection("EMPTY_REVIEW_COLLECTION")
    arm = import_rig(repo / HERO_SOURCE, ASSET_ID, female_coll, True)
    motion_sources = {
        name: bpy.data.actions.get(name)
        for name in CANONICAL_MOTION_CLIPS
        if name != "idle_standing_relaxed" and bpy.data.actions.get(name)
    }
    build_female_standin(arm, female_coll)
    configure_motion_clips((arm,), motion_sources, repo / IDLE_SOURCE)

    export_character(arm, female_coll, output_dir / f"{ASSET_ID}.glb")
    arm.data.pose_position = "REST"

    setup_stage(args.resolution)
    scene = bpy.context.scene
    render_views(
        scene, arm, female_coll, empty_coll, output_dir, ASSET_ID
    )
    arm.rotation_euler.z = 0.0
    save_workbench(
        output_dir / f"{ASSET_ID}.blend", female_coll, empty_coll
    )
    print(f"[build_female_standin_1999] Wrote {ASSET_ID} to {output_dir}")


if __name__ == "__main__":
    main()
