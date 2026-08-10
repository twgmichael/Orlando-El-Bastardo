#!/usr/bin/env python3
"""build_set.py -- headless Blender: assemble a real, kitbashed set from a
SetSpec (schemas/setspec.schema.json), the set designer kitbash tier's
"generic set assembler" (docs/planning/PRODUCTION-DESIGNER-PLAN.md,
"Build order" step 2). Generalizes tools/build_scifi_bar.py's hardcoded
LAYOUT table into data: the designer authors a spec, not a script.

Runs identically for local iteration (fast look-adjust-look loop against
a spec on disk) and as a worker job (docs/planning/WORKER-AGENT-PLAN.md,
BlenderCLIAdapter script_file mode) -- same script either way, same
convention as tools/build_scifi_bar.py/tools/set_designer.py.

  blender --background --factory-startup --python tools/build_set.py -- \\
      --spec data/setspecs/bar_scene_scifi.setspec.json \\
      --output assets/sets/bar_scene_scifi

Acceptance (PRODUCTION-DESIGNER-PLAN.md step 2): rebuilding the existing
sci-fi bar from a spec reproduces it -- same canonical node, same
placement count, same poly count, allowing for nondeterministic binary
bytes. See docs/setspecs/bar_scene_scifi.setspec.json for that fixture.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_set")
    p.add_argument("--spec", required=True)
    p.add_argument("--output", required=True,
                   help="Output path stem (no extension); .glb/.usdc appended")
    return p.parse_args(argv)


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_base(base_placeholder, remove_from_base):
    if not base_placeholder:
        return
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.getcwd(), base_placeholder))
    for name in remove_from_base or []:
        old = bpy.data.objects.get(name)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data_clear()


def place_layout(kit_root, layout):
    """Import each distinct kit piece once as a template (world transform
    baked into vertex data, same as build_scifi_bar.py), instantiate
    linked copies at each placement, return the placed objects.
    """
    pieces = sorted({row["piece"] for row in layout})
    templates = {}
    for piece in pieces:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=os.path.join(os.getcwd(), kit_root, piece + ".glb"))
        imported = list(set(bpy.data.objects) - before)
        meshes = [o for o in imported if o.type == 'MESH']
        if not meshes:
            sys.exit(f"[build_set] ERROR: no mesh in kit piece {piece!r}")
        for o in meshes:
            o.data.transform(o.matrix_world)
            o.matrix_world = Matrix.Identity(4)
            o.parent = None
        for o in imported:
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)
        templates[piece] = meshes

    placed = []
    for row in layout:
        x, y, z = row["position"]
        rot = row.get("z_rotation_deg", 0)
        for tmpl in templates[row["piece"]]:
            dup = tmpl.copy()
            bpy.context.scene.collection.objects.link(dup)
            dup.location = (x, y, z)
            dup.rotation_euler = (0.0, 0.0, math.radians(rot))
            placed.append(dup)
    for objs in templates.values():
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
    return placed


def build_primitive_prop(spec):
    """One prop as a stack of box/cylinder primitives joined into a
    single mesh named spec['id'], generalizing build_scifi_bar.py's
    bespoke barstool/bar-counter bmesh code into data.
    """
    mesh = bpy.data.meshes.new(f"{spec['id']}_mesh")
    bm = bmesh.new()
    for prim in spec["primitives"]:
        cx, cy, cz = prim["center"]
        if prim["shape"] == "box":
            sx, sy, sz = prim["size"]
            res = bmesh.ops.create_cube(bm, size=1.0)
            for v in res["verts"]:
                v.co = (v.co.x * sx + cx, v.co.y * sy + cy, v.co.z * sz + cz)
        else:  # cylinder
            res = bmesh.ops.create_cone(
                bm, cap_ends=True, segments=16,
                radius1=prim["radius"], radius2=prim["radius"],
                depth=prim["height"])
            for v in res["verts"]:
                v.co.x += cx
                v.co.y += cy
                v.co.z += cz
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(spec["id"], mesh)
    obj.location = tuple(spec["position"])
    bpy.context.scene.collection.objects.link(obj)

    material = spec.get("material")
    if material:
        mat = bpy.data.materials.new(f"mat_{spec['id']}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            if "base_color" in material:
                bsdf.inputs["Base Color"].default_value = tuple(material["base_color"])
            if "roughness" in material:
                bsdf.inputs["Roughness"].default_value = material["roughness"]
        obj.data.materials.append(mat)
    return obj


def apply_marks(marks):
    for mark in marks or []:
        obj = bpy.data.objects.get(mark["name"])
        if obj is None:
            obj = bpy.data.objects.new(mark["name"], None)
            obj.empty_display_size = 0.2
            bpy.context.scene.collection.objects.link(obj)
        obj.location = tuple(mark["position"])


def apply_cameras(cameras):
    for cam_spec in cameras or []:
        name = cam_spec["name"]
        if bpy.data.objects.get(name):
            continue
        cam_data = bpy.data.cameras.new(name)
        cam_data.lens = cam_spec.get("lens_mm", 35)
        cam = bpy.data.objects.new(name, cam_data)
        cam.location = tuple(cam_spec["position"])
        if cam_spec.get("aim_at_mark"):
            target = bpy.data.objects.get(cam_spec["aim_at_mark"])
            if target is None:
                sys.exit(f"[build_set] ERROR: camera {name!r} aim_at_mark "
                         f"{cam_spec['aim_at_mark']!r} does not exist")
            aim = target.location
        elif cam_spec.get("aim_at"):
            aim = Vector(cam_spec["aim_at"])
        else:
            aim = None
        if aim is not None:
            direction = Vector(aim) - Vector(cam.location)
            if direction.length > 0:
                cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.collection.objects.link(cam)


def join_and_fix_materials(placed, canonical_node, force_opaque):
    bpy.ops.object.select_all(action='DESELECT')
    for o in placed:
        o.select_set(True)
    bpy.context.view_layer.objects.active = placed[0]
    bpy.ops.object.join()
    set_obj = bpy.context.view_layer.objects.active
    set_obj.name = canonical_node
    set_obj.data.name = f"{canonical_node}_mesh"

    if force_opaque:
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
    return set_obj


def main():
    args = parse_args()
    spec = json.loads(open(args.spec).read())

    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    clear_scene()
    import_base(spec.get("base_placeholder"), spec.get("remove_from_base"))

    for prop_spec in spec.get("primitive_props", []):
        old = bpy.data.objects.get(prop_spec["id"])
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        build_primitive_prop(prop_spec)

    apply_marks(spec.get("marks"))
    apply_cameras(spec.get("cameras"))

    placed = place_layout(spec["kit_root"], spec["layout"])
    if not placed:
        sys.exit("[build_set] ERROR: layout produced no placed objects")
    force_opaque = (spec.get("material_fixes") or {}).get("force_opaque", False)
    set_obj = join_and_fix_materials(placed, spec["canonical_node"], force_opaque)

    print(f"[build_set] {spec['canonical_id']}: {len(spec['layout'])} kit "
          f"placements, {len(spec.get('primitive_props', []))} primitive "
          f"prop(s), {len(set_obj.data.polygons)} polys, "
          f"{len(set_obj.material_slots)} material slots")

    glb = out_stem + ".glb"
    print(f"[build_set] Exporting {glb}")
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB',
                              use_selection=False, export_cameras=True)

    export_cfg = spec.get("export", {})
    if export_cfg.get("usdc", True):
        usdc = out_stem + ".usdc"
        print(f"[build_set] Exporting {usdc}")
        try:
            bpy.ops.wm.usd_export(filepath=usdc, export_materials=True)
        except TypeError:
            bpy.ops.wm.usd_export(filepath=usdc)

    manifest = {
        "canonical_id": spec["canonical_id"],
        "canonical_node": spec["canonical_node"],
        "kit_placements": len(spec["layout"]),
        "primitive_props": [p["id"] for p in spec.get("primitive_props", [])],
        "marks": [m["name"] for m in spec.get("marks", [])],
        "cameras": [c["name"] for c in spec.get("cameras", [])],
        "polygon_count": len(set_obj.data.polygons),
        "glb": glb,
    }
    manifest_path = out_stem + ".manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"[build_set] Wrote {manifest_path}")
    print("[build_set] Done.")


if __name__ == "__main__":
    main()
