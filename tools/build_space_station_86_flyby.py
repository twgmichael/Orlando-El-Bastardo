#!/usr/bin/env python3
"""Build and render a simple Starbase 86 / Bugblatter flyby.

The shot deliberately keeps the staging plain: a static station, a sparse
starfield, neutral lighting, and one interceptor crossing close to camera and
receding past the station.  There are no engine flares, bloom, motion blur,
volumetrics, lens effects, or other action effects.

Outputs:
    scene_versions/space_station_86_bugblatter_flyby_v005.blend
    out/space_station_86_bugblatter_flyby_v005.mp4
    out/space_station_86_bugblatter_flyby_v005_preview/*.png (with --preview)
    scene_versions/space_station_86_bugblatter_flyby_v005_final.blend
    out/space_station_86_bugblatter_flyby_v005_final.mp4 (with --final)
"""

from __future__ import annotations

import glob
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
SHIP_PATH = (
    ROOT
    / "assets"
    / "ships"
    / "bugblatter_interceptor_v1.0.0"
    / "bugblatter_interceptor_v1.0.0.glb"
)
BLEND_PATH = ROOT / "scene_versions" / "space_station_86_bugblatter_flyby_v005.blend"
MOVIE_PATH = ROOT / "out" / "space_station_86_bugblatter_flyby_v005.mp4"
FRAME_DIR = ROOT / "out" / "space_station_86_bugblatter_flyby_v005_frames"
PREVIEW_DIR = ROOT / "out" / "space_station_86_bugblatter_flyby_v005_preview"
FINAL_BLEND_PATH = ROOT / "scene_versions" / "space_station_86_bugblatter_flyby_v005_final.blend"
FINAL_MOVIE_PATH = ROOT / "out" / "space_station_86_bugblatter_flyby_v005_final.mp4"
FINAL_FRAME_DIR = ROOT / "out" / "space_station_86_bugblatter_flyby_v005_final_frames"

FPS = 30
FRAME_START = 1
FRAME_END = 60
STARBASE_HEIGHT_METERS = 150.0
STARBASE_UNSCALED_HEIGHT = 8.0
STARBASE_SCALE = STARBASE_HEIGHT_METERS / STARBASE_UNSCALED_HEIGHT
INTERCEPTOR_LENGTH_METERS = 5.0
INTERCEPTOR_HEIGHT_METERS = 3.0


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.72):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    emission_strength = bsdf.inputs.get("Emission Strength")
    if emission_strength is not None:
        emission_strength.default_value = 0.0
    return mat


def assign(obj, mat):
    obj.data.materials.append(mat)
    return obj


