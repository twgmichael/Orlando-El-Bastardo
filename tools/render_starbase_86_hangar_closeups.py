#!/usr/bin/env python3
"""Render close review angles of Starbase 86's fully open hangar.

The camera placement comes from the semantic hangar markers carried by the
registered hero GLB, so these views stay aligned with the gameplay passage.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    return parser.parse_args(argv)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_starfield() -> None:
    random.seed(86)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for _index in range(420):
        direction = Vector(
            (
                random.uniform(-1.0, 1.0),
                random.uniform(-1.0, 1.0),
                random.uniform(-0.85, 0.85),
            )
        ).normalized()
        center = direction * random.uniform(330.0, 430.0) + Vector((0.0, 0.0, 70.0))
        size = random.uniform(0.18, 0.52)
        base = len(vertices)
        vertices.extend(
            [
                tuple(center + Vector((size, 0.0, -size * 0.65))),
                tuple(center + Vector((-size, 0.0, -size * 0.65))),
                tuple(center + Vector((0.0, size, size * 0.65))),
                tuple(center + Vector((0.0, -size, size * 0.65))),
            ]
        )
        faces.extend(
            [
                (base, base + 1, base + 2),
                (base, base + 3, base + 1),
                (base, base + 2, base + 3),
                (base + 1, base + 3, base + 2),
            ]
        )
    mesh = bpy.data.meshes.new("review_starfield_mesh")
    mesh.from_pydata(vertices, [], faces)
    starfield = bpy.data.objects.new("review_starfield", mesh)
    bpy.context.collection.objects.link(starfield)
    material = bpy.data.materials.new("review_star_emission")
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0.72, 0.82, 1.0, 1.0)
    emission = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
    if emission is not None:
        emission.default_value = (0.72, 0.82, 1.0, 1.0)
    shader.inputs["Emission Strength"].default_value = 7.0
    starfield.data.materials.append(material)


def add_lights(center: Vector, entrance: Vector, exit_point: Vector) -> None:
    sun_data = bpy.data.lights.new("hangar_review_sun", "SUN")
    sun_data.energy = 2.3
    sun = bpy.data.objects.new("hangar_review_sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38.0), 0.0, math.radians(-28.0))

    axis = (entrance - exit_point).normalized()
    for name, position, energy, size in (
        ("entrance_fill", entrance + axis * 18.0 + Vector((0.0, 0.0, 14.0)), 1500.0, 22.0),
        ("exit_fill", exit_point - axis * 18.0 + Vector((0.0, 0.0, 12.0)), 900.0, 18.0),
        ("interior_fill", center + Vector((0.0, 0.0, 1.0)), 450.0, 8.0),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = position
        look_at(light, center)

    # Eevee does not bounce exterior light into the long, dark passage. These
    # neutral review lights reveal the authored floor, walls, and flat ceiling
    # without becoming part of the exported asset.
    for index, offset in enumerate((-11.0, 11.0), start=1):
        data = bpy.data.lights.new(f"interior_point_{index}", "POINT")
        data.energy = 2600.0
        data.color = (0.68, 0.78, 1.0)
        data.shadow_soft_size = 5.0
        light = bpy.data.objects.new(f"interior_point_{index}", data)
        bpy.context.collection.objects.link(light)
        light.location = center + axis * offset + Vector((0.0, 0.0, 1.8))


def make_camera(name: str, position: Vector, target: Vector, lens: float) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.1
    data.clip_end = 1200.0
    camera = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(camera)
    camera.location = position
    look_at(camera, target)
    return camera


def marker(name: str) -> Vector:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise RuntimeError(f"Hero asset is missing semantic marker {name!r}")
    return obj.matrix_world.translation.copy()


def main() -> None:
    args = parse_args()
    asset_path = Path(args.asset).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.import_scene.gltf(filepath=str(asset_path))
    bpy.context.view_layer.update()

    center = marker("prop_starbase_86_A_hangar_1_volume")
    entrance = marker("prop_starbase_86_A_hangar_1_entrance")
    exit_point = marker("prop_starbase_86_A_hangar_1_exit")
    entrance_axis = (entrance - center).normalized()
    exit_axis = (exit_point - center).normalized()

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world = bpy.data.worlds.new("hangar_review_world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.001,
        0.002,
        0.006,
        1.0,
    )
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08

    add_starfield()
    add_lights(center, entrance, exit_point)

    cameras = {
        "open_hangar_exterior_entrance": (
            entrance + entrance_axis * 88.0 + Vector((0.0, 0.0, 7.0)),
            center + Vector((0.0, 0.0, 0.5)),
            52.0,
        ),
        "open_hangar_exterior_exit": (
            exit_point + exit_axis * 82.0 + Vector((0.0, 0.0, 6.0)),
            center + Vector((0.0, 0.0, 0.5)),
            52.0,
        ),
        "open_hangar_flythrough": (
            entrance + entrance_axis * 10.0 + Vector((0.0, 0.0, -1.0)),
            exit_point + exit_axis * 20.0 + Vector((0.0, 0.0, 0.5)),
            38.0,
        ),
        "open_hangar_flat_ceiling": (
            center + entrance_axis * 15.0 + Vector((0.0, 0.0, -2.5)),
            center - entrance_axis * 8.0 + Vector((0.0, 0.0, 5.2)),
            35.0,
        ),
    }

    written = []
    for view, (position, target, lens) in cameras.items():
        camera = make_camera(f"camera_{view}", position, target, lens)
        scene.camera = camera
        output_path = output_dir / f"prop_starbase_86_A_{view}.png"
        scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)
        written.append({"view": view, "path": str(output_path)})
        bpy.data.objects.remove(camera, do_unlink=True)

    manifest = {
        "asset": str(asset_path),
        "hangar": 1,
        "state": "open",
        "marker_center": list(center),
        "marker_entrance": list(entrance),
        "marker_exit": list(exit_point),
        "views": written,
    }
    (output_dir / "prop_starbase_86_A_open_hangar_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
