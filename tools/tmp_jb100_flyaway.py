"""JB100 fly-away — engines face camera, ship accelerates into the distance.

Ship is rotated 132° around Z so nose points along (0.74, 0.67, 0) — the
direction away from the action-shot camera. Engines (+Y) face the camera.
Quadratic acceleration path: starts close, shrinks into distance over 6 s.
Engine flare: mat_jb100_lamp emission pulsed to ~8×, two orange point lights
parented to the ship at engine-tip positions for physical hull glow.

Output: out/jb100_flyaway.mp4 (960×540, H.264)
"""
import bpy, math, os, glob as globmod, shutil, subprocess
from mathutils import Vector, Matrix

FPS = 24
N_FRAMES = FPS * 6   # 144
CWD = os.getcwd()

# Direction away from camera (XY only, normalised)
DIR_X, DIR_Y = 0.743, 0.669   # normalize(10.5, 9.5)
SHIP_ROT_Z = math.radians(132)   # nose (-Y local) → (DIR_X, DIR_Y, 0) world

# Quadratic path: ship starts close to camera, accelerates 22 m over 6 s
# p(t) = start + dir * 22 * (t/6)²
START = Vector((-3.0, -2.7, 0.0))
TOTAL_DIST = 22.0
def path(t_sec):
    d = TOTAL_DIST * (t_sec / 6.0) ** 2
    return (START.x + DIR_X * d, START.y + DIR_Y * d, 0.0)

# Engine tip local positions (ship space), for point-light placement
ENGINE_TIPS = [(-0.95, 3.01, 1.1), (0.95, 3.01, 1.1)]

# ── clear ─────────────────────────────────────────────────────────────────────
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── load ship ─────────────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/ships/jb100.glb"))
ship = bpy.data.objects["prop_jb100_A"]
ship.rotation_mode = 'XYZ'
ship.rotation_euler.z = SHIP_ROT_Z

# ── engine flare: boost emission on lamp and exhaust materials ────────────────
for slot in ship.material_slots:
    mat = slot.material
    if mat is None:
        continue
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        continue
    if "lamp" in mat.name:
        # Pulse between 7 and 9 (engine power fluctuation)
        for frame in range(1, N_FRAMES + 1, 4):
            t = frame / FPS
            strength = 8.0 + 1.5 * math.sin(t * 9.0)
            bsdf.inputs["Emission Strength"].default_value = strength
            bsdf.inputs["Emission Strength"].keyframe_insert(
                "default_value", frame=frame)
    elif "exhaust" in mat.name:
        bsdf.inputs["Emission Strength"].default_value = 2.5

# ── engine point lights (parented to ship, orange, constant) ─────────────────
for i, (lx, ly, lz) in enumerate(ENGINE_TIPS):
    ld = bpy.data.lights.new(f"engine_glow_{i}", type='POINT')
    ld.color = (1.0, 0.38, 0.05)
    ld.energy = 550
    lo = bpy.data.objects.new(f"engine_glow_{i}", ld)
    bpy.context.scene.collection.objects.link(lo)
    lo.location = (lx, ly, lz)
    lo.parent = ship

# ── load hero, strip bartender ─────────────────────────────────────────────────
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/characters/oeb_dressed_characters.glb"))
new_objs = set(bpy.data.objects) - before
hero = bpy.data.objects["char_hero_v1"]

def under(o, root):
    while o:
        if o is root: return True
        o = o.parent
    return False

for o in list(new_objs):
    if o.name in bpy.data.objects and not under(o, hero):
        bpy.data.objects.remove(o, do_unlink=True)

hero.parent = ship
hero.matrix_parent_inverse = Matrix.Identity(4)  # rotation_euler is ship-local
hero.location = (0.0, -0.4, 0.23)
hero.rotation_mode = 'XYZ'
hero.rotation_euler.z = math.radians(180)
hero.scale = (1.2, 1.2, 1.2)

# ── NLA base: idle_seated_relaxed looping ────────────────────────────────────
idle_act = bpy.data.actions["idle_seated_relaxed"]
if hero.animation_data is None:
    hero.animation_data_create()
idle_track = hero.animation_data.nla_tracks.new()
idle_track.name = "idle_base"
act_len = idle_act.frame_range[1] - idle_act.frame_range[0]
idle_strip = idle_track.strips.new(idle_act.name, 1, idle_act)
idle_strip.repeat = math.ceil(N_FRAMES / act_len) + 1
idle_strip.use_auto_blend = False
idle_strip.blend_in = 0
idle_strip.blend_out = 0
idle_strip.extrapolation = 'NOTHING'

