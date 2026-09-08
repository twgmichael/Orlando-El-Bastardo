#!/usr/bin/env python3
"""Render four JB100 v37 cockpit closeups through the transparent bubble."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
VERSION_LABEL = os.environ.get("JB100_RENDER_VERSION", "v37")
OUT = os.environ.get(
    "JB100_RENDER_OUT",
    os.path.join(ROOT, "review-stills", "jb100_v37_bubble_action_angles"),
)
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

world = bpy.data.worlds.get("jb100_bubble_angles_world") or bpy.data.worlds.new(
    "jb100_bubble_angles_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.002, 0.004, 0.009, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.06
scene.world = world

# Restore and tune the smoked canopy without changing the saved working asset.
canopy = bpy.data.objects["jb100_canopy"]
canopy.hide_viewport = False
canopy.hide_render = False
canopy.hide_set(False)
glass = bpy.data.materials.get("mat_jb100_canopy")
if glass and glass.use_nodes:
    bsdf = glass.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.025, 0.04, 0.065, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.06
        bsdf.inputs["Alpha"].default_value = 0.22
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.30
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.45
    if hasattr(glass, "surface_render_method"):
        glass.surface_render_method = 'DITHERED'
    if hasattr(glass, "use_transparency_overlap"):
        glass.use_transparency_overlap = False


def add_area(name, location, energy, size, color, target=(0, 0, 1.0)):
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


add_area("bubble_angles_key", (-4.5, -4.0, 6.5), 680, 3.5,
         (1.0, 0.70, 0.48))
add_area("bubble_angles_fill", (4.8, -1.0, 4.3), 430, 3.0,
         (0.34, 0.56, 1.0))
add_area("bubble_angles_aft", (0.0, 5.5, 4.7), 720, 2.5,
         (1.0, 0.13, 0.035))
add_area("bubble_angles_strip", (-1.8, 1.2, 6.8), 860, 1.2,
         (0.62, 0.78, 1.0), target=(0, 0, 1.65))

camera_data = bpy.data.cameras.new("jb100_bubble_angles_camera")
camera_data.type = 'PERSP'
camera_data.lens = 70
camera_data.sensor_width = 36
camera = bpy.data.objects.new("jb100_bubble_angles_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera

target = Vector((0.0, 0.0, 1.02))
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
    scene.render.filepath = os.path.join(
        OUT, f"jb100_{VERSION_LABEL}_bubble_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[jb100 bubble angles] wrote {scene.render.filepath}")
