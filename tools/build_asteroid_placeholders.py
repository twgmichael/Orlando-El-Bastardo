#!/usr/bin/env python3
"""Build five deterministic late-1990s-style asteroid placeholder assets."""

from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import placeholder_blueprint as pb  # noqa: E402 -- SHOT_SCALE_CAMERAS, single source of truth

OUT_DIR = PROJECT_ROOT / "assets" / "placeholders" / "asteroids"
PREVIEW_DIR = OUT_DIR / "previews"
FIELD_ID = "placeholder_location_asteroid_field_A"
# data/resolver_map.json's asteroid_field location relies on these three
# named marks existing in this same GLB (tools/placeholder_blueprint.py's
# with_location_marks convention) -- build_field() replaces that location's
# only geometry, so it must keep providing them or every scene using this
# location fails validate_spec.py's mark resolution (confirmed live 2026-08-09).
#
# Widened 2026-08-10 (docs/planning/CAMERA-SHOT-SCALE-PLAN.md) from the
# original +-2/+-5m spread once real-world scale was applied: JB100 is
# ~6.6m wide (radius ~3.3m, oeb.config.json's prop_jb100_A) and each
# asteroid is targeted to ~10m wide (radius 5m, ASTEROID_LAYOUT below) --
# marks stay on the y=z=0 travel line, deliberately kept clear of every
# asteroid's registered position by more than the sum of both radii
# (verified by the same math tools/motion_library.py's
# clear_marks_for_mover() uses, not just eyeballed).
FIELD_MARKS = {
    "entry": (-25.0, 0.0, 0.0),
    "center": (0.0, 0.0, 0.0),
    "exit": (25.0, 0.0, 0.0),
}

# Real-world-scale asteroid placement (docs/planning/CAMERA-SHOT-SCALE-PLAN.md):
# each asteroid's own scale factor is computed (in build_field()) to bring
# its actual max dimension to ~10m, matching the story's stated scale.
# Positions are pushed well off the y=z=0 entry-center-exit travel line so
# JB100 can move to any of the three marks without its own ~3.3m radius
# ever overlapping an asteroid's ~5m radius -- collision-checked, not
# just spread out by eye (see the module docstring above FIELD_MARKS).
ASTEROID_TARGET_DIAMETER_M = 10.0
ASTEROID_LAYOUT = (
    # (position, rotation_degrees) -- scale is computed per-spec from
    # ASTEROID_TARGET_DIAMETER_M / that spec's own raw max dimension,
    # not a fixed literal here (each raw mesh is a different size).
    ((-22.0, 8.0, 9.0), (12, 18, -18)),
    ((-11.0, -10.0, 7.0), (-18, 26, 14)),
    ((0.0, 11.0, -8.0), (28, -12, 36)),
    ((11.0, -9.0, -10.0), (-14, -22, -20)),
    ((22.0, 10.0, -7.0), (20, 30, 8)),
)


@dataclass(frozen=True)
class AsteroidSpec:
    canonical_id: str
    label: str
    seed: int
    scale: tuple[float, float, float]
    roughness: float
    craters: tuple[tuple[tuple[float, float, float], float, float], ...]
    waist: float = 0.0


SPECS = (
    AsteroidSpec(
        "placeholder_prop_asteroid_round_A",
        "Round",
        199901,
        (1.00, 0.92, 0.88),
        0.13,
        (
            ((0.78, -0.28, 0.56), 0.34, 0.24),
            ((-0.18, -0.82, 0.54), 0.25, 0.13),
        ),
    ),
    AsteroidSpec(
        "placeholder_prop_asteroid_oblong_A",
        "Oblong",
        199902,
        (1.42, 0.72, 0.79),
        0.16,
        (
            ((0.18, -0.76, 0.63), 0.29, 0.19),
            ((-0.81, 0.42, 0.40), 0.23, 0.12),
        ),
    ),
    AsteroidSpec(
        "placeholder_prop_asteroid_jagged_A",
        "Jagged",
        199903,
        (1.08, 0.86, 1.14),
        0.24,
        (((0.58, -0.61, 0.54), 0.25, 0.15),),
    ),
    AsteroidSpec(
        "placeholder_prop_asteroid_peanut_A",
        "Peanut",
        199904,
        (1.34, 0.84, 0.82),
        0.14,
        (
            ((0.72, -0.38, 0.58), 0.27, 0.16),
            ((-0.67, 0.59, 0.45), 0.22, 0.12),
        ),
        waist=0.30,
    ),
    AsteroidSpec(
        "placeholder_prop_asteroid_cratered_A",
        "Cratered",
        199905,
        (1.05, 0.96, 0.91),
        0.12,
        (
            ((0.62, -0.54, 0.57), 0.43, 0.34),
            ((-0.64, -0.38, 0.66), 0.28, 0.18),
            ((0.16, 0.88, 0.44), 0.22, 0.12),
        ),
    ),
)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            datablocks.remove(block)


