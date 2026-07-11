#!/usr/bin/env python3
"""
build_scifi_bar.py — Headless Blender: assemble the sci-fi bar set from the
Modular Sci-Fi kit (CC0, see docs/PROVENANCE.md).

Loads the placeholder scene (props/marks/cameras carry over verbatim),
replaces the grey-box `set_bar_small_A` with a kit-built 8x8 m room — floor
grid, back/side walls (front open for the cameras), corner columns, backbar
shelves and set dressing — joins the kit pieces into ONE mesh named exactly
`set_bar_small_A`, and exports the whole scene bundle to GLB + USDC.

Layout is data (LAYOUT table below): piece name, position, z-rotation deg.
Floor tiles sit at z = -0.09 so their walking surface is exactly z = 0.

Run from repo root:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/build_scifi_bar.py -- \
    --output assets/sets/bar_scene_scifi
"""

import sys
import os
import argparse
import math

import bpy
from mathutils import Matrix

KIT = "assets/Ultimate Modular Sci-Fi - Feb 2021/GLB"
PLACEHOLDERS = "assets/placeholders/bar_scene_placeholders.glb"

# (kit piece, (x, y, z), z-rotation degrees)
LAYOUT = []

# Floor: 4x4 grid of the PLAIN tile (simplified 2026-07-06 — the detailed
# Basic/Basic2 checker read too busy under the characters)
for x in (-3, -1, 1, 3):
    for y in (-3, -1, 1, 3):
        LAYOUT.append(("FloorTile_Empty", (x, y, -0.09), 0))

