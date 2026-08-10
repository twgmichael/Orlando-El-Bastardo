#!/usr/bin/env python3
"""Recreate the approved 1990s teaser hyperspace-entry shot with Ellipso Flyer.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_ellipso_hyperspace_reference_shot.py

Optional single-frame validation:
  ... -- --test-frame=13
"""
import glob
import math
import os
import random
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector

FPS = 30
END = 28
ROOT = os.getcwd()
ACTION_ANGLE = "--action-angle" in sys.argv
BUILD_NAME = ("ellipso_hyperspace_action_angle" if ACTION_ANGLE else
              "ellipso_hyperspace_reference_recreation")
OUT = os.path.join(ROOT, "out", BUILD_NAME)
FRAMES = os.path.join(OUT, "frames")
SHIP_PATH = os.path.join(ROOT, "assets", "ships", "ellipso_flyer_mk1.glb")
random.seed(1995)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def empty(name, parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def surface_mat(name, color, emission=0.0, roughness=.45):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Emission Color"].default_value = color
    bsdf.inputs["Emission Strength"].default_value = emission
    return m


def noisy_volume(name, color, emission_color, density, emission, scale):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = color
    vol.inputs["Anisotropy"].default_value = .18
    vol.inputs["Emission Color"].default_value = emission_color
    vol.inputs["Emission Strength"].default_value = emission
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = .72
    noise.inputs["W"].default_value = random.random() * 10
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mult = nt.nodes.new("ShaderNodeMath")
    mult.operation = "MULTIPLY"
    mult.inputs[1].default_value = density
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mult.inputs[0])
    nt.links.new(mult.outputs[0], vol.inputs["Density"])
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def key(obj, path, values, interpolation="BEZIER"):
    for frame, value in values:
        setattr(obj, path, value)
        obj.keyframe_insert(path, frame=frame)
    action = getattr(getattr(obj, "animation_data", None), "action", None)
    for fc in getattr(action, "fcurves", []):
        for kp in fc.keyframe_points:
            kp.interpolation = interpolation


def add_cloud_piece(name, parent, material, location, scale, seed):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1,
                                         location=location)
    ob = bpy.context.object
    ob.name = name
    ob.parent = parent
    ob.scale = scale
    ob.data.materials.append(material)
    tex = bpy.data.textures.new(name + "_boundary_noise", type="CLOUDS")
    tex.noise_scale = .38 + (seed % 7) * .025
    tex.noise_depth = 2
    mod = ob.modifiers.new("TURBULENT_BOUNDARY", "DISPLACE")
    mod.texture = tex
    mod.strength = .32
    return ob


clear_scene()
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = END
scene.render.fps = FPS
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 960
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.filepath = os.path.join(FRAMES, "frame_")
scene.render.film_transparent = False
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -.15

world = bpy.data.worlds.new("REFERENCE_DEEP_SPACE")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (.00008, .0001, .0002, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = .006
scene.world = world

shot_root = empty("HYPERSPACE_EVENT_ROOT")
shot_root["canonical_id"] = "fx_hyperspace_effect_A"
shot_root["display_name"] = "Hyperspace Effect"
shot_root["asset_status"] = "hero_locked"
shot_root["asset_version"] = "1.0.0"
shot_root["asset_kind"] = "effect"
shot_root["reference"] = "Scene Six NTSC - escape.mp4"
shot_root["duration_frames"] = END
shot_root["travel_axis"] = "world -Y away from aft camera"

# The production Ellipso Mark 1 points nose -Y, placing its aft toward camera +Y.
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=SHIP_PATH)
ship_objects = list(set(bpy.data.objects) - before)
ship_root = empty("ELLIPSO_FLYER_HERO", shot_root)
for ob in ship_objects:
    if ob.parent is None:
        ob.parent = ship_root
# Correct hero roll: the frozen asset's authored top must face the elevated
# action camera rather than presenting the craft upside down.
ship_root.rotation_euler = (0, math.pi, 0)
ship_root.location = (0, 0, 2.0)

# Ship and attached effect accelerate away together. This perspective motion is
# the principal scale cue in the approved shot; there is no artificial scaling.
key(shot_root, "location", [
    (1, (0, 0.0, 0)), (5, (0, -1.0, .02)), (8, (0, -2.6, .04)),
    (11, (0, -5.8, .08)), (15, (0, -11.5, .13)),
    (20, (0, -16.0, .20)), (24, (0, -23.0, .26)),
    (27, (0, -30.0, .31)), (28, (0, -30.0, .31))], "BEZIER")
