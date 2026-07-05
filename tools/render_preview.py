#!/usr/bin/env python3
"""
render_preview.py — Headless Blender still-frame previews of a scene GLB.

Imports the GLB, adds simple preview lighting (sun + world), and renders one
PNG per requested camera-grammar camera.

Run from repo root:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/render_preview.py -- \
    --glb assets/placeholders/bar_scene_placeholders.glb \
    --cameras all --output-dir renders/previews
"""

import sys
import os
import argparse
import math

import bpy

KNOWN_CAMERAS = [
    "cam_establishing_wide",
    "cam_two_shot_bar",
    "cam_close_hero",
    "cam_close_bartender",
]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="render_preview")
    p.add_argument("--glb", required=True)
    p.add_argument("--cameras", default="all",
                   help='"all" or comma-separated camera object names')
    p.add_argument("--output-dir", default="renders/previews")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
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


def main():
    args = parse_args()

    glb = args.glb if os.path.isabs(args.glb) else os.path.join(os.getcwd(), args.glb)
    if not os.path.isfile(glb):
        print(f"[render_preview] ERROR: GLB not found: {glb}")
        sys.exit(1)

    out_dir = args.output_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(os.getcwd(), out_dir)
    os.makedirs(out_dir, exist_ok=True)

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=glb)
    setup_lighting()

    scene = bpy.context.scene
    engine = set_engine(scene)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.image_settings.file_format = 'PNG'
    scene.frame_set(1)

    wanted = KNOWN_CAMERAS if args.cameras == "all" else [
        c.strip() for c in args.cameras.split(",") if c.strip()
    ]

    rendered = []
    for cam_name in wanted:
        cam = bpy.data.objects.get(cam_name)
        if cam is None or cam.type != 'CAMERA':
            print(f"[render_preview] ERROR: camera object not found: {cam_name}")
            sys.exit(1)
        scene.camera = cam
        out_path = os.path.join(out_dir, f"preview_{cam_name}.png")
        scene.render.filepath = out_path
        print(f"[render_preview] Rendering {cam_name} ({engine}) → {out_path}")
        bpy.ops.render.render(write_still=True)
        rendered.append(out_path)

    print(f"[render_preview] Done — {len(rendered)} still(s):")
    for pth in rendered:
        print(f"  {pth}")


if __name__ == "__main__":
    main()
