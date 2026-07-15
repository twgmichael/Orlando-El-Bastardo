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


def spec_text(spec):
    parts = [
        spec.get("canonical_id", ""),
        spec.get("name", ""),
        spec.get("kind", ""),
        spec.get("style", ""),
        " ".join(str(c) for c in spec.get("components", [])),
    ]
    return " ".join(parts).lower()


def wants_station(spec):
    text = spec_text(spec)
    station_words = ("station", "orbital", "habitat", "window", "ring", "dock", "solar")
    return any(word in text for word in station_words)


def wants_office(spec):
    text = spec_text(spec)
    office_words = ("office", "desk", "chair", "lamp", "conference", "cubicle", "workspace")
    return any(word in text for word in office_words)


def wants_park(spec):
    text = spec_text(spec)
    park_words = ("park", "tree", "path", "trail", "bench", "grass", "garden")
    return any(word in text for word in park_words)


def wants_vehicle(spec):
    text = spec_text(spec)
    vehicle_words = ("ship", "spaceship", "fighter", "vehicle", "craft", "engine", "wing")
    return any(word in text for word in vehicle_words)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


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


def make_fighter_scene(spec):
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

    add_preview_setup(ortho_scale=5.2)
    return parent_to_root(spec, objects), "fighter"


def make_station_scene(spec):
    shell = material("station_shell_warm_white", (0.72, 0.70, 0.62, 1))
    metal = material("station_dark_metal", (0.2, 0.22, 0.24, 1))
    glass = material("large_blue_observation_window", (0.05, 0.45, 0.9, 0.85))
    solar = material("deep_blue_solar_panels", (0.02, 0.06, 0.18, 1))
    glow = material("soft_window_glow", (0.2, 0.65, 1.0, 1))

    objects = []
    objects.append(sphere("central_habitat_hub", (0, 0, 0), (0.9, 0.9, 0.7), shell))
    objects.append(torus("outer_ring_module", (0, 0, 0), 1.65, 0.12, shell))
    objects.append(torus("inner_service_ring", (0, 0, 0), 1.12, 0.06, metal))
    objects.append(cylinder("large_observation_window", (0.93, 0, 0.02), 0.38, 0.05, glass, rotation=(0, 1.5708, 0)))
    objects.append(cylinder("window_inner_glow", (0.97, 0, 0.02), 0.29, 0.03, glow, rotation=(0, 1.5708, 0)))

    for idx, angle in enumerate((0, 1.5708, 3.1416, 4.7124)):
        x = 1.34 if idx == 0 else -1.34 if idx == 2 else 0
        y = 1.34 if idx == 1 else -1.34 if idx == 3 else 0
        arm = cube(f"docking_arm_{idx + 1}", (x / 2, y / 2, 0), (1.25, 0.18, 0.18), metal)
        arm.rotation_euler[2] = angle
        objects.append(arm)
        objects.append(cylinder(f"docking_port_{idx + 1}", (x, y, 0), 0.18, 0.28, metal, rotation=(1.5708, 0, angle)))

    objects.append(cylinder("antenna_mast", (0, 0, 0.95), 0.035, 1.05, metal))
    objects.append(sphere("antenna_tip", (0, 0, 1.55), (0.11, 0.11, 0.11), glow))

    left_panel = cube("left_solar_array", (0, 2.35, 0.15), (1.7, 0.08, 0.62), solar)
    right_panel = cube("right_solar_array", (0, -2.35, 0.15), (1.7, 0.08, 0.62), solar)
    objects.extend([left_panel, right_panel])

    for idx, x in enumerate((-0.42, 0, 0.42)):
        objects.append(cube(f"window_band_{idx + 1}", (x, -0.92, 0.34), (0.22, 0.04, 0.1), glass))

    add_preview_setup(camera_location=(5.4, -6.2, 4.0), target=(0, 0, 0.35), ortho_scale=5.8)
    return parent_to_root(spec, objects), "station"