def add_uv_sphere(name, location, scale, mat, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def add_half_uv_sphere(name, location, scale, mat, *, upper: bool, segments=64, rings=32):
    """Add a true upper or lower squashed hemisphere with a flat equator."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.bisect(
        plane_co=(0.0, 0.0, 0.0),
        plane_no=(0.0, 0.0, 1.0),
        clear_inner=upper,
        clear_outer=not upper,
        use_fill=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def smooth_cylinder_sides(obj) -> None:
    """Smooth curved walls while keeping planar end caps crisp and clean."""
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4


def add_cylinder(name, location, radius, depth, mat, vertices=48, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    smooth_cylinder_sides(obj)
    return obj


def add_beveled_cylinder(name, location, radius, depth, mat, bevel=0.18, vertices=64):
    obj = add_cylinder(name, location, radius, depth, mat, vertices=vertices)
    modifier = obj.modifiers.new("simple_edge_round", "BEVEL")
    modifier.width = bevel
    modifier.segments = 4
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    smooth_cylinder_sides(obj)
    return obj


def add_box(name, location, scale, mat, rotation_z=0.0, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=(0, 0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("simple_edge_round", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def add_elliptical_cylinder(name, location, radii, depth, mat, bevel=0.0):
    obj = add_cylinder(name, location, 1.0, depth, mat, vertices=64)
    obj.scale = (radii[0], radii[1], 1.0)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("soft_edge_round", "BEVEL")
        modifier.width = bevel
        modifier.segments = 4
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        smooth_cylinder_sides(obj)
    return obj


def cut_hangar_tunnel(pod_object, pod_center: Vector, theta: float) -> None:
    """Cut a real tangent-to-tangent void through a pod's rounded box hull."""
    bpy.ops.mesh.primitive_cube_add(
        location=pod_center,
        rotation=(0.0, 0.0, theta),
    )
    cutter = bpy.context.object
    cutter.name = f"{pod_object.name}_hangar_tunnel_cutter"
    cutter.scale = (0.80, 1.90, 0.29)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    modifier = pod_object.modifiers.new("tangent_hangar_tunnel", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = pod_object
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def add_opposed_hangar_faces(
    parts,
    index,
    pod_center: Vector,
    radial: Vector,
    tangent: Vector,
    theta: float,
    dark,
    inset,
    *,
    state: str,
) -> None:
    """Add paired tangent-facing bay frames and the requested door state."""
    body_half_tangent = 1.52
    face_offset = body_half_tangent + 0.025

    def local_point(x: float, y: float, z: float) -> Vector:
        return pod_center + radial * x + tangent * y + Vector((0.0, 0.0, z))

    for side_index, sign in enumerate((1.0, -1.0), start=1):
        side = "A" if side_index == 1 else "B"
        face_y = sign * face_offset
        prefix = f"station_pod_{index}_hangar_{side}_frame"
        parts.extend([
            add_box(f"{prefix}_top", local_point(0.0, face_y, 0.36),
                    (0.88, 0.075, 0.09), dark, rotation_z=theta, bevel=0.045),
            add_box(f"{prefix}_bottom", local_point(0.0, face_y, -0.36),
                    (0.88, 0.075, 0.09), dark, rotation_z=theta, bevel=0.045),
            add_box(f"{prefix}_left", local_point(-0.79, face_y, 0.0),
                    (0.09, 0.075, 0.36), dark, rotation_z=theta, bevel=0.045),
            add_box(f"{prefix}_right", local_point(0.79, face_y, 0.0),
                    (0.09, 0.075, 0.36), dark, rotation_z=theta, bevel=0.045),
        ])

        panel_y = sign * (face_offset + 0.085)
        if state == "closed":
            parts.append(add_box(
                f"station_pod_{index}_hangar_{side}_closed_door",
                local_point(0.0, panel_y, 0.0),
                (0.68, 0.055, 0.25),
                inset,
                rotation_z=theta,
                bevel=0.035,
            ))
        elif state == "half-closed":
            # Two withdrawn sliding leaves cover half the total doorway while
            # leaving a centered 50-percent opening visible from either side.
            for leaf, x_offset in (("left", -0.51), ("right", 0.51)):
                parts.append(add_box(
                    f"station_pod_{index}_hangar_{side}_{leaf}_half_door",
                    local_point(x_offset, panel_y, 0.0),
                    (0.17, 0.055, 0.25),
                    inset,
                    rotation_z=theta,
                    bevel=0.025,
                ))

        mark = bpy.data.objects.new(f"station_pod_{index}_hangar_mark_{side}", None)
        bpy.context.scene.collection.objects.link(mark)
        outward = tangent * sign
        mark.location = local_point(0.0, sign * (face_offset + 0.18), 0.0)
        mark.rotation_mode = "QUATERNION"
        mark.rotation_quaternion = outward.to_track_quat("Z", "Y")
        mark["hangar_state"] = state
        mark["door_side"] = f"opposed tangent {side}"
        parts.append(mark)

        if side == "A":
            legacy = bpy.data.objects.new(f"station_pod_{index}_hangar_mark", None)
            bpy.context.scene.collection.objects.link(legacy)
            legacy.matrix_world = mark.matrix_world.copy()
            legacy["hangar_state"] = state
            legacy["door_side"] = "opposed tangent A (legacy primary mark)"
            parts.append(legacy)

    # Dark inner wall strips make the real through-tunnel readable without
    # blocking the opening on either side.
    parts.extend([
        add_box(f"station_pod_{index}_hangar_liner_left",
                local_point(-0.74, 0.0, 0.0),
                (0.055, 1.43, 0.27), dark, rotation_z=theta),
        add_box(f"station_pod_{index}_hangar_liner_right",
                local_point(0.74, 0.0, 0.0),
                (0.055, 1.43, 0.27), dark, rotation_z=theta),
        add_box(f"station_pod_{index}_hangar_liner_top",
                local_point(0.0, 0.0, 0.28),
                (0.74, 1.43, 0.055), dark, rotation_z=theta),
        add_box(f"station_pod_{index}_hangar_liner_bottom",
                local_point(0.0, 0.0, -0.28),
                (0.74, 1.43, 0.055), dark, rotation_z=theta),
    ])


def cylinder_between(name, start: Vector, end: Vector, radius: float, mat):
    delta = end - start
    midpoint = (start + end) * 0.5
    obj = add_cylinder(name, midpoint, radius, delta.length, mat, vertices=48)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    return obj


def parent_preserve_world(obj, parent) -> None:
    world_matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world_matrix


def combined_mesh_bounds(objects, inverse_reference_matrix):
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    found_mesh = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        found_mesh = True
        transform = inverse_reference_matrix @ obj.matrix_world
        for corner in obj.bound_box:
            point = transform @ Vector(corner)
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
    if not found_mesh:
        raise RuntimeError("No mesh geometry found while measuring the interceptor")
    return minimum, maximum


def build_station() -> bpy.types.Object:
    root = bpy.data.objects.new("Starbase_86_150m", None)
    bpy.context.scene.collection.objects.link(root)

    gray = material("station_medium_gray", (0.32, 0.33, 0.35, 1.0), 0.55)
    charcoal = material("station_charcoal", (0.035, 0.042, 0.055, 1.0), 0.62)
    off_white = material("station_pod_off_white", (0.80, 0.79, 0.75, 1.0), 0.58)
    pod_box_gray = material("station_pod_rounded_box_gray", (0.25, 0.27, 0.30, 1.0), 0.60)
    dark = material("station_docking_dark", (0.055, 0.06, 0.07, 1.0), 0.70)
    inset = material("station_docking_inset", (0.24, 0.25, 0.27, 1.0), 0.64)
    red = material("station_indicator_red", (0.55, 0.015, 0.012, 1.0), 0.45)
    accent = material("station_ring_pale_green", (0.62, 0.68, 0.58, 1.0), 0.58)

    parts = []
    parts.append(add_uv_sphere("station_core", (0, 0, 0.55), (1.9, 1.9, 1.65), gray, 64, 32))
    parts.append(add_cylinder("station_neck", (0, 0, 2.85), 0.72, 2.25, gray, vertices=64))
    parts.append(add_beveled_cylinder("station_docking_drum", (0, 0, 4.15), 2.55, 0.72, gray, 0.16, 64))
    parts.append(add_cylinder("station_accent_ring", (0, 0, 4.70), 2.18, 0.18, accent, vertices=64))
    parts.append(add_beveled_cylinder("station_upper_cap", (0, 0, 5.85), 2.34, 2.10, charcoal, 0.30, 64))

    arm_radius = 6.35
    pod_z = 0.56
    pod_states = {1: "open", 2: "half-closed", 3: "closed"}
    for index, angle_deg in enumerate((0.0, 120.0, 240.0), start=1):
        theta = math.radians(angle_deg)
        radial = Vector((math.cos(theta), math.sin(theta), 0.0))
        start = radial * 1.42 + Vector((0, 0, pod_z))
        end = radial * (arm_radius - 1.05) + Vector((0, 0, pod_z))
        arm = cylinder_between(f"station_arm_{index}", start, end, 0.27, gray)
        parts.append(arm)

        pod_center = radial * arm_radius + Vector((0, 0, pod_z))
        tangent = Vector((-math.sin(theta), math.cos(theta), 0.0))
        state = pod_states[index]

        # Original construction: a short rounded box aligned radially with the
        # spoke, visibly projecting beyond separate circular-footprint upper
        # and lower squashed hemispheres.  The two bay faces oppose each other
        # across the tangent axis, so their planes run parallel to the spoke.
        pod_body = add_box(
            f"station_pod_{index}_rounded_box_hull",
            pod_center,
            (1.28, 1.52, 0.36),
            pod_box_gray,
            rotation_z=theta,
            bevel=0.18,
        )
        cut_hangar_tunnel(pod_body, pod_center, theta)

        pod_top = add_half_uv_sphere(
            f"station_pod_{index}_squashed_top_hemisphere",
            pod_center + Vector((0.0, 0.0, 0.36)),
            (1.24, 1.24, 0.42),
            off_white,
            upper=True,
        )
        pod_bottom = add_half_uv_sphere(
            f"station_pod_{index}_squashed_bottom_hemisphere",
            pod_center + Vector((0.0, 0.0, -0.36)),
            (1.24, 1.24, 0.42),
            off_white,
            upper=False,
        )
        for pod_piece in (pod_body, pod_top, pod_bottom):
            pod_piece["hangar_state"] = state
            pod_piece["door_sides"] = "opposed tangent faces; planes parallel to spoke"
            pod_piece["construction"] = "rounded box plus squashed top/bottom hemispheres"
        parts.extend((pod_body, pod_top, pod_bottom))

        dome_center = pod_center + Vector((0, 0, 0.82))
        parts.append(add_uv_sphere(
            f"station_pod_{index}_indicator",
            dome_center,
            (0.21, 0.21, 0.13),
            red,
            32,
            16,
        ))

        add_opposed_hangar_faces(
            parts,
            index,
            pod_center,
            radial,
            tangent,
            theta,
            dark,
            inset,
            state=state,
        )

    for part in parts:
        parent_preserve_world(part, root)
    root.rotation_euler.z = math.radians(17.0)
    root.scale = (STARBASE_SCALE, STARBASE_SCALE, STARBASE_SCALE)
    print(f"[station86] starbase height: {STARBASE_HEIGHT_METERS:.2f} m")
    return root


def disable_ship_effects(imported_objects) -> None:
    materials = set()
    for obj in imported_objects:
        if getattr(obj, "data", None) is None:
            continue
        for slot in getattr(obj, "material_slots", ()): 
            if slot.material is not None:
                materials.add(slot.material)

    for mat in materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED":
                continue
            strength = node.inputs.get("Emission Strength")
            if strength is not None:
                strength.default_value = 0.0
            emission = node.inputs.get("Emission Color") or node.inputs.get("Emission")
            if emission is not None:
                emission.default_value = (0.0, 0.0, 0.0, 1.0)
            if "exhaust" in mat.name.lower():
                node.inputs["Base Color"].default_value = (0.025, 0.03, 0.035, 1.0)
                node.inputs["Roughness"].default_value = 0.82


def import_and_animate_ship(scene, camera) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(SHIP_PATH))
    imported = set(bpy.data.objects) - before
    disable_ship_effects(imported)

    root = bpy.data.objects.new("Bugblatter_Interceptor_5m_x_3m", None)
    scene.collection.objects.link(root)
    geometry_root = bpy.data.objects.new("Bugblatter_Interceptor_Geometry", None)
    scene.collection.objects.link(geometry_root)
    geometry_root.parent = root
    imported_roots = [obj for obj in imported if obj.parent not in imported]
    for obj in imported_roots:
        parent_preserve_world(obj, geometry_root)

    bpy.context.view_layer.update()
    minimum, maximum = combined_mesh_bounds(imported, geometry_root.matrix_world.inverted())
    dimensions = maximum - minimum
    center = (minimum + maximum) * 0.5
    geometry_root.location = -center

    horizontal_scale = INTERCEPTOR_LENGTH_METERS / dimensions.x
    vertical_scale = INTERCEPTOR_HEIGHT_METERS / dimensions.z
    root.scale = (horizontal_scale, horizontal_scale, vertical_scale)
    root.rotation_mode = "QUATERNION"

    camera_rotation = camera.matrix_world.to_quaternion()
    forward = camera_rotation @ Vector((0.0, 0.0, -1.0))
    right = camera_rotation @ Vector((1.0, 0.0, 0.0))
    up = camera_rotation @ Vector((0.0, 1.0, 0.0))

    # Camera-relative path: large and close at entry, then rapidly receding to
    # true scale beside the 150 m starbase.  The local -X axis is used because
    # the exported hero asset's cockpit pods sit at its -X end.
    path_spec = (
        (FRAME_START, 30.0, -17.0, -2.0),
        (15, 42.0, -8.0, -1.0),
        (30, 105.0, -3.0, 0.0),
        (45, 310.0, 18.0, 15.0),
        (FRAME_END, 690.0, 82.0, 54.0),
    )
    path = tuple(
        (frame, camera.location + forward * distance + right * x_offset + up * z_offset)
        for frame, distance, x_offset, z_offset in path_spec
    )
    direction = (path[-1][1] - path[0][1]).normalized()
    facing = direction.to_track_quat("-X", "Z")
    bank = Quaternion((1.0, 0.0, 0.0), math.radians(-8.0))

    for frame, location in path:
        root.location = location
        root.rotation_quaternion = facing @ bank
        root.keyframe_insert(data_path="location", frame=frame)
        root.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    print(
        "[station86] interceptor dimensions: "
        f"{INTERCEPTOR_LENGTH_METERS:.2f} m long x "
        f"{dimensions.y * horizontal_scale:.2f} m wide x "
        f"{INTERCEPTOR_HEIGHT_METERS:.2f} m tall"
    )
    return root


def add_starfield(scene) -> None:
    world = bpy.data.worlds.new("space_black")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    background.inputs["Strength"].default_value = 0.0
    scene.world = world

    bpy.ops.mesh.primitive_uv_sphere_add(radius=2000.0, segments=48, ring_count=24)
    sphere = bpy.context.object
    sphere.name = "static_sparse_starfield"
    sphere.visible_shadow = False

    mat = bpy.data.materials.new("static_sparse_stars")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise = nodes.new("ShaderNodeTexNoise")
    coord = nodes.new("ShaderNodeTexCoord")

    noise.inputs["Scale"].default_value = 330.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.55
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.72, 0.76, 0.82, 1.0)
    emission.inputs["Strength"].default_value = 3.5

    mat.node_tree.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    mat.node_tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    mat.node_tree.links.new(ramp.outputs["Color"], emission.inputs["Color"])
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    sphere.data.materials.append(mat)


