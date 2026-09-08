#!/usr/bin/env python3
"""Render close working views of the canopy-hidden JB100 v37 cockpit."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
OUT = os.environ.get(
    "JB100_PREVIEW_OUT",
    os.path.join(ROOT, "review-stills", "jb100_cockpit_v37"),
)
os.makedirs(OUT, exist_ok=True)

scene = bpy.context.scene
for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES'):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
scene.render.resolution_x = 960
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_percentage = 100
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass

world = bpy.data.worlds.get("jb100_cockpit_preview_world") or bpy.data.worlds.new(
    "jb100_cockpit_preview_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.006, 0.008, 0.012, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.08
scene.world = world

# The v37 working source already stores the canopy hidden; enforce that state
# here so the preview remains deterministic even after an artist toggles it.
canopy = bpy.data.objects.get("jb100_canopy")
if canopy is not None:
    canopy.hide_render = True
    canopy.hide_set(True)
if os.environ.get("JB100_HIDE_BOWL") == "1":
    bpy.data.objects["jb100_bowl"].hide_render = True


def add_area(name, location, energy, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, 0.75)) - obj.location).to_track_quat(
        '-Z', 'Y').to_euler()
    return obj


add_area("cockpit_key", (-2.8, -2.6, 5.0), 480, 3.0, (1.0, 0.73, 0.55))
add_area("cockpit_fill", (3.0, -0.8, 3.0), 280, 2.5, (0.38, 0.58, 1.0))
add_area("cockpit_rim", (0.0, 2.8, 3.5), 340, 2.0, (1.0, 0.18, 0.06))

camera_data = bpy.data.cameras.new("jb100_cockpit_camera")
camera_data.lens = 58
camera_data.sensor_width = 36
camera = bpy.data.objects.new("jb100_cockpit_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera

views = {
    "overview": ((2.55, 2.55, 3.15), (0.0, -0.08, 0.82), 62),
    "top": ((0.0, 0.02, 4.35), (0.0, 0.02, 0.78), 70),
    "port": ((-3.15, -1.30, 1.85), (0.0, 0.0, 0.88), 68),
    "pilot_view": ((0.0, 0.20, 1.62), (0.0, -0.78, 1.10), 54),
}

only_view = os.environ.get("JB100_PREVIEW_VIEW")
for name, (location, target, lens) in views.items():
    if only_view and name != only_view:
        continue
    camera.location = location
    camera.rotation_euler = (Vector(target) - Vector(location)).to_track_quat(
        '-Z', 'Y').to_euler()
    camera_data.lens = lens
    scene.render.filepath = os.path.join(OUT, f"jb100_cockpit_v37_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[jb100 cockpit preview] wrote {scene.render.filepath}")