def make_office_scene(spec):
    floor_mat = material("office_floor_neutral", (0.42, 0.4, 0.36, 1))
    wall_mat = material("office_wall_soft_gray", (0.74, 0.74, 0.7, 1))
    wood = material("desk_warm_wood", (0.45, 0.28, 0.14, 1))
    dark = material("chair_dark_fabric", (0.06, 0.07, 0.08, 1))
    glass = material("window_cool_blue", (0.18, 0.5, 0.85, 0.75))
    lamp = material("lamp_warm_light", (1.0, 0.78, 0.35, 1))
    metal = material("lamp_dark_metal", (0.18, 0.18, 0.17, 1))

    objects = []
    objects.append(cube("office_floor", (0, 0, -0.08), (5.8, 4.0, 0.12), floor_mat))
    objects.append(cube("back_wall", (0, 1.9, 1.05), (5.8, 0.12, 2.2), wall_mat))
    objects.append(cube("large_window", (-1.35, 1.82, 1.25), (1.45, 0.05, 0.9), glass))
    objects.append(cube("desk_top", (0, 0.15, 0.72), (2.1, 0.9, 0.16), wood))
    for idx, x in enumerate((-0.82, 0.82)):
        for jdx, y in enumerate((-0.22, 0.5)):
            objects.append(cylinder(f"desk_leg_{idx + 1}_{jdx + 1}", (x, y, 0.33), 0.045, 0.72, wood))

    for idx, x in enumerate((-0.72, 0.72)):
        objects.append(cube(f"chair_{idx + 1}_seat", (x, -1.0, 0.38), (0.58, 0.52, 0.14), dark))
        objects.append(cube(f"chair_{idx + 1}_back", (x, -1.22, 0.82), (0.58, 0.12, 0.78), dark))
        objects.append(cylinder(f"chair_{idx + 1}_post", (x, -1.0, 0.16), 0.045, 0.35, metal))

    objects.append(cylinder("lamp_stem", (0.72, 0.32, 1.08), 0.035, 0.74, metal))
    shade = cylinder("lamp_shade", (0.72, 0.32, 1.48), 0.18, 0.22, lamp)
    shade.scale[0] = 1.2
    objects.append(shade)

    add_preview_setup(camera_location=(5.4, -6.2, 4.1), target=(0, 0, 0.55), ortho_scale=6.4)
    return parent_to_root(spec, objects), "office"


def make_park_scene(spec):
    grass = material("park_grass", (0.16, 0.42, 0.14, 1))
    path_mat = material("curving_path_sand", (0.58, 0.48, 0.34, 1))
    bark = material("tree_bark", (0.28, 0.15, 0.07, 1))
    leaves = material("tree_leaf_canopy", (0.08, 0.34, 0.11, 1))
    bench_mat = material("bench_weathered_wood", (0.36, 0.21, 0.11, 1))

    objects = []
    objects.append(cube("park_ground", (0, 0, -0.06), (6.4, 4.2, 0.1), grass))
    path = cube("walking_path", (0, -0.05, 0.01), (5.8, 0.65, 0.04), path_mat)
    path.rotation_euler[2] = -0.18
    objects.append(path)

    tree_positions = [(-2.2, 1.15), (-1.35, -1.15), (1.55, 1.05), (2.25, -0.95)]
    for idx, (x, y) in enumerate(tree_positions):
        objects.append(cylinder(f"tree_{idx + 1}_trunk", (x, y, 0.45), 0.09, 0.95, bark))
        objects.append(sphere(f"tree_{idx + 1}_canopy", (x, y, 1.12), (0.48, 0.48, 0.42), leaves))

    objects.append(cube("park_bench_seat", (0.95, -1.18, 0.32), (1.0, 0.22, 0.12), bench_mat))
    objects.append(cube("park_bench_back", (0.95, -1.36, 0.62), (1.0, 0.12, 0.48), bench_mat))
    objects.append(cylinder("bench_left_leg", (0.55, -1.18, 0.15), 0.035, 0.32, bench_mat))
    objects.append(cylinder("bench_right_leg", (1.35, -1.18, 0.15), 0.035, 0.32, bench_mat))

    add_preview_setup(camera_location=(5.8, -6.6, 4.4), target=(0, 0, 0.45), ortho_scale=7.0)
    return parent_to_root(spec, objects), "park"


