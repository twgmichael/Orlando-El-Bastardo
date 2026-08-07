#!/usr/bin/env python3
"""
blueprint_interpreter.py -- OEB Blueprint interpreter (v0.1).

Standalone headless-Blender tool that builds a Canonical Asset from a
Blueprint: a portable, renderer-agnostic construction spec (primitives +
deterministic operations), per the studio ontology in
docs/planning/REVIEW-AUDIT.md section 12. This is section 13 item 1 -- the
"generic operation compiler" -- built as its own standalone tool per
section 13's correction, not folded into tools/primitive_asset_builder.py.

v0.1 scope, deliberately narrow:
  - Primitives: cube, cylinder, cone, sphere, torus, plane, wedge,
    hemisphere -- reusing tools/oeb_blender/primitives.py, the same shared
    module tools/primitive_asset_builder.py uses (no duplicate geometry
    code -- see REVIEW-AUDIT.md section 13 item 1 / the shared-module
    extraction that preceded this file).
  - Operations: bevel, mirror, array -- native Blender modifier
    equivalents (BEVEL/MIRROR/ARRAY modifier_add + apply). The full
    ontology vocabulary (bisect, loft, sweep, boolean, extrude) is
    deliberately deferred; add an `_apply_<op>` function and register it
    in OPERATIONS as each is actually needed.
  - Output: both halves of the Canonical Asset dual-artifact pattern
    (section 13 item 2) -- a .glb (Production Variant, the format the
    main pipeline's exporters already consume) and a .blend (editable
    master). Studio Chat's own builder still only produces a .glb; this
    does not retrofit that, it's a separate, more complete builder.
  - No preview rendering. Preview/review rendering is an orthogonal,
    already-solved concern elsewhere in the pipeline.

Blueprint JSON shape (v0.1):
{
  "schema_version": "0.1.0",
  "canonical_id": "prop_example_A",
  "name": "Example",
  "kind": "prop",
  "primitives": [
    {
      "id": "body",
      "type": "cube",   # cube|cylinder|cone|sphere|torus|plane|wedge|hemisphere
      "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
      "material": {"color": [0.6, 0.6, 0.6, 1.0]}
    }
  ],
  "operations": [
    {"op": "bevel", "target": "body", "params": {"width": 0.05, "segments": 2}},
    {"op": "mirror", "target": "body", "params": {"axis": "Y"}},
    {"op": "array", "target": "body", "params": {"axis": "X", "count": 4, "offset": 1.2}}
  ]
}

For cylinder/cone, `transform.scale` is read as [radius, radius, depth].
For torus, [major_radius, minor_radius, unused]. For everything else,
scale is a literal per-axis scale factor, matching
tools/oeb_blender/primitives.py's existing conventions.

Run by headless Blender:
  blender --background --python tools/blueprint_interpreter.py -- \\
    --blueprint-json '{...}' \\
    --glb-output assets/props/prop_example_A.glb \\
    --blend-output assets/props/prop_example_A.blend \\
    --manifest-output out/blueprint_builds/prop_example_A.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oeb_blender.primitives import (  # noqa: E402
    clear_scene,
    cone,
    cube,
    cylinder,
    hemisphere,
    material,
    plane,
    sphere,
    torus,
    wedge,
)

SCHEMA_VERSION = "0.1.0"


def parse_args():
    parser = argparse.ArgumentParser(prog="blueprint_interpreter")
    parser.add_argument("--blueprint-json", required=True)
    parser.add_argument("--glb-output", required=True)
    parser.add_argument("--blend-output", required=True)
    parser.add_argument("--manifest-output", required=True)

    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    return parser.parse_args(argv)


def _vec3(value, default):
    if isinstance(value, list) and len(value) == 3:
        return tuple(float(v) for v in value)
    return default


def _material_for(mat_spec, cache):
    raw = (mat_spec or {}).get("color")
    rgb = _vec3(raw[:3] if isinstance(raw, list) else None, (0.6, 0.6, 0.6))
    alpha = float(raw[3]) if isinstance(raw, list) and len(raw) == 4 else 1.0
    key = rgb + (alpha,)
    if key not in cache:
        cache[key] = material(f"mat_{len(cache)}", key)
    return cache[key]


_PRIMITIVE_TYPES = frozenset({"cube", "sphere", "cylinder", "cone", "torus", "plane", "wedge", "hemisphere"})


def build_primitive(spec, mat_cache):
    prim_id = spec["id"]
    prim_type = spec["type"]
    if prim_type not in _PRIMITIVE_TYPES:
        raise ValueError(f"Unknown primitive type: {prim_type!r} (id={prim_id!r})")

    transform = spec.get("transform") or {}
    location = _vec3(transform.get("location"), (0.0, 0.0, 0.0))
    rotation = _vec3(transform.get("rotation"), (0.0, 0.0, 0.0))
    scale = _vec3(transform.get("scale"), (1.0, 1.0, 1.0))
    mat = _material_for(spec.get("material"), mat_cache)

    if prim_type == "cube":
        obj = cube(prim_id, location, scale, mat)
        obj.rotation_euler = rotation
    elif prim_type == "sphere":
        obj = sphere(prim_id, location, scale, mat)
        obj.rotation_euler = rotation
    elif prim_type == "cylinder":
        obj = cylinder(prim_id, location, scale[0], scale[2], mat, rotation=rotation)
    elif prim_type == "cone":
        obj = cone(prim_id, location, scale[0], scale[2], mat, rotation=rotation)
    elif prim_type == "torus":
        minor_radius = scale[1] if scale[1] else scale[0] * 0.3
        obj = torus(prim_id, location, scale[0], minor_radius, mat, rotation=rotation)
    elif prim_type == "plane":
        obj = plane(prim_id, location, scale, mat, rotation=rotation)
    elif prim_type == "wedge":
        obj = wedge(prim_id, location, scale, mat, rotation=rotation)
    elif prim_type == "hemisphere":
        obj = hemisphere(prim_id, location, scale[0], mat)
        obj.rotation_euler = rotation
        obj.scale = scale
    else:
        raise ValueError(f"Unknown primitive type: {prim_type!r} (id={prim_id!r})")

    return obj


def _apply_bevel(obj, params):
    modifier = obj.modifiers.new(name="blueprint_bevel", type="BEVEL")
    modifier.width = float(params.get("width", 0.02))
    modifier.segments = int(params.get("segments", 2))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _apply_mirror(obj, params):
    modifier = obj.modifiers.new(name="blueprint_mirror", type="MIRROR")
    axis = str(params.get("axis", "X")).upper()
    modifier.use_axis = (axis == "X", axis == "Y", axis == "Z")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _apply_array(obj, params):
    modifier = obj.modifiers.new(name="blueprint_array", type="ARRAY")
    modifier.count = int(params.get("count", 2))
    axis = str(params.get("axis", "X")).upper()
    offset = float(params.get("offset", 1.0))
    modifier.use_relative_offset = False
    modifier.use_constant_offset = True
    modifier.constant_offset_displace = (
        offset if axis == "X" else 0.0,
        offset if axis == "Y" else 0.0,
        offset if axis == "Z" else 0.0,
    )
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


OPERATIONS = {
    "bevel": _apply_bevel,
    "mirror": _apply_mirror,
    "array": _apply_array,
}


def apply_operation(op_spec, objects_by_id):
    op_name = op_spec["op"]
    apply_fn = OPERATIONS.get(op_name)
    if apply_fn is None:
        raise ValueError(f"Unknown operation: {op_name!r} (supported: {sorted(OPERATIONS)})")
    target_id = op_spec["target"]
    obj = objects_by_id.get(target_id)
    if obj is None:
        raise ValueError(f"Operation {op_name!r} references unknown target {target_id!r}")
    apply_fn(obj, op_spec.get("params") or {})


def parent_to_root(canonical_id, objects):
    root = bpy.data.objects.new(canonical_id, None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
    return root


def build_blueprint(blueprint):
    clear_scene()
    mat_cache = {}
    objects_by_id = {}
    for prim_spec in blueprint.get("primitives", []):
        objects_by_id[prim_spec["id"]] = build_primitive(prim_spec, mat_cache)

    applied_ops = []
    for op_spec in blueprint.get("operations", []):
        apply_operation(op_spec, objects_by_id)
        applied_ops.append({"op": op_spec["op"], "target": op_spec["target"]})

    root = parent_to_root(blueprint["canonical_id"], list(objects_by_id.values()))
    return root, applied_ops


def main():
    args = parse_args()
    blueprint = json.loads(args.blueprint_json)

    glb_output = Path(args.glb_output)
    blend_output = Path(args.blend_output)
    manifest_output = Path(args.manifest_output)
    for path in (glb_output, blend_output, manifest_output):
        path.parent.mkdir(parents=True, exist_ok=True)

    root, applied_ops = build_blueprint(blueprint)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj == root or obj.parent == root:
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(glb_output), export_format="GLB", use_selection=True)

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "canonical_id": blueprint["canonical_id"],
        "name": blueprint.get("name"),
        "kind": blueprint.get("kind"),
        "primitives": [p["id"] for p in blueprint.get("primitives", [])],
        "operations_applied": applied_ops,
        "outputs": {"glb": str(glb_output), "blend": str(blend_output)},
    }
    manifest_output.write_text(json.dumps(manifest, indent=2))
    print(f"Blueprint {blueprint['canonical_id']} built: {glb_output}, {blend_output}")


if __name__ == "__main__":
    main()
