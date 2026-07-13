"""Temp: port-side cutaway — ship halved at x=0, pilot intact."""
import bpy, bmesh, os, math
from mathutils import Vector

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), "assets/ships/jb100.glb"))
ship = bpy.data.objects["prop_jb100_A"]
bm = bmesh.new()
bm.from_mesh(ship.data)
kill = [v for v in bm.verts if v.co.x < -0.02]
bmesh.ops.delete(bm, geom=kill, context='VERTS')
bm.to_mesh(ship.data)
bm.free()

before = set(bpy.data.objects)
SHOW_PILOT = os.environ.get("JB_PILOT", "1") == "1"
CAST = os.environ.get("JB_CAST", "hero")   # hero = dressed bar hero
src = ("assets/characters/oeb_dressed_characters.glb" if CAST == "hero"
       else "assets/characters/oeb_guy_characters.glb")
bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), src))
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
act = bpy.data.actions.get("idle_seated_relaxed")
if hero.animation_data is None:
    hero.animation_data_create()
hero.animation_data.action = act
hero.location = (0, -0.4, 0.23 if CAST == 'hero' else 0.49)
hero.rotation_mode = 'XYZ'
hero.rotation_euler.z += math.radians(180)
hero.scale = (1.2, 1.2, 1.2)
if not SHOW_PILOT:
    doomed = [o for o in bpy.data.objects if under(o, hero)]
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)

scene = bpy.context.scene
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
scene.frame_set(10)
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.02, 0.025, 1)
scene.world = world
key = bpy.data.lights.new("key", type='SUN'); key.energy = 6
ko = bpy.data.objects.new("key", key); scene.collection.objects.link(ko)
ko.rotation_euler = (math.radians(50), 0, math.radians(-30))
cock = bpy.data.lights.new("cock", type='POINT'); cock.energy = 200
co = bpy.data.objects.new("cock", cock); scene.collection.objects.link(co)
co.location = (-0.6, 0.1, 1.8)

cd = bpy.data.cameras.new("cam"); cd.lens = 50
cam = bpy.data.objects.new("cam", cd); scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (-9.35, 0, 1.4)
d = Vector((0, 0, 1.0)) - Vector(cam.location)
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
scene.render.resolution_x = 1280
scene.render.resolution_y = 960
scene.render.filepath = os.path.join(os.getcwd(), "out/tmp_jb100_cutaway.png")
bpy.ops.render.render(write_still=True)
print("[cutaway] wrote", scene.render.filepath)
