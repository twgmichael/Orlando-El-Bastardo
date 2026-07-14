"""JB100 barrel roll — ship appears out of nowhere, executes one full 360°
barrel roll as it rushes past the camera, then punches to warp speed.

Path: (64, 57, -3) → (-28, -25, 6), quadratic accel over 9 s (phase 1).
Phase 2: 4× speed boost at t=9 s for 1 s (ship zooms into the distance).
Roll: one full 360° around the flight axis over 10 s.
Pilot seated in cockpit; world-space tracking follows the quaternion roll.
Camera sweeps 30% further back to shoulder position by 5 s, then holds.

Output: out/jb100_barrel_roll.mp4 (960×540, H.264)
"""
import bpy, math, os, glob as globmod, shutil, subprocess
from mathutils import Vector, Quaternion, Euler

FPS      = 24
N_FRAMES = FPS * 10  # 240
DURATION = 10.0
CWD      = os.getcwd()

# ── clear ─────────────────────────────────────────────────────────────────────
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene

# ── load ship ─────────────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/ships/jb100.glb"))
ship = bpy.data.objects["prop_jb100_A"]
ship.rotation_mode = 'QUATERNION'

# ── engine flare ──────────────────────────────────────────────────────────────
for slot in ship.material_slots:
    mat = slot.material
    if mat is None:
        continue
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        continue
    if "lamp" in mat.name:
        for frame in range(1, N_FRAMES + 1, 4):
            t = frame / FPS
            strength = 8.0 + 1.5 * math.sin(t * 9.0)
            bsdf.inputs["Emission Strength"].default_value = strength
            bsdf.inputs["Emission Strength"].keyframe_insert(
                "default_value", frame=frame)
    elif "exhaust" in mat.name:
        bsdf.inputs["Emission Strength"].default_value = 2.5

# Engine point lights parented in ship local space
for i, (lx, ly, lz) in enumerate([(-0.95, 3.01, 1.1), (0.95, 3.01, 1.1)]):
    ld = bpy.data.lights.new(f"engine_glow_{i}", type='POINT')
    ld.color  = (1.0, 0.38, 0.05)
    ld.energy = 400
    lo = bpy.data.objects.new(f"engine_glow_{i}", ld)
    scene.collection.objects.link(lo)
    lo.location = (lx, ly, lz)
    lo.parent   = ship

# Cabin light parented to ship in local space
cabin_ld = bpy.data.lights.new("cabin_light", type='POINT')
cabin_ld.color  = (1.0, 0.85, 0.60)
cabin_ld.energy = 50
cabin_lo = bpy.data.objects.new("cabin_light", cabin_ld)
scene.collection.objects.link(cabin_lo)
cabin_lo.location = (0.0, -0.92, 1.5)
cabin_lo.parent   = ship

# ── load hero ─────────────────────────────────────────────────────────────────
before   = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/characters/oeb_dressed_characters.glb"))
new_objs = set(bpy.data.objects) - before
hero     = bpy.data.objects["char_hero_v1"]

def under(o, root):
    while o:
        if o is root: return True
        o = o.parent
    return False

for o in list(new_objs):
    if o.name in bpy.data.objects and not under(o, hero):
        bpy.data.objects.remove(o, do_unlink=True)

# Cockpit offset in ship local space (nose = -Y local)
COCKPIT_LOCAL = Vector((0.0, -0.4, 0.23))

# Hero orientation in ship local space: face -Y (toward nose).
# Capture import rotation, then add π around Z so hero faces -Y local.
hero.rotation_mode = 'XYZ'
base_rot = tuple(hero.rotation_euler)
hero_local_quat = Euler(
    (base_rot[0], base_rot[1], base_rot[2] + math.pi), 'XYZ'
).to_quaternion()
hero.rotation_mode = 'QUATERNION'
hero.scale = (1.2, 1.2, 1.2)

idle_act = bpy.data.actions["idle_seated_relaxed"]
if hero.animation_data is None:
    hero.animation_data_create()

act_len    = idle_act.frame_range[1] - idle_act.frame_range[0]
idle_track = hero.animation_data.nla_tracks.new()
idle_track.name = "idle_base"
idle_strip = idle_track.strips.new(idle_act.name, 1, idle_act)
idle_strip.repeat        = math.ceil(N_FRAMES / act_len) + 1
idle_strip.use_auto_blend = False
idle_strip.blend_in      = 0
idle_strip.blend_out     = 0
idle_strip.extrapolation = 'NOTHING'

