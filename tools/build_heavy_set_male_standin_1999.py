#!/usr/bin/env python3
"""Build the additive heavy-set male stand-in v0.0.1 character asset.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_heavy_set_male_standin_1999.py -- \
    --output-dir assets/concepts/orlando_1999
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_orlando_1999 import (  # noqa: E402
    CANONICAL_MOTION_CLIPS,
    HERO_SOURCE,
    IDLE_SOURCE,
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
    setup_stage,
)


ASSET_ID = "heavy-set-male-stand-in_v0.0.1"
DISPLAY_LABEL = "Heavy-Set Male Stand-In"
VERSION = "0.0.1"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_heavy_set_male_standin_1999")
    parser.add_argument(
        "--output-dir", default="assets/concepts/orlando_1999"
    )
    parser.add_argument("--resolution", type=int, default=640)
    return parser.parse_args(argv)


def build_heavy_set_male_standin(arm, coll):
    mats = {
        "body": make_material(
            "heavy_male_standin_body_green", (0.065, 0.245, 0.205, 1), 0.84
        ),
        "limb": make_material(
            "heavy_male_standin_limb_bluegray", (0.12, 0.18, 0.235, 1), 0.84
        ),
        "joint": make_material(
            "heavy_male_standin_joint_dark", (0.024, 0.040, 0.050, 1), 0.76
        ),
        "id": make_material(
            "heavy_male_standin_identifier_amber", (0.95, 0.42, 0.035, 1), 0.70
        ),
    }
    b = bone_points(arm)
    made = [
        ellipsoid(
            "standin_heavy_torso",
            (0, 0.006, 1.295),
            (0.265, 0.145, 0.300),
            mats["body"], coll, arm, "spine_02", 20, 10,
        ),
        ellipsoid(
            "standin_heavy_belly",
            (0, 0.075, 1.205),
            (0.245, 0.145, 0.210),
            mats["body"], coll, arm, "spine_01", 20, 9,
        ),
        ellipsoid(
            "standin_heavy_pelvis",
            (0, 0.018, 0.985),
            (0.225, 0.125, 0.145),
            mats["joint"], coll, arm, "pelvis", 16, 8,
        ),
        ellipsoid(
            "standin_heavy_shoulder_l",
            (0.225, 0, 1.455),
            (0.095, 0.100, 0.090),
            mats["body"], coll, arm, "spine_03", 14, 7,
        ),
        ellipsoid(
            "standin_heavy_shoulder_r",
            (-0.225, 0, 1.455),
            (0.095, 0.100, 0.090),
            mats["body"], coll, arm, "spine_03", 14, 7,
        ),
        ellipsoid(
            "standin_heavy_neck",
            (0, 0.01, 1.565),
            (0.072, 0.066, 0.085),
            mats["id"], coll, arm, "neck_01", 14, 7,
        ),
        ellipsoid(
            "standin_heavy_head",
            (0, 0.01, 1.73),
            (0.135, 0.123, 0.162),
            mats["id"], coll, arm, "Head", 16, 8,
        ),
        ellipsoid(
            "standin_heavy_eye_l",
            (0.049, 0.127, 1.756),
            (0.012, 0.008, 0.014),
            mats["joint"], coll, arm, "Head", 10, 6,
        ),
        ellipsoid(
            "standin_heavy_eye_r",
            (-0.049, 0.127, 1.756),
            (0.012, 0.008, 0.014),
            mats["joint"], coll, arm, "Head", 10, 6,
        ),
    ]

    for side in ("l", "r"):
        for bone, radii in (
            (f"upperarm_{side}", (0.092, 0.074)),
            (f"lowerarm_{side}", (0.072, 0.058)),
            (f"thigh_{side}", (0.118, 0.092)),
            (f"calf_{side}", (0.090, 0.066)),
        ):
            p0, p1 = b[bone]
            made.append(
                segment(
                    f"standin_heavy_{bone}", p0, p1, radii[0], radii[1],
                    mats["limb"], coll, arm, bone, sides=12,
                    squash=(1.0, 0.90),
                )
            )
        hand0, hand1 = b[f"hand_{side}"]
        made.append(
            ellipsoid(
                f"standin_heavy_hand_{side}", (hand0 + hand1) * 0.5,
                (0.060, 0.042, 0.041), mats["id"], coll, arm,
                f"hand_{side}", 12, 6,
            )
        )
        foot0, _foot1 = b[f"foot_{side}"]
        made.append(
            rounded_box(
                f"standin_heavy_foot_{side}",
                foot0 + Vector((0, 0.078, -0.005)),
                (0.170, 0.300, 0.135), mats["joint"], coll, arm,
                f"foot_{side}", bevel=0.044,
            )
        )

    arm["character_id"] = ASSET_ID
    arm["asset_version"] = VERSION
    arm["display_label"] = DISPLAY_LABEL
    arm["purpose"] = "shared heavy-set male stand-in"
    arm["body_type"] = "heavy-set"
    arm["gender_presentation"] = "male"
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
    heavy_coll = make_collection("HEAVY_SET_MALE_STAND_IN_V0_0_1")
    empty_coll = make_collection("EMPTY_REVIEW_HIDE")
    arm = import_rig(repo / HERO_SOURCE, ASSET_ID, heavy_coll, True)
    motion_sources = {
        name: bpy.data.actions.get(name)
        for name in CANONICAL_MOTION_CLIPS
        if name != "idle_standing_relaxed" and bpy.data.actions.get(name)
    }
    build_heavy_set_male_standin(arm, heavy_coll)
    configure_motion_clips((arm,), motion_sources, repo / IDLE_SOURCE)

    export_character(arm, heavy_coll, output_dir / f"{ASSET_ID}.glb")

    arm.data.pose_position = "REST"
    _camera, _stage = setup_stage(args.resolution)
    scene = bpy.context.scene
    render_views(scene, arm, heavy_coll, empty_coll, output_dir, ASSET_ID)
    arm.rotation_euler.z = 0.0
    save_workbench(
        output_dir / f"{ASSET_ID}.blend", heavy_coll, empty_coll
    )
    print(f"[build_heavy_set_male_standin_1999] Wrote {ASSET_ID} to {output_dir}")


if __name__ == "__main__":
    main()