# ── NLA additive: forearm/hand oscillation ───────────────────────────────────
arm_act = bpy.data.actions.new("arm_controls")
hero.animation_data.action = arm_act
bpy.context.view_layer.objects.active = hero
bpy.ops.object.mode_set(mode='POSE')
scene = bpy.context.scene

controls = [
    ("lowerarm_l", 0, 20, 0.0,            1.0),
    ("lowerarm_r", 0, 20, math.pi * 0.5,  1.0),
    ("hand_l",     2, 12, math.pi * 0.25, 0.6),
    ("hand_r",     2, 12, math.pi * 0.75, 0.6),
]
for frame in range(1, N_FRAMES + 1, 4):
    t = frame / FPS
    scene.frame_set(frame)
    for bone_name, axis, amp_deg, phase, cycle in controls:
        pb = hero.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler[axis] = math.radians(amp_deg) * math.sin(
            2 * math.pi * t / cycle + phase)
        pb.keyframe_insert(data_path="rotation_euler", index=axis, frame=frame)

bpy.ops.object.mode_set(mode='OBJECT')
hero.animation_data.action = None
arm_track = hero.animation_data.nla_tracks.new()
arm_track.name = "arm_controls"
arm_strip = arm_track.strips.new(arm_act.name, 1, arm_act)
arm_strip.blend_type = 'ADD'
arm_strip.use_auto_blend = False
arm_strip.blend_in = 0
arm_strip.blend_out = 0

# ── ship flight path (quadratic acceleration) ─────────────────────────────────
ship.animation_data_create()
ship_act = bpy.data.actions.new("ship_flyaway")
ship.animation_data.action = ship_act

for t_sec in (0, 2, 4, 6):
    frame = int(t_sec * FPS) + 1
    px, py, pz = path(t_sec)
    scene.frame_set(frame)
    ship.location = (px, py, pz)
    ship.keyframe_insert(data_path="location", frame=frame)

# ── scene ─────────────────────────────────────────────────────────────────────
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = N_FRAMES

try:
    scene.view_settings.view_transform = 'Standard'
except Exception:
    pass
for c in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = c
        break
    except TypeError:
        continue

# Enable bloom if available (EEVEE)
if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_bloom'):
    scene.eevee.use_bloom = True
    scene.eevee.bloom_threshold = 0.8
    scene.eevee.bloom_intensity = 0.6
    scene.eevee.bloom_radius = 5.0

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.01, 0.015, 1)
scene.world = world

key = bpy.data.lights.new("key", type='SUN')
key.energy = 5.0
ko = bpy.data.objects.new("key", key)
scene.collection.objects.link(ko)
ko.rotation_euler = (math.radians(55), 0, math.radians(-35))

fill = bpy.data.lights.new("fill", type='SUN')
fill.energy = 1.2
fo = bpy.data.objects.new("fill", fill)
scene.collection.objects.link(fo)
fo.rotation_euler = (math.radians(120), 0, math.radians(140))

# ── camera: action-shot angle, static ────────────────────────────────────────
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 42
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_pos = Vector((-10.5, -9.5, 5.5))
cam.location = cam_pos
d = Vector((0, 0, 0.9)) - cam_pos
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.rotation_euler.rotate_axis('Z', math.radians(-18))

# ── render ────────────────────────────────────────────────────────────────────
frames_dir = os.path.join(CWD, "out/jb100_flyaway_frames")
os.makedirs(frames_dir, exist_ok=True)
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = os.path.join(frames_dir, "frame_")
print(f"[flyaway] rendering {N_FRAMES} frames …")
bpy.ops.render.render(animation=True)
print("[flyaway] render done")

# ── encode ────────────────────────────────────────────────────────────────────
hits = globmod.glob(os.path.join(CWD,
    ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = hits[0] if hits else shutil.which("ffmpeg") or "ffmpeg"
out_mp4 = os.path.join(CWD, "out/jb100_flyaway.mp4")
subprocess.run([
    ffmpeg, "-y",
    "-framerate", str(FPS),
    "-start_number", "1",
    "-i", os.path.join(frames_dir, "frame_%04d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
    out_mp4,
], check=True)
shutil.rmtree(frames_dir)
print("[flyaway] wrote", out_mp4)