def add_lighting(scene) -> None:
    key_data = bpy.data.lights.new("neutral_key", "SUN")
    key_data.energy = 2.6
    key_data.color = (0.92, 0.95, 1.0)
    key = bpy.data.objects.new("neutral_key", key_data)
    scene.collection.objects.link(key)
    key.rotation_euler = (math.radians(42), math.radians(-18), math.radians(-35))

    fill_data = bpy.data.lights.new("neutral_fill", "SUN")
    fill_data.energy = 1.15
    fill_data.color = (0.70, 0.76, 0.90)
    fill = bpy.data.objects.new("neutral_fill", fill_data)
    scene.collection.objects.link(fill)
    fill.rotation_euler = (math.radians(105), math.radians(5), math.radians(135))

    rim_data = bpy.data.lights.new("neutral_rim", "SUN")
    rim_data.energy = 1.0
    rim_data.color = (0.95, 0.80, 0.65)
    rim = bpy.data.objects.new("neutral_rim", rim_data)
    scene.collection.objects.link(rim)
    rim.rotation_euler = (math.radians(-25), math.radians(12), math.radians(160))


def add_camera(scene) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("flyby_camera")
    camera_data.lens = 45.0
    camera_data.sensor_width = 36.0
    camera_data.clip_end = 5000.0
    camera = bpy.data.objects.new("flyby_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    camera.location = (
        15.5 * STARBASE_SCALE,
        -29.0 * STARBASE_SCALE,
        12.0 * STARBASE_SCALE,
    )
    target = Vector((0.1, 0.0, 2.25)) * STARBASE_SCALE
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    return camera


