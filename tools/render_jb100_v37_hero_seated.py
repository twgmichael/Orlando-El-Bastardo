#!/usr/bin/env python3
"""Render the Orlando 1999 hero stand-in seated in the JB100 v37 cockpit."""

import math
import os

import bpy
from mathutils import Vector


ROOT = os.getcwd()
OUT = os.path.join(ROOT, "review-stills", "jb100_v37_hero_seated")
HERO_ASSET = os.path.join(
    ROOT, "assets", "concepts", "orlando_1999", "hero-stand-in_v0.0.1.glb")
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

# Import only the hero hierarchy and put its validated seated loop on frame 20.
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=HERO_ASSET)
imported = set(bpy.data.objects) - before
hero = bpy.data.objects["char_orlando_1999_A"]


def under(obj, root):
    while obj:
        if obj == root:
            return True
        obj = obj.parent
    return False


for obj in list(imported):
    if obj.name in bpy.data.objects and not under(obj, hero):
        bpy.data.objects.remove(obj, do_unlink=True)

hero.animation_data_create()
hero.animation_data.action = bpy.data.actions["idle_seated_relaxed"]
hero.location = (0.0, 0.24, 0.22)
hero.rotation_mode = 'XYZ'
# This versioned GLB imports already facing the JB100's local -Y nose.
hero.rotation_euler = (0.0, 0.0, 0.0)
hero.scale = (0.94, 0.94, 0.94)
scene.frame_set(20)

# Restore the smoked half-sphere for an honest pilot-visibility check.
canopy = bpy.data.objects["jb100_canopy"]
canopy.hide_viewport = False
canopy.hide_render = False
canopy.hide_set(False)
glass = bpy.data.materials.get("mat_jb100_canopy")
if glass and glass.use_nodes:
    bsdf = glass.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.025, 0.04, 0.065, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.055
        bsdf.inputs["Alpha"].default_value = 0.20
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.28
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.45
    if hasattr(glass, "surface_render_method"):
        glass.surface_render_method = 'DITHERED'
    if hasattr(glass, "use_transparency_overlap"):
        glass.use_transparency_overlap = False

world = bpy.data.worlds.get("jb100_hero_seated_world") or bpy.data.worlds.new(
    "jb100_hero_seated_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.002, 0.004, 0.009, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.065
scene.world = world


def add_area(name, location, energy, size, color, target=(0, 0, 1.05)):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'RECTANGLE'
    data.size = size
    data.size_y = size * 0.34
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat(
        '-Z', 'Y').to_euler()


add_area("hero_key", (-3.8, -4.5, 6.2), 720, 3.2, (1.0, 0.70, 0.48))
add_area("hero_face_fill", (2.8, -3.8, 3.5), 520, 2.2, (0.42, 0.62, 1.0))
add_area("hero_aft_rim", (0.0, 5.2, 4.5), 650, 2.7, (1.0, 0.15, 0.04))
add_area("hero_canopy_strip", (-1.5, 0.8, 6.6), 780, 1.1,
         (0.64, 0.80, 1.0), target=(0, 0, 1.65))

# Low-power instrument bounce keeps the face readable through smoked glass.
face_data = bpy.data.lights.new("hero_instrument_bounce", 'POINT')
face_data.energy = 55
face_data.color = (0.55, 0.72, 1.0)
face_light = bpy.data.objects.new("hero_instrument_bounce", face_data)
scene.collection.objects.link(face_light)
face_light.location = (0.0, -0.58, 1.28)

camera_data = bpy.data.cameras.new("jb100_hero_seated_camera")
camera_data.type = 'PERSP'
camera_data.lens = 68
camera_data.sensor_width = 36
camera = bpy.data.objects.new("jb100_hero_seated_camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
target = Vector((0.0, 0.12, 1.08))
views = {
    "front_action": ((2.75, -4.35, 2.95), -3.0),
    "back_action": ((-2.75, 4.35, 3.10), 3.0),
    "left_action": ((-4.35, -2.75, 3.00), -3.0),
    "right_action": ((4.35, 2.75, 3.00), 3.0),
}

for name, (location, roll) in views.items():
    camera.location = location
    camera.rotation_euler = (target - camera.location).to_track_quat(
        '-Z', 'Y').to_euler()
    camera.rotation_euler.rotate_axis('Z', math.radians(roll))
    scene.render.filepath = os.path.join(
        OUT, f"jb100_v37_hero_bubble_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[jb100 hero seated] wrote {scene.render.filepath}")
