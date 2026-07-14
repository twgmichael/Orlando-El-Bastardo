"""JB100 space action — flyby in deep space with starfield, sun glow, engine flare.

Ship flies left to right at the action-shot camera angle. Pilot seated with
working controls. Space environment: procedural star field, emissive sun sphere,
EEVEE bloom.

Output: out/jb100_space_action.mp4 (960×540, H.264)
"""
import bpy, math, os, glob as globmod, shutil, subprocess
from mathutils import Vector

FPS = 24
N_FRAMES = FPS * 5   # 120
CWD = os.getcwd()

# ── clear ─────────────────────────────────────────────────────────────────────
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene

# ── load ship ─────────────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath=os.path.join(CWD, "assets/ships/jb100.glb"))
ship = bpy.data.objects["prop_jb100_A"]
ship.rotation_mode = 'XYZ'
ship.rotation_euler.z = math.radians(90)   # nose (-Y local) → +X world

# ── O2 tank colour ────────────────────────────────────────────────────────────
tanks_mat = bpy.data.materials.get("mat_jb100_tanks")
if tanks_mat:
    bsdf_t = tanks_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf_t:
        bsdf_t.inputs["Base Color"].default_value = (0.04, 0.08, 0.28, 1)

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

# Engine point lights parented in ship local space; ship rotated 90° so
# engines at +Y local trail behind as ship flies +X world.
for i, (lx, ly, lz) in enumerate([(-0.95, 3.01, 1.1), (0.95, 3.01, 1.1)]):
    ld = bpy.data.lights.new(f"engine_glow_{i}", type='POINT')
    ld.color  = (1.0, 0.38, 0.05)
    ld.energy = 400
    lo = bpy.data.objects.new(f"engine_glow_{i}", ld)
    scene.collection.objects.link(lo)
    lo.location = (lx, ly, lz)
    lo.parent   = ship

# Cabin light: dim warm point inside cockpit, parented to ship.
# Ship local position: (0, -0.92, 1.5) = centre of control panel, slightly above.
cabin_ld = bpy.data.lights.new("cabin_light", type='POINT')
cabin_ld.color  = (1.0, 0.85, 0.60)   # warm amber
cabin_ld.energy = 50                   # ~10% of key sun effect
cabin_lo = bpy.data.objects.new("cabin_light", cabin_ld)
scene.collection.objects.link(cabin_lo)
cabin_lo.location = (0.0, -0.92, 1.5)
cabin_lo.parent   = ship

# ── load hero ─────────────────────────────────────────────────────────────────
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

# ── hero: bar-scene pattern — no parenting ────────────────────────────────────
# Ship at 90°: cockpit local (0, -0.4, 0.23) → world (0.4, 0.0, 0.23)
COCKPIT_WX, COCKPIT_WY, COCKPIT_WZ = 0.4, 0.0, 0.23

hero.rotation_mode = 'XYZ'
base_rot = tuple(hero.rotation_euler)
nose_heading = math.radians(math.degrees(math.atan2(0.0, 1.0)) - 90.0)  # -π/2
hero.rotation_euler = (base_rot[0], base_rot[1], base_rot[2] + nose_heading)
hero.scale = (1.2, 1.2, 1.2)

# ── hero animation ─────────────────────────────────────────────────────────────
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

hero_act = bpy.data.actions.new("hero_flyby")
hero.animation_data.action = hero_act

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

# ── ship + hero flight path ────────────────────────────────────────────────────
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

# ── render settings ────────────────────────────────────────────────────────────
scene.render.fps   = FPS
scene.frame_start  = 1
scene.frame_end    = N_FRAMES

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
# EEVEE Next silently ignores complex World node trees — World shader approach
# confirmed non-functional. Using the reliable 1995 method: large inward-facing
# sphere with an emissive procedural star material. Object materials always
# evaluate correctly in EEVEE.

# Pure black world (no node complexity needed — sphere provides the stars)
world = bpy.data.worlds.new("space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)
scene.world = world

# Star sphere: normals OUT (default), backface_culling off so inner face
# renders; visible_shadow off so it doesn't block the sun lamps.
# Generated coordinate (normalised 0-1 bbox) gives even distribution.
# Threshold 0.75 + strength 8 ensures stars punch through ambient.
bpy.ops.mesh.primitive_uv_sphere_add(radius=800, segments=64, ring_count=32)
star_sphere = bpy.context.active_object
star_sphere.name = "env_star_sphere"
star_sphere.visible_shadow = False   # do NOT block sun lamps

star_mat = bpy.data.materials.new("mat_env_stars")
star_mat.use_nodes = True
star_mat.use_backface_culling = False  # render inner face from inside
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
s_ramp.color_ramp.elements[1].position = 0.75   # lower threshold = more stars
s_ramp.color_ramp.elements[1].color    = (1.0, 1.0, 1.0, 1)

s_emit.inputs["Strength"].default_value = 8.0   # bright enough to see

snt.links.new(s_coord.outputs["Generated"], s_noise.inputs["Vector"])
snt.links.new(s_noise.outputs["Fac"],       s_ramp.inputs["Fac"])
snt.links.new(s_ramp.outputs["Color"],      s_emit.inputs["Color"])
snt.links.new(s_emit.outputs["Emission"],   s_out.inputs["Surface"])
star_sphere.data.materials.append(star_mat)

# ── sun disc: emissive sphere; EEVEE bloom makes the halo ─────────────────────
# Positioned upper-right from camera's POV — rim-lights the ship as it passes
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

if hasattr(scene, 'eevee'):
    if hasattr(scene.eevee, 'use_bloom'):
        scene.eevee.use_bloom       = True
        scene.eevee.bloom_threshold = 0.6
        scene.eevee.bloom_intensity = 0.8
        scene.eevee.bloom_radius    = 6.0

# ── scene lighting ─────────────────────────────────────────────────────────────
# Warm key from sun direction; cool dim fill from shadow side
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

# ── render frames ──────────────────────────────────────────────────────────────
frames_dir = os.path.join(CWD, "out/jb100_space_action_frames")
os.makedirs(frames_dir, exist_ok=True)
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = os.path.join(frames_dir, "frame_")
print(f"[space_action] rendering {N_FRAMES} frames …")
bpy.ops.render.render(animation=True)
print("[space_action] render done")

# ── encode to MP4 ─────────────────────────────────────────────────────────────
hits = globmod.glob(os.path.join(CWD,
    ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = hits[0] if hits else shutil.which("ffmpeg") or "ffmpeg"
out_mp4 = os.path.join(CWD, "out/jb100_space_action.mp4")
subprocess.run([
    ffmpeg, "-y",
    "-framerate", str(FPS),
    "-start_number", "1",
    "-i", os.path.join(frames_dir, "frame_%04d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
    out_mp4,
], check=True)
shutil.rmtree(frames_dir)
print("[space_action] wrote", out_mp4)