def configure_scene(scene) -> None:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.fps = FPS
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.resolution_x = 648
    scene.render.resolution_y = 486
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True

    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_samples"):
            scene.eevee.taa_samples = 16
        if hasattr(scene.eevee, "use_bloom"):
            scene.eevee.use_bloom = False
        if hasattr(scene.eevee, "use_motion_blur"):
            scene.eevee.use_motion_blur = False
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = False

    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


def ffmpeg_binary() -> str:
    bundled = sorted(glob.glob(str(
        ROOT / ".venv" / "lib" / "python*" / "site-packages"
        / "imageio_ffmpeg" / "binaries" / "ffmpeg-*"
    )))
    return bundled[0] if bundled else (shutil.which("ffmpeg") or "ffmpeg")


def encode_movie(frame_dir: Path, movie_path: Path, crf: int) -> None:
    movie_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_binary(),
            "-y",
            "-framerate",
            str(FPS),
            "-start_number",
            str(FRAME_START),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(crf),
            "-movflags",
            "+faststart",
            str(movie_path),
        ],
        check=True,
    )


def build_scene() -> bpy.types.Scene:
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene)
    build_station()
    add_starfield(scene)
    add_lighting(scene)
    camera = add_camera(scene)
    import_and_animate_ship(scene, camera)
    scene.frame_set(FRAME_START)

    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return scene


