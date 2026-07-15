#!/usr/bin/env python3
"""
Build a simple GLB asset from Blender primitives and render a preview.

Run by the harness worker through Blender:
  blender --background --python tools/primitive_asset_builder.py -- \
    --spec-json '{"canonical_id":"ship_demo_A",...}' \
    --output assets/ships/ship_demo_A.glb \
    --preview-output renders/asset_previews/ship_demo_A.png \
    --manifest-output out/asset_builds/ship_demo_A.json
"""

import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    parser = argparse.ArgumentParser(prog="primitive_asset_builder")
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview-output", required=True)
    parser.add_argument("--manifest-output", required=True)
    return parser.parse_args()


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def cube(name, location, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def sphere(name, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def make_scene(spec):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    hull = material("bruised_red_hull", (0.45, 0.08, 0.06, 1))
    dark = material("dark_canopy", (0.02, 0.05, 0.08, 0.75))
    metal = material("burnt_metal", (0.22, 0.21, 0.19, 1))
    glow = material("engine_glow", (0.1, 0.45, 1.0, 1))

    objects = []
    objects.append(cube("main_hull", (0, 0, 0), (3.2, 1.2, 0.55), hull))
    nose = cube("wedge_nose", (1.95, 0, 0.05), (1.55, 0.85, 0.42), hull)
    nose.rotation_euler[2] = 0.0
    objects.append(nose)
    objects.append(sphere("cockpit_canopy", (0.45, 0, 0.42), (0.58, 0.42, 0.24), dark))

    left_wing = cube("left_swept_wing", (-0.2, 1.05, -0.06), (2.4, 1.0, 0.12), hull)
    left_wing.rotation_euler[2] = -0.35
    right_wing = cube("right_swept_wing", (-0.2, -1.05, -0.06), (2.4, 1.0, 0.12), hull)
    right_wing.rotation_euler[2] = 0.35
    objects.extend([left_wing, right_wing])

    objects.append(cylinder("engine_left", (-1.85, 0.43, -0.02), 0.28, 0.85, metal, rotation=(0, 1.5708, 0)))
    objects.append(cylinder("engine_right", (-1.85, -0.43, -0.02), 0.28, 0.85, metal, rotation=(0, 1.5708, 0)))
    objects.append(cylinder("engine_glow_left", (-2.3, 0.43, -0.02), 0.2, 0.06, glow, rotation=(0, 1.5708, 0)))
    objects.append(cylinder("engine_glow_right", (-2.3, -0.43, -0.02), 0.2, 0.06, glow, rotation=(0, 1.5708, 0)))

    fin = cube("crooked_tail_fin", (-1.1, 0.18, 0.65), (0.18, 0.12, 1.0), hull)
    fin.rotation_euler[0] = 0.18
    fin.rotation_euler[2] = -0.28
    objects.append(fin)

    for idx, x in enumerate([-0.7, -0.15, 0.75]):
        y = 0.68 if idx % 2 == 0 else -0.7
        objects.append(cube(f"asymmetric_greeble_{idx + 1}", (x, y, 0.34), (0.42, 0.12, 0.12), metal))

    root = bpy.data.objects.new(spec["canonical_id"], None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root

    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.name = "preview_key_light"
    light.data.energy = 450
    light.data.size = 5

    bpy.ops.object.camera_add(location=(4.2, -5.0, 2.4), rotation=(1.15, 0, 0.72))
    bpy.context.scene.camera = bpy.context.object
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 720
    if hasattr(bpy.context.scene, "eevee"):
        bpy.context.scene.eevee.taa_render_samples = 32

    return root


def main():
    args = parse_args()
    spec = json.loads(args.spec_json)

    output = Path(args.output)
    preview = Path(args.preview_output)
    manifest = Path(args.manifest_output)
    for path in (output, preview, manifest):
        path.parent.mkdir(parents=True, exist_ok=True)

    root = make_scene(spec)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj == root or obj.parent == root:
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", use_selection=True)

    bpy.context.scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)

    manifest.write_text(json.dumps({
        "canonical_id": spec["canonical_id"],
        "name": spec.get("name"),
        "kind": spec.get("kind"),
        "style": spec.get("style"),
        "components": spec.get("components", []),
        "outputs": {
            "glb": str(output),
            "preview": str(preview),
        },
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
