#!/usr/bin/env python3
"""Build a standalone, reusable hyperspace entry/exit effect draft.

Run from Orlando-El-Bastardo.src:
    blender --background --factory-startup \
      --python tools/build_hyperspace_effect_draft.py

The authored effect faces -Y (toward the preview camera).  Parent a ship to
SHIP_ATTACH and set HYPERSPACE_EFFECT_ROOT["ship_outline_*_m"] to its measured
dimensions.  The draft uses a deliberately generic black proxy only to judge
the mirror/silhouette reveal; it is isolated in TEST_SHIP_PROXY.
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

FPS = 24
END = 120
ROOT = os.getcwd()
VOLUMETRIC = "--volumetric" in sys.argv
FINAL = "--final" in sys.argv or VOLUMETRIC
BUILD_NAME = ("hyperspace_effect_final_v2" if VOLUMETRIC else
              "hyperspace_effect_final" if FINAL else "hyperspace_effect_draft")
OUT = os.path.join(ROOT, "out", BUILD_NAME)
FRAMES = os.path.join(OUT, "frames")
random.seed(1701)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                   bpy.data.cameras, bpy.data.lights, bpy.data.worlds):
        for block in list(blocks):
            if block.users == 0:
                blocks.remove(block)


def mat(name, color, emission=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Emission Color"].default_value = color
    bsdf.inputs["Emission Strength"].default_value = emission
    bsdf.inputs["Alpha"].default_value = alpha
    m.surface_render_method = "DITHERED"
    m.use_transparency_overlap = False
    return m


def volume_mat(name, color, density, emission_color, emission_strength):
    """Participating-media cloud; its lighting reveals real spatial depth."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = color
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = 0.28
    vol.inputs["Emission Color"].default_value = emission_color
    vol.inputs["Emission Strength"].default_value = emission_strength
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m


def key(obj, data_path, values):
    for frame, value in values:
        setattr(obj, data_path, value)
        obj.keyframe_insert(data_path=data_path, frame=frame)


def smooth_keys(obj):
    if not obj.animation_data or not obj.animation_data.action:
        return
    # Blender 4.x FCurves; harmlessly skipped by Blender 5 layered actions.
    for fc in getattr(obj.animation_data.action, "fcurves", []):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"