hero_act = bpy.data.actions.new("hero_barrel_roll")
hero.animation_data.action = hero_act

# ── camera ────────────────────────────────────────────────────────────────────
# Created here so it can receive keyframes inside the animation loop below.
# Starts at the original action-shot position, sweeps up and left to land
# over the ship's right shoulder as the barrel roll ends.
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 35
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

CAM_START = Vector((-10.5,  -9.5,  5.5))
CAM_END   = Vector((-29.35, -32.9, 8.75))  # 30% further pullback than before
CAM_MID   = CAM_START.lerp(CAM_END, 0.5)   # resting point reached at 5 s

def cam_ease(t):
    return t * t * (3.0 - 2.0 * t)   # smoothstep: slow start and end

# ── barrel roll: path + quaternion rotation ────────────────────────────────────
# Phase 1 (0–9 s): quadratic accel from far START to NORMAL_END.
# Phase 2 (9–10 s): 4× instantaneous speed — ship punches away.
START      = Vector((64.0,  57.0, -3.0))   # twice as far back along path
NORMAL_END = Vector((-28.0, -25.0,  6.0))  # reached at exactly t=9 s
travel_dir = (NORMAL_END - START).normalized()
DIST_1     = (NORMAL_END - START).length   # ≈ 123.6
PHASE1_DUR = 9.0
SPEED_AT_9 = 2.0 * DIST_1 / PHASE1_DUR    # instantaneous speed at phase boundary

# Base orientation: nose (-Y local) toward travel direction, dorsal (Z) up
base_quat = travel_dir.to_track_quat('-Y', 'Z')

ship.animation_data_create()
ship_act = bpy.data.actions.new("ship_barrel_roll")
ship.animation_data.action = ship_act

for frame in range(1, N_FRAMES + 2, 2):   # every 2 frames for smooth roll
    frame = min(frame, N_FRAMES)
    t = (frame - 1) / FPS

    # Phase 1: quadratic accel 0–9 s; Phase 2: 4× speed boost 9–10 s
    if t <= PHASE1_DUR:
        pos = START + travel_dir * (DIST_1 * (t / PHASE1_DUR) ** 2)
    else:
        pos = NORMAL_END + travel_dir * (SPEED_AT_9 * 4.0 * (t - PHASE1_DUR))

    # One full 360° roll over the full 10 s
    roll_angle = 2.0 * math.pi * (t / DURATION)
    roll_quat  = Quaternion(travel_dir, roll_angle)
    final_quat = roll_quat @ base_quat

    scene.frame_set(frame)
    ship.location            = pos
    ship.rotation_quaternion = final_quat
    ship.keyframe_insert(data_path="location",            frame=frame)
    ship.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    # Hero world position/rotation tracks the ship's quaternion roll
    cockpit_world            = pos + final_quat.to_matrix() @ COCKPIT_LOCAL
    hero.location            = cockpit_world
    hero.rotation_quaternion = final_quat @ hero_local_quat
    hero.keyframe_insert(data_path="location",            frame=frame)
    hero.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    # Camera: sweep to 50% position over first 5 s, then hold and track
    t_cam        = min(t / 5.0, 1.0)
    cam.location = CAM_START.lerp(CAM_MID, cam_ease(t_cam))
    cam_look     = cockpit_world - cam.location
    cam.rotation_euler = cam_look.to_track_quat('-Z', 'Y').to_euler()
    cam.keyframe_insert(data_path="location",       frame=frame)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame)

    if frame == N_FRAMES:
        break

