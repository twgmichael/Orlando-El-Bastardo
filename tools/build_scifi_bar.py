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

# Floor: 4x4 grid of 2m tiles, mixed for visual variety
for i, x in enumerate((-3, -1, 1, 3)):
    for j, y in enumerate((-3, -1, 1, 3)):
        piece = "FloorTile_Basic" if (i + j) % 2 == 0 else "FloorTile_Basic2"
        LAYOUT.append((piece, (x, y, -0.09), 0))

# Back wall (y=+4): two 4m modules, one plain + one window band
LAYOUT += [
    ("Wall_2",                (-2, 4, 0), 0),
    ("LongWindow_Wall_SideA", (2, 4, 0), 0),
]
# Side walls (x=±4): two 4m modules each, rotated to run along y
LAYOUT += [
    ("Wall_1", (-4, -2, 0),  90),
    ("Wall_3", (-4,  2, 0),  90),
    ("Wall_1", (4, -2, 0),  -90),
    ("Wall_4", (4,  2, 0),  -90),
]
# Corner columns
LAYOUT += [
    ("Column_1", (-3.7, 3.7, 0), 0),
    ("Column_1", (3.7, 3.7, 0), 0),
    ("Column_2", (-3.7, -3.7, 0), 0),
    ("Column_2", (3.7, -3.7, 0), 0),
]
# Backbar dressing: shelves behind the counter, tech + clutter
LAYOUT += [
    ("Props_Shelf_Tall", (-2.2, 3.55, 0), 0),
    ("Props_Shelf",      (0.2, 3.55, 0), 0),
    ("Props_Computer",   (3.1, 3.4, 0), 180),
    ("Props_Vessel_Tall", (-3.4, 3.1, 0), 0),
    ("Props_Crate",      (-3.35, -2.6, 0), 15),
    ("Props_CrateLong",  (-3.3, -1.6, 0), 90),
    ("Props_Teleporter_1", (3.2, 2.6, 0), -90),
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

    # 1. Carry over props/marks/cameras; drop the grey-box set
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), PLACEHOLDERS))
    old = bpy.data.objects.get("set_bar_small_A")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()

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
