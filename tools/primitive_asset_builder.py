#!/usr/bin/env python3
"""
Build a simple GLB asset from Blender primitives and render a preview.

Run by the harness worker through Blender:
  blender --background --python tools/primitive_asset_builder.py -- \
    --spec-json '{"canonical_id":"asset_demo_A",...}' \
    --output assets/asset_demo_A.glb \
    --preview-output renders/asset_previews/asset_demo_A.png \
    --manifest-output out/asset_builds/asset_demo_A.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    parser = argparse.ArgumentParser(prog="primitive_asset_builder")
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview-output", required=True)
    parser.add_argument("--manifest-output", required=True)

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    return parser.parse_args(argv)


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


def cone(name, location, radius, depth, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=radius, radius2=0, depth=depth, location=location, rotation=rotation)
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


def torus(name, location, major_radius, minor_radius, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=96,
        minor_segments=12,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def plane(name, location, scale, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def wedge(name, location, scale, mat, rotation=(0, 0, 0)):
    verts = [
        (-0.5, -0.5, -0.5),
        (0.5, -0.5, -0.5),
        (0.5, 0.5, -0.5),
        (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),
        (-0.5, 0.5, 0.5),
    ]
    faces = [
        (0, 1, 2, 3),
        (0, 4, 5, 3),
        (0, 1, 4),
        (1, 2, 5, 4),
        (2, 3, 5),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


ASSET_LOCAL_AXES = {
    "front_axis": "+X",
    "rear_axis": "-X",
    "left_axis": "-Y",
    "right_axis": "+Y",
    "up_axis": "+Z",
    "down_axis": "-Z",
}


def origin_policy_for_kind(kind):
    if kind in {"location", "set"}:
        return "location_center_floor_origin"
    if kind == "vehicle":
        return "vehicle_centerline_midpoint"
    return "asset_center_bottom_origin"


def orientation_standard(spec=None):
    kind = spec.get("kind") if isinstance(spec, dict) else None
    return {
        **ASSET_LOCAL_AXES,
        "origin_policy": origin_policy_for_kind(kind),
        "documentation": "docs/planning/ASSET-LOCATION-ORIENTATION-STANDARD.md",
    }


def axis_position_for_placement(placement, distance=1.0, z=0.35):
    placement = str(placement or "").lower()
    if placement in {"front", "in_front", "in_front_of"}:
        return distance, 0, z
    if placement in {"back", "rear", "behind", "rear_wall"}:
        return -distance, 0, z
    if placement == "left":
        return 0, -distance, z
    if placement == "right":
        return 0, distance, z
    if placement in {"top", "above", "upper"}:
        return 0, 0, distance
    if placement in {"bottom", "below", "under"}:
        return 0, 0, -distance
    return 0, 0, z


def canonical_camera_views(target=(0, 0, 0.45), distance=6.4, ortho_scale=6.8):
    return {
        "action": {"location": (5.6, -6.4, 4.2), "target": target, "ortho_scale": ortho_scale},
        "front": {"location": (distance, 0, target[2]), "target": target, "ortho_scale": ortho_scale},
        "rear": {"location": (-distance, 0, target[2]), "target": target, "ortho_scale": ortho_scale},
        "left": {"location": (0, -distance, target[2]), "target": target, "ortho_scale": ortho_scale},
        "right": {"location": (0, distance, target[2]), "target": target, "ortho_scale": ortho_scale},
        "top": {"location": (0, 0, distance), "target": target, "ortho_scale": ortho_scale},
        "bottom": {"location": (0, 0, -distance), "target": target, "ortho_scale": ortho_scale},
    }


def add_preview_setup(camera_location=(5.2, -6.0, 4.0), target=(0, 0, 0.4), ortho_scale=6.0):
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.name = "preview_key_light"
    light.data.energy = 450
    light.data.size = 5

    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    direction = Vector(target) - Vector(camera_location)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    bpy.context.scene.camera = camera
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 720
    if hasattr(bpy.context.scene, "eevee"):
        bpy.context.scene.eevee.taa_render_samples = 32


def parent_to_root(spec, objects):
    root = bpy.data.objects.new(spec["canonical_id"], None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
    return root


def safe_object_name(text, fallback):
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(text).lower()).strip("_")
    return safe or fallback


def semantic_name(component):
    name = str(component).lower().replace("-", "_").replace(" ", "_")
    for prefix in ("box_", "cube_", "cylinder_", "sphere_", "cone_", "torus_", "plane_", "wedge_"):
        if name.startswith(prefix):
            return name[len(prefix):], prefix[:-1]
    return name, None


def tokenize_name(name):
    return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]


def has_any(tokens, words):
    return any(word in tokens for word in words)


def flatten_detail_values(value):
    if isinstance(value, dict):
        values = []
        for nested in value.values():
            values.extend(flatten_detail_values(nested))
        return values
    if isinstance(value, list):
        values = []
        for nested in value:
            values.extend(flatten_detail_values(nested))
        return values
    if value is None:
        return []
    return [str(value)]


def count_from_tokens(tokens):
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
    }
    for token in tokens:
        if token.isdigit():
            return max(1, min(6, int(token)))
        if token in number_words:
            return number_words[token]
    if any(token.endswith("s") for token in tokens) and not has_any(tokens, ("glass", "grass")):
        return 2
    return 1


def category_for_name(name, shape_hint):
    tokens = tokenize_name(name)
    if shape_hint:
        return shape_hint
    categories = [
        ("tree", ("tree", "plant", "bush", "shrub", "foliage")),
        ("bed", ("bed", "bunk", "cot", "gurney", "examination", "exam", "stretcher", "sofa", "couch")),
        ("cabinet", ("dresser", "nightstand", "cabinet", "locker", "storage", "shelf", "bookshelf", "closet", "crate", "box")),
        ("lamp", ("lamp", "light", "lighting", "lantern", "sconce", "beacon")),
        ("vehicle_seat", ("saddle",)),
        ("chair", ("chair", "stool", "seat", "seating", "bench")),
        ("monitor", ("monitor", "computer", "screen", "terminal", "display", "console", "control", "scanner", "sensor")),
        ("wall_panel", ("window", "mirror", "poster", "door", "panel", "sign", "gate", "barrier", "wall_item")),
        ("path", ("path", "road", "river", "walkway", "corridor", "trail", "track")),
        ("vehicle_fuselage", ("fuselage", "airframe")),
        ("vehicle_fuselage", ("body", "hull")),
        ("vehicle_wing", ("wing", "wings")),
        ("vehicle_nose", ("nose",)),
        ("vehicle_tail", ("tail", "fin", "rudder", "stabilizer")),
        ("vehicle_controls", ("handlebar", "handlebars", "steering", "controls", "yoke")),
        ("vehicle_engine", ("engine", "motor", "thruster", "exhaust", "nozzle")),
        ("table", ("desk", "table", "counter", "workbench", "altar", "bar", "stall", "surface")),
        ("ring", ("ring", "wheel", "loop", "portal")),
        ("cylinder", ("pipe", "column", "post", "tank", "barrel", "tube", "canister", "reactor", "cannon", "gun")),
        ("sphere", ("globe", "ball", "orb", "rock", "boulder", "planet")),
        ("thin_slab", ("rug", "mat", "platform", "pad", "floor", "carpet", "canopy", "awning", "roof")),
        ("tall_block", ("tower", "pillar", "wardrobe", "machine", "kiosk", "vending", "booth", "pod", "structure")),
    ]
    for category, words in categories:
        if has_any(tokens, words):
            return category
    if has_any(tokens, ("long", "wide", "low")):
        return "thin_slab"
    if has_any(tokens, ("tall", "vertical", "standing")):
        return "tall_block"
    return "block"


def material_for_category(category, tokens, mat):
    for color_key in ("blue", "red", "yellow", "orange", "purple", "black", "white", "gray"):
        if has_any(tokens, (color_key,)):
            return mat[color_key]
    if has_any(tokens, ("grey",)):
        return mat["gray"]
    if has_any(tokens, ("wood", "wooden", "desk", "table", "cabinet", "dresser", "bench", "shelf")):
        return mat["wood"]
    if has_any(tokens, ("glass", "window", "screen", "monitor", "mirror")):
        return mat["glass"]
    if has_any(tokens, ("metal", "steel", "pipe", "medical", "machine", "robot", "reactor")):
        return mat["metal"]
    if has_any(tokens, ("green", "plant", "tree", "grass", "park")):
        return mat["green"]
    if has_any(tokens, ("light", "lamp", "glow", "beacon")):
        return mat["glow"]
    if category in {"chair", "monitor"}:
        return mat["dark"]
    if category in {"bed"}:
        return mat["soft"]
    return mat["neutral"]


def component_position(name, idx):
    x = -2.1 + (idx % 4) * 1.4
    y = -0.9 + (idx // 4) * 1.1
    z = 0.35
    tokens = tokenize_name(name)

    if "left" in name:
        y = -1.25
    if "right" in name:
        y = 1.25
    if "center" in name or "middle" in name:
        x = 0
        y = 0
    if "behind" in name or "back" in name:
        x = -1.15
    if "front" in name:
        x = 1.25
    if "front" in name and has_any(tokens, ("wheel", "tire", "handlebar", "handlebars", "fork")):
        x = 1.25
        y = 0
    if "rear" in name and has_any(tokens, ("wheel", "tire", "engine", "exhaust")):
        x = -1.25
        y = 0
    if has_any(tokens, ("frame", "chassis")):
        x = 0
        y = 0
        z = 0.62
    if has_any(tokens, ("engine", "motor")):
        x = -0.2
        y = 0
        z = 0.46
    if has_any(tokens, ("saddle", "seat")):
        x = -0.45
        y = 0
        z = 0.9
    if has_any(tokens, ("handlebar", "handlebars", "steering", "controls")):
        x = 1.05
        y = 0
        z = 1.15
    if has_any(tokens, ("fuselage", "airframe")):
        x = 0
        y = 0
        z = 0.72
    if "left" in name and has_any(tokens, ("wing", "wings")):
        x = -0.05
        y = -0.95
        z = 0.58
    if "right" in name and has_any(tokens, ("wing", "wings")):
        x = -0.05
        y = 0.95
        z = 0.58
    if has_any(tokens, ("nose",)):
        x = 1.45
        y = 0
        z = 0.72
    if has_any(tokens, ("tail", "fin", "rudder", "stabilizer")):
        x = -1.45
        y = 0
        z = 1.0
    if "side" in name and "left" not in name and "right" not in name:
        y = -1.8 if idx % 2 == 0 else 1.8
    if "on_desk" in name or "on_table" in name or "on_counter" in name:
        x = 0.35 if idx % 2 else -0.35
        y = 0.05
        z = 0.98
    if "wall" in name:
        x = -1.85
        z = 1.1
    if "overhead" in name or "ceiling" in name or "canopy" in name:
        x = 0
        y = 0
        z = 1.65
    return x, y, z


def scene_object_name(obj, idx):
    return safe_object_name(obj.get("id") or obj.get("label") or f"object_{idx + 1}", f"object_{idx + 1}")


def scene_object_tokens(obj):
    parts = [
        str(obj.get("label") or ""),
        str(obj.get("id") or ""),
        str(obj.get("category") or ""),
        str(obj.get("size") or ""),
        str(obj.get("placement") or ""),
        str(obj.get("mounting") or ""),
    ]
    orientation = obj.get("orientation")
    if isinstance(orientation, dict):
        parts.append(str(orientation.get("faces") or ""))
    for key in ("shape", "required_features", "source_phrases", "materials", "style_details", "parts"):
        parts.extend(flatten_detail_values(obj.get(key)))
    return tokenize_name(" ".join(parts))


def scene_object_category(obj):
    label = str(obj.get("label") or obj.get("id") or "")
    category = str(obj.get("category") or "")
    tokens = scene_object_tokens(obj)
    if category == "screen":
        return "wall_panel" if has_any(tokens, ("window", "porthole")) else "monitor"
    if category == "lighting":
        return "lamp"
    if category == "plant":
        return "tree"
    if category == "path":
        return "path"
    if category in {"cube", "sphere", "cylinder", "cone"}:
        return category
    if category == "surface":
        return "wall_panel" if has_any(tokens, ("panel", "plate")) else "table"
    if category == "machine" and has_any(tokens, ("engine", "motor", "thruster", "exhaust", "nozzle")):
        return "vehicle_engine"
    return category_for_name(label, None)


def scene_object_count(obj):
    count = obj.get("count")
    if isinstance(count, int):
        return max(1, min(6, count))
    return count_from_tokens(scene_object_tokens(obj))


def scene_object_position(obj, idx, category):
    label = str(obj.get("label") or obj.get("id") or "")
    placement = str(obj.get("placement") or "")
    mounting = str(obj.get("mounting") or "")
    size = str(obj.get("size") or "")
    text = "_".join(part for part in (size, label, placement, mounting) if part)
    x, y, z = component_position(text, idx)
    tokens = scene_object_tokens(obj)

    if placement in {"left", "right", "front", "back", "rear", "rear_wall", "top", "bottom"}:
        x, y, z = axis_position_for_placement(placement, distance=1.15, z=z)
    elif placement in {"center", "middle"}:
        x, y = 0, 0
    elif placement == "corner":
        x = -1.6
        y = -1.15 if idx % 2 == 0 else 1.15

    if mounting in {"wall", "ceiling"} or placement == "rear_wall":
        x = -1.85 if mounting != "ceiling" else 0
        y = 0 if mounting != "ceiling" else y
        z = 1.15 if mounting != "ceiling" else 1.7
    elif mounting == "surface":
        z = max(z, 0.92)

    if category == "vehicle_fuselage":
        x, y, z = 0, 0, 0.72
    elif category == "vehicle_wing":
        x = -0.05
        y = -0.95 if placement == "left" or (placement not in {"right", "left"} and idx % 2 == 0) else 0.95
        z = 0.58
    elif category == "vehicle_engine":
        x = -1.25 if has_any(tokens, ("ship", "rocket", "rear", "engine", "thruster")) else x
        y = 0 if has_any(tokens, ("ship", "rocket", "engine", "thruster")) else y
        z = 0.62
    elif category == "vehicle_nose":
        x, y, z = 1.45, 0, 0.72
    elif category == "vehicle_tail":
        x, y, z = -1.45, 0, 1.0

    return x, y, z


def offset_position(base, copy_idx, total):
    if total == 1:
        return base
    x, y, z = base
    spread = 0.38
    return x + (copy_idx - (total - 1) / 2) * spread, y, z


def offset_position_for_category(base, copy_idx, total, category):
    if total == 1:
        return base
    x, y, z = base
    if category == "vehicle_wing":
        spread = 1.9
        return x, y + (copy_idx - (total - 1) / 2) * spread, z
    return offset_position(base, copy_idx, total)


def object_has_detail(obj, words):
    return has_any(scene_object_tokens(obj), words)


def make_table_like(name, x, y, z, mat, rounded=False, thin_legs=False):
    leg_radius = 0.024 if thin_legs else 0.035
    if rounded:
        top = [
            cube(f"{name}_top_center", (x, y, 0.68), (1.05, 0.72, 0.14), mat["wood"]),
            cube(f"{name}_top_mid", (x, y, 0.68), (1.35, 0.4, 0.14), mat["wood"]),
        ]
        for corner_idx, (cx, cy) in enumerate(((-0.52, -0.2), (-0.52, 0.2), (0.52, -0.2), (0.52, 0.2)), start=1):
            top.append(cylinder(f"{name}_rounded_corner_{corner_idx}", (x + cx, y + cy, 0.68), 0.16, 0.14, mat["wood"]))
    else:
        top = [cube(f"{name}_top", (x, y, 0.68), (1.35, 0.72, 0.14), mat["wood"])]
    legs = []
    for lx in (-0.52, 0.52):
        for ly in (-0.25, 0.25):
            legs.append(cylinder(f"{name}_leg_{len(legs) + 1}", (x + lx, y + ly, 0.34), leg_radius, 0.68, mat["metal"]))
    return [*top, *legs]


def make_chair(name, x, y, mat):
    back_y = y + (0.24 if "front" not in name else -0.24)
    return [
        cube(f"{name}_seat", (x, y, 0.34), (0.5, 0.48, 0.12), mat["dark"]),
        cube(f"{name}_back", (x, back_y, 0.72), (0.5, 0.1, 0.68), mat["dark"]),
        cylinder(f"{name}_post", (x, y, 0.17), 0.035, 0.34, mat["metal"]),
    ]


def make_bed(name, x, y, mat):
    return [
        cube(f"{name}_base", (x, y, 0.32), (1.55, 0.86, 0.28), mat["neutral"]),
        cube(f"{name}_mattress", (x, y, 0.53), (1.45, 0.78, 0.18), mat["soft"]),
        cube(f"{name}_pillow", (x - 0.46, y + 0.22, 0.68), (0.38, 0.26, 0.12), mat["light"]),
    ]


def make_cabinet(name, x, y, mat):
    return [
        cube(f"{name}_body", (x, y, 0.45), (0.72, 0.42, 0.82), mat["wood"]),
        cube(f"{name}_drawer_1", (x, y - 0.22, 0.56), (0.56, 0.04, 0.13), mat["dark"]),
        cube(f"{name}_drawer_2", (x, y - 0.22, 0.34), (0.56, 0.04, 0.13), mat["dark"]),
    ]


def make_monitor(name, x, y, z, mat):
    return [
        cube(f"{name}_screen", (x, y, z + 0.12), (0.5, 0.06, 0.34), mat["glass"]),
        cylinder(f"{name}_stand", (x, y, z - 0.12), 0.025, 0.28, mat["metal"]),
        cube(f"{name}_base", (x, y, z - 0.27), (0.32, 0.18, 0.04), mat["metal"]),
    ]


def make_lamp(name, x, y, z, mat):
    return [
        cylinder(f"{name}_stem", (x, y, z), 0.025, 0.56, mat["metal"]),
        cylinder(f"{name}_shade", (x, y, z + 0.34), 0.16, 0.2, mat["glow"]),
    ]


def make_vehicle_controls(name, x, y, z, mat):
    return [
        cylinder(f"{name}_stem", (x, y, z - 0.16), 0.03, 0.38, mat["metal"]),
        cylinder(f"{name}_bar", (x, y, z + 0.08), 0.035, 0.78, mat["metal"], rotation=(1.5708, 0, 0)),
    ]


def make_vehicle_seat(name, x, y, z, mat):
    return [
        cube(f"{name}_pad", (x, y, z), (0.7, 0.34, 0.1), mat["dark"]),
        cylinder(f"{name}_post", (x, y, z - 0.18), 0.035, 0.34, mat["metal"]),
    ]


def make_vehicle_fuselage(name, x, y, z, mat):
    return [
        cylinder(f"{name}_body", (x, y, z), 0.24, 2.7, mat["metal"], rotation=(0, 1.5708, 0)),
        sphere(f"{name}_canopy", (x + 0.42, y, z + 0.26), (0.34, 0.22, 0.14), mat["glass"]),
    ]


def make_vehicle_wing(name, x, y, z, mat):
    wing = cube(name, (x, y, z), (0.95, 1.35, 0.07), mat["neutral"])
    wing.rotation_euler[2] = -0.16 if y > 0 else 0.16
    return [wing]


def make_vehicle_nose(name, x, y, z, mat):
    nose = sphere(name, (x, y, z), (0.42, 0.23, 0.2), mat["metal"])
    return [nose]


def make_vehicle_tail(name, x, y, z, mat):
    vertical = cube(f"{name}_vertical", (x, y, z), (0.14, 0.08, 0.72), mat["metal"])
    vertical.rotation_euler[1] = -0.18
    horizontal = cube(f"{name}_horizontal", (x + 0.05, y, z - 0.3), (0.58, 0.82, 0.07), mat["neutral"])
    return [vertical, horizontal]


def primitive_for_component(component, idx, mat):
    name, shape_hint = semantic_name(component)
    safe_name = safe_object_name(name, f"component_{idx + 1}")
    tokens = tokenize_name(name)
    category = category_for_name(name, shape_hint)
    count = count_from_tokens(tokens)
    base_position = component_position(name, idx)
    objects = []

    for copy_idx in range(count):
        x, y, z = offset_position_for_category(base_position, copy_idx, count, category)
        suffix = f"_{copy_idx + 1}" if count > 1 else ""
        obj_name = f"{safe_name}{suffix}"
        mat_choice = material_for_category(category, tokens, mat)

        if category == "tree":
            objects.append(cylinder(f"{obj_name}_trunk", (x, y, 0.38), 0.08, 0.76, mat["bark"]))
            objects.append(sphere(f"{obj_name}_canopy", (x, y, 0.95), (0.38, 0.38, 0.34), mat["green"]))
        elif category == "bed":
            objects.extend(make_bed(obj_name, x, y, mat))
        elif category == "cabinet":
            objects.extend(make_cabinet(obj_name, x, y, mat))
        elif category == "lamp":
            objects.extend(make_lamp(obj_name, x, y, z, mat))
        elif category == "chair":
            objects.extend(make_chair(obj_name, x, y, mat))
        elif category == "monitor":
            objects.extend(make_monitor(obj_name, x, y, z, mat))
        elif category == "wall_panel":
            objects.append(cube(obj_name, (x, y, z), (0.95, 0.05, 0.7), mat_choice))
        elif category == "path":
            obj = cube(obj_name, (x, y, 0.04), (1.45, 0.38, 0.05), mat["path"])
            obj.rotation_euler[2] = -0.25
            objects.append(obj)
        elif category == "vehicle_fuselage":
            objects.extend(make_vehicle_fuselage(obj_name, x, y, z, mat))
        elif category == "vehicle_wing":
            objects.extend(make_vehicle_wing(obj_name, x, y, z, mat))
        elif category == "vehicle_nose":
            objects.extend(make_vehicle_nose(obj_name, x, y, z, mat))
        elif category == "vehicle_tail":
            objects.extend(make_vehicle_tail(obj_name, x, y, z, mat))
        elif category == "vehicle_controls":
            objects.extend(make_vehicle_controls(obj_name, x, y, z, mat))
        elif category == "vehicle_seat":
            objects.extend(make_vehicle_seat(obj_name, x, y, z, mat))
        elif category == "vehicle_engine":
            objects.append(cylinder(obj_name, (x, y, 0.72), 0.18, 0.58, mat["metal"], rotation=(0, 1.5708, 0)))
        elif category == "table":
            objects.extend(make_table_like(
                obj_name,
                x,
                y,
                z,
                mat,
                rounded=has_any(tokens, ("rounded", "rounded_corners")),
                thin_legs=has_any(tokens, ("thin_legs", "thin")),
            ))
        elif category == "ring":
            objects.append(torus(obj_name, (x, y, 0.48), 0.34, 0.04, mat_choice, rotation=(1.5708, 0, 0)))
        elif category == "cylinder":
            radius = 0.14 if has_any(tokens, ("thin", "small", "pipe", "post")) else 0.22
            depth = 0.75 if has_any(tokens, ("short", "small")) else 1.0
            objects.append(cylinder(obj_name, (x, y, depth / 2), radius, depth, mat_choice))
        elif category == "sphere":
            scale = (0.28, 0.28, 0.25) if has_any(tokens, ("small", "tiny")) else (0.42, 0.42, 0.36)
            objects.append(sphere(obj_name, (x, y, 0.42), scale, mat_choice))
        elif category == "thin_slab":
            scale = (1.1, 0.7, 0.08) if not has_any(tokens, ("large", "big", "wide")) else (1.8, 1.0, 0.08)
            if has_any(tokens, ("frame", "chassis")):
                scale = (1.75, 0.16, 0.14)
            slab_z = z if has_any(tokens, ("overhead", "ceiling", "canopy", "awning", "roof")) else 0.06
            if has_any(tokens, ("low", "frame", "chassis")):
                slab_z = z
            objects.append(cube(obj_name, (x, y, slab_z), scale, mat_choice))
        elif category == "tall_block":
            objects.append(cube(obj_name, (x, y, 0.8), (0.45, 0.45, 1.45), mat_choice))
        else:
            scale = (0.72, 0.46, 0.46)
            if has_any(tokens, ("large", "big", "wide")):
                scale = (1.05, 0.62, 0.58)
            if has_any(tokens, ("small", "tiny")):
                scale = (0.42, 0.32, 0.3)
            objects.append(cube(obj_name, (x, y, scale[2] / 2), scale, mat_choice))

    return objects


def scene_plan_objects(spec):
    for key in ("repaired_scene_plan", "scene_plan"):
        plan = spec.get(key)
        if isinstance(plan, dict) and isinstance(plan.get("objects"), list) and plan["objects"]:
            return [obj for obj in plan["objects"] if isinstance(obj, dict)]
    return []


def registry_primitives(spec):
    primitives = spec.get("primitives")
    if isinstance(primitives, list):
        return [primitive for primitive in primitives if isinstance(primitive, dict)]
    return []


def vec3(value, default):
    if isinstance(value, list) and len(value) == 3:
        try:
            return tuple(float(item) for item in value)
        except (TypeError, ValueError):
            return default
    return default


def material_for_registry_primitive(primitive, mat):
    material_key = str(primitive.get("material") or "neutral").lower()
    if material_key == "grey":
        material_key = "gray"
    if material_key == "metallic":
        material_key = "metal"
    return mat.get(material_key, mat["neutral"])


def _registry_box(name, location, rotation, scale, params, mat):
    obj = cube(name, location, scale, mat)
    obj.rotation_euler = rotation
    return [obj]


def _registry_sphere(name, location, rotation, scale, params, mat):
    radius = float(params.get("radius", 0.5))
    obj = sphere(name, location, (scale[0] * radius, scale[1] * radius, scale[2] * radius), mat)
    obj.rotation_euler = rotation
    return [obj]


def _registry_cylinder(name, location, rotation, scale, params, mat):
    radius = float(params.get("radius", 0.35))
    depth = float(params.get("depth", 1.0))
    obj = cylinder(name, location, radius, depth, mat, rotation=rotation)
    obj.scale = (scale[0], scale[1], scale[2])
    return [obj]


def _registry_cone(name, location, rotation, scale, params, mat):
    radius = float(params.get("radius", 0.4))
    depth = float(params.get("depth", 1.0))
    obj = cone(name, location, radius, depth, mat, rotation=rotation)
    obj.scale = (scale[0], scale[1], scale[2])
    return [obj]


def _registry_torus(name, location, rotation, scale, params, mat):
    major_radius = float(params.get("major_radius", 0.45))
    minor_radius = float(params.get("minor_radius", 0.08))
    obj = torus(name, location, major_radius, minor_radius, mat, rotation=rotation)
    obj.scale = scale
    return [obj]


def _registry_plane(name, location, rotation, scale, params, mat):
    return [plane(name, location, scale, mat, rotation=rotation)]


def _registry_wedge(name, location, rotation, scale, params, mat):
    return [wedge(name, location, scale, mat, rotation=rotation)]


PRIMITIVE_BUILDERS = {
    "box": _registry_box,
    "cube": _registry_box,
    "sphere": _registry_sphere,
    "cylinder": _registry_cylinder,
    "cone": _registry_cone,
    "torus": _registry_torus,
    "plane": _registry_plane,
    "wedge": _registry_wedge,
}


def primitive_for_registry_instance(primitive, idx, mat):
    primitive_type = str(primitive.get("type") or "").lower()
    builder = PRIMITIVE_BUILDERS.get(primitive_type)
    if not builder:
        raise ValueError(f"Unsupported primitive type: {primitive_type}")
    transform = primitive.get("transform") if isinstance(primitive.get("transform"), dict) else {}
    name = safe_object_name(primitive.get("id"), f"{primitive_type}_{idx + 1}")
    location = vec3(transform.get("location"), (0.0, 0.0, 0.5))
    rotation = vec3(transform.get("rotation"), (0.0, 0.0, 0.0))
    scale = vec3(transform.get("scale"), (1.0, 1.0, 1.0))
    params = primitive.get("params") if isinstance(primitive.get("params"), dict) else {}
    return builder(name, location, rotation, scale, params, material_for_registry_primitive(primitive, mat))


def layout_items_for_spec(spec):
    objects = scene_plan_objects(spec)
    if objects:
        return [{"source": "scene_object", "value": obj} for obj in objects]
    components = spec.get("components")
    if isinstance(components, list) and components:
        return [{"source": "component", "value": component} for component in components]
    raise ValueError("Primitive build spec must include scene objects or non-empty components")


def components_for_layout(spec):
    return [item["value"] for item in layout_items_for_spec(spec) if item["source"] == "component"]


def primitive_for_scene_object(obj, idx, mat):
    name = scene_object_name(obj, idx)
    category = scene_object_category(obj)
    tokens = scene_object_tokens(obj)
    count = scene_object_count(obj)
    base_position = scene_object_position(obj, idx, category)
    objects = []

    for copy_idx in range(count):
        x, y, z = offset_position_for_category(base_position, copy_idx, count, category)
        suffix = f"_{copy_idx + 1}" if count > 1 else ""
        obj_name = f"{name}{suffix}"
        mat_choice = material_for_category(category, tokens, mat)

        if category == "vehicle_fuselage":
            objects.extend(make_vehicle_fuselage(obj_name, x, y, z, mat))
        elif category == "vehicle_wing":
            objects.extend(make_vehicle_wing(obj_name, x, y, z, mat))
        elif category == "vehicle_nose":
            objects.extend(make_vehicle_nose(obj_name, x, y, z, mat))
        elif category == "vehicle_tail":
            objects.extend(make_vehicle_tail(obj_name, x, y, z, mat))
        elif category == "vehicle_engine":
            objects.append(cylinder(obj_name, (x, y, z), 0.18, 0.58, mat["metal"], rotation=(0, 1.5708, 0)))
        elif category == "wall_panel":
            objects.append(cube(obj_name, (x, y, z), (0.62, 0.05, 0.42), mat_choice))
        elif category in {"box", "cube"}:
            objects.append(cube(obj_name, (x, y, z), (0.72, 0.72, 0.72), mat_choice))
        elif category == "sphere":
            objects.append(sphere(obj_name, (x, y, z), (0.42, 0.42, 0.42), mat_choice))
        elif category == "cylinder":
            objects.append(cylinder(obj_name, (x, y, z), 0.28, 0.82, mat_choice))
        elif category == "cone":
            objects.append(cone(obj_name, (x, y, z), 0.34, 0.82, mat_choice))
        elif category == "table":
            objects.extend(make_table_like(
                obj_name,
                x,
                y,
                z,
                mat,
                rounded=object_has_detail(obj, ("rounded", "rounded_corners")),
                thin_legs=object_has_detail(obj, ("thin_legs", "thin")),
            ))
        else:
            objects.extend(primitive_for_component(" ".join(tokens) or name, idx, mat))

    return objects


def uses_location_shell(spec):
    return spec.get("kind") in {"location", "set"}


def layout_shell_descriptors(spec):
    if not uses_location_shell(spec):
        return []
    return [
        ("layout_floor", (0, 0, -0.08), (6.2, 3.8, 0.1), "neutral"),
        ("layout_back_wall", (-3.1, 0, 1.0), (0.08, 3.8, 2.05), "light"),
    ]


def make_component_layout_scene(spec):
    mats = {
        "neutral": material("component_neutral_clay", (0.64, 0.62, 0.57, 1)),
        "dark": material("component_dark", (0.09, 0.1, 0.1, 1)),
        "metal": material("component_metal", (0.24, 0.25, 0.25, 1)),
        "wood": material("component_wood", (0.42, 0.25, 0.12, 1)),
        "glass": material("component_glass_blue", (0.14, 0.45, 0.8, 0.72)),
        "green": material("component_green", (0.1, 0.34, 0.12, 1)),
        "blue": material("component_blue", (0.05, 0.22, 0.85, 1)),
        "red": material("component_red", (0.78, 0.08, 0.06, 1)),
        "yellow": material("component_yellow", (1.0, 0.78, 0.08, 1)),
        "orange": material("component_orange", (0.95, 0.38, 0.06, 1)),
        "purple": material("component_purple", (0.45, 0.14, 0.72, 1)),
        "black": material("component_black", (0.02, 0.02, 0.025, 1)),
        "white": material("component_white", (0.92, 0.92, 0.88, 1)),
        "gray": material("component_gray", (0.45, 0.46, 0.48, 1)),
        "bark": material("component_bark", (0.26, 0.13, 0.06, 1)),
        "path": material("component_path", (0.55, 0.46, 0.33, 1)),
        "glow": material("component_warm_glow", (1.0, 0.74, 0.28, 1)),
        "soft": material("component_soft_surface", (0.72, 0.72, 0.68, 1)),
        "light": material("component_light_surface", (0.86, 0.86, 0.82, 1)),
    }
    objects = [
        cube(name, location, scale, mats[mat_key])
        for name, location, scale, mat_key in layout_shell_descriptors(spec)
    ]
    primitives = registry_primitives(spec)
    if primitives:
        for idx, primitive in enumerate(primitives[:100]):
            objects.extend(primitive_for_registry_instance(primitive, idx, mats))
    else:
        layout_items = layout_items_for_spec(spec)
        for idx, item in enumerate(layout_items[:10]):
            if item["source"] == "scene_object":
                objects.extend(primitive_for_scene_object(item["value"], idx, mats))
            else:
                objects.extend(primitive_for_component(item["value"], idx, mats))

    action_view = canonical_camera_views()["action"]
    add_preview_setup(
        camera_location=action_view["location"],
        target=action_view["target"],
        ortho_scale=action_view["ortho_scale"],
    )
    return parent_to_root(spec, objects), "component_layout"


def make_scene(spec):
    clear_scene()
    return make_component_layout_scene(spec)


def main():
    args = parse_args()
    spec = json.loads(args.spec_json)

    output = Path(args.output)
    preview = Path(args.preview_output)
    manifest = Path(args.manifest_output)
    for path in (output, preview, manifest):
        path.parent.mkdir(parents=True, exist_ok=True)

    root, variant = make_scene(spec)

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
        "creative_request": spec.get("creative_request"),
        "primitives": spec.get("primitives", []),
        "components": spec.get("components", []),
        "scene_plan": spec.get("scene_plan"),
        "repaired_scene_plan": spec.get("repaired_scene_plan"),
        "orientation_standard": orientation_standard(spec),
        "canonical_camera_views": canonical_camera_views(),
        "variant": variant,
        "outputs": {
            "glb": str(output),
            "preview": str(preview),
        },
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