def render_preview(scene) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for frame in (8, 15, 22, 30, 40, FRAME_END):
        scene.frame_set(frame)
        scene.render.filepath = str(PREVIEW_DIR / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)


def render_movie(scene, frame_dir=FRAME_DIR, movie_path=MOVIE_PATH, crf=18) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frame_dir / "frame_")
    bpy.ops.render.render(animation=True)
    encode_movie(frame_dir, movie_path, crf)


def render_final(scene) -> None:
    # Resolution and encode quality only; all scene content and animation remain
    # identical to the approved v005 preview.
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1440
    scene.render.resolution_percentage = 100
    bpy.ops.wm.save_as_mainfile(filepath=str(FINAL_BLEND_PATH))
    render_movie(scene, FINAL_FRAME_DIR, FINAL_MOVIE_PATH, crf=14)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    scene = build_scene()
    if "--preview" in args:
        render_preview(scene)
    if "--render" in args:
        render_movie(scene)
    if "--final" in args:
        render_final(scene)
    print(f"[station86] blend: {BLEND_PATH}")
    if "--preview" in args:
        print(f"[station86] preview: {PREVIEW_DIR}")
    if "--render" in args:
        print(f"[station86] movie: {MOVIE_PATH}")
    if "--final" in args:
        print(f"[station86] final blend: {FINAL_BLEND_PATH}")
        print(f"[station86] final movie: {FINAL_MOVIE_PATH}")


if __name__ == "__main__":
    main()