key(ship_root, "scale", [(1, (1, 1, 1)), (27, (1, 1, 1)),
                         (28, (.001, .001, .001))], "CONSTANT")

# Engine energy is visible before ignition, as in the teaser reference.
engine_white = surface_mat("ENGINE_WHITE_CORE", (1, .92, .66, 1), 18)
engine_violet = noisy_volume("ENGINE_LAVENDER_EXHAUST", (.20, .04, .65, 1),
                             (.40, .08, 1, 1), 1.8, 2.4, 3.5)
engine_root = empty("ELLIPSO_ENGINE_EFFECTS", ship_root)
engine_objects = []
for i, x in enumerate((-.92, .92), 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=.10,
                                         location=(x, 1.52, 1.18))
    core = bpy.context.object
    core.name = f"ENGINE_CORE_{i:02d}"
    core.parent = engine_root
    core.data.materials.append(engine_white)
    engine_objects.append(core)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1,
                                         location=(x, 1.72, 1.18))
    plume = bpy.context.object
    plume.name = f"ENGINE_PLUME_{i:02d}"
    plume.parent = engine_root
    plume.scale = (.17, .36, .17)
    plume.data.materials.append(engine_violet)
    engine_objects.append(plume)

# Once the foreground plasma has fully crossed the hull, the hero is inside
# hyperspace and must not reappear as the cloud contracts.
for ob in ship_objects + engine_objects:
    ob.hide_render = False
    ob.keyframe_insert("hide_render", frame=1)
    ob.keyframe_insert("hide_render", frame=16)
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=17)

# Ignition is warm, small and mostly hidden behind the hull.
ignition_mat = surface_mat("HYPERSPACE_YELLOW_GREEN_IGNITION",
                           (1.0, .62, .015, 1), 24)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1,
                                     location=(0, -.72, 1.08))
ignition = bpy.context.object
ignition.name = "CONCEALED_IGNITION"
ignition.parent = shot_root
ignition.data.materials.append(ignition_mat)
key(ignition, "scale", [(1, (.001,)*3), (6, (.001,)*3),
                        (8, (.28, .12, .22)), (10, (.75, .20, .56)),
                        (13, (.34, .10, .28)), (17, (.001,)*3),
                        (23, (.001,)*3), (25, (.28, .10, .20)),
                        (27, (.18, .08, .14)), (28, (.001,)*3)])

cloud_root = empty("TRAVELING_HYPERSPACE_CLOUD", shot_root)
cloud_root.location = (0, -.90, 1.08)
outer = empty("PURPLE_TURBULENT_PERIMETER", cloud_root)
middle = empty("LAVENDER_BODY", cloud_root)
core_root = empty("WHITE_PLASMA_CORE", cloud_root)

purple_mat = noisy_volume("DARK_PURPLE_PLASMA", (.10, .07, .25, 1),
                          (.17, .10, .44, 1), 1.40, .38, 2.9)
lavender_mat = noisy_volume("LAVENDER_PLASMA", (.38, .32, .68, 1),
                            (.62, .52, .88, 1), 1.62, .90, 3.4)
white_mat = noisy_volume("WHITE_HYPERSPACE_CORE", (.94, .97, 1, 1),
                         (1.0, .94, .72, 1), 1.95, 3.8, 3.8)

# Camera-side plasma grows across the hull at peak. This is a separate depth
# layer from the backlit burst, so the ship is visibly engulfed rather than
# remaining a persistent black cutout through the whole collapse.
engulf_root = empty("FOREGROUND_ENGULFMENT", cloud_root)
add_cloud_piece("ENGULFMENT_MAIN_MASS", engulf_root, white_mat,
                (1.05, 3.05, .42), (2.15, 1.55, 1.42), 179)
for i in range(12):
    a = math.tau * i / 12 + random.uniform(-.16, .16)
    r = random.uniform(.15, 1.25)
    x = .32 + math.cos(a) * r
    z = math.sin(a) * r * .72
    material = white_mat if i % 3 else lavender_mat
    add_cloud_piece(f"ENGULFMENT_{i+1:02d}", engulf_root, material,
                    (x, 2.25 + random.uniform(-.18, .28), z),
                    (random.uniform(.58, 1.05), random.uniform(.70, 1.18),
                     random.uniform(.48, .92)), 180 + i)
