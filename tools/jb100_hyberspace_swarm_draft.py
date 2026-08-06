"""Ten-second JB100 hyberspace-to-interceptor-swarm previs.

Run from Orlando-El-Bastardo.src:
    blender --background --factory-startup --python tools/jb100_hyberspace_swarm_draft.py

Outputs:
    out/jb100_hyberspace_swarm_draft.blend
    out/jb100_hyberspace_swarm_draft.mp4
"""
import bpy
import glob
import math
import os
import random
import shutil
import subprocess
from mathutils import Vector

FPS = 24
END = 240
ROOT = os.getcwd()
OUT = os.path.join(ROOT, "out")
FRAMES = os.path.join(OUT, "jb100_hyberspace_swarm_draft_frames")
JB100 = os.path.join(ROOT, "assets/ships/jb100.glb")
PILOT = os.path.join(ROOT, "assets/characters/oeb_dressed_characters.glb")
BI = os.path.join(ROOT, "assets/ships/bugblatter_interceptor_v1.0.0/bugblatter_interceptor_v1.0.0.glb")
random.seed(100)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                       bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name, color, metallic=0.0, roughness=0.5, emission=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def import_as_root(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    imported = list(set(bpy.data.objects) - before)
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            obj.parent = root
    return root, imported


def key_transform(obj, frame, location, rotation=(0, 0, 0), scale=None):
    obj.location = location
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = rotation
    if scale is not None:
        obj.scale = scale
    obj.keyframe_insert("location", frame=frame)
    obj.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        obj.keyframe_insert("scale", frame=frame)


def set_linear(obj):
    # Blender 5 stores keyframe channels in layered Action slots. Default
    # interpolation is suitable for this previs, so no version-specific edit.
    return


def look_at(obj, point, roll=0.0):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()
    obj.rotation_euler.rotate_axis("Z", roll)


def key_camera(cam, frame, location, target, lens, roll=0.0):
    cam.location = location
    look_at(cam, target, roll)
    cam.data.lens = lens
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)
    cam.data.keyframe_insert("lens", frame=frame)


def add_empty(name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.parent = parent
    return obj


def key_scale(obj, keys):
    for frame, scale in keys:
        obj.scale = scale
        obj.keyframe_insert("scale", frame=frame)


def key_visibility(obj, visible_from, visible_to):
    obj.hide_render = True
    obj.keyframe_insert("hide_render", frame=1)
    obj.keyframe_insert("hide_render", frame=max(1, visible_from - 1))
    obj.hide_render = False
    obj.keyframe_insert("hide_render", frame=visible_from)
    obj.keyframe_insert("hide_render", frame=visible_to)
    obj.hide_render = True
    obj.keyframe_insert("hide_render", frame=min(END, visible_to + 1))


def key_visibility_many(objects, visible_from, visible_to):
    for obj in objects:
        key_visibility(obj, visible_from, visible_to)


clear_scene()
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = END
scene.render.fps = FPS
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.use_file_extension = True
scene.render.image_settings.color_mode = "RGB"
scene.render.filepath = os.path.join(FRAMES, "frame_")
scene.render.use_compositing = True
scene.render.use_sequencer = False
scene.render.use_motion_blur = False
scene.display.shading.light = "STUDIO"
scene.display.shading.studio_light = "paint.sl"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.cavity_type = "WORLD"
scene.display.shading.curvature_ridge_factor = 1.5
scene.display.shading.curvature_valley_factor = 1.0
scene.display.shading.show_specular_highlight = True
scene.display.shading.background_type = "VIEWPORT"
scene.display.shading.background_color = (0.003, 0.006, 0.012)
scene.view_settings.look = "AgX - Medium High Contrast"

world = bpy.data.worlds.new("Deep Space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.0002, 0.0004, 0.001, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.02
scene.world = world

# Procedural stars on an inward-visible sphere.
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=450)
stars = bpy.context.object
stars.name = "STARFIELD"
stars.visible_shadow = False
stars.hide_render = True  # Workbench draft uses the dark viewport background.
sm = bpy.data.materials.new("Stars")
sm.use_nodes = True
sm.use_backface_culling = False
nt = sm.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")
ramp = nt.nodes.new("ShaderNodeValToRGB")
noise = nt.nodes.new("ShaderNodeTexNoise")
coord = nt.nodes.new("ShaderNodeTexCoord")
noise.inputs["Scale"].default_value = 260
noise.inputs["Detail"].default_value = 2
ramp.color_ramp.interpolation = "CONSTANT"
ramp.color_ramp.elements[0].position = 0.82
ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
ramp.color_ramp.elements[1].position = 0.835
ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
emit.inputs["Strength"].default_value = 5
nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
stars.data.materials.append(sm)

# Hero ship and pilot.
ship, ship_objects = import_as_root(JB100, "JB100_FLIGHT_ROOT")
ship.rotation_mode = "XYZ"
pilot_before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=PILOT)
pilot_imported = list(set(bpy.data.objects) - pilot_before)
hero = bpy.data.objects.get("char_hero_v1")

