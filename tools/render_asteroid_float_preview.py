#!/usr/bin/env python3
"""Render a five-second Studio Harness asteroid-field motion preview."""

from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "assets" / "placeholders"
PREVIEW_DIR = ASSET_DIR / "asteroids" / "previews"
FIELD_GLB = ASSET_DIR / "placeholder_location_asteroid_field_A.glb"
OUTPUT_MP4 = PREVIEW_DIR / "asteroid_float_5s.mp4"
OUTPUT_BLEND = PREVIEW_DIR / "asteroid_float_5s.blend"
OUTPUT_POSTER = PREVIEW_DIR / "asteroid_float_5s_poster.png"
FRAME_DIR = Path("/tmp/oeb_asteroid_float_frames")
FFMPEG = (
    PROJECT_ROOT
    / ".venv/lib/python3.14/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
)
FPS = 24
FRAME_END = FPS * 5


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def emission_material(name: str, color, strength: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def add_starfield() -> None:
    rng = random.Random(1999)
    vertices = []
    faces = []
    for _ in range(180):
        center = Vector((rng.uniform(-24, 24), rng.uniform(17, 34), rng.uniform(-14, 14)))
        radius = rng.uniform(0.018, 0.065)
        start = len(vertices)
        vertices.extend(
            center + offset
            for offset in (
                Vector((radius, 0, 0)),
                Vector((-radius, 0, 0)),
                Vector((0, radius, 0)),
                Vector((0, -radius, 0)),
                Vector((0, 0, radius)),
                Vector((0, 0, -radius)),
            )
        )
        faces.extend(
            (start + a, start + b, start + c)
            for a, b, c in (
                (0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
                (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5),
            )
        )
    mesh = bpy.data.meshes.new("starfield_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    stars = bpy.data.objects.new("starfield", mesh)
    bpy.context.collection.objects.link(stars)
    stars.data.materials.append(emission_material("star_glow", (0.72, 0.82, 1.0, 1.0), 8.0))


def import_and_arrange_asteroids() -> list[bpy.types.Object]:
    bpy.ops.import_scene.gltf(filepath=str(FIELD_GLB))
    sources = sorted(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda obj: obj.name,
    )
    for obj in list(bpy.context.scene.objects):
        if obj.type == "EMPTY":
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in sources:
        obj.parent = None

    placements = (
        ((-4.2, -0.5, 2.2), 1.08),
        ((-2.0, 1.2, -1.2), 0.72),
        ((0.2, 2.7, 0.5), 1.28),
        ((2.7, 4.3, -1.5), 0.84),
        ((4.5, 5.8, 2.0), 0.92),
        ((-5.0, 7.4, -2.3), 0.62),
        ((-1.6, 8.8, 2.9), 0.80),
        ((2.0, 10.2, 0.4), 0.58),
        ((5.0, 11.8, -2.1), 0.75),
        ((-3.5, 13.0, 0.9), 0.54),
        ((0.2, 14.4, -2.8), 0.68),
        ((4.0, 15.8, 2.7), 0.50),
    )
    asteroids = []
    rng = random.Random(5000)
    for index, (location, scale) in enumerate(placements):
        source = sources[index % len(sources)]
        asteroid = source if index < len(sources) else source.copy()
        if asteroid is not source:
            asteroid.data = source.data
            bpy.context.collection.objects.link(asteroid)
        asteroid.name = f"floating_asteroid_{index + 1:02d}"
        asteroid.location = location
        asteroid.scale = (scale, scale, scale)
        start_rotation = tuple(rng.uniform(-math.pi, math.pi) for _ in range(3))
        asteroid.rotation_euler = start_rotation
        asteroid.keyframe_insert(data_path="rotation_euler", frame=1)
        asteroid.rotation_euler = tuple(
            start_rotation[axis] + rng.uniform(0.45, 1.35) * (-1 if (index + axis) % 2 else 1)
            for axis in range(3)
        )
        asteroid.keyframe_insert(data_path="rotation_euler", frame=FRAME_END)
        asteroid.keyframe_insert(data_path="location", frame=1)
        asteroid.location.z += rng.uniform(-0.28, 0.28)
        asteroid.location.x += rng.uniform(-0.18, 0.18)
        asteroid.keyframe_insert(data_path="location", frame=FRAME_END)
        asteroids.append(asteroid)
    for source in sources:
        if source not in asteroids:
            bpy.data.objects.remove(source, do_unlink=True)
    return asteroids


def add_camera() -> None:
    camera_data = bpy.data.cameras.new("asteroid_camera")
    camera = bpy.data.objects.new("asteroid_camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.lens = 48
    camera.data.clip_end = 200
    camera.location = (0.0, -11.8, 1.3)

    target = bpy.data.objects.new("camera_target", None)
    bpy.context.collection.objects.link(target)
    target.location = (0.0, 5.0, 0.1)
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"

    camera.keyframe_insert(data_path="location", frame=1)
    camera.location = (1.1, -6.6, 0.45)
    camera.keyframe_insert(data_path="location", frame=FRAME_END)
    target.keyframe_insert(data_path="location", frame=1)
    target.location = (-0.45, 9.2, 0.25)
    target.keyframe_insert(data_path="location", frame=FRAME_END)
    bpy.context.scene.camera = camera


def add_lighting() -> None:
    sun_data = bpy.data.lights.new("distant_key", "SUN")
    sun_data.energy = 2.0
    sun_data.color = (0.72, 0.80, 1.0)
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("distant_key", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(24), math.radians(-18), math.radians(-36))

    rim_data = bpy.data.lights.new("warm_rim", "AREA")
    rim_data.energy = 850
    rim_data.color = (1.0, 0.28, 0.08)
    rim_data.shape = "DISK"
    rim_data.size = 8.0
    rim = bpy.data.objects.new("warm_rim", rim_data)
    bpy.context.collection.objects.link(rim)
    rim.location = (7.0, 6.0, 2.5)
    look_at(rim, Vector((0, 6, 0)))

    fill_data = bpy.data.lights.new("soft_fill", "AREA")
    fill_data.energy = 600
    fill_data.color = (0.18, 0.32, 0.72)
    fill_data.size = 10.0
    fill = bpy.data.objects.new("soft_fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-6.0, 1.0, 5.0)
    look_at(fill, Vector((0, 7, 0)))


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.002, 0.004, 0.014, 1.0)
    background.inputs["Strength"].default_value = 0.08

    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(FRAME_DIR / "frame_")


def encode_video() -> None:
    subprocess.run(
        (
            str(FFMPEG),
            "-y",
            "-framerate", str(FPS),
            "-start_number", "1",
            "-i", str(FRAME_DIR / "frame_%04d.png"),
            "-frames:v", str(FRAME_END),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(OUTPUT_MP4),
        ),
        check=True,
    )


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    import_and_arrange_asteroids()
    add_starfield()
    add_camera()
    add_lighting()
    configure_render()
    bpy.context.scene.frame_set(FPS * 2)
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.filepath = str(OUTPUT_POSTER)
    bpy.ops.render.render(write_still=True)
    configure_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(animation=True)
    encode_video()
    print(f"Rendered five-second asteroid preview to {OUTPUT_MP4}")


if __name__ == "__main__":
    main()