def add_empty(name, parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def add_cloud_lobe(name, parent, material, loc, scale, seed):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.parent = parent
    ob.scale = scale
    ob.data.materials.append(material)
    # Displace the sphere into a soft, irregular cloud rather than a clean orb.
    tex = bpy.data.textures.new(name + "_NOISE", type="CLOUDS")
    tex.noise_scale = 0.48 + seed * 0.01
    tex.noise_depth = 2
    mod = ob.modifiers.new("CLOUD_BREAKUP", "DISPLACE")
    mod.texture = tex
    mod.strength = 0.24
    mod.texture_coords = "GLOBAL"
    return ob


def add_burst_ray(parent, angle, length, width, material):
    # Rays lie in the XZ portal plane and taper away from the pinpoint.
    verts = [(0, 0, -width), (0, 0, width),
             (length, 0, width * 0.08), (length, 0, -width * 0.08)]
    mesh = bpy.data.meshes.new("burst_ray_mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("YELLOW_BURST_RAY", mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    ob.rotation_euler[1] = angle
    ob.data.materials.append(material)
    return ob


def add_proxy_ship(parent, black):
    # Abstract plan silhouette: not any production ship and easy to replace.
    verts = [(-0.18, -1.4, 0), (0.18, -1.4, 0), (0.5, 0.15, 0),
             (1.7, 0.75, 0), (0.7, 0.95, 0), (0.32, 1.35, 0),
             (-0.32, 1.35, 0), (-0.7, 0.95, 0), (-1.7, 0.75, 0),
             (-0.5, 0.15, 0)]
    # Put silhouette in XZ, with thickness along travel axis Y.
    verts = [(x, -0.10, z) for x, z, _ in verts] + [(x, 0.10, z) for x, z, _ in verts]
    faces = [tuple(range(10)), tuple(range(19, 9, -1))]
    for i in range(10):
        faces.append((i, (i + 1) % 10, (i + 1) % 10 + 10, i + 10))
    mesh = bpy.data.meshes.new("test_ship_proxy_mesh")
    mesh.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("TEST_SHIP_PROXY", mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    ob.data.materials.append(black)
    return ob


clear()
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = END
scene.render.fps = FPS
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1080 if FINAL else 720
scene.render.resolution_y = 1080 if FINAL else 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.filepath = os.path.join(FRAMES, "frame_")
scene.render.film_transparent = False
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.35 if FINAL else 0.0

world = bpy.data.worlds.new("DEEP_SPACE")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.00005, 0.00008, 0.0002, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.005
scene.world = world

root = add_empty("HYPERSPACE_EFFECT_ROOT")
root["effect_version"] = ("final-2.0-volumetric" if VOLUMETRIC else
                          "final-1.0" if FINAL else "draft-0.1")
root["travel_axis"] = "local -Y"
root["ship_outline_width_m"] = 6.5
root["ship_outline_height_m"] = 1.8
root["ship_outline_length_m"] = 7.0
root["cloud_width_ratio"] = 1.35
root["cloud_height_ratio"] = 1.55
root["cloud_depth_ratio"] = 0.38
root["attachment_note"] = "Parent production ship to SHIP_ATTACH; fit root from outline ratios."
burst_root = add_empty("BURST_YELLOW", root)
white_root = add_empty("CLOUD_WHITE_CORE", root)
purple_root = add_empty("CLOUD_PURPLE_EDGE", root)
mirror_root = add_empty("MIRROR_APERTURE", root)
attach = add_empty("SHIP_ATTACH", root)

yellow = mat("FX_YELLOW_HOT", (1.0, 0.34 if FINAL else 0.52, 0.005, 1),
             11 if FINAL else 18, 0.78 if FINAL else 0.82)
if VOLUMETRIC:
    white = volume_mat("FX_WHITE_VOLUME", (0.92, 0.96, 1.0, 1), 1.35,
                       (1.0, 0.78, 0.48, 1), 0.55)
    violet = volume_mat("FX_PURPLE_VOLUME", (0.12, 0.008, 0.42, 1), 0.92,
                        (0.34, 0.015, 1.0, 1), 1.25)
else:
    white = mat("FX_WHITE_CLOUD", (1.0, 0.94, 0.86, 1),
                2.6 if FINAL else 4.2, 0.56 if FINAL else 0.62)
    violet = mat("FX_PURPLE_EDGE", (0.24, 0.008, 0.68, 1),
                 4.5 if FINAL else 7.0, 0.48 if FINAL else 0.52)
black = mat("FX_MIRROR_BLACK", (0.0001, 0.0001, 0.0002, 1), 0, 1)

if FINAL:
    amber = mat("FX_AMBER_GLOW", (1.0, 0.12, 0.002, 1), 3.0, 0.22)
    # A soft, asymmetric luminous body behind the graphic rays keeps the first
    # beat photographic without turning it into a conventional lens flare.
    for name, radius, squash, delay in [
            ("AMBER_GLOW_NEAR", 1.0, (1.8, 0.18, 1.0), 0),
            ("AMBER_GLOW_WIDE", 1.0, (3.3, 0.10, 1.45), 3)]:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius)
        halo = bpy.context.object
        halo.name = name
        halo.parent = burst_root
        halo.data.materials.append(amber)
        halo.scale = (0.001,) * 3
        key(halo, "scale", [(1, (0.001,) * 3), (8 + delay, (0.001,) * 3),
                            (17 + delay, squash),
                            (28 + delay, tuple(v * .42 for v in squash)),
                            (38 + delay, (0.001,) * 3)])

# Pinpoint and off-axis flare rings: visibly a burst, not a stock lens flare.
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.16)
pin = bpy.context.object
pin.name = "YELLOW_PINPOINT"
pin.parent = burst_root
pin.data.materials.append(yellow)
key(pin, "scale", [(1, (0.001,)*3), (8, (0.18,)*3), (15, (1.9,)*3),
                    (24, (0.5,)*3), (31, (0.001,)*3)])

for i in range(22):
    angle = (math.tau * i / 22) + random.uniform(-0.07, 0.07)
    ray = add_burst_ray(burst_root, angle, random.uniform(2.2, 6.8),
                        random.uniform(0.018, 0.085), yellow)
    key(ray, "scale", [(1, (0.001,)*3), (9, (0.001,)*3),
                       (16, (1, 1, 1)), (27, (0.35, 0.35, 0.35)),
                       (34, (0.001,)*3)])

# Dark mirror aperture sits behind the cloud and expands to the ship outline.
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1,
                                     location=(0, 0.30, 0))
