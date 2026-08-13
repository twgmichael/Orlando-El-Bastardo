#!/usr/bin/env python3
"""Build the OEB primitive Earth Starfighter from editable Blender geometry.

The approved concept is a low, broad, single-seat Earth interceptor in the
project's simple smooth 1999 CGI language.  The ship is authored at real scale:

    14 m long (+X front), 12 m wide, 3 m high, lowest point at Z=0.

Run from Orlando-El-Bastardo.src:

    blender --background --factory-startup \
      --python tools/build_earth_starfighter.py -- \
      --output assets/ships/earth_starfighter_hero_v0.0.3/earth_starfighter_hero_v0.0.3 \
      --review-dir assets/ships/earth_starfighter_hero_v0.0.3/review
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ASSET_ID = "ship_earth_starfighter_hero_A"
DISPLAY_NAME = "Earth Starfighter Hero"
VERSION = "0.0.3"
DIMENSIONS_M = (14.0, 12.0, 3.0)


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser(prog="build_earth_starfighter")
    parser.add_argument(
        "--output",
        default="assets/ships/earth_starfighter_hero_v0.0.3/earth_starfighter_hero_v0.0.3",
        help="Output stem for .blend, .glb, and .manifest.json",
    )
    parser.add_argument("--review-dir", default=None)
    return parser.parse_args(argv)


def make_material(
    name: str,
    color: tuple[float, float, float],
    *,
    roughness: float = 0.42,
    metallic: float = 0.08,
    emission: tuple[tuple[float, float, float], float] | None = None,
    alpha: float | None = None,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission[0], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        material.surface_render_method = "DITHERED"
        material.use_transparency_overlap = False
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.append(material)


def smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def apply_scale(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)


def bevel(obj: bpy.types.Object, width: float, segments: int = 3) -> None:
    modifier = obj.modifiers.new(f"{obj.name}_soft_1999_edges", "BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"


def add_rounded_box(
    name: str,
    material: bpy.types.Material,
    dimensions: tuple[float, float, float],
    location: tuple[float, float, float],
    *,
    bevel_width: float = 0.08,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    obj.dimensions = dimensions
    apply_scale(obj)
    assign_material(obj, material)
    bevel(obj, bevel_width)
    return obj


def add_uv_ellipsoid(
    name: str,
    material: bpy.types.Material,
    scale: tuple[float, float, float],
    location: tuple[float, float, float],
    *,
    segments: int = 32,
    rings: int = 16,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=1.0,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    obj.scale = scale
    apply_scale(obj)
    assign_material(obj, material)
    smooth(obj)
    return obj


def add_upper_hemisphere(
    name: str,
    material: bpy.types.Material,
    radius: float,
    base_z: float,
    center_xy: tuple[float, float],
    *,
    segments: int = 32,
    rings: int = 16,
) -> bpy.types.Object:
    """Create a true sealed half sphere with its flat base at ``base_z``."""
    bm = bmesh.new()
    result = bmesh.ops.create_uvsphere(
        bm,
        u_segments=segments,
        v_segments=rings,
        radius=radius,
    )
    lower = [vertex for vertex in result["verts"] if vertex.co.z < -1e-6]
    bmesh.ops.delete(bm, geom=lower, context="VERTS")
    boundary = [edge for edge in bm.edges if edge.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(bm, edges=boundary)
    for vertex in bm.verts:
        vertex.co += Vector((center_xy[0], center_xy[1], base_z))
    obj = object_from_bmesh(name, bm, material)
    smooth(obj)
    return obj


def add_cylinder_x(
    name: str,
    material: bpy.types.Material,
    radius: float,
    depth: float,
    location: tuple[float, float, float],
    *,
    vertices: int = 24,
    bevel_width: float | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=(0.0, math.pi * 0.5, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    assign_material(obj, material)
    smooth(obj)
    if bevel_width is None:
        bevel_width = min(0.045, depth * 0.08)
    if bevel_width:
        bevel(obj, bevel_width, segments=2)
    return obj


def add_cylinder_z(
    name: str,
    material: bpy.types.Material,
    radius: float,
    depth: float,
    location: tuple[float, float, float],
    *,
    vertices: int = 24,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    assign_material(obj, material)
    smooth(obj)
    bevel(obj, min(0.035, depth * 0.12), segments=2)
    return obj


def add_cone_x(
    name: str,
    material: bpy.types.Material,
    radius_rear: float,
    radius_front: float,
    depth: float,
    location: tuple[float, float, float],
    *,
    vertices: int = 24,
) -> bpy.types.Object:
    # Default cone bottom (-Z) becomes rear (-X); top (+Z) becomes front (+X).
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius_rear,
        radius2=radius_front,
        depth=depth,
        location=location,
        rotation=(0.0, math.pi * 0.5, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    assign_material(obj, material)
    smooth(obj)
    return obj


def add_torus(
    name: str,
    material: bpy.types.Material,
    major_radius: float,
    minor_radius: float,
    scale_xy: tuple[float, float],
    location: tuple[float, float, float],
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=32,
        minor_segments=8,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_mesh"
    obj.scale = (scale_xy[0], scale_xy[1], 1.0)
    apply_scale(obj)
    assign_material(obj, material)
    smooth(obj)
    return obj


def object_from_bmesh(
    name: str, bm: bmesh.types.BMesh, material: bpy.types.Material
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    assign_material(obj, material)
    return obj


def add_prism(
    name: str,
    material: bpy.types.Material,
    outline_xy: list[tuple[float, float]],
    z_bottom: float,
    z_top: float,
    *,
    bevel_width: float = 0.0,
    smooth_faces: bool = False,
) -> bpy.types.Object:
    bm = bmesh.new()
    bottom = [bm.verts.new((x, y, z_bottom)) for x, y in outline_xy]
    top = [bm.verts.new((x, y, z_top)) for x, y in outline_xy]
    bm.faces.new(list(reversed(bottom)))
    bm.faces.new(top)
    for index in range(len(outline_xy)):
        nxt = (index + 1) % len(outline_xy)
        bm.faces.new((bottom[index], bottom[nxt], top[nxt], top[index]))
    obj = object_from_bmesh(name, bm, material)
    if smooth_faces:
        smooth(obj)
    if bevel_width:
        bevel(obj, bevel_width, segments=3)
    return obj


def add_fuselage(name: str, material: bpy.types.Material) -> bpy.types.Object:
    """Create a blunt, smoothly faceted hull from eight-point cross sections."""
    slices = (
        (-5.55, 2.35, 0.46, 1.62),
        (-3.10, 3.10, 0.38, 1.78),
        (0.10, 3.55, 0.34, 1.82),
        (3.20, 2.80, 0.38, 1.67),
        (5.55, 1.55, 0.43, 1.43),
        (6.42, 0.76, 0.52, 1.26),
    )
    bm = bmesh.new()
    rings: list[list[bmesh.types.BMVert]] = []
    for x, half_width, z_bottom, z_top in slices:
        height = z_top - z_bottom
        coordinates = (
            (0.72 * half_width, z_bottom),
            (half_width, z_bottom + 0.28 * height),
            (half_width, z_top - 0.28 * height),
            (0.70 * half_width, z_top),
            (-0.70 * half_width, z_top),
            (-half_width, z_top - 0.28 * height),
            (-half_width, z_bottom + 0.28 * height),
            (-0.72 * half_width, z_bottom),
        )
        rings.append([bm.verts.new((x, y, z)) for y, z in coordinates])
    for first, second in zip(rings, rings[1:]):
        for index in range(8):
            nxt = (index + 1) % 8
            bm.faces.new((first[index], second[index], second[nxt], first[nxt]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    obj = object_from_bmesh(name, bm, material)
    smooth(obj)
    bevel(obj, 0.075, segments=3)
    return obj


def parent_parts(root: bpy.types.Object, parts: list[bpy.types.Object]) -> None:
    for part in parts:
        part.parent = root


def evaluated_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        for vertex in mesh.vertices:
            point = evaluated.matrix_world @ vertex.co
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
        evaluated.to_mesh_clear()
    return minimum, maximum


def build_ship() -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    navy = make_material(
        "mat_earth_starfighter_navy", (0.025, 0.12, 0.30), roughness=0.34, metallic=0.18
    )
    navy_light = make_material(
        "mat_earth_starfighter_navy_light", (0.08, 0.24, 0.47), roughness=0.38, metallic=0.12
    )
    ivory = make_material(
        "mat_earth_starfighter_ivory", (0.78, 0.74, 0.61), roughness=0.46, metallic=0.05
    )
    orange = make_material(
        "mat_earth_starfighter_safety_orange", (0.95, 0.22, 0.015), roughness=0.34, metallic=0.08
    )
    dark_metal = make_material(
        "mat_earth_starfighter_dark_metal", (0.055, 0.065, 0.075), roughness=0.30, metallic=0.72
    )
    silver = make_material(
        "mat_earth_starfighter_engine_metal", (0.38, 0.40, 0.42), roughness=0.28, metallic=0.82
    )
    glass = make_material(
        "mat_earth_starfighter_canopy", (0.018, 0.021, 0.024), roughness=0.18, metallic=0.28
    )
    yellow = make_material(
        "mat_earth_starfighter_nav_yellow",
        (1.0, 0.72, 0.02),
        roughness=0.22,
        emission=((1.0, 0.48, 0.0), 1.8),
    )

    root = bpy.data.objects.new(ASSET_ID, None)
    bpy.context.scene.collection.objects.link(root)
    root.empty_display_type = "ARROWS"
    root["asset_id"] = ASSET_ID
    root["display_name"] = DISPLAY_NAME
    root["version"] = VERSION
    root["previous_version"] = "0.0.2"
    root["production_role"] = "hero"
    root["asset_family"] = "vehicle.ship.starfighter"
    root["style"] = "simple smooth 1999 CGI"
    root["dimensions_m"] = list(DIMENSIONS_M)
    root["front_axis"] = "+X"
    root["up_axis"] = "+Z"
    root["origin_policy"] = "vehicle centerline at body midpoint; lowest geometry Z=0"

    parts: list[bpy.types.Object] = []

    # Broad delta shoulders establish the exact 12 m span.
    left_wing = [
        (4.20, 0.72),
        (2.45, 2.10),
        (-0.35, 6.00),
        (-2.85, 5.25),
        (-4.85, 3.05),
        (-4.20, 1.62),
    ]
    right_wing = [(x, -y) for x, y in left_wing]
    # Keep the outer wing edges sharp, like a 1999 low-poly flight model. This
    # also preserves the authored Y=+/-6 m extrema exactly.
    parts.append(add_prism("earth_starfighter_left_wing", navy, left_wing, 0.58, 1.25))
    parts.append(add_prism("earth_starfighter_right_wing", navy, right_wing, 0.58, 1.25))

    # Raised ivory wing caps carry the intentionally simple texture-map read.
    left_cap = [
        (3.35, 1.75),
        (2.15, 3.15),
        (-0.40, 5.55),
        (-1.85, 5.05),
        (-2.65, 4.05),
        (-0.85, 2.75),
        (2.25, 1.45),
    ]
    right_cap = [(x, -y) for x, y in left_cap]
    parts.append(add_prism("earth_starfighter_left_ivory_panel", ivory, left_cap, 1.245, 1.285, bevel_width=0.018))
    parts.append(add_prism("earth_starfighter_right_ivory_panel", ivory, right_cap, 1.245, 1.285, bevel_width=0.018))

    parts.append(add_fuselage("earth_starfighter_primary_hull", navy))
    parts.append(add_uv_ellipsoid("earth_starfighter_orange_nose", orange, (1.10, 1.36, 0.63), (5.90, 0.0, 1.05), segments=28, rings=14))

    # A cream dorsal stripe and raised equipment spine echo the approved plate.
    parts.append(add_rounded_box("earth_starfighter_dorsal_ivory_stripe", ivory, (5.10, 1.05, 0.10), (3.12, 0.0, 1.76), bevel_width=0.04))
    parts.append(add_rounded_box("earth_starfighter_equipment_spine", navy_light, (3.10, 1.35, 0.66), (-1.42, 0.0, 1.72), bevel_width=0.22))
    parts.append(add_rounded_box("earth_starfighter_spine_orange_band", orange, (0.22, 1.39, 0.70), (-2.20, 0.0, 1.72), bevel_width=0.035))

    # True circular half-sphere canopy. Its sealed base sits below the local
    # deck surface, so the bubble and matching circular rim cannot reveal a
    # gap even at grazing angles. The upper pole remains exactly Z=3 m.
    parts.append(add_upper_hemisphere(
        "earth_starfighter_canopy", glass, 1.42, 1.58, (1.43, 0.0),
        segments=32, rings=16,
    ))
    parts.append(add_torus(
        "earth_starfighter_canopy_ivory_rim", ivory, 1.31, 0.085,
        (1.0, 1.0), (1.43, 0.0, 1.67),
    ))

    # Twin exposed primitive engines: blue cans, metallic collars, orange tails.
    for side, y in (("left", -3.18), ("right", 3.18)):
        parts.append(add_cylinder_x(f"earth_starfighter_engine_{side}_body", navy_light, 0.69, 3.55, (-4.40, y, 2.02)))
        parts.append(add_cone_x(f"earth_starfighter_engine_{side}_fore_cap", silver, 0.66, 0.19, 0.85, (-2.20, y, 2.02)))
        parts.append(add_cylinder_x(f"earth_starfighter_engine_{side}_silver_ring", silver, 0.74, 0.22, (-5.80, y, 2.02)))
        parts.append(add_cylinder_x(f"earth_starfighter_engine_{side}_dark_ring", dark_metal, 0.71, 0.28, (-6.03, y, 2.02)))
        # Rear caps run exactly to X=-7, fixing the overall length with the nose.
        parts.append(add_cylinder_x(f"earth_starfighter_engine_{side}_orange_exhaust", orange, 0.69, 0.80, (-6.60, y, 2.02), bevel_width=0.0))
        parts.append(add_cylinder_x(f"earth_starfighter_engine_{side}_hot_core", yellow, 0.31, 0.025, (-6.9875, y, 2.02), vertices=20, bevel_width=0.0))

    # Four recessed-looking maneuver discs touch Z=0 but remain inside the hull.
    for x in (-1.55, 2.65):
        for side, y in (("left", -2.30), ("right", 2.30)):
            parts.append(add_cylinder_z(f"earth_starfighter_belly_disc_{x:+.2f}_{side}", dark_metal, 0.43, 0.16, (x, y, 0.08), vertices=20))
            parts.append(add_cylinder_z(f"earth_starfighter_belly_disc_core_{x:+.2f}_{side}", ivory, 0.20, 0.025, (x, y, 0.165), vertices=16))

    # Yellow navigation blocks at the shoulder tips.
    for side, y in (("left", -5.38), ("right", 5.38)):
        parts.append(add_rounded_box(f"earth_starfighter_nav_light_{side}", yellow, (0.56, 0.38, 0.13), (-0.42, y, 1.34), bevel_width=0.09))

    # Blunt black intake/grille on the orange nose.
    parts.append(add_rounded_box("earth_starfighter_nose_grille", dark_metal, (0.05, 0.70, 0.33), (6.952, 0.0, 0.98), bevel_width=0.018))
    for y in (-0.22, 0.0, 0.22):
        parts.append(add_rounded_box(f"earth_starfighter_nose_grille_bar_{y:+.2f}", silver, (0.012, 0.045, 0.27), (6.988, y, 0.98), bevel_width=0.002))

    parent_parts(root, parts)
    return root, parts


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_reviews(review_dir: Path, parts: list[bpy.types.Object]) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass

    world = bpy.data.worlds.new("earth_starfighter_review_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.018, 0.022, 0.028, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.22
    scene.world = world

    for name, energy, location, size in (
        ("review_key", 1350.0, (11.0, -12.0, 13.0), 8.0),
        ("review_fill", 800.0, (-10.0, 9.0, 8.0), 10.0),
        ("review_rim", 950.0, (-8.0, -8.0, 11.0), 7.0),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, Vector((0.0, 0.0, 1.3)))

    # Inspection fill used only by the bottom orthographic view. Keeping it
    # disabled for the other angles preserves their existing contrast while
    # making the navy belly and maneuver discs legible against black.
    underside_data = bpy.data.lights.new("review_underside_fill", "AREA")
    underside_data.energy = 0.0
    underside_data.shape = "DISK"
    underside_data.size = 12.0
    underside = bpy.data.objects.new("review_underside_fill", underside_data)
    scene.collection.objects.link(underside)
    underside.location = (1.5, -2.0, -9.0)
    look_at(underside, Vector((0.0, 0.0, 0.7)))

    camera_data = bpy.data.cameras.new("earth_starfighter_review_camera")
    camera = bpy.data.objects.new("earth_starfighter_review_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    target = Vector((0.0, 0.0, 1.35))

    views = {
        "front": ((20.0, 0.0, 2.7), "ORTHO", 15.0),
        "back": ((-20.0, 0.0, 2.7), "ORTHO", 15.0),
        "left": ((0.0, -20.0, 2.7), "ORTHO", 16.5),
        "right": ((0.0, 20.0, 2.7), "ORTHO", 16.5),
        "top": ((0.0, 0.0, 24.0), "ORTHO", 17.0),
        "bottom": ((0.0, 0.0, -24.0), "ORTHO", 17.0),
        "action": ((18.0, -18.0, 11.0), "PERSP", 52.0),
    }
    for view, (position, camera_type, value) in views.items():
        underside_data.energy = 1050.0 if view == "bottom" else 0.0
        camera.location = position
        camera_data.type = camera_type
        if camera_type == "ORTHO":
            camera_data.ortho_scale = value
        else:
            camera_data.lens = value
        look_at(camera, target)
        scene.render.filepath = str(review_dir / f"earth_starfighter_hero_{view}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[build_earth_starfighter] review wrote {scene.render.filepath}")


def main() -> None:
    args = parse_args()
    output_stem = Path(args.output)
    if not output_stem.is_absolute():
        output_stem = Path.cwd() / output_stem
    output_stem.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    root, parts = build_ship()
    bpy.context.view_layer.update()

    minimum, maximum = evaluated_bounds(parts)
    dimensions = maximum - minimum
    used_materials = sorted({
        material.name
        for part in parts
        for material in part.data.materials
        if material is not None
    })
    print(f"[build_earth_starfighter] bounds min={tuple(minimum)} max={tuple(maximum)} dims={tuple(dimensions)}")

    # The semantic version is part of the basename, so Path.with_suffix()
    # would incorrectly turn v1.0.0 into v1.0.blend.
    blend_path = Path(str(output_stem) + ".blend")
    glb_path = Path(str(output_stem) + ".glb")
    manifest_path = Path(str(output_stem) + ".manifest.json")

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
    )

    manifest = {
        "asset_id": ASSET_ID,
        "display_name": DISPLAY_NAME,
        "version": VERSION,
        "previous_version": "0.0.2",
        "production_role": "hero",
        "maturity": "first_pass",
        "change_summary": "Cockpit bubble replaced by a sealed true half sphere intersecting the hull, with a slightly reflective charcoal-black finish; all other elements unchanged.",
        "style": "simple smooth 1999 CGI",
        "source_concept": "assets/concepts/earth_starfighter_primitive_v1.png",
        "files": {"blend": blend_path.name, "glb": glb_path.name},
        "dimensions_m": {"length_x": 14.0, "width_y": 12.0, "height_z": 3.0},
        "evaluated_bounds": {
            "min": [round(value, 6) for value in minimum],
            "max": [round(value, 6) for value in maximum],
            "dimensions": [round(value, 6) for value in dimensions],
        },
        "orientation_standard": {
            "front_axis": "+X",
            "rear_axis": "-X",
            "left_axis": "-Y",
            "right_axis": "+Y",
            "up_axis": "+Z",
            "down_axis": "-Z",
            "origin_policy": "vehicle centerline at body midpoint; lowest geometry Z=0",
        },
        "construction": {
            "root_node": ASSET_ID,
            "editable_named_parts": len(parts),
            "materials": used_materials,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[build_earth_starfighter] wrote {blend_path}")
    print(f"[build_earth_starfighter] wrote {glb_path}")
    print(f"[build_earth_starfighter] wrote {manifest_path}")

    if args.review_dir:
        review_dir = Path(args.review_dir)
        if not review_dir.is_absolute():
            review_dir = Path.cwd() / review_dir
        render_reviews(review_dir, parts)


if __name__ == "__main__":
    main()