key(engulf_root, "scale", [(1, (.001,)*3), (10, (.001,)*3),
                           (12, (.12, .10, .12)), (14, (.70, .64, .70)),
                           (16, (1.18, 1.08, 1.18)),
                           (22, (1.0, .95, 1.0)),
                           (27, (.38, .38, .38)), (28, (.001,)*3)])

# Filled central body: randomly packed in an ellipse, avoiding a ring read.
for i in range(34):
    a = random.uniform(0, math.tau)
    r = math.sqrt(random.random())
    x = math.cos(a) * r * 1.75
    z = math.sin(a) * r * 1.35
    add_cloud_piece(f"WHITE_CORE_{i+1:02d}", core_root, white_mat,
                    (x, random.uniform(-.55, .45), z),
                    (random.uniform(.52, .96), random.uniform(.55, 1.15),
                     random.uniform(.48, .88)), i)

for i in range(30):
    a = random.uniform(0, math.tau)
    r = math.sqrt(random.uniform(.28, 1.0))
    x = math.cos(a) * r * 2.15
    z = math.sin(a) * r * 1.72
    add_cloud_piece(f"LAVENDER_BODY_{i+1:02d}", middle, lavender_mat,
                    (x, random.uniform(-.75, .55), z),
                    (random.uniform(.62, 1.14), random.uniform(.70, 1.35),
                     random.uniform(.56, 1.02)), 50 + i)

# Perimeter scallops, holes and elongated radial splashes reproduce the old
# teaser's energetic edge rather than a modern smooth smoke ring.
for i in range(34):
    a = math.tau * i / 34 + random.uniform(-.10, .10)
    radius = random.uniform(2.00, 2.42)
    x, z = math.cos(a) * radius, math.sin(a) * radius * .78
    radial = random.uniform(1.0, 1.65) if i % 3 else random.uniform(1.7, 2.45)
    ob = add_cloud_piece(f"PURPLE_EDGE_{i+1:02d}", outer, purple_mat,
                         (x, random.uniform(-.85, .65), z),
                         (radial, random.uniform(.75, 1.45), random.uniform(.34, .70)),
                         100 + i)
    ob.rotation_euler[1] = -a

# The cloud is born behind the hull, flashes outward, then contracts while the
# entire event continues into the distance.
key(cloud_root, "scale", [
    (1, (.001,)*3), (7, (.001,)*3), (9, (.12, .10, .12)),
    (11, (.54, .50, .54)), (13, (.86, .82, .86)),
    (15, (.80, .76, .80)), (18, (.62, .60, .62)),
    (22, (.55, .52, .55)), (25, (.42, .40, .42)),
    (27, (.28, .28, .28)),
    (28, (.001,)*3)])
key(cloud_root, "rotation_euler", [(7, (0, 0, 0)),
                                   (18, (.12, .18, -.16)),
                                   (28, (.25, .45, -.34))])

# The source clip ends on a dim green-yellow plasma afterimage after the ship
# and white-violet bloom have vanished.
residue_mat = noisy_volume("YELLOW_GREEN_RESIDUE", (.22, .20, .025, 1),
                           (.42, .34, .035, 1), .72, .20, 3.2)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1,
                                     location=(0, -.92, 1.08))
residue = bpy.context.object
residue.name = "TERMINAL_HYPERSPACE_RESIDUE"
residue.parent = shot_root
residue.data.materials.append(residue_mat)
key(residue, "scale", [(1, (.001,)*3), (25, (.001,)*3),
                       (27, (.25, .14, .20)), (28, (.72, .36, .56))])

# Bright backlight makes the retreating craft read as a clean silhouette at peak.
back_data = bpy.data.lights.new("WHITE_CORE_BACKLIGHT", "POINT")
back_data.energy = 2600
back_data.color = (1.0, .86, .62)
back_data.shadow_soft_size = 1.1
back = bpy.data.objects.new("WHITE_CORE_BACKLIGHT", back_data)
bpy.context.scene.collection.objects.link(back)
back.parent = shot_root
back.location = (0, -1.35, 1.08)
back.data.energy = 0
back.data.keyframe_insert("energy", frame=1)
back.data.keyframe_insert("energy", frame=7)
back.data.energy = 3000
back.data.keyframe_insert("energy", frame=11)
back.data.energy = 2200
back.data.keyframe_insert("energy", frame=16)
back.data.energy = 0
back.data.keyframe_insert("energy", frame=25)

