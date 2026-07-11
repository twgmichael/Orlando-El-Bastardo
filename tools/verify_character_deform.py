"""Temp check: reproduce the TODO repro — import a character GLB, scrub
into strips, and measure evaluated vertex displacement per skinned mesh.
Usage: blender --background --factory-startup --python this.py -- <glb>"""
import bpy
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
glb = argv[0] if argv else "assets/characters/oeb_dressed_characters.glb"

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), glb))

scene = bpy.context.scene

# Report NLA state as imported
strips = []
for o in bpy.data.objects:
    if o.type == 'ARMATURE' and o.animation_data:
        ad = o.animation_data
        print(f"[verify] {o.name}: active_action={ad.action.name if ad.action else None}")
        for tr in ad.nla_tracks:
            for st in tr.strips:
                print(f"[verify]   track '{tr.name}' mute={tr.mute} "
                      f"strip '{st.name}' {st.frame_start:.0f}..{st.frame_end:.0f}")
                strips.append((o, tr, st))

def eval_verts(mesh_obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = mesh_obj.evaluated_get(deps)
    me = ev.to_mesh()
    out = [ev.matrix_world @ v.co.copy() for v in me.vertices]
    ev.to_mesh_clear()
    return out

# The glTF importer mutes all NLA tracks, so "scrub into a strip" evaluates
# nothing (the original repro partly measured this importer artifact).
# Downstream (export_blender.py) assigns actions per cue — test that way:
# assign each strip's action to its armature and scrub within the range.
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
fails = 0
for arm, tr, st in strips:
    arm.animation_data.action = st.action
    f0, f1 = (int(x) for x in st.action.frame_range)
    mid = max(f0 + 1, (f0 + f1) // 2)
    mine = [m for m in meshes if m.parent is arm
            or (m.parent and m.parent.parent is arm)]
    scene.frame_set(f0)
    base = {m.name: eval_verts(m) for m in mine}
    scene.frame_set(mid)
    for name, verts in base.items():
        m = bpy.data.objects[name]
        moved = max(((a - b).length for a, b in zip(eval_verts(m), verts)),
                    default=0.0)
        status = "OK " if moved > 0.005 else "FAIL"
        if status == "FAIL":
            fails += 1
        print(f"[verify] {status} {st.name:24s} {name:36s} max-disp {moved:.4f} m")
    arm.animation_data.action = None
print(f"[verify] DONE fails={fails}")