def descends_from(obj, ancestor):
    while obj:
        if obj == ancestor:
            return True
        obj = obj.parent
    return False

for obj in pilot_imported:
    if hero and not descends_from(obj, hero):
        bpy.data.objects.remove(obj, do_unlink=True)
if hero:
    hero.parent = ship
    hero.location = (0.0, -0.42, 0.22)
    hero.rotation_mode = "XYZ"
    hero.rotation_euler = (0, 0, 0)
    hero.scale = (1.15, 1.15, 1.15)
    if "idle_seated_relaxed" in bpy.data.actions:
        hero.animation_data_create()
        hero.animation_data.action = bpy.data.actions["idle_seated_relaxed"]

# Nose is local -Y. The ship keeps its straight forward path, with a subtle
# roll/bank waggle that now begins while the camera is still finishing its
# right-side-up roll.
SHIP_EMERGE_FRAME = 13
SHIP_FULL_SCALE_FRAME = 30
SHIP_VISIBLE_FRAME = SHIP_EMERGE_FRAME
UNDERPASS_FRAME = 99

def base_ship_y_at(frame):
    t = (frame - 1) / (END - 1)
    return 75.0 + (-165.0 - 75.0) * t


def ship_location_at(frame):
    # Preserve the current opening/chase timing: the JB100 holds briefly at
    # distance, then accelerates back onto the underpass/chase lane.
    if frame <= SHIP_EMERGE_FRAME:
        ship_y = base_ship_y_at(1)
    elif frame <= UNDERPASS_FRAME:
        t = smoothstep((frame - SHIP_EMERGE_FRAME) / (UNDERPASS_FRAME - SHIP_EMERGE_FRAME))
        ship_y = base_ship_y_at(1) + (base_ship_y_at(UNDERPASS_FRAME) - base_ship_y_at(1)) * t
    else:
        t = (frame - UNDERPASS_FRAME) / (END - UNDERPASS_FRAME)
        ship_y = base_ship_y_at(UNDERPASS_FRAME) + (base_ship_y_at(END) - base_ship_y_at(UNDERPASS_FRAME)) * t
    return (0.0, ship_y, 0.0)

def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

def ship_roll_at(frame):
    # Bank around the JB100's nose/tail axis: left side dips first, then right,
    # with a smaller settling correction as the swarm tightens.
    roll_keys = [
        (1, 0.0),
        (108, 0.0),
        (124, math.radians(-14.0)),
        (142, 0.0),
        (162, math.radians(16.0)),
        (184, 0.0),
        (208, math.radians(-8.0)),
        (228, math.radians(0.0)),
        (240, 0.0),
    ]
    for (f0, r0), (f1, r1) in zip(roll_keys, roll_keys[1:]):
        if f0 <= frame <= f1:
            t = smoothstep((frame - f0) / (f1 - f0))
            return r0 + (r1 - r0) * t
    return roll_keys[-1][1]

for f in range(1, END + 1):
    key_transform(ship, f, ship_location_at(f), (0, ship_roll_at(f), 0))