# ── hero arm animation ─────────────────────────────────────────────────────────
controls = [
    ("lowerarm_l", 0, 20, 0.0,            1.0),
    ("lowerarm_r", 0, 20, math.pi * 0.5,  1.0),
    ("hand_l",     2, 12, math.pi * 0.25, 0.6),
    ("hand_r",     2, 12, math.pi * 0.75, 0.6),
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

# ── render settings ────────────────────────────────────────────────────────────
scene.render.fps  = FPS
scene.frame_start = 1
scene.frame_end   = N_FRAMES

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

# ── space environment ──────────────────────────────────────────────────────────
world = bpy.data.worlds.new("space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)
scene.world = world

bpy.ops.mesh.primitive_uv_sphere_add(radius=800, segments=64, ring_count=32)
star_sphere = bpy.context.active_object
star_sphere.name           = "env_star_sphere"
star_sphere.visible_shadow = False

star_mat = bpy.data.materials.new("mat_env_stars")
star_mat.use_nodes        = True
star_mat.use_backface_culling = False
snt = star_mat.node_tree
for n in list(snt.nodes):
    snt.nodes.remove(n)
s_out   = snt.nodes.new("ShaderNodeOutputMaterial")
s_emit  = snt.nodes.new("ShaderNodeEmission")
s_ramp  = snt.nodes.new("ShaderNodeValToRGB")
s_noise = snt.nodes.new("ShaderNodeTexNoise")
s_coord = snt.nodes.new("ShaderNodeTexCoord")

s_noise.inputs["Scale"].default_value     = 300.0
s_noise.inputs["Detail"].default_value    = 8.0
s_noise.inputs["Roughness"].default_value = 0.6

s_ramp.color_ramp.interpolation        = 'CONSTANT'
s_ramp.color_ramp.elements[0].position = 0.0
s_ramp.color_ramp.elements[0].color    = (0.003, 0.003, 0.006, 1)
s_ramp.color_ramp.elements[1].position = 0.75
s_ramp.color_ramp.elements[1].color    = (1.0, 1.0, 1.0, 1)

s_emit.inputs["Strength"].default_value = 8.0

snt.links.new(s_coord.outputs["Generated"], s_noise.inputs["Vector"])
snt.links.new(s_noise.outputs["Fac"],       s_ramp.inputs["Fac"])
snt.links.new(s_ramp.outputs["Color"],      s_emit.inputs["Color"])
snt.links.new(s_emit.outputs["Emission"],   s_out.inputs["Surface"])
star_sphere.data.materials.append(star_mat)

# Sun disc: upper-right of frame, bloom = halo
bpy.ops.mesh.primitive_uv_sphere_add(radius=18, location=(300, 500, 250),
                                      segments=32, ring_count=16)
sun_obj = bpy.context.active_object
sun_obj.name = "env_sun"
sun_mat = bpy.data.materials.new("mat_env_sun")
sun_mat.use_nodes = True
for n in list(sun_mat.node_tree.nodes):
    sun_mat.node_tree.nodes.remove(n)
sun_emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
sun_out  = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
sun_emit.inputs["Color"].default_value    = (1.0, 0.78, 0.30, 1)
sun_emit.inputs["Strength"].default_value = 120.0
sun_mat.node_tree.links.new(sun_emit.outputs["Emission"], sun_out.inputs["Surface"])
sun_obj.data.materials.append(sun_mat)

if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_bloom'):
    scene.eevee.use_bloom       = True
    scene.eevee.bloom_threshold = 0.6
    scene.eevee.bloom_intensity = 0.8
    scene.eevee.bloom_radius    = 6.0

# ── lighting ───────────────────────────────────────────────────────────────────
key = bpy.data.lights.new("key", type='SUN')
key.energy = 5.0
key.color  = (1.0, 0.92, 0.78)
ko = bpy.data.objects.new("key", key)
scene.collection.objects.link(ko)
ko.rotation_euler = (math.radians(55), 0, math.radians(-35))

fill = bpy.data.lights.new("fill", type='SUN')
fill.energy = 0.8
fo = bpy.data.objects.new("fill", fill)
scene.collection.objects.link(fo)
fo.rotation_euler = (math.radians(120), 0, math.radians(140))

# ── render frames ──────────────────────────────────────────────────────────────
frames_dir = os.path.join(CWD, "out/jb100_barrel_roll_frames")
os.makedirs(frames_dir, exist_ok=True)
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = os.path.join(frames_dir, "frame_")
print(f"[barrel_roll] rendering {N_FRAMES} frames …")
bpy.ops.render.render(animation=True)
print("[barrel_roll] render done")

# ── encode to MP4 ─────────────────────────────────────────────────────────────
hits = globmod.glob(os.path.join(CWD,
    ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = hits[0] if hits else shutil.which("ffmpeg") or "ffmpeg"
out_mp4 = os.path.join(CWD, "out/jb100_barrel_roll.mp4")
subprocess.run([
    ffmpeg, "-y",
    "-framerate", str(FPS),
    "-start_number", "1",
    "-i", os.path.join(frames_dir, "frame_%04d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
    out_mp4,
], check=True)
shutil.rmtree(frames_dir)
print("[barrel_roll] wrote", out_mp4)
