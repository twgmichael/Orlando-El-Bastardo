#!/usr/bin/env python3
"""
blueprint_interpreter.py -- OEB Blueprint interpreter (the Blender translator).

Headless-Blender tool that builds a Canonical Asset from a Blueprint: a
portable, renderer-agnostic construction spec (primitives + deterministic
operations), per the studio ontology in docs/planning/REVIEW-AUDIT.md
section 12. This is section 13 item 1 -- the "generic operation
compiler". It is now Studio Chat's *only* build script -- see "Studio
Chat wiring" below and REVIEW-AUDIT.md section 18 for the unification
that retired tools/primitive_asset_builder.py as a second, separately-run
path.

**Core spec vs. translator (docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md
section 3):** the Blueprint format itself is defined independently of
this file, in schemas/blueprint.schema.json -- engine-blind, no Blender
API surface in the schema. This file is *a* translator that consumes
that spec and produces Blender-native output, not the schema's only
possible reference implementation. A future non-Blender translator would
consume the same schemas/blueprint.schema.json and implement the same
`OPERATIONS` contract (see the dict of that name below) against a
different engine -- nothing here should be read as coupling the spec
itself to Blender.

Scope, deliberately narrow where it's still narrow:
  - Primitives: cube, cylinder, cone, sphere, torus, plane, wedge,
    hemisphere -- via tools/oeb_blender/primitives.py, shared with the
    hierarchical/recipe system below (no duplicate geometry code).
  - Hierarchical/recipe objects: tools/oeb_blender/recipes.py --
    category dispatch (make_chair, make_table_like, make_vehicle_*, the
    Milestone 18 archetype system) driven by a compiled Studio Chat spec
    (scene_plan/components/registry primitives). Moved here from
    tools/primitive_asset_builder.py, unified rather than duplicated or
    called into as a second script -- see "Studio Chat wiring" below.
  - Operations: bevel, mirror, array -- native Blender modifier
    equivalents (BEVEL/MIRROR/ARRAY modifier_add + apply). The full
    ontology vocabulary (bisect, loft, sweep, boolean, extrude) is
    deliberately deferred; add an `_apply_<op>` function and register it
    in OPERATIONS as each is actually needed.
  - Keyframe/camera/timeline operations: set_keyframe, set_camera_keyframe,
    orbit_around, dolly_to -- real bpy keyframe_insert calls, not metadata.
    set_keyframe/set_camera_keyframe are the same operation under two
    names: set_keyframe may target any primitive id built via the native
    primitives/import path (e.g. animating an imported ship in a scene),
    set_camera_keyframe is the same call conventionally aimed at the
    reserved "camera" object. orbit_around/dolly_to remain camera-specific
    choreography. See docs/planning/REVIEW-AUDIT.md section 17 /
    docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 8 /
    PROJECT-TODO.md. Deliberately separate from
    data/camera_grammar.json's discrete establishing/two_shot/close_on
    setup vocabulary used by the teleplay production pipeline
    (tools/export_blender.py) -- that system picks a pre-defined camera
    setup per shot from a fixed vocabulary tied to a set's marks; this one
    is continuous cinematic choreography (orbits, dollies, hero moves) for
    Studio Chat's own Blueprints. The two are intentionally not unified
    yet. When a build has no camera operation at all, the reserved camera
    gets a default preview framing (see canonical_camera_views's "action"
    view) instead of sitting unpositioned at the origin.
  - Asset import: a primitive entry with `"type": "import"` references an
    existing Canonical Asset by canonical_id instead of building geometry
    from scratch -- reusing oeb.config.json's registry and
    bpy.ops.import_scene.gltf(...) + bpy.data.objects.get(node_name)
    exactly the way tools/export_blender.py already resolves
    actor/prop/set references, not a new mechanism (REVIEW-AUDIT.md
    section 17, "asset-import as a Blueprint/scene component"). Imported
    assets bring their own materials; `material` is ignored for this
    primitive type. The same source .glb is only ever imported once per
    build even if referenced by multiple import primitives.
  - Output: both halves of the Canonical Asset dual-artifact pattern
    (section 13 item 2) -- a .glb (Production Variant, the format the
    main pipeline's exporters already consume) and a .blend (editable
    master).
  - Optional single-frame preview render (--preview-output) -- the
    fast synchronous snapshot the chat UI shows immediately after a
    build completes. The multi-view gallery review render remains a
    separate downstream job.

Studio Chat wiring (docs/planning/REVIEW-AUDIT.md section 16/18 onward):
  `app.routers.conversations._build_job_payload` targets this file for
  every Studio Chat build job; tools/primitive_asset_builder.py has been
  retired (its hierarchical/recipe logic now lives in
  tools/oeb_blender/recipes.py, imported here directly -- one build path,
  not two). A Blueprint's `compiled_spec` key, when present, carries the
  full compiled PrimitiveBuildSpec dict (scene_plan/components/registry
  primitives) and is handed to
  `oeb_blender.recipes.build_object_graph()`. The reserved "camera"
  object and its preview light are always this interpreter's own (see
  _ensure_camera/_add_preview_light/_setup_default_preview_camera below)
  regardless of which path built the geometry, so a Blueprint's own
  camera operations always have a single, consistent object to retarget.

Blueprint JSON shape (v0.1):
{
  "schema_version": "0.1.0",
  "canonical_id": "prop_example_A",
  "name": "Example",
  "kind": "prop",
  "units_per_meter": 1.0,
  "frame_range": {"start": 1, "end": 193, "fps": 29.97},
  "primitives": [
    {
      "id": "body",
      "type": "cube",   # cube|cylinder|cone|sphere|torus|plane|wedge|hemisphere
      "transform": {"location": [0, 0, 0.5], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
      "material": {"color": [0.6, 0.6, 0.6, 1.0]}
    },
    {
      "id": "logo",
      "type": "import",   # references an existing Canonical Asset instead of building geometry
      "canonical_id": "set_bar_small_A",
      "transform": {"location": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
    }
  ],
  "operations": [
    {"op": "bevel", "target": "body", "params": {"width": 0.05, "segments": 2}},
    {"op": "mirror", "target": "body", "params": {"axis": "Y"}},
    {"op": "array", "target": "body", "params": {"axis": "X", "count": 4, "offset": 1.2}},
    {"op": "set_camera_keyframe", "target": "camera", "params": {
        "frame": 1, "position": [13.8, 0.2, 3.8], "aim": [1.5, 0.2, 0], "roll_degrees": 0}},
    {"op": "orbit_around", "target": "camera", "params": {
        "pivot": [0, 0, 0], "start_frame": 1, "end_frame": 97,
        "arc_degrees": 65, "radius_start": 14, "radius_end": 14.5, "height": 1.0}},
    {"op": "dolly_to", "target": "camera", "params": {
        "target": [4.5, -0.65, -1.2], "start_frame": 166, "end_frame": 193,
        "distance_start": 13, "distance_end": 1}}
  ]
}

`"camera"` is a reserved primitive id: the interpreter always creates and
registers a camera object under it before applying operations, so
set_camera_keyframe/orbit_around/dolly_to target it exactly like bevel
targets a primitive -- no special-casing in the dispatch mechanism.
`frame_range` (optional, default start=1 end=250 fps=24.0) sets the
scene's frame range and is the bound every camera-op frame number is
validated against. The camera is intentionally excluded from the .glb
export (geometry only, the Production Variant placed by canonical_id) --
camera choreography lives only in the saved .blend, since presentation
timing is not part of an asset's placeable geometry.

For cylinder/cone, `transform.scale` is read as [radius, radius, depth].
For torus, [major_radius, minor_radius, unused]. For everything else,
scale is a literal per-axis scale factor, matching
tools/oeb_blender/primitives.py's existing conventions.

`units_per_meter` (optional, default 1.0) declares this Blueprint's scale
reference: how many Blender units equal one real-world meter, i.e. it
follows Blender's own native 1 unit = 1 meter convention unless a
Blueprint states otherwise. This does not affect anything primitives
build here -- it exists so a future relative-edit operation (e.g.
"move the engine pods 10 centimeters forward") has something to convert
real-world units against instead of guessing. See
docs/planning/REVIEW-AUDIT.md section 17's reference-frame addendum.
Recorded in the build manifest; not yet consumed by any operation.

Run by headless Blender:
  blender --background --python tools/blueprint_interpreter.py -- \\
    --blueprint-json '{...}' \\
    --glb-output assets/props/prop_example_A.glb \\
    --blend-output assets/props/prop_example_A.blend \\
    --manifest-output out/blueprint_builds/prop_example_A.json \\
    [--preview-output renders/asset_previews/prop_example_A.png]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oeb_blender.primitives import (  # noqa: E402
    clear_scene,
    cone,
    cube,
    cylinder,
    hemisphere,
    material,
    parent_to_root,
    plane,
    sphere,
    torus,
    wedge,
)
from oeb_blender.recipes import (  # noqa: E402
    build_object_graph,
    canonical_camera_views,
    orientation_standard,
)

SCHEMA_VERSION = "0.1.0"

DEFAULT_FRAME_RANGE = {"start": 1, "end": 250, "fps": 24.0}
CAMERA_ID = "camera"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    parser = argparse.ArgumentParser(prog="blueprint_interpreter")
    parser.add_argument("--blueprint-json", required=True)
    parser.add_argument("--glb-output", required=True)
    parser.add_argument("--blend-output", required=True)
    parser.add_argument("--manifest-output", required=True)
    parser.add_argument(
        "--preview-output",
        default=None,
        help="optional single-frame preview PNG, rendered at frame_range.start",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "oeb.config.json"),
        help="oeb.config.json path, for resolving type=import canonical_id references",
    )

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


def load_import_config(config_path):
    config = json.loads(Path(config_path).read_text())
    asset_root = os.environ.get("OEB_ASSET_ROOT", config.get("asset_root", "assets"))
    asset_root = Path(asset_root)
    if not asset_root.is_absolute():
        asset_root = PROJECT_ROOT / asset_root
    return {"config": config, "asset_root": asset_root, "imported_files": set()}


def build_import_primitive(spec, import_ctx):
    """Reference an existing Canonical Asset by canonical_id instead of
    building geometry -- same registry (oeb.config.json) and resolution
    (bpy.ops.import_scene.gltf + bpy.data.objects.get(node_name)) that
    tools/export_blender.py already uses for actor/prop/set references.

    Optional `mark` field: place this import at a named mark object
    instead of (or overriding) `transform.location` -- the same
    mark-object convention tools/export_blender.py already uses for
    actor spawn_mark / prop at_mark placement (R6/R12). The mark object
    must already exist in the scene, i.e. the set's own import primitive
    (whose glTF carries the mark objects) must appear earlier in this
    Blueprint's `primitives` list than anything placed by mark.
    `mark_mode: "prop"` keeps the imported object's own z (R6's
    take-x/y-keep-z convention); any other/absent mode copies the mark's
    full location (R12's actor convention). See
    docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 2 and
    tools/scenespec_to_blueprint.py, the first real caller of this.
    """
    prim_id = spec["id"]
    canonical_id = spec.get("canonical_id")
    if not canonical_id:
        raise ValueError(f"Import primitive {prim_id!r} is missing canonical_id")

    assets = import_ctx["config"].get("assets", {})
    entry = assets.get(canonical_id)
    if entry is None:
        raise ValueError(
            f"Unknown canonical_id {canonical_id!r} (id={prim_id!r}) -- not found in oeb.config.json's assets map"
        )

    asset_root = import_ctx["asset_root"]
    glb_path = asset_root / entry["file"]
    if str(glb_path) not in import_ctx["imported_files"]:
        if not glb_path.is_file():
            raise ValueError(f"Referenced asset file not found: {glb_path} (canonical_id={canonical_id!r})")
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        import_ctx["imported_files"].add(str(glb_path))

    node_name = entry["node"]
    obj = bpy.data.objects.get(node_name)
    if obj is None:
        raise ValueError(
            f"Imported {glb_path} but node {node_name!r} was not found in it "
            f"(canonical_id={canonical_id!r}) -- check oeb.config.json's node field"
        )
    if obj.name != prim_id:
        obj.name = prim_id

    transform = spec.get("transform") or {}
    obj.location = _vec3(transform.get("location"), (0.0, 0.0, 0.0))
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = _vec3(transform.get("rotation"), (0.0, 0.0, 0.0))
    obj.scale = _vec3(transform.get("scale"), (1.0, 1.0, 1.0))

    mark_name = spec.get("mark")
    if mark_name:
        mark_obj = bpy.data.objects.get(mark_name)
        if mark_obj is None:
            raise ValueError(
                f"Import primitive {prim_id!r} references mark {mark_name!r}, not found in the "
                f"scene -- the set's own import primitive must appear earlier in `primitives` "
                f"so its mark objects exist before this one resolves"
            )
        # World translation, not .location: a mark's own .location is
        # local-space only and wrong if the mark is parented.
        mark_world_location = mark_obj.matrix_world.translation
        if spec.get("mark_mode") == "prop":
            obj.location.x = mark_world_location.x
            obj.location.y = mark_world_location.y
        else:
            obj.location = mark_world_location.copy()

    return obj


def _apply_frame_range(blueprint):
    frame_range = blueprint.get("frame_range") or {}
    start = int(frame_range.get("start", DEFAULT_FRAME_RANGE["start"]))
    end = int(frame_range.get("end", DEFAULT_FRAME_RANGE["end"]))
    fps = float(frame_range.get("fps", DEFAULT_FRAME_RANGE["fps"]))
    if end <= start:
        raise ValueError(f"frame_range.end ({end}) must be greater than frame_range.start ({start})")
    if fps <= 0:
        raise ValueError(f"frame_range.fps must be positive, got {fps}")
    bpy.context.scene.frame_start = start
    bpy.context.scene.frame_end = end
    fps_int = round(fps)
    bpy.context.scene.render.fps = fps_int
    bpy.context.scene.render.fps_base = fps_int / fps if fps else 1.0
    return {"frame_start": start, "frame_end": end, "fps": fps}


def _validate_frame(frame, ctx):
    frame = int(frame)
    if frame < ctx["frame_start"] or frame > ctx["frame_end"]:
        raise ValueError(
            f"frame {frame} is outside this Blueprint's frame_range "
            f"[{ctx['frame_start']}, {ctx['frame_end']}]"
        )
    return frame


def _look_at_rotation(position, target, roll_degrees=0.0):
    """Return an XYZ Euler pointing the camera's local -Z axis at *target*
    (local Y as up -- Blender's camera convention), then applying
    *roll_degrees* around the resulting forward axis.
    """
    direction = Vector(target) - Vector(position)
    if direction.length < 1e-9:
        raise ValueError("camera position and aim target are the same point")
    track_quat = direction.to_track_quat("-Z", "Y")
    if roll_degrees:
        forward_world = track_quat @ Vector((0.0, 0.0, -1.0))
        roll_quat = Quaternion(forward_world, math.radians(roll_degrees))
        track_quat = roll_quat @ track_quat
    return track_quat.to_euler("XYZ")


def _ensure_camera(objects_by_id):
    camera_data = bpy.data.cameras.new(f"{CAMERA_ID}_data")
    camera_obj = bpy.data.objects.new(CAMERA_ID, camera_data)
    bpy.context.collection.objects.link(camera_obj)
    bpy.context.scene.camera = camera_obj
    camera_obj.rotation_mode = "XYZ"
    objects_by_id[CAMERA_ID] = camera_obj
    return camera_obj


def _apply_bevel(obj, params, ctx):
    modifier = obj.modifiers.new(name="blueprint_bevel", type="BEVEL")
    modifier.width = float(params.get("width", 0.02))
    modifier.segments = int(params.get("segments", 2))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _apply_mirror(obj, params, ctx):
    modifier = obj.modifiers.new(name="blueprint_mirror", type="MIRROR")
    axis = str(params.get("axis", "X")).upper()
    modifier.use_axis = (axis == "X", axis == "Y", axis == "Z")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def _apply_array(obj, params, ctx):
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


def _apply_set_keyframe(obj, params, ctx):
    """Generic single-keyframe insert on any object's location (and,
    if `aim` is given, look-at rotation) -- not camera-specific. Per
    docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 8/2: scene
    composition needs the same keyframe machinery applied to arbitrary
    imported-asset ids (e.g. a chase scene's flyers/cruiser), not just
    the reserved "camera" id. Registered under both "set_keyframe" (the
    general name) and "set_camera_keyframe" (kept for the camera's own
    semantic framing vocabulary, section 17/18) -- identical behavior,
    not two implementations.

    Optional `camera_mark`: instead of `position`/`aim`, copy location
    AND rotation directly from a named scene camera object -- the same
    data/camera_grammar.json `scene_object` convention
    tools/export_blender.py already resolves for shot cameras (already
    correctly aimed in the set's own glTF, not an empty needing a
    look-at target). See tools/scenespec_to_blueprint.py.
    """
    frame = _validate_frame(params["frame"], ctx)

    camera_mark = params.get("camera_mark")
    if camera_mark:
        mark_obj = bpy.data.objects.get(camera_mark)
        if mark_obj is None:
            raise ValueError(
                f"set_keyframe references camera_mark {camera_mark!r}, not found in the scene "
                f"-- the set's own import primitive must appear earlier in `primitives`"
            )
        # World matrix, not .location/.rotation_euler directly: mark objects
        # in real set glTFs are frequently QUATERNION rotation_mode (confirmed
        # live against fixtures/bar_scene.scenespec.json's camera marks) or
        # parented, either of which makes .rotation_euler/.location alone
        # stale or local-space-only. to_euler() on the world matrix is
        # correct regardless of the mark's own rotation_mode or parenting.
        obj.location = mark_obj.matrix_world.translation.copy()
        obj.keyframe_insert("location", frame=frame)
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = mark_obj.matrix_world.to_euler("XYZ")
        obj.keyframe_insert("rotation_euler", frame=frame)
        return

    position = _vec3(params.get("position"), tuple(obj.location))
    obj.location = position
    obj.keyframe_insert("location", frame=frame)

    aim = params.get("aim")
    if aim is not None:
        roll = float(params.get("roll_degrees", 0.0))
        obj.rotation_euler = _look_at_rotation(position, _vec3(aim, (0.0, 0.0, 0.0)), roll)
        obj.keyframe_insert("rotation_euler", frame=frame)


def _apply_orbit_around(obj, params, ctx):
    start = _validate_frame(params["start_frame"], ctx)
    end = _validate_frame(params["end_frame"], ctx)
    if end <= start:
        raise ValueError(f"orbit_around end_frame ({end}) must be greater than start_frame ({start})")
    pivot = _vec3(params.get("pivot"), (0.0, 0.0, 0.0))
    radius_start = float(params["radius_start"])
    radius_end = float(params.get("radius_end", radius_start))
    if radius_start <= 0 or radius_end <= 0:
        raise ValueError("orbit_around radius must be positive")
    arc_degrees = float(params.get("arc_degrees", 90.0))
    start_angle = float(params.get("start_angle_degrees", 0.0))
    height = float(params.get("height", pivot[2]))
    roll_start = float(params.get("roll_degrees_start", 0.0))
    roll_end = float(params.get("roll_degrees_end", roll_start))

    # Sampled, not a single 2-key chord: a straight interpolation between
    # just start/end keyframes cuts the corner of the arc instead of
    # tracing it, producing exactly the "discontinuous jump" this
    # operation is required not to have.
    samples = max(2, int(params.get("samples", 6)))
    for i in range(samples):
        t = i / (samples - 1)
        frame = round(start + t * (end - start))
        angle = math.radians(start_angle + t * arc_degrees)
        radius = radius_start + t * (radius_end - radius_start)
        position = (
            pivot[0] + radius * math.cos(angle),
            pivot[1] + radius * math.sin(angle),
            height,
        )
        roll = roll_start + t * (roll_end - roll_start)
        obj.location = position
        obj.keyframe_insert("location", frame=frame)
        obj.rotation_euler = _look_at_rotation(position, pivot, roll)
        obj.keyframe_insert("rotation_euler", frame=frame)


def _apply_dolly_to(obj, params, ctx):
    start = _validate_frame(params["start_frame"], ctx)
    end = _validate_frame(params["end_frame"], ctx)
    if end <= start:
        raise ValueError(f"dolly_to end_frame ({end}) must be greater than start_frame ({start})")
    target = _vec3(params.get("target"), (0.0, 0.0, 0.0))
    distance_start = float(params["distance_start"])
    distance_end = float(params["distance_end"])
    if distance_start <= 0 or distance_end <= 0:
        raise ValueError("dolly_to distances must be positive")
    roll = float(params.get("roll_degrees", 0.0))

    direction_param = params.get("direction")
    if direction_param is not None:
        dir_vec = Vector(_vec3(direction_param, (0.0, -1.0, 0.0)))
    else:
        dir_vec = Vector(obj.location) - Vector(target)
    if dir_vec.length < 1e-9:
        dir_vec = Vector((0.0, -1.0, 0.0))
    dir_vec.normalize()

    samples = max(2, int(params.get("samples", 4)))
    for i in range(samples):
        t = i / (samples - 1)
        frame = round(start + t * (end - start))
        distance = distance_start + t * (distance_end - distance_start)
        position = Vector(target) + dir_vec * distance
        obj.location = (position.x, position.y, position.z)
        obj.keyframe_insert("location", frame=frame)
        obj.rotation_euler = _look_at_rotation(tuple(position), target, roll)
        obj.keyframe_insert("rotation_euler", frame=frame)


def _apply_set_material(obj, params, ctx):
    """Extend a primitive's material past the flat RGBA `material.color`
    a Blueprint's primitive-level material already supports -- finish
    (roughness) and metallic, applied to the object's existing material
    slot(s) via the Principled BSDF the shared `material()` helper
    (tools/oeb_blender/primitives.py) already sets up. Per
    docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 8: proposed
    in REVIEW-AUDIT.md section 11, previously undelivered.
    """
    roughness = params.get("roughness")
    metallic = params.get("metallic")
    color = params.get("color")
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        if roughness is not None and "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(roughness)
        if metallic is not None and "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = float(metallic)
        if color is not None and "Base Color" in bsdf.inputs:
            rgba = _vec3(color[:3] if isinstance(color, list) else None, (0.6, 0.6, 0.6)) + (
                float(color[3]) if isinstance(color, list) and len(color) == 4 else 1.0,
            )
            bsdf.inputs["Base Color"].default_value = rgba


_SHAPE_DETAIL_BEVEL_DEFAULTS = {
    "rounded": {"width": 0.04, "segments": 4},
    "beveled": {"width": 0.02, "segments": 1},
    "soft_beveled": {"width": 0.03, "segments": 3},
}


def _apply_set_shape_detail(obj, params, ctx):
    """Turn the LLM-captured, previously-discarded `corner_style`/
    `edge_profile` fields (REVIEW-AUDIT.md section 8's original finding:
    `_compile_typed_object_primitives` captured these but never turned
    them into geometry) into a real BEVEL modifier -- reusing
    `_apply_bevel` rather than a second modifier code path. `edge_profile`
    is checked first, falling back to `corner_style`; an unrecognized
    value applies no modifier rather than guessing.
    """
    style = params.get("edge_profile") or params.get("corner_style")
    defaults = _SHAPE_DETAIL_BEVEL_DEFAULTS.get(str(style).strip().lower()) if style else None
    if defaults is None:
        return
    _apply_bevel(obj, {**defaults, **{k: v for k, v in params.items() if k in ("width", "segments")}}, ctx)


def _apply_set_environment(params, ctx):
    """Scene-level lighting/environment preset. v0.1 has exactly one
    preset, "deep_space" -- the star-sphere + emissive-sun-sphere + EEVEE
    bloom setup already proven working in two real render scripts
    (tools/tmp_jb100_space_action.py; docs/world-building/SPACESCAPE.md),
    adapted here rather than redesigned. Additional presets get added the
    same way OPERATIONS entries are: one at a time, when an actual scene
    needs them -- not built speculatively ahead of that need.
    """
    preset = str(params.get("preset", "deep_space")).strip().lower()
    if preset != "deep_space":
        raise ValueError(f"Unknown set_environment preset: {preset!r} (supported: ['deep_space'])")

    scene = bpy.context.scene
    world = bpy.data.worlds.new("blueprint_space_env")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
    scene.world = world

    star_radius = float(params.get("star_radius", 800.0))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=star_radius, segments=64, ring_count=32)
    star_sphere = bpy.context.active_object
    star_sphere.name = "env_star_sphere"
    star_sphere.visible_shadow = False

    star_mat = bpy.data.materials.new("mat_env_stars")
    star_mat.use_nodes = True
    star_mat.use_backface_culling = False
    snt = star_mat.node_tree
    for node in list(snt.nodes):
        snt.nodes.remove(node)
    s_out = snt.nodes.new("ShaderNodeOutputMaterial")
    s_emit = snt.nodes.new("ShaderNodeEmission")
    s_ramp = snt.nodes.new("ShaderNodeValToRGB")
    s_noise = snt.nodes.new("ShaderNodeTexNoise")
    s_coord = snt.nodes.new("ShaderNodeTexCoord")
    s_noise.inputs["Scale"].default_value = 300.0
    s_noise.inputs["Detail"].default_value = 8.0
    s_noise.inputs["Roughness"].default_value = 0.6
    s_ramp.color_ramp.interpolation = "CONSTANT"
    s_ramp.color_ramp.elements[0].position = 0.0
    s_ramp.color_ramp.elements[0].color = (0.003, 0.003, 0.006, 1)
    s_ramp.color_ramp.elements[1].position = float(params.get("star_threshold", 0.75))
    s_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    s_emit.inputs["Strength"].default_value = float(params.get("star_strength", 8.0))
    snt.links.new(s_coord.outputs["Generated"], s_noise.inputs["Vector"])
    snt.links.new(s_noise.outputs["Fac"], s_ramp.inputs["Fac"])
    snt.links.new(s_ramp.outputs["Color"], s_emit.inputs["Color"])
    snt.links.new(s_emit.outputs["Emission"], s_out.inputs["Surface"])
    star_sphere.data.materials.append(star_mat)

    sun_location = _vec3(params.get("sun_location"), (300.0, 500.0, 250.0))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=float(params.get("sun_radius", 18.0)),
                                          location=sun_location, segments=32, ring_count=16)
    sun_obj = bpy.context.active_object
    sun_obj.name = "env_sun"
    sun_mat = bpy.data.materials.new("mat_env_sun")
    sun_mat.use_nodes = True
    for node in list(sun_mat.node_tree.nodes):
        sun_mat.node_tree.nodes.remove(node)
    sun_emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
    sun_out = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    sun_color = _vec3(params.get("sun_color"), (1.0, 0.78, 0.30))
    sun_emit.inputs["Color"].default_value = sun_color + (1.0,)
    sun_emit.inputs["Strength"].default_value = float(params.get("sun_strength", 120.0))
    sun_mat.node_tree.links.new(sun_emit.outputs["Emission"], sun_out.inputs["Surface"])
    sun_obj.data.materials.append(sun_mat)

    if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_bloom"):
        scene.eevee.use_bloom = True
        scene.eevee.bloom_threshold = float(params.get("bloom_threshold", 0.6))
        scene.eevee.bloom_intensity = float(params.get("bloom_intensity", 0.8))
        scene.eevee.bloom_radius = float(params.get("bloom_radius", 6.0))


OPERATIONS = {
    "bevel": _apply_bevel,
    "mirror": _apply_mirror,
    "array": _apply_array,
    "set_keyframe": _apply_set_keyframe,
    "set_camera_keyframe": _apply_set_keyframe,
    "orbit_around": _apply_orbit_around,
    "dolly_to": _apply_dolly_to,
    "set_material": _apply_set_material,
    "set_shape_detail": _apply_set_shape_detail,
    "set_environment": _apply_set_environment,
}


SCENE_LEVEL_OPERATIONS = frozenset({"set_environment"})
"""Operations that act on the scene as a whole, not one target object --
`target` is still required in the Blueprint JSON for a uniform operation
shape, but is not resolved against objects_by_id or passed to the apply
function.
"""


def apply_operation(op_spec, objects_by_id, ctx):
    op_name = op_spec["op"]
    apply_fn = OPERATIONS.get(op_name)
    if apply_fn is None:
        raise ValueError(f"Unknown operation: {op_name!r} (supported: {sorted(OPERATIONS)})")
    if op_name in SCENE_LEVEL_OPERATIONS:
        apply_fn(op_spec.get("params") or {}, ctx)
        return
    target_id = op_spec["target"]
    obj = objects_by_id.get(target_id)
    if obj is None:
        raise ValueError(f"Operation {op_name!r} references unknown target {target_id!r}")
    apply_fn(obj, op_spec.get("params") or {}, ctx)


def _add_preview_light():
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.name = "preview_key_light"
    light.data.energy = 450
    light.data.size = 5
    return light


def _setup_default_preview_camera(camera_obj):
    """Give the reserved camera a sane default framing when a Blueprint's
    operations don't say anything about it, instead of leaving it
    unpositioned at the origin. Reuses the same named "action" view (and
    render resolution/sample settings) the old primitive_asset_builder.py
    preview always used, now applied uniformly to every build.
    """
    view = canonical_camera_views()["action"]
    camera_obj.location = view["location"]
    camera_obj.rotation_euler = _look_at_rotation(view["location"], view["target"])
    camera_obj.data.type = "ORTHO"
    camera_obj.data.ortho_scale = view["ortho_scale"]
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 720
    if hasattr(bpy.context.scene, "eevee"):
        bpy.context.scene.eevee.taa_render_samples = 32


def build_blueprint(blueprint, config_path=None):
    clear_scene()
    ctx = _apply_frame_range(blueprint)
    objects_by_id = {}
    compiled_spec = blueprint.get("compiled_spec")

    if compiled_spec is not None:
        root, variant = build_object_graph(compiled_spec)
    else:
        mat_cache = {}
        import_ctx = None  # lazy: only load oeb.config.json if a type=import primitive actually needs it
        for prim_spec in blueprint.get("primitives", []):
            if prim_spec.get("type") == "import":
                if import_ctx is None:
                    import_ctx = load_import_config(config_path or (PROJECT_ROOT / "oeb.config.json"))
                objects_by_id[prim_spec["id"]] = build_import_primitive(prim_spec, import_ctx)
            else:
                objects_by_id[prim_spec["id"]] = build_primitive(prim_spec, mat_cache)
        root = parent_to_root(blueprint["canonical_id"], list(objects_by_id.values()))
        variant = None

    # The camera is a reserved id, registered for operation targeting after
    # geometry construction so it's never mistaken for a geometry object --
    # it stays a scene-level sibling of the asset root, not a child of it,
    # and is excluded from the geometry (.glb) export selection accordingly.
    _ensure_camera(objects_by_id)
    _add_preview_light()

    applied_ops = []
    camera_targeted = False
    for op_spec in blueprint.get("operations", []):
        apply_operation(op_spec, objects_by_id, ctx)
        applied_ops.append({"op": op_spec["op"], "target": op_spec["target"]})
        camera_targeted = camera_targeted or op_spec["target"] == CAMERA_ID

    if not camera_targeted:
        _setup_default_preview_camera(objects_by_id[CAMERA_ID])

    return root, applied_ops, ctx, variant


def main():
    args = parse_args()
    blueprint = json.loads(args.blueprint_json)

    glb_output = Path(args.glb_output)
    blend_output = Path(args.blend_output)
    manifest_output = Path(args.manifest_output)
    preview_output = Path(args.preview_output) if args.preview_output else None
    for path in (glb_output, blend_output, manifest_output, *([preview_output] if preview_output else [])):
        path.parent.mkdir(parents=True, exist_ok=True)

    root, applied_ops, ctx, variant = build_blueprint(blueprint, config_path=args.config)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj == root or obj.parent == root:
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(glb_output), export_format="GLB", use_selection=True)

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))

    if preview_output is not None:
        bpy.context.scene.frame_set(ctx["frame_start"])
        bpy.context.scene.render.filepath = str(preview_output)
        bpy.ops.render.render(write_still=True)

    outputs = {"glb": str(glb_output), "blend": str(blend_output)}
    if preview_output is not None:
        outputs["preview"] = str(preview_output)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "canonical_id": blueprint["canonical_id"],
        "name": blueprint.get("name"),
        "kind": blueprint.get("kind"),
        "units_per_meter": blueprint.get("units_per_meter", 1.0),
        "frame_range": ctx,
        "primitives": [p["id"] for p in blueprint.get("primitives", [])],
        "operations_applied": applied_ops,
        "build_variant": variant,
        "outputs": outputs,
    }
    compiled_spec = blueprint.get("compiled_spec")
    if compiled_spec is not None:
        # Parity with the manifest tools/primitive_asset_builder.py used to
        # write for these same fields, since this file now builds every
        # Studio Chat asset (see "Studio Chat wiring" above).
        manifest.update({
            "style": compiled_spec.get("style"),
            "creative_request": compiled_spec.get("creative_request"),
            "components": compiled_spec.get("components", []),
            "scene_plan": compiled_spec.get("scene_plan"),
            "repaired_scene_plan": compiled_spec.get("repaired_scene_plan"),
            "orientation_standard": orientation_standard(compiled_spec),
            "canonical_camera_views": canonical_camera_views(),
        })
    manifest_output.write_text(json.dumps(manifest, indent=2))
    print(f"Blueprint {blueprint['canonical_id']} built: {glb_output}, {blend_output}")


if __name__ == "__main__":
    main()