def make_asteroid_material():
    material = bpy.data.materials.new("asteroid_rock")
    material.diffuse_color = (0.34, 0.28, 0.21, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.34, 0.28, 0.21, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.88
    bsdf.inputs["Metallic"].default_value = 0.0
    vertex_color = material.node_tree.nodes.new("ShaderNodeVertexColor")
    vertex_color.layer_name = "asteroid_color"
    material.node_tree.links.new(vertex_color.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def unit(vector: tuple[float, float, float]) -> Vector:
    value = Vector(vector)
    value.normalize()
    return value


def coherent_lumps(direction: Vector, seed: int) -> float:
    phase = seed * 0.00091
    x, y, z = direction
    low = math.sin(2.3 * x + 3.1 * y - 2.7 * z + phase)
    mid = math.sin(-5.2 * x + 4.4 * y + 3.7 * z + phase * 1.7)
    high = math.cos(8.1 * x - 6.2 * y + 5.4 * z + phase * 2.3)
    return low * 0.54 + mid * 0.30 + high * 0.16


def crater_displacement(
    direction: Vector,
    crater_defs: tuple[tuple[tuple[float, float, float], float, float], ...],
) -> tuple[float, float]:
    depression = 0.0
    crater_score = 0.0
    for crater_direction, angular_radius, depth in crater_defs:
        alignment = max(-1.0, min(1.0, direction.dot(unit(crater_direction))))
        angle = math.acos(alignment)
        if angle >= angular_radius:
            continue
        t = 1.0 - angle / angular_radius
        bowl = depth * (t * t)
        rim = depth * 0.22 * math.exp(-((t - 0.22) / 0.10) ** 2)
        depression += bowl - rim
        crater_score = max(crater_score, t)
    return depression, crater_score


def build_asteroid(spec: AsteroidSpec, material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=3,
        radius=1.0,
        calc_uvs=False,
        location=(0, 0, 0),
    )
    obj = bpy.context.object
    obj.name = spec.canonical_id
    mesh = obj.data
    mesh.name = f"{spec.canonical_id}_mesh"
    rng = random.Random(spec.seed)
    vertex_colors: list[tuple[float, float, float, float]] = []

    for vertex in mesh.vertices:
        direction = vertex.co.normalized()
        lumps = coherent_lumps(direction, spec.seed)
        micro = rng.uniform(-1.0, 1.0)
        radial = 1.0 + spec.roughness * lumps + spec.roughness * 0.12 * micro
        depression, crater_score = crater_displacement(direction, spec.craters)
        radial = max(0.72, radial - depression)
        shaped = Vector((
            direction.x * radial * spec.scale[0],
            direction.y * radial * spec.scale[1],
            direction.z * radial * spec.scale[2],
        ))
        if spec.waist:
            longitudinal = min(1.0, abs(direction.x) * 1.8)
            waist_factor = 1.0 - spec.waist * (1.0 - longitudinal) ** 2
            shaped.y *= waist_factor
            shaped.z *= waist_factor
        vertex.co = shaped
        tone = 0.88 + lumps * 0.16 + micro * 0.035
        tone *= 1.0 - crater_score * 0.38
        vertex_colors.append((0.38 * tone, 0.31 * tone, 0.23 * tone, 1.0))

    color_attribute = mesh.color_attributes.new(
        name="asteroid_color",
        type="BYTE_COLOR",
        domain="POINT",
    )
    for index, color in enumerate(vertex_colors):
        color_attribute.data[index].color = color
    mesh.color_attributes.active_color = color_attribute
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        polygon.material_index = 0
    mesh.validate(verbose=True, clean_customdata=True)
    mesh.update(calc_edges=True, calc_edges_loose=True)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    non_manifold = [edge.index for edge in bm.edges if not edge.is_manifold]
    signed_volume = bm.calc_volume(signed=True)
    bm.free()
    inward_faces = [
        polygon.index
        for polygon in mesh.polygons
        if polygon.center.length and polygon.normal.dot(polygon.center.normalized()) <= 0.0
    ]
    if non_manifold or signed_volume <= 0.0 or inward_faces:
        raise RuntimeError(
            f"{spec.canonical_id}: unsafe topology: non_manifold={len(non_manifold)}, "
            f"signed_volume={signed_volume:.6f}, inward_faces={len(inward_faces)}"
        )

    obj["oeb_placeholder"] = True
    obj["oeb_asset_kind"] = "prop"
    obj["oeb_style"] = "late-1990s low-poly CGI"
    obj["oeb_variant"] = spec.label.lower()
    obj["oeb_unit_diameter_m"] = 2.0
    return obj


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_glb(obj: bpy.types.Object, path: Path) -> None:
    select_only(obj)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup_preview_scene() -> bpy.types.Camera:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"

    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.006, 0.010, 0.026, 1.0)
    background.inputs["Strength"].default_value = 0.24

    camera_data = bpy.data.cameras.new("preview_camera")
    camera = bpy.data.objects.new("preview_camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (4.4, -5.2, 3.25)
    camera.data.lens = 58
    look_at(camera, Vector((0, 0, 0)))
    scene.camera = camera

    sun_data = bpy.data.lights.new("key_sun", "SUN")
    sun_data.energy = 1.65
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("key_sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-42))

    fill_data = bpy.data.lights.new("cool_fill", "AREA")
    fill_data.energy = 760
    fill_data.color = (0.24, 0.34, 0.58)
    fill_data.shape = "DISK"
    fill_data.size = 5.0
    fill = bpy.data.objects.new("cool_fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-3.2, 1.8, 1.3)
    look_at(fill, Vector((0, 0, 0)))

    rim_data = bpy.data.lights.new("amber_rim", "AREA")
    rim_data.energy = 300
    rim_data.color = (0.80, 0.36, 0.13)
    rim_data.size = 3.0
    rim = bpy.data.objects.new("amber_rim", rim_data)
    bpy.context.collection.objects.link(rim)
    rim.location = (0.6, 3.4, -0.7)
    look_at(rim, Vector((0, 0, 0)))

    front_data = bpy.data.lights.new("camera_fill", "AREA")
    front_data.energy = 620
    front_data.color = (0.72, 0.78, 1.0)
    front_data.shape = "DISK"
    front_data.size = 5.5
    front = bpy.data.objects.new("camera_fill", front_data)
    bpy.context.collection.objects.link(front)
    front.location = (2.4, -4.2, 2.1)
    look_at(front, Vector((0, 0, 0)))
    return camera


def render_preview(obj: bpy.types.Object, path: Path, rotation: tuple[float, float, float]) -> None:
    obj.rotation_euler = tuple(math.radians(value) for value in rotation)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    obj.rotation_euler = (0.0, 0.0, 0.0)


def build_individual(spec: AsteroidSpec) -> None:
    clear_scene()
    asteroid = build_asteroid(spec, make_asteroid_material())
    setup_preview_scene()
    render_preview(
        asteroid,
        PREVIEW_DIR / f"{spec.canonical_id}.png",
        (18 + (spec.seed % 13), -12 + (spec.seed % 9), 22 + (spec.seed % 17)),
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_DIR / f"{spec.canonical_id}.blend"))
    export_glb(asteroid, OUT_DIR / f"{spec.canonical_id}.glb")


def build_field() -> list[dict]:
    """Returns the obstacle list actually built -- [{"label", "position",
    "radius_m"}, ...] -- so main()/the retrofit caller can register it
    into data/resolver_map.json without recomputing anything (single
    source of truth: what got built IS what gets registered).
    """
    clear_scene()
    material = make_asteroid_material()
    root = bpy.data.objects.new(FIELD_ID, None)
    bpy.context.collection.objects.link(root)
    root["oeb_placeholder"] = True
    root["oeb_asset_kind"] = "location"
    root["oeb_style"] = "late-1990s low-poly CGI"
    marks = []
    for mark, offset in FIELD_MARKS.items():
        bpy.ops.object.empty_add(type="PLAIN_AXES", radius=0.2, location=offset)
        mark_obj = bpy.context.object
        mark_obj.name = f"{FIELD_ID}_{mark}"
        mark_obj.parent = root
        marks.append(mark_obj)
    asteroids = []
    obstacles = []
    for spec, (location, rotation) in zip(SPECS, ASTEROID_LAYOUT):
        asteroid = build_asteroid(spec, material)
        asteroid.name = f"{spec.canonical_id}_instance"
        raw_max_dim = max(asteroid.dimensions)
        target_scale = ASTEROID_TARGET_DIAMETER_M / raw_max_dim
        asteroid.parent = root
        asteroid.location = location
        asteroid.scale = (target_scale, target_scale, target_scale)
        asteroid.rotation_euler = tuple(math.radians(value) for value in rotation)
        asteroids.append(asteroid)
        obstacles.append({
            "label": spec.canonical_id,
            "position": list(location),
            "radius_m": round(raw_max_dim * target_scale / 2, 3),
        })

    camera = setup_preview_scene()
    camera.location = (0.0, -60.0, 5.0)
    camera.data.lens = 24
    look_at(camera, Vector((0, 0, 0)))
    scene = bpy.context.scene
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.filepath = str(PREVIEW_DIR / "asteroid_placeholder_set.png")
    bpy.ops.render.render(write_still=True)

    # A real, named, EXPORTED camera_grammar.json scene_object -- distinct
    # from the preview-only `camera` above (never exported, selection
    # below excludes it). docs/planning/CAMERA-SHOT-SCALE-PLAN.md: this
    # location previously had no such camera at all, so
    # tools/export_blender.py fell back to a fixed generic position tuned
    # for a small interior, producing extreme clipping when a full-size
    # spacecraft was placed here. asteroid_field is "vast" shot_scale --
    # same SHOT_SCALE_CAMERAS template every other vast placeholder
    # location uses (tools/placeholder_blueprint.py), single source of
    # truth via the pb import above, not duplicated numbers.
    vast_cam_spec = pb.SHOT_SCALE_CAMERAS["vast"]
    export_cam_data = bpy.data.cameras.new(f"{vast_cam_spec['scene_object']}_data")
    export_cam_data.lens = vast_cam_spec["lens_mm"]
    export_camera = bpy.data.objects.new(vast_cam_spec["scene_object"], export_cam_data)
    bpy.context.collection.objects.link(export_camera)
    export_camera.parent = root
    export_camera.location = vast_cam_spec["position"]
    look_at(export_camera, Vector(vast_cam_spec["aim_at"]))

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_DIR / f"{FIELD_ID}.blend"))

    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for asteroid in asteroids:
        asteroid.select_set(True)
    for mark_obj in marks:
        mark_obj.select_set(True)
    export_camera.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=str(OUT_DIR.parent / f"{FIELD_ID}.glb"),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=True,
    )
    return obstacles