mirror = bpy.context.object
mirror.name = "BLACK_MIRROR_SURFACE"
mirror.parent = mirror_root
mirror.scale = (0.001, 0.05, 0.001)
mirror.data.materials.append(black)
key(mirror, "scale", [(1, (0.001, 0.05, 0.001)), (23, (0.001, 0.05, 0.001)),
                      (43, (3.8, 0.12, 2.25)), (82, (4.0, 0.12, 2.4)),
                      (108, (0.001, 0.05, 0.001))])

if FINAL and not VOLUMETRIC:
    # Thin, offset energy membranes create the sense of passing through a
    # surface instead of merely emerging from a hole in a cloud.
    membrane_mat = mat("FX_MEMBRANE_VIOLET", (0.48, 0.04, 1.0, 1), 5.5, 0.34)
    for i, (major, minor, y) in enumerate(((3.45, .035, .16),
                                           (3.75, .022, .22),
                                           (4.02, .014, .28)), 1):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                         major_segments=96, minor_segments=12,
                                         location=(0, y, 0),
                                         rotation=(math.pi / 2, 0, 0))
        ring = bpy.context.object
        ring.name = f"MIRROR_MEMBRANE_{i:02d}"
        ring.parent = mirror_root
        ring.scale = (0.001,) * 3
        ring.data.materials.append(membrane_mat)
        key(ring, "scale", [(1, (0.001,) * 3), (29 + i * 2, (0.001,) * 3),
                            (48 + i * 2, (1.0, .58, 1.0)),
                            (83 + i * 2, (1.04, .60, 1.04)),
                            (108 + i, (0.001,) * 3)])

# Outer purple cloud is larger and arrives first around the white boiling rim.
for layer, parent, material_, count, radius, depth in [
        ("PURPLE", purple_root, violet, 28 if VOLUMETRIC else 20,
         3.3, 1.55 if VOLUMETRIC else 0.42),
        ("WHITE", white_root, white, 24 if VOLUMETRIC else 17,
         2.55, 1.05 if VOLUMETRIC else 0.26)]:
    for i in range(count):
        a = math.tau * i / count + random.uniform(-0.13, 0.13)
        r = radius * random.uniform(0.82, 1.16)
        x, z = math.cos(a) * r, math.sin(a) * r * 0.64
        lobe = add_cloud_lobe(f"{layer}_LOBE_{i+1:02d}", parent, material_,
                              (x, random.uniform(-depth, depth), z),
                              (random.uniform(.72, 1.32),
                               random.uniform(.75, 1.55) if VOLUMETRIC else random.uniform(.32, .62),
                               random.uniform(.62, 1.12)), i + 1)
        key(lobe, "scale", [(1, (0.001,)*3),
                            (18 + i % 5, (0.001,)*3),
                            (38 + i % 7, tuple(v * .72 for v in lobe.scale)),
                            (61 + i % 9, tuple(lobe.scale)),
                            (92 + i % 8, tuple(v * .78 for v in lobe.scale)),
                            (114, (0.001,)*3)])
        # Slow rolling motion sells cloud turbulence in draft mode.
        lobe.rotation_mode = "XYZ"
        lobe.rotation_euler = (0, 0, random.uniform(-1, 1))
        lobe.keyframe_insert("rotation_euler", frame=25)
        lobe.rotation_euler[1] += random.uniform(-1.1, 1.1)
        lobe.rotation_euler[2] += random.uniform(-1.6, 1.6)
        lobe.keyframe_insert("rotation_euler", frame=112)

if VOLUMETRIC:
    # Use a production mesh in the final depth test. It remains nearly black
    # while behind the mirror, then catches motivated light as it crosses.
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "ships", "jb100.glb"))
    imported_ship = list(set(bpy.data.objects) - before)
    ship_root = add_empty("PRODUCTION_SHIP_JB100", attach)
    for ob in imported_ship:
        if ob.parent is None:
            ob.parent = ship_root
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=1)
        ob.keyframe_insert("hide_render", frame=42)
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=43)
    ship_root.scale = (1.0,) * 3
else:
    proxy = add_proxy_ship(attach, black)
    proxy.scale = (0.001,)*3
    key(proxy, "scale", [(1, (0.001,)*3), (46, (0.001,)*3),
                         (63, (0.95, 0.95, 0.95)), (88, (1, 1, 1)),
                         (104, (0.001,)*3)])
key(attach, "location", [(1, (0, 1.15, 0)), (52, (0, 0.4, 0)),
                         (74, (0, -0.55, 0)), (104, (0, -4.0, 0))])