# Simplified set (2026-07-06): TWO walls only — back + left — no columns,
# no dressing. Head-on-friendly composition.
LAYOUT += [
    ("Wall_2",                (-2, 4, 0), 0),   # back wall, plain half
    ("LongWindow_Wall_SideA", (2, 4, 0), 0),    # back wall, window half
    ("Wall_1", (-4, -2, 0), 90),                # left wall
    ("Wall_3", (-4,  2, 0), 90),
]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_scifi_bar")
    p.add_argument("--output", default="assets/sets/bar_scene_scifi")
    return p.parse_args(argv)


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # 1. Carry over props/marks/cameras; drop the grey-box set AND the old
    # single-slab counter (rebuilt from boxes below)
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), PLACEHOLDERS))
    for name in ("set_bar_small_A", "prop_bar_counter_A"):
        old = bpy.data.objects.get(name)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()

    # Barstool + raised sit (2026-07-06, per reference photos): the UAL sit
    # is a chair pose (pelvis 0.44 above its origin), so a bar-height perch
    # means raising the WHOLE pose — done via the spawn mark's z (the
    # exporter places the actor at the mark's full xyz, and the stool
    # follows the mark xy via at_mark). Seat 0.75 m; hero origin at
    # 0.75 − 0.44 = 0.31; his clip-floor feet then hover at 0.31 — exactly
    # where the footrest ring sits. Mark pulled back to y = −1.13 so knees
    # clear the counter body and tuck under the top's overhang.
    SEAT_TOP = 0.75
    CLIP_PELVIS = 0.44
    mark = bpy.data.objects.get("hero_barstool_A")
    if mark:
        mark.location.y = -1.13
        mark.location.z = SEAT_TOP - CLIP_PELVIS
    # Medium-shot cameras (2026-07-11, screenplay vocabulary): positioned
    # from the marks so they track any future mark moves. Both aim with
    # -Z forward / Y up (Blender camera convention).
    from mathutils import Vector as _V
    bar_mark = bpy.data.objects.get("bartender_idle_A")
    hero_mark = bpy.data.objects.get("hero_barstool_A")
    if bar_mark and hero_mark:
        bm, hm = bar_mark.location, hero_mark.location

        def add_cam(name, pos, aim):
            if bpy.data.objects.get(name):
                return
            cd = bpy.data.cameras.new(name)
            cd.lens = 35
            cam = bpy.data.objects.new(name, cd)
            cam.location = pos
            direction = _V(aim) - _V(pos)
            cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            bpy.context.scene.collection.objects.link(cam)

        # Waist-up on the bartender, shot from the patron side of the bar
        add_cam("cam_medium_bartender",
                (bm.x, bm.y - 2.3, 1.45), (bm.x, bm.y, 1.3))
        # Seated hero from behind: camera on the bartender→hero axis
        # extended 1.6 m past the hero, so the hero's back fills the
        # foreground and the bartender stays centered beyond.
        away = (_V((hm.x, hm.y, 0.0)) - _V((bm.x, bm.y, 0.0))).normalized()
        add_cam("cam_medium_hero_back",
                (hm.x + 1.6 * away.x, hm.y + 1.6 * away.y, 1.55),
                (bm.x, bm.y, 1.25))

    # Entrance marks (2026-07-11, walk-in support): hero_entry_A near the
    # left wall and hero_stool_front_A just left of the stool — the walk
    # lane is y = -1.13 (clears the counter-top overhang at y = -0.7).
    # Both floor-level; the raised barstool z is reached by the settle move.
    for mname, mloc in (("hero_entry_A", (-3.2, -1.13, 0.0)),
                        ("hero_stool_front_A", (1.05, -1.13, 0.0))):
        if bpy.data.objects.get(mname) is None:
            e = bpy.data.objects.new(mname, None)
            e.empty_display_size = 0.2
            e.location = mloc
            bpy.context.scene.collection.objects.link(e)

    old_stool = bpy.data.objects.get("prop_stool_A")
    if old_stool:
        bpy.data.objects.remove(old_stool, do_unlink=True)
    import bmesh as _bm
    stool_mesh = bpy.data.meshes.new("prop_stool_A_mesh")
    sbm = _bm.new()
    for radius, height, z_center in (
        (0.22, 0.04, 0.02),                    # base disc
        (0.06, 0.72, 0.36),                    # post
        (0.16, 0.04, 0.30),                    # footrest ring
        (0.20, 0.06, SEAT_TOP - 0.03),         # seat (top = SEAT_TOP)
    ):
        res = _bm.ops.create_cone(sbm, cap_ends=True, segments=16,
                                  radius1=radius, radius2=radius, depth=height)
        for v in res["verts"]:
            v.co.z += z_center
    sbm.to_mesh(stool_mesh)
    sbm.free()
    stool_mesh.update()
    stool = bpy.data.objects.new("prop_stool_A", stool_mesh)
    stool.location = (1.5, -1.13, 0.0)         # exporter re-snaps xy to mark
    bpy.context.scene.collection.objects.link(stool)
    stool_mat = bpy.data.materials.new("mat_stool")
    stool_mat.use_nodes = True
    sb = stool_mat.node_tree.nodes.get("Principled BSDF")
    if sb:
        sb.inputs["Base Color"].default_value = (0.30, 0.31, 0.35, 1.0)
        sb.inputs["Roughness"].default_value = 0.5
    stool.data.materials.append(stool_mat)

    # 1b. Box-built bar counter (canonical node name preserved): plinth +
    # body + overhanging top. Stool/glass/bottle stay primitive, carried over.
    import bmesh
    bar_mesh = bpy.data.meshes.new("prop_bar_counter_A_mesh")
    bm = bmesh.new()
    BAR_H = 0.97   # 2026-07-06: bar lowered 3% (top surface 1.12 → ~1.086 m)
    for size, center in (
        ((5.8, 1.30, 0.15 * BAR_H), (0, 0, 0.075 * BAR_H)),   # plinth
        ((5.6, 1.10, 0.85 * BAR_H), (0, 0, 0.575 * BAR_H)),   # body
        ((6.0, 1.40, 0.12 * BAR_H), (0, 0, 1.06 * BAR_H)),    # top slab
    ):
        res = bmesh.ops.create_cube(bm, size=1.0)
        verts = res["verts"]
        for v in verts:
            v.co = (v.co.x * size[0] + center[0],
                    v.co.y * size[1] + center[1],
                    v.co.z * size[2] + center[2])
    bm.to_mesh(bar_mesh)
    bm.free()
    bar_mesh.update()
    bar_obj = bpy.data.objects.new("prop_bar_counter_A", bar_mesh)
    bar_obj.location = (0.0, 0.0, 0.0)
    bpy.context.scene.collection.objects.link(bar_obj)
    bar_mat = bpy.data.materials.new("mat_bar_counter")
    bar_mat.use_nodes = True
    bsdf = bar_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.28, 0.29, 0.33, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
    bar_obj.data.materials.append(bar_mat)

    # 2. Import each distinct kit piece once as a template. Imports arrive as
    # small hierarchies with axis-conversion transforms — bake every mesh's
    # WORLD transform into its vertex data so placement below is a pure
    # translate + z-rotation, then drop the non-mesh carriers.
    templates = {}
    for piece in sorted({p for p, _pos, _r in LAYOUT}):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=os.path.join(os.getcwd(), KIT, piece + ".glb"))
        imported = list(set(bpy.data.objects) - before)
        meshes = [o for o in imported if o.type == 'MESH']
        if not meshes:
            print(f"[build_scifi_bar] ERROR: no mesh in {piece}")
            sys.exit(1)
        for o in meshes:
            o.data.transform(o.matrix_world)
            o.matrix_world = Matrix.Identity(4)
            o.parent = None
        for o in imported:               # remove empties/armature carriers
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)
        templates[piece] = meshes

    # 3. Instantiate the layout (linked-mesh copies; world-space geometry)
    placed = []
    for piece, (x, y, z), rot in LAYOUT:
        for tmpl in templates[piece]:
            dup = tmpl.copy()            # shares baked mesh data
            bpy.context.scene.collection.objects.link(dup)
            dup.location = (x, y, z)
            dup.rotation_euler = (0.0, 0.0, math.radians(rot))
            placed.append(dup)
    for objs in templates.values():      # remove template originals
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)

    # 4. Join everything into ONE canonical set mesh
    bpy.ops.object.select_all(action='DESELECT')
    for o in placed:
        o.select_set(True)
    bpy.context.view_layer.objects.active = placed[0]
    bpy.ops.object.join()
    set_obj = bpy.context.view_layer.objects.active
    set_obj.name = "set_bar_small_A"
    set_obj.data.name = "set_bar_small_A_mesh"

    # Kit materials import alpha-HASHED with alpha ≈ 0 (renders invisible;
    # found 2026-07-06). Force everything opaque, alpha 1, no culling.
    for slot in set_obj.material_slots:
        m = slot.material
        if not m:
            continue
        if hasattr(m, "blend_method"):
            m.blend_method = 'OPAQUE'
        m.use_backface_culling = False
        if m.use_nodes:
            bsdf = m.node_tree.nodes.get("Principled BSDF")
            if bsdf and "Alpha" in bsdf.inputs:
                for link in list(bsdf.inputs["Alpha"].links):
                    m.node_tree.links.remove(link)
                bsdf.inputs["Alpha"].default_value = 1.0
    print(f"[build_scifi_bar] set joined: {len(LAYOUT)} placements, "
          f"{len(set_obj.data.polygons)} polys, "
          f"{len(set_obj.material_slots)} material slots")

    # 5. Export the scene bundle
    glb = out_stem + ".glb"
    print(f"[build_scifi_bar] Exporting {glb}")
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB',
                              use_selection=False, export_cameras=True)
    usdc = out_stem + ".usdc"
    print(f"[build_scifi_bar] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)
    print("[build_scifi_bar] Done.")


if __name__ == "__main__":
    main()
