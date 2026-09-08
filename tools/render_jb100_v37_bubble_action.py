#!/usr/bin/env python3
"""Render a JB100 v37 cockpit action angle with its transparent bubble."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
OUT = os.path.join(ROOT, "review-stills", "jb100_v37_bubble_action")
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

world = bpy.data.worlds.get("jb100_bubble_action_world") or bpy.data.worlds.new(
    "jb100_bubble_action_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.002, 0.004, 0.009, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.06
scene.world = world

# Restore the canopy that is deliberately hidden in the v37 working file.
canopy = bpy.data.objects["jb100_canopy"]
canopy.hide_viewport = False
canopy.hide_render = False
canopy.hide_set(False)

# Make the working material explicitly transmissive for this beauty render.
glass = bpy.data.materials.get("mat_jb100_canopy")
if glass and glass.use_nodes:
    bsdf = glass.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.025, 0.04, 0.065, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.06
        bsdf.inputs["Alpha"].default_value = 0.24
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.32
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


add_area("bubble_key", (-4.5, -4.0, 6.5), 680, 3.5, (1.0, 0.70, 0.48))
add_area("bubble_fill", (4.8, -1.0, 4.3), 430, 3.0, (0.34, 0.56, 1.0))
add_area("bubble_rim", (0.0, 5.5, 4.7), 820, 2.5, (1.0, 0.13, 0.035))
# A long, soft strip reflection makes the dome curvature legible.
add_area("bubble_glass_strip", (-1.8, 1.2, 6.8), 900, 1.2,
         (0.62, 0.78, 1.0), target=(0, 0, 1.65))

camera_data = bpy.data.cameras.new("jb100_bubble_action_camera")
camera_data.type = 'PERSP'
camera_data.lens = 66
camera_data.sensor_width = 36
camera = bpy.data.objects.new("jb100_bubble_action_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera.location = (3.85, 4.10, 3.15)
target = Vector((0.0, -0.02, 1.04))
camera.rotation_euler = (target - camera.location).to_track_quat(
    '-Z', 'Y').to_euler()
camera.rotation_euler.rotate_axis('Z', math.radians(-4.0))

scene.render.filepath = os.path.join(
    OUT, "jb100_v37_transparent_bubble_action.png")
bpy.ops.render.render(write_still=True)
print(f"[jb100 bubble action] wrote {scene.render.filepath}")

