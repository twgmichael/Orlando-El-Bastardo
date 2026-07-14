"""JB100 6-second action-angle flyby with pilot working controls.

Ship flies screen-left to screen-right at the action-shot camera angle.
Pilot: idle_seated_relaxed looping as NLA base, additive forearm/hand
oscillation strip on top to read as "working the controls."

Output: out/jb100_flyby.mp4 (960x540, H.264)
"""
import bpy, math, os, glob as globmod, shutil, subprocess
from mathutils import Vector, Matrix

FPS = 24
N_FRAMES = FPS * 5   # 120
CWD = os.getcwd()

# ── clear ─────────────────────────────────────────────────────────────────────
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── load ship ─────────────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/ships/jb100.glb"))
ship = bpy.data.objects["prop_jb100_A"]
ship.rotation_mode = 'XYZ'
ship.rotation_euler.z = math.radians(90)   # nose (-Y local) → +X world = direction of travel

# ── load hero, strip bartender and extras ─────────────────────────────────────
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

# ── hero: no parenting — explicit world-space position/rotation (bar-scene pattern)
# Ship rotated 90°: cockpit local (0, -0.4, 0.23) → world (0.4, 0.0, 0.23)
COCKPIT_WX, COCKPIT_WY, COCKPIT_WZ = 0.4, 0.0, 0.23

hero.rotation_mode = 'XYZ'
base_rot = tuple(hero.rotation_euler)          # read imported rotation
# Face ship nose (+X world). Bar-scene formula: atan2(dy, dx) - 90°
nose_heading = math.radians(math.degrees(math.atan2(0.0, 1.0)) - 90.0)  # = -π/2
hero.rotation_euler = (base_rot[0], base_rot[1], base_rot[2] + nose_heading)
hero.scale = (1.2, 1.2, 1.2)

scene = bpy.context.scene

# ── hero action: location tracking + arm oscillation (active action) ──────────
idle_act = bpy.data.actions["idle_seated_relaxed"]
if hero.animation_data is None:
    hero.animation_data_create()

# idle_seated as NLA base (body/leg pose)
act_len = idle_act.frame_range[1] - idle_act.frame_range[0]
idle_track = hero.animation_data.nla_tracks.new()
idle_track.name = "idle_base"
idle_strip = idle_track.strips.new(idle_act.name, 1, idle_act)
idle_strip.repeat = math.ceil(N_FRAMES / act_len) + 1
idle_strip.use_auto_blend = False
idle_strip.blend_in = 0
idle_strip.blend_out = 0
idle_strip.extrapolation = 'NOTHING'

# Active action: location keyframes + arm overrides (higher priority than NLA)
hero_act = bpy.data.actions.new("hero_flyby")
hero.animation_data.action = hero_act

ARM_CYCLE = 1.0
HAND_CYCLE = 0.6
controls = [
    ("lowerarm_l", 0, 20, 0.0,            ARM_CYCLE),
    ("lowerarm_r", 0, 20, math.pi * 0.5,  ARM_CYCLE),
    ("hand_l",     2, 12, math.pi * 0.25, HAND_CYCLE),
    ("hand_r",     2, 12, math.pi * 0.75, HAND_CYCLE),
]

bpy.context.view_layer.objects.active = hero
bpy.ops.object.mode_set(mode='POSE')
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

# ── ship flyby: X from -14 to +14, hero location tracks with cockpit offset ───
ship.animation_data_create()
ship_act = bpy.data.actions.new("ship_flyby")
ship.animation_data.action = ship_act

for i, frame in enumerate([1, 40, 80, 120]):
    x = -14.0 + 28.0 * (i / 3.0)
    scene.frame_set(frame)
    ship.location.x = x
    ship.keyframe_insert(data_path="location", index=0, frame=frame)
    hero.location = (x + COCKPIT_WX, COCKPIT_WY, COCKPIT_WZ)
    hero.keyframe_insert(data_path="location", frame=frame)

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

# ── camera: action-shot angle (static) ────────────────────────────────────────
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

# ── render frames ─────────────────────────────────────────────────────────────
frames_dir = os.path.join(CWD, "out/jb100_flyby_frames")
os.makedirs(frames_dir, exist_ok=True)
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = os.path.join(frames_dir, "frame_")
print(f"[flyby] rendering {N_FRAMES} frames …")
bpy.ops.render.render(animation=True)
print("[flyby] render done")

# ── encode to MP4 ─────────────────────────────────────────────────────────────
hits = globmod.glob(os.path.join(CWD,
    ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = hits[0] if hits else shutil.which("ffmpeg") or "ffmpeg"
out_mp4 = os.path.join(CWD, "out/jb100_flyby.mp4")
subprocess.run([
    ffmpeg, "-y",
    "-framerate", str(FPS),
    "-start_number", "1",
    "-i", os.path.join(frames_dir, "frame_%04d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
    out_mp4,
], check=True)
shutil.rmtree(frames_dir)
print("[flyby] wrote", out_mp4)
