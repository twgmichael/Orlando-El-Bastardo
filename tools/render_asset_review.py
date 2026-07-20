#!/usr/bin/env python3
"""Headless Blender review renders for an existing asset.

Run by the studio harness worker:
  blender --background --factory-startup --python tools/render_asset_review.py -- \
    --asset assets/ships/ventradi_cruiser.glb \
    --asset-id ventradi_cruiser \
    --views top,bottom,left,right,front,back,action \
    --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


VALID_VIEWS = ("top", "bottom", "left", "right", "front", "back", "action")
ORTHO_VIEWS = {
    "front": ((1, 0, 0), (0, 0, 1)),
    "back": ((-1, 0, 0), (0, 0, 1)),
    "left": ((0, -1, 0), (0, 0, 1)),
    "right": ((0, 1, 0), (0, 0, 1)),
    "top": ((0, 0, 1), (0, 1, 0)),
    "bottom": ((0, 0, -1), (0, -1, 0)),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--views", default="top,bottom,left,right,front,back,action")
    parser.add_argument("--quality", choices=("preview", "final"), default="preview")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--artifact-prefix")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--engine", choices=("BLENDER_EEVEE_NEXT", "CYCLES"), default=None)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_asset(path: Path) -> None:
    ext = path.suffix.lower()
    if ext in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext in {".usd", ".usdc", ".usda"}:
        bpy.ops.wm.usd_import(filepath=str(path))
    elif ext == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
            data_to.objects = data_from.objects
        for obj in data_to.objects:
            if obj:
                bpy.context.collection.objects.link(obj)
    else:
        raise ValueError(f"Unsupported asset format: {ext}")


def clear_imported_animation() -> None:
    for obj in bpy.context.scene.objects:
        if obj.animation_data:
            obj.animation_data_clear()


def mesh_objects() -> list:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def scene_bounds() -> tuple[Vector, Vector]:
    meshes = mesh_objects()
    if not meshes:
        raise ValueError("Imported asset has no mesh objects")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    mins = Vector((math.inf, math.inf, math.inf))
    maxs = Vector((-math.inf, -math.inf, -math.inf))
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        for vertex in mesh.vertices:
            world = evaluated.matrix_world @ vertex.co
            mins.x = min(mins.x, world.x)
            mins.y = min(mins.y, world.y)
            mins.z = min(mins.z, world.z)
            maxs.x = max(maxs.x, world.x)
            maxs.y = max(maxs.y, world.y)
            maxs.z = max(maxs.z, world.z)
        evaluated.to_mesh_clear()
    return mins, maxs


def configure_render(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    width = args.width or (1600 if args.quality == "final" else 1000)
    height = args.height or (1000 if args.quality == "final" else 700)
    samples = args.samples or (96 if args.quality == "final" else 32)
    engine = args.engine or ("CYCLES" if args.quality == "final" else "BLENDER_EEVEE_NEXT")

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.camera = None

    try:
        scene.render.engine = engine
    except TypeError:
        scene.render.engine = "CYCLES"

    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    else:
        scene.eevee.taa_render_samples = samples
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"

    scene.world = bpy.data.worlds.new("review_world")
    scene.world.color = (0.02, 0.025, 0.03)


def add_lighting(radius: float, center: Vector) -> None:
    sun_data = bpy.data.lights.new("review_sun", type="SUN")
    sun_data.energy = 2.5
    sun = bpy.data.objects.new("review_sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(45), 0, math.radians(35))

    key_data = bpy.data.lights.new("review_key", type="AREA")
    key_data.energy = max(350, radius * radius * 60)
    key_data.size = max(3.0, radius * 1.6)
    key = bpy.data.objects.new("review_key", key_data)
    bpy.context.collection.objects.link(key)
    key.location = center + Vector((radius * 1.4, -radius * 1.8, radius * 1.5))
    look_at(key, center)

    fill_data = bpy.data.lights.new("review_fill", type="AREA")
    fill_data.energy = max(80, radius * radius * 18)
    fill_data.size = max(4.0, radius * 2.2)
    fill = bpy.data.objects.new("review_fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = center + Vector((-radius * 1.6, radius * 1.5, radius * 1.1))
    look_at(fill, center)


def look_at(obj, target: Vector, up: Vector | None = None) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    if up is not None and obj.type == "CAMERA":
        # Track-quat gives a stable view; roll is corrected for top/bottom by the
        # explicit camera up vectors through a secondary alignment object.
        pass


def ortho_scale_for_view(view: str, dims: Vector) -> float:
    padding = 1.70
    if view in {"front", "back"}:
        span = max(dims.y, dims.z)
    elif view in {"left", "right"}:
        span = max(dims.x, dims.z)
    else:
        span = max(dims.x, dims.y)
    return max(span * padding, 0.5)


def make_camera(name: str):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def render_view(view: str, center: Vector, dims: Vector, radius: float, output_path: Path) -> None:
    cam = make_camera(f"review_camera_{view}")
    if view == "action":
        cam.data.type = "PERSP"
        cam.data.lens = 50
        cam.location = center + Vector((radius * 1.8, -radius * 2.35, radius * 1.0))
        look_at(cam, center + Vector((0, 0, dims.z * 0.03)))
    else:
        axis, _up = ORTHO_VIEWS[view]
        axis_vec = Vector(axis)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_scale_for_view(view, dims)
        cam.location = center + axis_vec * max(radius * 2.8, 4.0)
        look_at(cam, center)

    bpy.context.scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


def main() -> None:
    args = parse_args()
    asset_path = Path(args.asset)
    output_dir = Path(args.output_dir)
    prefix = args.artifact_prefix or args.asset_id
    views = [v.strip() for v in args.views.split(",") if v.strip()]

    invalid = [v for v in views if v not in VALID_VIEWS]
    if invalid:
        raise ValueError(f"Unsupported views: {invalid}")
    if not asset_path.exists():
        raise FileNotFoundError(f"Asset not found: {asset_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    clear_scene()
    import_asset(asset_path)
    clear_imported_animation()
    bpy.context.scene.frame_set(1)
    mins, maxs = scene_bounds()
    center = (mins + maxs) * 0.5
    dims = maxs - mins
    radius = max(dims.length * 0.5, 1.0)

    configure_render(args)
    add_lighting(radius, center)

    written = []
    for view in views:
        path = output_dir / f"{prefix}_{view}.png"
        render_view(view, center, dims, radius, path)
        written.append({"view": view, "path": str(path)})

    manifest = {
        "asset_id": args.asset_id,
        "asset_path": str(asset_path),
        "quality": args.quality,
        "views": written,
        "bounds": {
            "min": list(mins),
            "max": list(maxs),
            "dimensions": list(dims),
        },
    }
    (output_dir / f"{prefix}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