def register_field_collision_data(resolver_map_path: str, location_tag: str, obstacles: list[dict]) -> None:
    """Merge *obstacles* and this field's own FIELD_MARKS positions into
    data/resolver_map.json's *location_tag* entry -- additive, doesn't
    touch marks/default_props/variants/etc. See
    tools/motion_library.py's clear_marks_for_mover(), which is what
    actually reads these two fields back.
    """
    rmap_data = json.loads(Path(resolver_map_path).read_text())
    entry = rmap_data["locations"][location_tag]
    entry["obstacles"] = obstacles
    entry["mark_positions"] = {
        f"{FIELD_ID}_{mark}": list(offset) for mark, offset in FIELD_MARKS.items()
    }
    Path(resolver_map_path).write_text(json.dumps(rmap_data, indent=2) + "\n")


def validate_lit_material(obj: bpy.types.Object) -> None:
    setup_preview_scene()
    scene = bpy.context.scene
    scene.render.resolution_x = 160
    scene.render.resolution_y = 160
    for engine, slug in (("BLENDER_EEVEE", "eevee"), ("CYCLES", "cycles")):
        scene.render.engine = engine
        if engine == "CYCLES":
            scene.cycles.samples = 16
        render_path = Path(f"/tmp/oeb_asteroid_material_validation_{slug}.png")
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(str(render_path), check_existing=False)
        red_values = list(image.pixels)[0::4]
        max_red = max(red_values, default=0.0)
        bpy.data.images.remove(image)
        if max_red < 0.10:
            raise RuntimeError(
                f"{obj.name}: exported PBR material rendered black in {slug} "
                f"(max red={max_red:.6f})"
            )
        print(f"Validated {obj.name} lighting in {slug}: max red={max_red:.3f}")