set_linear(ship)
key_scale(ship, [
    (1, (0.001, 0.001, 0.001)),
    (SHIP_EMERGE_FRAME - 1, (0.001, 0.001, 0.001)),
    (SHIP_EMERGE_FRAME, (0.08, 0.08, 0.08)),
    (SHIP_FULL_SCALE_FRAME, (1.0, 1.0, 1.0)),
    (END, (1.0, 1.0, 1.0)),
])
ship_appearance_objects = [obj for obj in bpy.data.objects if descends_from(obj, ship)]
key_visibility_many(ship_appearance_objects, SHIP_VISIBLE_FRAME, END)


def add_simple_arrival_flash():
    """A single white flash beat immediately before the JB100 appears."""
    flash_mat = material("ARRIVAL_FLASH_WHITE", (1.0, 1.0, 1.0, 1),
                         emission=(1.0, 1.0, 1.0, 1), strength=20)
    verts = [(0.0, 0.0, 0.0)]
    faces = []
    segments = 48
    for i in range(segments):
        angle = math.tau * i / segments
        verts.append((math.cos(angle), 0.0, math.sin(angle)))
    for i in range(1, segments + 1):
        faces.append((0, i, 1 if i == segments else i + 1))
    mesh = bpy.data.meshes.new("ARRIVAL_WHITE_FLASH_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    flash = bpy.data.objects.new("ARRIVAL_WHITE_FLASH", mesh)
    bpy.context.scene.collection.objects.link(flash)
    flash.name = "ARRIVAL_WHITE_FLASH"
    flash.location = ship_location_at(SHIP_EMERGE_FRAME)
    flash.data.materials.append(flash_mat)
    key_scale(flash, [
        (1, (0.001, 0.001, 0.001)),
        (7, (0.001, 0.001, 0.001)),
        (10, (1.1, 1.1, 1.1)),
        (12, (2.0, 2.0, 2.0)),
        (13, (0.001, 0.001, 0.001)),
    ])
    key_visibility(flash, 7, 12)


add_simple_arrival_flash()


# Camera: fixed in place through the underpass, then follows the JB100 while
# the pitch tracks the cockpit and the roll brings the frame right-side-up.
cam_data = bpy.data.cameras.new("CAMERA_DATA")
cam = bpy.data.objects.new("CAMERA", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.rotation_mode = "XYZ"
CAMERA_START = (0.0, -24.0, 4.2)
cam.location = CAMERA_START
cam.data.lens = 50

def cockpit_target_at(frame):
    ship_x, ship_y, ship_z = ship_location_at(frame)
    return (ship_x, ship_y - 0.42, ship_z + 0.22)

FOLLOW_START_FRAME = 120
ROLL_END_FRAME = 120
FOLLOW_Y_OFFSET = CAMERA_START[1] - cockpit_target_at(FOLLOW_START_FRAME)[1]
CHASE_BACKOFF_EXTRA = 26.0
CHASE_CLEAR_START = 132
CHASE_CLEAR_PEAK = 168
CHASE_CLEAR_END = 204
CHASE_RIGHT_OFFSET = -5.0
CHASE_HEIGHT_BOOST = 7.0
CHASE_LEFT_START = 204
CHASE_LEFT_PEAK = 222
CHASE_LEFT_END = 240
CHASE_LEFT_OFFSET = 2.8
CHASE_LEFT_HEIGHT_BOOST = 6.5

def chase_clearance_at(frame):
    # Post-chase dodge only: rise over the JB100's right side for the close
    # BI pass, then settle back into the 1.0.7 chase/backoff lane.
    if frame < CHASE_CLEAR_START or frame > CHASE_CLEAR_END:
        return 0.0
    if frame <= CHASE_CLEAR_PEAK:
        return smoothstep((frame - CHASE_CLEAR_START) / (CHASE_CLEAR_PEAK - CHASE_CLEAR_START))
    return 1.0 - smoothstep((frame - CHASE_CLEAR_PEAK) / (CHASE_CLEAR_END - CHASE_CLEAR_PEAK))

def chase_left_arc_at(frame):
    # After the right-side clearance has returned to the chase path, rise high
    # and left, then settle back into the lane again before the shot ends.
    if frame < CHASE_LEFT_START or frame > CHASE_LEFT_END:
        return 0.0
    if frame <= CHASE_LEFT_PEAK:
        return smoothstep((frame - CHASE_LEFT_START) / (CHASE_LEFT_PEAK - CHASE_LEFT_START))
    return 1.0 - smoothstep((frame - CHASE_LEFT_PEAK) / (CHASE_LEFT_END - CHASE_LEFT_PEAK))

def camera_location_at(frame):
    if frame < FOLLOW_START_FRAME:
        return CAMERA_START
    target_x, target_y, _ = cockpit_target_at(frame)
    raw_backoff_t = (frame - FOLLOW_START_FRAME) / (END - FOLLOW_START_FRAME)
    # Let the chase camera drift back more gradually; it no longer reaches the
    # full 1.0.7 backoff distance inside this ten-second rough pass.
    backoff_t = smoothstep(raw_backoff_t * 0.42)
    trailing_offset = FOLLOW_Y_OFFSET + CHASE_BACKOFF_EXTRA * backoff_t
    clear_t = chase_clearance_at(frame)
    left_t = chase_left_arc_at(frame)
    return (
        target_x + CHASE_RIGHT_OFFSET * clear_t + CHASE_LEFT_OFFSET * left_t,
        target_y + trailing_offset,
        CAMERA_START[2] + CHASE_HEIGHT_BOOST * clear_t + CHASE_LEFT_HEIGHT_BOOST * left_t,
    )

for f in range(1, END + 1):
    cam.location = camera_location_at(f)
    _, target_y, target_z = cockpit_target_at(f)
    dy = target_y - cam.location.y
    dz = target_z - cam.location.z
    cam.rotation_euler = (math.atan2(dy, -dz), 0.0, 0.0)
    if f >= UNDERPASS_FRAME:
        roll_t = min(1.0, (f - UNDERPASS_FRAME) / (ROLL_END_FRAME - UNDERPASS_FRAME))
        roll_t = roll_t * roll_t * (3.0 - 2.0 * roll_t)
        cam.rotation_euler.rotate_axis("Z", math.pi * roll_t)
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

# Interceptor source collection. Imported geometry is grouped under one root.
bi_source, bi_objects = import_as_root(BI, "BI_SOURCE")
bi_source.hide_render = True
bi_source.hide_viewport = True
bi_collection = bpy.data.collections.new("BI_ASSET")
for obj in bi_objects:
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    bi_collection.objects.link(obj)

def interceptor(name, keys, scale=1.0):
    inst = bpy.data.objects.new(name, None)
    scene.collection.objects.link(inst)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = bi_collection
    inst.rotation_mode = "XYZ"
    inst.scale = (scale, scale, scale)
    # Do not let Blender's pre-keyframe extrapolation reveal the swarm during
    # the hero flyby. Each ship appears only when it reaches its distant entry.
    first_frame = keys[0][0]
    inst.hide_render = True
    inst.keyframe_insert("hide_render", frame=1)
    inst.keyframe_insert("hide_render", frame=max(1, first_frame - 1))
    inst.hide_render = False
    inst.keyframe_insert("hide_render", frame=first_frame)
    for f, loc, rot in keys:
        key_transform(inst, f, loc, rot, (scale, scale, scale))
    return inst

# Twelve hand-staged near/mid interceptors. Their noses and velocity point +Y,
# toward the post-pivot camera, with only small lane changes around the JB100.
crossings = [
    (142, -7,  3,  5, -2,  0.05), (149, -5, -4,  7,  1, -0.10),
    (156,  8,  2, -6,  5,  0.14), (163,  3, -7, -2,  6, -0.18),
    (170, -9,  6,  8, -3,  0.22), (177,  6,  7, -8, -2, -0.08),
    (184, -2, -8, -5,  8,  0.18), (191, 10, -1, -9, -5, -0.22),
    (198, -8, -5,  4,  8,  0.10), (205,  4,  9,  1, -8, -0.14),
    (214,-11,  1, 10,  3,  0.20), (223,  7, -9, -5, 10, -0.20),
]
for i, (cross, x0, z0, x1, z1, roll) in enumerate(crossings, 1):
    y = -77 - (cross - 142) * 1.18
    # Keep every hero interceptor outside the JB100's central safety tube.
    cross_x = math.copysign(max(4.5, abs(x0) * 0.55), x0)
    cross_z_raw = (z0 + z1) * 0.10
    cross_z = math.copysign(max(2.7, abs(cross_z_raw)), cross_z_raw or z0 or 1)
    exit_x = cross_x + (x1 - x0) * 0.12
    keys = [
        (max(96, cross - 26), (x0, y - 84, z0), (roll, 0, -math.pi / 2 + roll * .15)),
        (cross, (cross_x, y, cross_z), (-roll * .4, 0, -math.pi / 2 - roll * .10)),
        (min(240, cross + 28), (exit_x, y + 48, z1), (roll * .5, 0, -math.pi / 2 + roll * .08)),
    ]
    if i == 5:
        # This is the close pass visible around the 7-second mark. At this
        # point in the shot the camera has rolled, so moving world-left reads
        # as screen-right; the added Z lift moves it visually upward.
        keys = [
            (f, (loc[0] - 4.5, loc[1], loc[2] + 4.0), rot)
            for f, loc, rot in keys
        ]
    interceptor(f"BI_HERO_{i:02d}", keys, 0.86 + random.random() * 0.22)

# Seventy-two background ships in broad, loose coordinated waves. The first
# distant layer appears as the camera begins its turn, then rapidly thickens.
for i in range(72):
    cross = random.randint(132, 238)
    y = -78 - (cross - 132) * 1.18
    side = random.choice((-1, 1))
    # Regular edge lanes guarantee coverage beyond the central swarm body.
    x_band = random.uniform(34, 56) if i % 3 == 0 else random.uniform(10, 44)
    x0 = side * x_band
    x1 = -side * random.uniform(12, 50)
    if i % 4 == 0:
        z0 = random.choice((-1, 1)) * random.uniform(20, 38)
    else:
        z0 = random.uniform(-32, 33)
    z1 = z0 + random.uniform(-12, 12)
    roll = random.uniform(-0.45, 0.45)
    keys = [
        (max(104, cross - 34), (x0, y - random.uniform(96, 160), z0), (roll, 0, -math.pi / 2 + roll * .12)),
        (cross, (x0 * 0.62, y, z0 * 0.58 + random.uniform(-4, 4)), (-roll * .3, 0, -math.pi / 2 - roll * .08)),
        (min(260, cross + 38), (x0 * 0.48 + (x1 - x0) * 0.08, y + random.uniform(55, 90), z1), (roll * .4, 0, -math.pi / 2 + roll * .06)),
    ]
    interceptor(f"BI_BG_{i+1:02d}", keys, random.uniform(0.55, 0.9))

# Simple motivated space lighting.
sun_data = bpy.data.lights.new("KEY_SUN", "SUN")
sun_data.energy = 2.3
sun_data.color = (0.62, 0.75, 1.0)
sun = bpy.data.objects.new("KEY_SUN", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), math.radians(-20), math.radians(-35))
rim_data = bpy.data.lights.new("WARM_RIM", "SUN")
rim_data.energy = 1.2
rim_data.color = (1.0, 0.35, 0.08)
rim = bpy.data.objects.new("WARM_RIM", rim_data)
scene.collection.objects.link(rim)
rim.rotation_euler = (math.radians(-35), math.radians(15), math.radians(140))

os.makedirs(OUT, exist_ok=True)
os.makedirs(FRAMES, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "jb100_hyberspace_swarm_draft.blend"))
print("[draft] rendering 240 frames")
bpy.ops.render.render(animation=True)

ffmpeg_hits = glob.glob(os.path.join(ROOT, ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = ffmpeg_hits[0] if ffmpeg_hits else shutil.which("ffmpeg") or "ffmpeg"
mp4 = os.path.join(OUT, "jb100_hyberspace_swarm_draft.mp4")
subprocess.run([
    ffmpeg, "-y", "-framerate", str(FPS), "-start_number", "1",
    "-i", os.path.join(FRAMES, "frame_%04d.png"),
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4,
], check=True)
print("[draft] wrote", mp4)