# Aft-side fill shows the hero before the jump, then drops for the silhouette.
fill_data = bpy.data.lights.new("AFT_SHIP_FILL", "AREA")
fill_data.energy = 650
fill_data.color = (.52, .62, 1.0)
fill_data.shape = "DISK"
fill_data.size = 5
fill = bpy.data.objects.new("AFT_SHIP_FILL", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.location = (0, 6, 5)
fill.rotation_euler = ((Vector((0, 0, .5)) - fill.location).to_track_quat("-Z", "Y").to_euler())
fill.data.keyframe_insert("energy", frame=1)
fill.data.keyframe_insert("energy", frame=7)
fill.data.energy = 25
fill.data.keyframe_insert("energy", frame=11)
fill.data.energy = 0
fill.data.keyframe_insert("energy", frame=24)

# Dense, fixed 1990s-style star plate.
star_mat = surface_mat("DENSE_STARFIELD", (.80, .85, 1.0, 1), 5.5)
star_verts = []
star_faces = []
for i in range(1250):
    x = random.uniform(-78, 78)
    z = random.uniform(-58, 58)
    y = random.uniform(-82, -68)
    radius = random.choice((.018, .024, .032, .045, .065))
    base = len(star_verts)
    star_verts.extend(((x-radius, y, z-radius), (x+radius, y, z-radius),
                       (x+radius, y, z+radius), (x-radius, y, z+radius)))
    star_faces.append((base, base+1, base+2, base+3))
star_mesh = bpy.data.meshes.new("dense_starfield_mesh")
star_mesh.from_pydata(star_verts, [], star_faces)
starfield = bpy.data.objects.new("DENSE_FIXED_STAR_PLATE", star_mesh)
bpy.context.scene.collection.objects.link(starfield)
starfield.data.materials.append(star_mat)

# Locked aft camera; no orbit or shake in the approved clip.
cam_data = bpy.data.cameras.new("LOCKED_AFT_CAMERA_DATA")
cam = bpy.data.objects.new("LOCKED_AFT_CAMERA", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = ((5.6, 7.4, 3.3) if ACTION_ANGLE else (0, 7.8, 1.12))
if ACTION_ANGLE:
    action_target = empty("ACTION_CAMERA_TARGET", shot_root)
    action_target.location = (0, 0, .82)
    track = cam.constraints.new("DAMPED_TRACK")
    track.target = action_target
    track.track_axis = "TRACK_NEGATIVE_Z"
else:
    cam.rotation_euler = ((Vector((0, -2.5, .60)) - cam.location).to_track_quat("-Z", "Y").to_euler())
cam.data.lens = 50 if ACTION_ANGLE else 52
scene.camera = cam

os.makedirs(FRAMES, exist_ok=True)
blend = os.path.join(OUT, BUILD_NAME + ".blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
test = [a for a in sys.argv if a.startswith("--test-frame=")]
replace = [a for a in sys.argv if a.startswith("--replace-frame=")]
if test or replace:
    selected = (replace or test)[-1]
    f = int(selected.split("=", 1)[1])
    scene.frame_set(f)
    scene.render.filepath = (os.path.join(FRAMES, f"frame_{f:04d}.png") if replace
                             else os.path.join(OUT, f"test_frame_{f:04d}.png"))
    bpy.ops.render.render(write_still=True)
    raise SystemExit(0)

bpy.ops.render.render(animation=True)
ffmpeg_hits = glob.glob(os.path.join(ROOT, ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = ffmpeg_hits[0] if ffmpeg_hits else shutil.which("ffmpeg") or "ffmpeg"
mp4 = os.path.join(OUT, BUILD_NAME + ".mp4")
subprocess.run([ffmpeg, "-y", "-framerate", str(FPS), "-start_number", "1",
                "-i", os.path.join(FRAMES, "frame_%04d.png"),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4], check=True)
print("[ellipso-hyperspace] wrote", blend)
print("[ellipso-hyperspace] wrote", mp4)