def primitive_for_component(component, idx, mat):
    name = str(component).lower()
    x = -2.2 + (idx % 4) * 1.45
    y = -0.9 + (idx // 4) * 1.2
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or f"component_{idx + 1}"

    if any(word in name for word in ("tree", "plant")):
        trunk = cylinder(f"{safe_name}_trunk", (x, y, 0.38), 0.08, 0.76, mat["bark"])
        canopy = sphere(f"{safe_name}_canopy", (x, y, 0.95), (0.38, 0.38, 0.34), mat["green"])
        return [trunk, canopy]
    if "lamp" in name:
        return [
            cylinder(f"{safe_name}_stem", (x, y, 0.55), 0.035, 1.0, mat["metal"]),
            sphere(f"{safe_name}_glow", (x, y, 1.12), (0.18, 0.18, 0.18), mat["glow"]),
        ]
    if "chair" in name:
        return [
            cube(f"{safe_name}_seat", (x, y, 0.32), (0.48, 0.45, 0.12), mat["dark"]),
            cube(f"{safe_name}_back", (x, y + 0.2, 0.68), (0.48, 0.1, 0.62), mat["dark"]),
        ]
    if any(word in name for word in ("window", "screen", "mirror")):
        return [cube(safe_name, (x, y, 0.75), (0.75, 0.06, 0.55), mat["glass"])]
    if any(word in name for word in ("path", "road", "river")):
        obj = cube(safe_name, (x, y, 0.04), (1.25, 0.35, 0.05), mat["path"])
        obj.rotation_euler[2] = -0.25
        return [obj]
    if any(word in name for word in ("desk", "table", "counter")):
        return [cube(safe_name, (x, y, 0.48), (0.95, 0.55, 0.16), mat["wood"])]
    if any(word in name for word in ("ring", "wheel")):
        return [torus(safe_name, (x, y, 0.55), 0.34, 0.04, mat["metal"])]
    if any(word in name for word in ("engine", "pipe", "column", "post")):
        return [cylinder(safe_name, (x, y, 0.42), 0.18, 0.85, mat["metal"])]
    if any(word in name for word in ("globe", "ball", "rock")):
        return [sphere(safe_name, (x, y, 0.38), (0.36, 0.36, 0.32), mat["neutral"])]
    return [cube(safe_name, (x, y, 0.35), (0.75, 0.48, 0.5), mat["neutral"])]


def make_component_layout_scene(spec):
    mats = {
        "neutral": material("component_neutral_clay", (0.64, 0.62, 0.57, 1)),
        "dark": material("component_dark", (0.09, 0.1, 0.1, 1)),
        "metal": material("component_metal", (0.24, 0.25, 0.25, 1)),
        "wood": material("component_wood", (0.42, 0.25, 0.12, 1)),
        "glass": material("component_glass_blue", (0.14, 0.45, 0.8, 0.72)),
        "green": material("component_green", (0.1, 0.34, 0.12, 1)),
        "bark": material("component_bark", (0.26, 0.13, 0.06, 1)),
        "path": material("component_path", (0.55, 0.46, 0.33, 1)),
        "glow": material("component_warm_glow", (1.0, 0.74, 0.28, 1)),
    }
    objects = [cube("layout_base", (0, 0, -0.08), (6.2, 3.8, 0.1), mats["neutral"])]
    components = spec.get("components") or ["primary mass", "secondary detail", "accent feature"]
    for idx, component in enumerate(components[:10]):
        objects.extend(primitive_for_component(component, idx, mats))

    add_preview_setup(camera_location=(5.6, -6.4, 4.2), target=(0, 0, 0.45), ortho_scale=6.8)
    return parent_to_root(spec, objects), "component_layout"


def make_scene(spec):
    clear_scene()
    if wants_office(spec):
        return make_office_scene(spec)
    if wants_park(spec):
        return make_park_scene(spec)
    if wants_station(spec):
        return make_station_scene(spec)
    if wants_vehicle(spec):
        return make_fighter_scene(spec)
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
        "components": spec.get("components", []),
        "variant": variant,
        "outputs": {
            "glb": str(output),
            "preview": str(preview),
        },
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
