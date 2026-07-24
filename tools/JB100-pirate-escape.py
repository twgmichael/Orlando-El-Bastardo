"""JB100 / Ellipso Flyer / Ventradi Cruiser short chase preview.

Staging:
  1. JB100 hurtles toward the camera.
  2. Camera cranes high and right, tracking the JB100 as it passes.
  3. One Ellipso Flyer flashes past in pursuit, then two more, then twelve in
     a non-overlapping formation.
  4. The Ventradi Cruiser passes overhead after the fighter wave recedes.

Output: out/jb100_ellipso_ventradi_chase.mp4 (960x540, H.264)
Blocking output: out/jb100_ellipso_ventradi_chase_blocking.mp4 (1280x720)

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/tmp_jb100_ellipso_ventradi_chase.py

  blender --background --factory-startup \
    --python tools/tmp_jb100_ellipso_ventradi_chase.py -- --mode blocking
"""

import argparse
import glob as globmod
import math
import os
import shutil
import subprocess

import bpy
from mathutils import Vector
from oeb_blender.render_device import configure_render_device_from_env


FPS = 24
N_FRAMES = FPS * 15
CWD = os.getcwd()
OUT_MP4 = os.path.join(CWD, "out/jb100_ellipso_ventradi_chase.mp4")
FRAMES_DIR = os.path.join(CWD, "out/jb100_ellipso_ventradi_chase_frames")
FLYER_SCALE = 2.1
CRUISER_SCALE = 12.0
CHASE_START_Y = -110.0
CHASE_SPEED = 3.0


def parse_args():
    argv = None
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1:]
    parser = argparse.ArgumentParser(prog="tmp_jb100_ellipso_ventradi_chase")
    parser.add_argument("--mode", choices=("preview", "blocking"),
                        default="preview")
    parser.add_argument("--output", default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    return parser.parse_args(argv)


def find_ffmpeg():
    candidates = []
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        candidates.append(system_ffmpeg)
    candidates.extend(globmod.glob(os.path.join(
        CWD, ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*")))

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return candidate
    raise RuntimeError("No compatible ffmpeg binary found on PATH or in .venv")


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_engine(scene, mode):
    candidates = ("BLENDER_WORKBENCH",) if mode == "blocking" else (
        "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")
    for candidate in candidates:
        try:
            scene.render.engine = candidate
            return
        except TypeError:
            continue
    raise RuntimeError("No usable Blender render engine found.")


def look_at(obj, target, roll=0.0):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    if roll:
        obj.rotation_euler.rotate_axis("Z", roll)


def import_asset(filepath, fallback_name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    imported = list(set(bpy.data.objects) - before)
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No mesh objects imported from {filepath}")
    if len(meshes) == 1 and len(imported) == 1:
        meshes[0].name = fallback_name
        return meshes[0]

    empty = bpy.data.objects.new(fallback_name, None)
    bpy.context.scene.collection.objects.link(empty)
    roots = [o for o in imported if o.parent not in imported]
    for obj in roots:
        obj.parent = empty
        obj.matrix_parent_inverse = empty.matrix_world.inverted()
    return empty


def duplicate_linked(source, name, hide=False):
    obj = source.copy()
    if source.data:
        obj.data = source.data
    obj.animation_data_clear()
    obj.name = name
    bpy.context.scene.collection.objects.link(obj)
    obj.hide_render = hide
    obj.hide_viewport = hide
    for child in source.children:
        child_copy = duplicate_linked(child, f"{name}_{child.name}", hide=hide)
        child_copy.parent = obj
        child_copy.matrix_parent_inverse = obj.matrix_world.inverted()
    return obj


def set_hidden_recursive(obj, hidden):
    obj.hide_render = hidden
    obj.hide_viewport = hidden
    for child in obj.children:
        set_hidden_recursive(child, hidden)


def key_loc_rot(obj, frame, loc, rot_z, scale=None):
    bpy.context.scene.frame_set(frame)
    obj.location = loc
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, rot_z)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)
    obj.keyframe_insert(data_path="location", frame=frame)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_camera(cam, frame, loc, target):
    bpy.context.scene.frame_set(frame)
    cam.location = loc
    look_at(cam, target, 0.0)
    cam.keyframe_insert(data_path="location", frame=frame)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame)


def assign_linear_interpolation():
    for action in bpy.data.actions:
        if not hasattr(action, "fcurves"):
            continue
        for fcurve in action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "LINEAR"


def add_engine_glow(parent, positions, color, energy, prefix):
    scene = bpy.context.scene
    for idx, loc in enumerate(positions):
        light = bpy.data.lights.new(f"{prefix}_{idx}", type="POINT")
        light.color = color
        light.energy = energy
        obj = bpy.data.objects.new(f"{prefix}_{idx}", light)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.parent = parent


def animate_emission(name_part, base, pulse):
    for mat in bpy.data.materials:
        if name_part not in mat.name or not mat.use_nodes:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if not bsdf or "Emission Strength" not in bsdf.inputs:
            continue
        for frame in range(1, N_FRAMES + 1, 4):
            t = frame / FPS
            bsdf.inputs["Emission Strength"].default_value = base + pulse * math.sin(t * 9.5)
            bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=frame)


def setup_space(scene):
    world = bpy.data.worlds.new("space")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs[1].default_value = 0.0
    scene.world = world

    bpy.ops.mesh.primitive_uv_sphere_add(radius=900, segments=64, ring_count=32)
    stars = bpy.context.active_object
    stars.name = "env_star_sphere"
    stars.visible_shadow = False
    mat = bpy.data.materials.new("mat_env_stars")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 360.0
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.62
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.002, 0.002, 0.006, 1)
    ramp.color_ramp.elements[1].position = 0.775
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    emit.inputs["Strength"].default_value = 8.0
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    stars.data.materials.append(mat)

    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=22, location=(-260, -520, 250), segments=32, ring_count=16)
    sun = bpy.context.active_object
    sun.name = "env_sun"
    sun_mat = bpy.data.materials.new("mat_env_sun")
    sun_mat.use_nodes = True
    for node in list(sun_mat.node_tree.nodes):
        sun_mat.node_tree.nodes.remove(node)
    emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
    out = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    emit.inputs["Color"].default_value = (1.0, 0.74, 0.28, 1)
    emit.inputs["Strength"].default_value = 120.0
    sun_mat.node_tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    sun.data.materials.append(sun_mat)

    for name, energy, color, rot in (
        ("key", 5.0, (1.0, 0.9, 0.76), (55, 0, -35)),
        ("rim", 2.0, (0.65, 0.78, 1.0), (88, 0, 145)),
        ("fill", 0.7, (0.62, 0.72, 1.0), (125, 0, 130)),
    ):
        light = bpy.data.lights.new(name, type="SUN")
        light.energy = energy
        light.color = color
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.rotation_euler = tuple(math.radians(v) for v in rot)

    if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_bloom"):
        scene.eevee.use_bloom = True
        scene.eevee.bloom_threshold = 0.55
        scene.eevee.bloom_intensity = 0.8
        scene.eevee.bloom_radius = 6.0


