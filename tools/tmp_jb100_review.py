"""Temp: review renders of the JB5K — side/top framed aft-LEFT fore-RIGHT
to match the reference sheets."""
import bpy
import os
import math
from mathutils import Vector

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(
    os.getcwd(), "assets/ships/jb100.glb"))

scene = bpy.context.scene
try:
    scene.view_settings.view_transform = 'Standard'
except Exception:
    pass
for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = candidate
        break
    except TypeError:
        continue
world = bpy.data.worlds.new("space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.01, 0.015, 1)
scene.world = world

key = bpy.data.lights.new("key", type='SUN')
key.energy = 4.0
ko = bpy.data.objects.new("key", key)
scene.collection.objects.link(ko)
ko.rotation_euler = (math.radians(55), 0, math.radians(-35))
fill = bpy.data.lights.new("fill", type='SUN')
fill.energy = 1.2
fo = bpy.data.objects.new("fill", fill)
scene.collection.objects.link(fo)
fo.rotation_euler = (math.radians(120), 0, math.radians(140))

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 50
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x = 720
scene.render.resolution_y = 540

target = Vector((0, 0, 0.9))
# side from -X puts aft (+Y) on the LEFT of frame, fore (-Y) on the RIGHT
views = {
    "port":   (-14, 0, 1.6),
    "front":  (0, -14, 1.8),
    "back":   (0, 14, 2.0),
    "top":    (0, 0.01, 16.0),
    "bottom": (0, 0.01, -16.0),
    "action": (-10.5, -9.5, 5.5),
}
from mathutils import Matrix
# top/bottom framed aft-LEFT fore-RIGHT like the side sheets
plan_rots = {
    "top":    Matrix(((0, 1, 0), (-1, 0, 0), (0, 0, 1))).to_euler(),
    "bottom": Matrix(((0, -1, 0), (-1, 0, 0), (0, 0, -1))).to_euler(),
}
for name, pos in views.items():
    cam.location = pos
    if name in plan_rots:
        cam.rotation_euler = plan_rots[name]
    else:
        direction = target - Vector(pos)
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    if name == "action":                      # banked hero angle
        cam.rotation_euler.rotate_axis('Z', math.radians(-18))
        cam_data.lens = 42
    else:
        cam_data.lens = 50
    scene.render.filepath = os.path.join(os.getcwd(), f"out/tmp_jb100_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("[review] wrote", scene.render.filepath)

# ── pilot for scale: the OEB DXF guy seated in the chair ─────────────────────
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), "assets/characters/oeb_dressed_characters.glb"))
new_objs = set(bpy.data.objects) - before
hero = bpy.data.objects.get("char_hero_v1")
def under(o, root):
    while o:
        if o is root:
            return True
        o = o.parent
    return False
for o in list(new_objs):
    if o.name in bpy.data.objects and not under(o, hero):
        bpy.data.objects.remove(o, do_unlink=True)
if hero:
    act = bpy.data.actions.get("idle_seated_relaxed") or \
          next((a for a in bpy.data.actions
                if "seated" in a.name or "Sitting" in a.name), None)
    if hero.animation_data is None:
        hero.animation_data_create()
    hero.animation_data.action = act
    scene.frame_set(10)
    hero.location = (0, -0.4, 0.17)
    hero.rotation_mode = 'XYZ'
    hero.rotation_euler.z += math.radians(180)   # face the nose (-Y)
    hero.scale = (1.2, 1.2, 1.2)
    for name, pos in views.items():
        cam.location = pos
        if name in plan_rots:
            cam.rotation_euler = plan_rots[name]
        else:
            direction = target - Vector(pos)
            cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        cam_data.lens = 42 if name == "action" else 50
        if name == "action":
            cam.rotation_euler.rotate_axis('Z', math.radians(-18))
        scene.render.filepath = os.path.join(
            os.getcwd(), f"out/tmp_jb100_pilot_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("[review] wrote", scene.render.filepath)
