#!/usr/bin/env python3
"""Render four canopy-hidden cockpit action closeups around the JB100 v37."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
OUT = os.path.join(ROOT, "review-stills", "jb100_v37_action_angles")
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

world = bpy.data.worlds.get("jb100_action_angles_world") or bpy.data.worlds.new(
    "jb100_action_angles_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.003, 0.005, 0.010, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.07
scene.world = world

canopy = bpy.data.objects.get("jb100_canopy")
if canopy is not None:
    canopy.hide_viewport = True
    canopy.hide_render = True
    canopy.hide_set(True)


def add_area(name, location, energy, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, 0.85)) - obj.location).to_track_quat(
        '-Z', 'Y').to_euler()


# Broad studio lighting keeps each side readable without changing the light rig
# between views, so color and material response remain directly comparable.
add_area("angles_key", (-4.5, -4.5, 6.5), 620, 3.5, (1.0, 0.68, 0.46))
add_area("angles_fill", (4.5, -2.0, 4.5), 390, 3.0, (0.34, 0.54, 1.0))
add_area("angles_aft", (0.0, 5.0, 5.0), 470, 3.0, (1.0, 0.16, 0.045))

camera_data = bpy.data.cameras.new("jb100_action_angles_camera")
camera_data.type = 'PERSP'
camera_data.lens = 70
camera_data.sensor_width = 36
camera = bpy.data.objects.new("jb100_action_angles_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera

target = Vector((0.0, 0.0, 0.94))

# Nose is -Y. Each camera favors its named side while keeping a diagonal
# component so none of the results collapse into a straight elevation.
views = {
    "front_action": ((2.55, -4.20, 3.20), -4.0),
    "back_action": ((-2.55, 4.20, 3.20), 4.0),
    "left_action": ((-4.20, -2.55, 3.20), -3.0),
    "right_action": ((4.20, 2.55, 3.20), 3.0),
}

for name, (location, roll) in views.items():
    camera.location = location
    camera.rotation_euler = (target - camera.location).to_track_quat(
        '-Z', 'Y').to_euler()
    camera.rotation_euler.rotate_axis('Z', math.radians(roll))
    scene.render.filepath = os.path.join(OUT, f"jb100_v37_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[jb100 action angles] wrote {scene.render.filepath}")
