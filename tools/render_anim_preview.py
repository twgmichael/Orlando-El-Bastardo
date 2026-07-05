#!/usr/bin/env python3
"""
render_anim_preview.py — Headless Blender animated preview of the bar scene.

End-to-end motion render test: imports the placeholder GLB, gives the hero
armature object straight-line location keyframes (entry mark → stool approach
→ up onto the seat), renders a PNG sequence through one grammar camera, and
encodes it to H.264 MP4. This Blender 5.1 build ships no FFMPEG output
format, so encoding uses the ffmpeg binary bundled with the venv's
imageio-ffmpeg package (frames are deleted after a successful encode).

No rig posing and no NLA actions are used — the placeholders have no usable
rigging, so this is plain object-level translation only. All imported
animation data is cleared first so the render is deterministic.

Run from repo root:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/render_anim_preview.py -- \
    --glb assets/placeholders/bar_scene_placeholders.glb \
    --camera cam_establishing_wide \
    --output renders/previews/anim_hero_walk_sit.mp4
"""

import sys
import os
import glob as globmod
import argparse
import math
import shutil
import subprocess

import bpy

VENV_FFMPEG_GLOB = ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"

HERO = "char_hero_v1"

# Motion plan (24 fps). Waypoints from docs/BAR-SCENE.md canonical layout:
# hero_entry_A mark → midpoint (turn to face the bar, pause) → point in
# front of prop_stool_A → onto the seat.
# Seat top z: stool centre 0.38 + (unit cylinder depth 1.0 * scale_z 0.75)/2
# = 0.755; hero body bottom sits 0.01 above its armature origin, so the
# armature lands at z = 0.745 when seated.
# Heading is degrees around Z; 0 = facing the bar (+Y), applied on top of
# whatever static rotation the glTF import left on the armature.
FPS = 24
WALK_HEADING = math.degrees(math.atan2(0.4, 2.5)) - 90.0  # facing travel dir
WAYPOINTS = [
    # (frame, location, heading_deg)
    (1,   (-3.5, -3.0, 0.0),   WALK_HEADING),  # hero_entry_A, facing travel
    (48,  (-1.0, -2.6, 0.0),   WALK_HEADING),  # halfway point
    (60,  (-1.0, -2.6, 0.0),   0.0),           # turn to face the bar
    (78,  (-1.0, -2.6, 0.0),   0.0),           # pause, taking it in
    (90,  None,                WALK_HEADING),  # turn back to travel dir mid-stride
    (120, (1.5, -2.2, 0.0),    WALK_HEADING),  # arrive in front of the stool
    (126, (1.5, -2.2, 0.0),    0.0),           # face the stool/bar
    (138, (1.5, -1.2, 0.745),  0.0),           # settle onto prop_stool_A
    (144, (1.5, -1.2, 0.745),  0.0),           # hold
]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="render_anim_preview")
    p.add_argument("--glb", required=True)
    p.add_argument("--camera", default="cam_establishing_wide")
    p.add_argument("--output", default="renders/previews/anim_hero_walk_sit.mp4")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--height", type=int, default=540)
    return p.parse_args(argv)


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_engine(scene):
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = candidate
            return candidate
        except TypeError:
            continue
    raise RuntimeError("No usable render engine found")


def setup_lighting():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.12, 0.12, 0.14, 1.0)  # dim night-ish
        bg.inputs[1].default_value = 0.6

    sun_data = bpy.data.lights.new("preview_sun", type='SUN')
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("preview_sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))
    bpy.context.scene.collection.objects.link(sun)

    fill_data = bpy.data.lights.new("preview_fill", type='AREA')
    fill_data.energy = 250.0
    fill_data.size = 4.0
    fill = bpy.data.objects.new("preview_fill", fill_data)
    fill.location = (0.0, -2.0, 3.2)
    fill.rotation_euler = (math.radians(-20), 0.0, 0.0)
    bpy.context.scene.collection.objects.link(fill)


def clear_imported_animation():
    """Strip all animation that came in with the GLB so only our keyframes
    drive the scene."""
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = globmod.glob(os.path.join(os.getcwd(), VENV_FFMPEG_GLOB))
    if hits:
        return hits[0]
    print("[render_anim_preview] ERROR: no ffmpeg on PATH and none bundled in "
          ".venv (pip install imageio-ffmpeg)")
    sys.exit(1)


def keyframe_hero():
    hero = bpy.data.objects.get(HERO)
    if hero is None:
        names = sorted(o.name for o in bpy.data.objects)
        print(f"[render_anim_preview] ERROR: {HERO} not found. Objects: {names}")
        sys.exit(1)

    hero.rotation_mode = 'XYZ'
    base_rot = tuple(hero.rotation_euler)

    for frame, loc, heading in WAYPOINTS:
        if loc is not None:
            hero.location = loc
            hero.keyframe_insert("location", frame=frame)
        hero.rotation_euler = (base_rot[0], base_rot[1],
                               base_rot[2] + math.radians(heading))
        hero.keyframe_insert("rotation_euler", frame=frame)

    return WAYPOINTS[0][0], WAYPOINTS[-1][0]


def main():
    args = parse_args()

    glb = args.glb if os.path.isabs(args.glb) else os.path.join(os.getcwd(), args.glb)
    if not os.path.isfile(glb):
        print(f"[render_anim_preview] ERROR: GLB not found: {glb}")
        sys.exit(1)

    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.getcwd(), out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=glb)
    clear_imported_animation()
    setup_lighting()

    scene = bpy.context.scene
    engine = set_engine(scene)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.fps = FPS

    frame_start, frame_end = keyframe_hero()
    scene.frame_start = frame_start
    scene.frame_end = frame_end

    cam = bpy.data.objects.get(args.camera)
    if cam is None or cam.type != 'CAMERA':
        print(f"[render_anim_preview] ERROR: camera object not found: {args.camera}")
        sys.exit(1)
    scene.camera = cam

    scene.render.image_settings.file_format = 'PNG'

    stem = out_path[:-4] if out_path.lower().endswith(".mp4") else out_path
    frames_dir = stem + "_frames"
    os.makedirs(frames_dir, exist_ok=True)
    scene.render.filepath = os.path.join(frames_dir, "frame_")

    print(f"[render_anim_preview] Rendering {frame_end - frame_start + 1} frames "
          f"({engine}, {args.width}x{args.height}@{FPS}fps) via {args.camera}")
    bpy.ops.render.render(animation=True)

    ffmpeg = find_ffmpeg()
    print(f"[render_anim_preview] Encoding with {ffmpeg}")
    subprocess.run([
        ffmpeg, "-y",
        "-framerate", str(FPS),
        "-start_number", str(frame_start),
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "23",
        out_path,
    ], check=True)
    shutil.rmtree(frames_dir)

    size_kb = os.path.getsize(out_path) // 1024
    print(f"[render_anim_preview] Done → {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
