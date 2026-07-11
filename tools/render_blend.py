#!/usr/bin/env python3
"""
render_blend.py — Headless Blender review render of an exported .blend.

Opens a pipeline-exported .blend (which carries no lights by design), adds
the standard preview lighting, renders the scene's full frame range as PNGs
(timeline-marker camera binding drives camera switching), and encodes an
H.264 MP4 via the imageio-ffmpeg binary in the venv (this Blender build has
no FFMPEG output format).

Run from repo root:
  blender --background --factory-startup \
    --python tools/render_blend.py -- \
    --blend out/blender/sc_bar_intro_001.blend \
    --output renders/reviews/sc_bar_intro_001.mp4
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


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="render_blend")
    p.add_argument("--blend", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--height", type=int, default=540)
    return p.parse_args(argv)


def setup_lighting():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.12, 0.12, 0.14, 1.0)  # dim night-ish
        bg.inputs[1].default_value = 0.6

    sun_data = bpy.data.lights.new("review_sun", type='SUN')
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("review_sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))
    bpy.context.scene.collection.objects.link(sun)

    fill_data = bpy.data.lights.new("review_fill", type='AREA')
    fill_data.energy = 250.0
    fill_data.size = 4.0
    fill = bpy.data.objects.new("review_fill", fill_data)
    fill.location = (0.0, -2.0, 3.2)
    fill.rotation_euler = (math.radians(-20), 0.0, 0.0)
    bpy.context.scene.collection.objects.link(fill)

    # Overhead key — enclosed sets (real walls) block the sun; without this
    # interiors review too dark (added 2026-07-06 with the sci-fi set).
    key_data = bpy.data.lights.new("review_key", type='AREA')
    key_data.energy = 700.0
    key_data.size = 6.0
    key = bpy.data.objects.new("review_key", key_data)
    key.location = (0.0, 0.5, 4.1)
    bpy.context.scene.collection.objects.link(key)

    bar_data = bpy.data.lights.new("review_bar", type='POINT')
    bar_data.energy = 200.0
    bar = bpy.data.objects.new("review_bar", bar_data)
    bar.location = (0.0, 2.6, 2.8)
    bpy.context.scene.collection.objects.link(bar)


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = globmod.glob(os.path.join(os.getcwd(), VENV_FFMPEG_GLOB))
    if hits:
        return hits[0]
    print("[render_blend] ERROR: no ffmpeg on PATH and none bundled in .venv")
    sys.exit(1)


def main():
    args = parse_args()

    blend = args.blend if os.path.isabs(args.blend) else os.path.join(os.getcwd(), args.blend)
    if not os.path.isfile(blend):
        print(f"[render_blend] ERROR: blend not found: {blend}")
        sys.exit(1)
    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.getcwd(), out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=blend)
    scene = bpy.context.scene
    setup_lighting()

    # First marker's camera is the starting camera; markers switch the rest.
    markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
    for m in markers:
        if m.camera:
            scene.camera = m.camera
            break
    if scene.camera is None:
        print("[render_blend] ERROR: no camera bound to any timeline marker")
        sys.exit(1)

    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = candidate
            break
        except TypeError:
            continue
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.image_settings.file_format = 'PNG'

    stem = out_path[:-4] if out_path.lower().endswith(".mp4") else out_path
    frames_dir = stem + "_frames"
    os.makedirs(frames_dir, exist_ok=True)
    scene.render.filepath = os.path.join(frames_dir, "frame_")

    fps = scene.render.fps
    total = scene.frame_end - scene.frame_start + 1
    print(f"[render_blend] Rendering {total} frames ({scene.render.engine}, "
          f"{args.width}x{args.height}@{fps}fps), frames "
          f"{scene.frame_start}-{scene.frame_end}")
    bpy.ops.render.render(animation=True)

    ffmpeg = find_ffmpeg()
    subprocess.run([
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-start_number", str(scene.frame_start),
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "23",
        out_path,
    ], check=True)
    shutil.rmtree(frames_dir)

    size_kb = os.path.getsize(out_path) // 1024
    print(f"[render_blend] Done → {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
