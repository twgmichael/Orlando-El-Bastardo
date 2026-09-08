#!/usr/bin/env python3
"""Render the canopy-hidden JB100 v37 from six directions plus action closeup."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
OUT = os.path.join(ROOT, "review-stills", "jb100_v37_full_review")
os.makedirs(OUT, exist_ok=True)

scene = bpy.context.scene
for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES'):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
scene.render.resolution_x = 1280
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.film_transparent = False
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass

world = bpy.data.worlds.get("jb100_v37_review_world") or bpy.data.worlds.new(
    "jb100_v37_review_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.004, 0.006, 0.012, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.08
scene.world = world

# Work-in-progress presentation state: keep the bubble out of the way.
canopy = bpy.data.objects.get("jb100_canopy")
if canopy is not None:
    canopy.hide_viewport = True
    canopy.hide_render = True
    canopy.hide_set(True)


def area_light(name, location, energy, size, color, target=(0, 0, 0.7)):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat(
        '-Z', 'Y').to_euler()


area_light("review_key", (-5.0, -5.5, 7.5), 760, 4.0, (1.0, 0.72, 0.52))
area_light("review_fill", (5.5, -2.0, 4.0), 480, 4.0, (0.38, 0.56, 1.0))
area_light("review_rim", (1.0, 6.0, 5.5), 620, 3.0, (1.0, 0.16, 0.045))
area_light("review_belly", (0.0, 0.0, -6.0), 520, 4.0, (0.30, 0.42, 1.0),
           target=(0, 0, 0))

camera_data = bpy.data.cameras.new("jb100_v37_review_camera")
camera = bpy.data.objects.new("jb100_v37_review_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera


def point_camera(location, target, roll=0.0):
    camera.location = location
    camera.rotation_euler = (Vector(target) - Vector(location)).to_track_quat(
        '-Z', 'Y').to_euler()
    if roll:
        camera.rotation_euler.rotate_axis('Z', math.radians(roll))


# Nose is -Y. Orthographic framing is consistent so silhouette and scale can
# be compared directly across all six directional views.
ortho_views = {
    "top": ((0.0, 0.0, 12.0), (0.0, 0.0, 0.75), 0.0),
    "bottom": ((0.0, 0.0, -12.0), (0.0, 0.0, 0.45), 180.0),
    "front": ((0.0, -12.0, 1.25), (0.0, 0.0, 0.75), 0.0),
    "back": ((0.0, 12.0, 1.25), (0.0, 0.0, 0.75), 0.0),
    "left": ((-12.0, 0.0, 1.35), (0.0, 0.0, 0.75), 0.0),
    "right": ((12.0, 0.0, 1.35), (0.0, 0.0, 0.75), 0.0),
}

camera_data.type = 'ORTHO'
for name, (location, target, roll) in ortho_views.items():
    camera_data.ortho_scale = 7.8 if name in {"top", "bottom"} else 5.5
    point_camera(location, target, roll)
    scene.render.filepath = os.path.join(OUT, f"jb100_v37_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[jb100 v37 review] wrote {scene.render.filepath}")

# Tight aft-quarter cockpit action view. This side of the craft shows the live
# display faces, chair, sticks, throttle, and both engine pods in one frame.
camera_data.type = 'PERSP'
camera_data.lens = 64
point_camera((3.65, 3.65, 3.25), (0.0, -0.02, 0.92), roll=-5.0)
scene.render.filepath = os.path.join(OUT, "jb100_v37_action_closeup.png")
bpy.ops.render.render(write_still=True)
print(f"[jb100 v37 review] wrote {scene.render.filepath}")