def setup_blocking_render(scene):
    """Workbench solid animatic: fast, readable forms with viewport outlines."""
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    shading = getattr(scene.display, "shading", None)
    if shading:
        for attr, value in (
            ("light", "STUDIO"),
            ("color_type", "MATERIAL"),
            ("background_type", "VIEWPORT"),
            ("background_color", (0.02, 0.025, 0.04)),
            ("show_object_outline", True),
            ("show_cavity", True),
            ("show_shadows", False),
        ):
            if hasattr(shading, attr):
                try:
                    setattr(shading, attr, value)
                except TypeError:
                    pass
    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
        if obj.name.startswith("env_"):
            obj.hide_render = True
            obj.hide_viewport = True


def point_on_path(frame, offset_x=0.0, offset_z=0.0, delay=0, speed=1.0):
    t = (frame - delay - 1) / max(1, N_FRAMES - 1)
    y = -92.0 + 190.0 * t * speed
    return (offset_x, y, 1.7 + offset_z)


def main():
    args = parse_args()
    out_mp4 = args.output
    if out_mp4 is None:
        name = "jb100_ellipso_ventradi_chase_blocking.mp4" \
            if args.mode == "blocking" else "jb100_ellipso_ventradi_chase.mp4"
        out_mp4 = os.path.join(CWD, "out", name)
    elif not os.path.isabs(out_mp4):
        out_mp4 = os.path.join(CWD, out_mp4)
    stem = out_mp4[:-4] if out_mp4.lower().endswith(".mp4") else out_mp4
    frames_dir = stem + "_frames"

    clear_scene()
    scene = bpy.context.scene
    set_engine(scene, args.mode)
    setup_space(scene)
    if args.mode == "blocking":
        setup_blocking_render(scene)

    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = N_FRAMES
    scene.render.resolution_x = args.width or (1280 if args.mode == "blocking" else 960)
    scene.render.resolution_y = args.height or (720 if args.mode == "blocking" else 540)
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass

    jb100 = import_asset(os.path.join(CWD, "assets/ships/jb100.glb"), "hero_jb100")
    jb100.scale = (1.0, 1.0, 1.0)
    key_loc_rot(jb100, 1, (0.0, -10.0, 1.7), math.radians(180))
    key_loc_rot(jb100, 16, (0.0, 14.0, 1.8), math.radians(180))
    key_loc_rot(jb100, 36, (0.0, 55.0, 2.1), math.radians(180))
    key_loc_rot(jb100, 70, (1.2, 130.0, 2.5), math.radians(180))
    key_loc_rot(jb100, N_FRAMES, (2.2, 520.0, 3.2), math.radians(180))
    add_engine_glow(jb100, [(-0.95, 3.01, 1.1), (0.95, 3.01, 1.1)],
                    (1.0, 0.38, 0.05), 450, "jb100_engine_glow")
    animate_emission("jb100_lamp", 8.0, 1.4)

    flyer_source = import_asset(
        os.path.join(CWD, "assets/ships/ellipso_flyer_mk1.glb"),
        "ellipso_source")
    set_hidden_recursive(flyer_source, True)

    chase_offsets = [
        (0.0, -36.0, 0.00, 64),
        (-8.0, -18.0, 1.8, 104),
        (8.0, -22.0, -1.4, 108),
    ]
    formation = [
        (-34.0, -33.5, 16.5), (-22.5, -26.0, 10.5), (-10.5, -31.0, 4.4),
        (-2.0, -24.5, 0.3), (9.5, -29.0, 4.0), (23.0, -25.5, 10.8),
        (35.5, -32.0, 16.0), (-36.0, -49.5, -10.4), (-23.0, -42.0, -7.0),
        (-8.5, -47.5, -2.6), (7.5, -40.5, -2.2), (22.5, -46.5, -7.4),
        (35.0, -43.0, -10.0),
    ]
    chase_offsets.extend((x, y, z, 176) for x, y, z in formation)

    for idx, (x, y_offset, z, start) in enumerate(chase_offsets):
        flyer = duplicate_linked(flyer_source, f"ellipso_flyer_{idx + 1:02d}")
        flyer.scale = (FLYER_SCALE, FLYER_SCALE, FLYER_SCALE)
        start_loc = (x, CHASE_START_Y + y_offset, 1.8 + z)
        mid_frame = min(N_FRAMES, start + 36)
        mid_loc = (x, CHASE_START_Y + y_offset + CHASE_SPEED * (mid_frame - start),
                   1.8 + z)
        end_loc = (x, CHASE_START_Y + y_offset + CHASE_SPEED * (N_FRAMES - start),
                   1.8 + z)
        key_loc_rot(flyer, start, start_loc, math.radians(180))
        key_loc_rot(flyer, mid_frame, mid_loc, math.radians(180))
        key_loc_rot(flyer, N_FRAMES, end_loc, math.radians(180))

    cruiser = import_asset(
        os.path.join(CWD, "assets/ships/ventradi_cruiser.glb"),
        "ventradi_cruiser_flyover")
    key_loc_rot(cruiser, 228, (-1.5, -220.0, 12.0), math.radians(180),
                scale=(CRUISER_SCALE, CRUISER_SCALE, CRUISER_SCALE))
    key_loc_rot(cruiser, 288, (-1.2, -7.5, 10.0), math.radians(180),
                scale=(CRUISER_SCALE, CRUISER_SCALE, CRUISER_SCALE))
    key_loc_rot(cruiser, N_FRAMES, (-1.2, 250.0, 11.0), math.radians(180),
                scale=(CRUISER_SCALE, CRUISER_SCALE, CRUISER_SCALE))
    add_engine_glow(cruiser, [(-0.7, 2.9, 0.8), (0.7, 2.9, 0.8)],
                    (1.0, 0.28, 0.04), 900, "cruiser_engine_glow")

    cam_data = bpy.data.cameras.new("chase_cam")
    cam_data.lens = 32
    cam = bpy.data.objects.new("chase_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    key_camera(cam, 1, (3.2, -8.5, 4.1), (0.0, 58.0, 8.2))
    key_camera(cam, 120, (3.2, -8.5, 4.1), (0.0, 58.0, 8.2))
    key_camera(cam, N_FRAMES, (3.2, -8.5, -7.5), (1.9, 430.0, 3.1))

    assign_linear_interpolation()

    configure_render_device_from_env(scene)
    os.makedirs(frames_dir, exist_ok=True)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(frames_dir, "frame_")
    print(f"[chase] rendering {N_FRAMES} {args.mode} frames to {frames_dir}")
    bpy.ops.render.render(animation=True)

    ffmpeg = find_ffmpeg()
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    print(f"[chase] encoding with {ffmpeg}")
    subprocess.run([
        ffmpeg, "-y",
        "-framerate", str(FPS),
        "-start_number", "1",
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19",
        out_mp4,
    ], check=True)
    shutil.rmtree(frames_dir)
    print("[chase] wrote", out_mp4)


if __name__ == "__main__":
    main()