if VOLUMETRIC:
    # Hot core light sculpts the white cloud from behind; violet lights around
    # the circumference tint only the exterior and give each lobe a dark side.
    core_data = bpy.data.lights.new("HYPERSPACE_CORE_LIGHT", "POINT")
    core_data.energy = 1750
    core_data.color = (1.0, .68, .34)
    core_data.shadow_soft_size = 1.8
    core = bpy.data.objects.new("HYPERSPACE_CORE_LIGHT", core_data)
    scene.collection.objects.link(core)
    core.location = (0, 1.8, 0)
    for i in range(5):
        a = math.tau * i / 5 + .3
        ld = bpy.data.lights.new(f"VIOLET_RIM_LIGHT_{i+1:02d}", "POINT")
        ld.energy = 430
        ld.color = (.20, .015, 1.0)
        ld.shadow_soft_size = 1.2
        lo = bpy.data.objects.new(f"VIOLET_RIM_LIGHT_{i+1:02d}", ld)
        scene.collection.objects.link(lo)
        lo.location = (math.cos(a) * 4.0, random.uniform(-.8, .8), math.sin(a) * 2.7)

    # Small incandescent fragments move down the travel axis toward camera,
    # providing unmistakable parallax and a sense of expelled energy.
    fragment_mat = mat("FX_TRAVEL_PARTICLE", (0.72, .18, 1.0, 1), 9.0, .9)
    particle_root = add_empty("FORWARD_TRAVEL_PARTICLES", root)
    for i in range(72):
        a = random.uniform(0, math.tau)
        r = random.uniform(.35, 3.8)
        x, z = math.cos(a) * r, math.sin(a) * r * .65
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=random.uniform(.012, .045),
                                             location=(x, random.uniform(1.5, 5.0), z))
        p = bpy.context.object
        p.name = f"TRAVEL_PARTICLE_{i+1:03d}"
        p.parent = particle_root
        p.data.materials.append(fragment_mat)
        start = random.randint(34, 69)
        p.keyframe_insert("location", frame=start)
        p.location.y = random.uniform(-10, -18)
        p.location.x *= random.uniform(1.05, 1.5)
        p.location.z *= random.uniform(1.05, 1.5)
        p.keyframe_insert("location", frame=min(118, start + random.randint(25, 43)))

# Sparse stars provide scale without competing with the effect.
star_mat = mat("STAR", (0.65, 0.72, 1.0, 1), 6, 1)
for i in range(145):
    a = random.uniform(0, math.tau)
    r = random.uniform(8, 22)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=random.uniform(.008, .035),
                                         location=(math.cos(a)*r, random.uniform(4, 14), math.sin(a)*r))
    bpy.context.object.data.materials.append(star_mat)

cam_data = bpy.data.cameras.new("PREVIEW_CAMERA_DATA")
cam = bpy.data.objects.new("PREVIEW_CAMERA", cam_data)
scene.collection.objects.link(cam)
cam.location = ((3.8, -18.5, 2.4) if VOLUMETRIC else (0, -18.5, 1.0))
cam.rotation_euler = ((Vector((0, 0, 0.15)) - cam.location).to_track_quat("-Z", "Y").to_euler())
cam.data.lens = 56 if VOLUMETRIC else 52
scene.camera = cam

os.makedirs(FRAMES, exist_ok=True)
blend = os.path.join(OUT, BUILD_NAME + ".blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
test_args = [a for a in sys.argv if a.startswith("--test-frame=")]
if test_args:
    test_frame = int(test_args[-1].split("=", 1)[1])
    scene.frame_set(test_frame)
    scene.render.filepath = os.path.join(OUT, f"visibility_test_{test_frame:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("[hyperspace-test] wrote", scene.render.filepath)
    raise SystemExit(0)
bpy.ops.render.render(animation=True)

ffmpeg_hits = glob.glob(os.path.join(ROOT, ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = ffmpeg_hits[0] if ffmpeg_hits else shutil.which("ffmpeg") or "ffmpeg"
mp4 = os.path.join(OUT, BUILD_NAME + ".mp4")
subprocess.run([ffmpeg, "-y", "-framerate", str(FPS), "-start_number", "1",
                "-i", os.path.join(FRAMES, "frame_%04d.png"), "-c:v", "libx264",
                "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", mp4], check=True)
print("[hyperspace-draft] wrote", blend)
print("[hyperspace-draft] wrote", mp4)