def validate_exports() -> None:
    for index, spec in enumerate(SPECS):
        clear_scene()
        path = OUT_DIR / f"{spec.canonical_id}.glb"
        bpy.ops.import_scene.gltf(filepath=str(path))
        mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        names = {obj.name for obj in mesh_objects}
        triangle_count = sum(len(obj.data.polygons) for obj in mesh_objects)
        vertex_count = sum(len(obj.data.vertices) for obj in mesh_objects)
        non_manifold_edges = 0
        for obj in mesh_objects:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            non_manifold_edges += sum(1 for edge in bm.edges if not edge.is_manifold)
            bm.free()
        if spec.canonical_id not in names:
            raise RuntimeError(f"{path.name}: missing canonical node {spec.canonical_id}")
        if (
            len(mesh_objects) != 1
            or not 100 <= triangle_count <= 700
            or vertex_count > 250
            or non_manifold_edges
        ):
            raise RuntimeError(
                f"{path.name}: expected one compact manifold mesh, got "
                f"{len(mesh_objects)} meshes / {vertex_count} vertices / "
                f"{triangle_count} triangles / {non_manifold_edges} non-manifold edges"
            )
        print(
            f"Validated {path.name}: 1 manifold mesh, {vertex_count} vertices, "
            f"{triangle_count} triangles"
        )
        if index == 0:
            validate_lit_material(mesh_objects[0])

    clear_scene()
    field_path = OUT_DIR.parent / f"{FIELD_ID}.glb"
    bpy.ops.import_scene.gltf(filepath=str(field_path))
    field_names = {obj.name for obj in bpy.context.scene.objects}
    field_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if FIELD_ID not in field_names or len(field_meshes) != len(SPECS):
        raise RuntimeError(
            f"{field_path.name}: expected root {FIELD_ID} and {len(SPECS)} meshes"
        )
    # data/resolver_map.json's asteroid_field location marks must resolve
    # against this exact GLB (this location's set_id) -- see FIELD_MARKS.
    expected_marks = {f"{FIELD_ID}_{mark}" for mark in FIELD_MARKS}
    missing_marks = expected_marks - field_names
    if missing_marks:
        raise RuntimeError(f"{field_path.name}: missing location marks {sorted(missing_marks)}")
    print(f"Validated {field_path.name}: root plus {len(field_meshes)} asteroid meshes "
          f"plus {len(expected_marks)} location marks")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        build_individual(spec)
    obstacles = build_field()
    register_field_collision_data(
        str(PROJECT_ROOT / "data" / "resolver_map.json"), "asteroid_field", obstacles)
    validate_exports()
    print(f"Built {len(SPECS)} asteroid placeholders in {OUT_DIR}")


if __name__ == "__main__":
    main()
