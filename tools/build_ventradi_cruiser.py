#!/usr/bin/env python3
"""
build_ventradi_cruiser.py - Headless Blender: Ventradi pirate cruiser.

Primitive rebuild of the Ventradi/Pismoni cruiser from the legacy top, side,
and action references. The ship is treated as a converted mining hull: a blunt
front hangar bay for mining diggers, ribbed industrial midsection, underslung
machinery, yellow utility markings, and paired aft engines.

Conventions match the other OEB ship builders: nose/front hangar points toward
-Y at identity, aft engines point toward +Y, origin is near hull centre, and
lowest point is z=0.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_ventradi_cruiser.py -- \
    --output assets/ships/ventradi_cruiser

Optional review renders:
  blender --background --factory-startup \
    --python tools/build_ventradi_cruiser.py -- \
    --output assets/ships/ventradi_cruiser \
    --review-dir out/ventradi_cruiser_review
"""

import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_ventradi_cruiser")
    p.add_argument("--output", default="assets/ships/ventradi_cruiser")
    p.add_argument("--review-dir", default=None)
    return p.parse_args(argv)


def mat(name, color, rough=0.55, metallic=0.0, emission=None, alpha=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission[0], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        if hasattr(m, "blend_method"):
            m.blend_method = "BLEND"
        m.use_backface_culling = False
    return m


def obj_from_bmesh(name, bm, material):
    me = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(me)
    bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(material)
    bpy.context.scene.collection.objects.link(ob)
    for poly in me.polygons:
        poly.use_smooth = True
    return ob


def add_cube_obj(name, material, size, loc, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "_mesh"
    ob.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    if bevel:
        mod = ob.modifiers.new(name + "_soft_edges", "BEVEL")
        mod.width = bevel
        mod.segments = 8
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_cylinder_y(name, material, radius, depth, loc, segs=36,
                   scale=(1.0, 1.0), bevel=False):
    rot = Matrix.Rotation(math.radians(90), 3, "X")
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=radius, radius2=radius, depth=depth)
    for v in res["verts"]:
        co = rot @ v.co
        co.x *= scale[0]
        co.z *= scale[1]
        v.co = co + Vector(loc)
    ob = obj_from_bmesh(name, bm, material)
    if bevel:
        mod = ob.modifiers.new(name + "_rim_soften", "BEVEL")
        mod.width = 0.035
        mod.segments = 4
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_cylinder_x(name, material, radius, depth, loc, segs=36,
                   scale=(1.0, 1.0), bevel=False):
    rot = Matrix.Rotation(math.radians(90), 3, "Y")
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=radius, radius2=radius, depth=depth)
    for v in res["verts"]:
        co = rot @ v.co
        co.y *= scale[0]
        co.z *= scale[1]
        v.co = co + Vector(loc)
    ob = obj_from_bmesh(name, bm, material)
    if bevel:
        mod = ob.modifiers.new(name + "_rim_soften", "BEVEL")
        mod.width = 0.035
        mod.segments = 4
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_cylinder_z(name, material, radius, depth, loc, segs=24,
                   scale=(1.0, 1.0), bevel=False):
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=radius, radius2=radius, depth=depth)
    for v in res["verts"]:
        v.co.x *= scale[0]
        v.co.y *= scale[1]
        v.co += Vector(loc)
    ob = obj_from_bmesh(name, bm, material)
    if bevel:
        mod = ob.modifiers.new(name + "_rim_soften", "BEVEL")
        mod.width = 0.02
        mod.segments = 3
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_torus_y(name, material, major_radius, minor_radius, loc):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius, minor_radius=minor_radius,
        major_segments=72, minor_segments=10, location=loc,
        rotation=(math.radians(90), 0, 0))
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "_mesh"
    ob.data.materials.append(material)
    return ob


def add_curved_rib_band(name, material, y, center_z=1.04,
                        outer_rx=1.46, outer_rz=0.88, band=0.16,
                        depth=0.22):
    """Curved yellow cage rib wrapping the top and sides of the mining bay."""
    bm = bmesh.new()
    angles = [math.radians(-104 + i * 208 / 42) for i in range(43)]
    layers = []
    for yy in (y - depth * 0.5, y + depth * 0.5):
        outer = []
        inner = []
        for a in angles:
            outer.append(bm.verts.new((
                outer_rx * math.sin(a), yy, center_z + outer_rz * math.cos(a)
            )))
            inner.append(bm.verts.new((
                (outer_rx - band) * math.sin(a), yy,
                center_z + (outer_rz - band) * math.cos(a)
            )))
        layers.append((outer, inner))
    for side in (0, 1):
        outer, inner = layers[side]
        for i in range(len(angles) - 1):
            bm.faces.new((outer[i], outer[i + 1], inner[i + 1], inner[i]))
    for i in range(len(angles) - 1):
        bm.faces.new((layers[0][0][i], layers[1][0][i],
                      layers[1][0][i + 1], layers[0][0][i + 1]))
        bm.faces.new((layers[0][1][i + 1], layers[1][1][i + 1],
                      layers[1][1][i], layers[0][1][i]))
    for idx in (0, -1):
        bm.faces.new((layers[0][0][idx], layers[0][1][idx],
                      layers[1][1][idx], layers[1][0][idx]))
    ob = obj_from_bmesh(name, bm, material)
    mod = ob.modifiers.new(name + "_worn_bevel", "BEVEL")
    mod.width = 0.045
    mod.segments = 5
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_capsule_y(name, material, radius, body_length, loc,
                  segs=36, cap_steps=8, scale_x=1.0):
    bm = bmesh.new()
    half_body = body_length * 0.5
    ys = []
    for i in range(cap_steps + 1):
        a = math.pi - (math.pi * 0.5) * i / cap_steps
        ys.append((-half_body + radius * math.cos(a), radius * math.sin(a)))
    ys.append((half_body, radius))
    for i in range(1, cap_steps + 1):
        a = math.pi * 0.5 - (math.pi * 0.5) * i / cap_steps
        ys.append((half_body + radius * math.cos(a), radius * math.sin(a)))

    rings = []
    for y, r in ys:
        ring = []
        rr = max(0.001, r)
        for j in range(segs):
            ang = 2 * math.pi * j / segs
            ring.append(bm.verts.new((
                loc[0] + scale_x * rr * math.cos(ang),
                loc[1] + y,
                loc[2] + rr * math.sin(ang),
            )))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for j in range(segs):
            bm.faces.new((a[j], a[(j + 1) % segs],
                          b[(j + 1) % segs], b[j]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    return obj_from_bmesh(name, bm, material)


def add_rect_decal_xy(name, material, size, loc):
    sx, sy = size[0] * 0.5, size[1] * 0.5
    bm = bmesh.new()
    verts = [
        bm.verts.new((loc[0] - sx, loc[1] - sy, loc[2])),
        bm.verts.new((loc[0] + sx, loc[1] - sy, loc[2])),
        bm.verts.new((loc[0] + sx, loc[1] + sy, loc[2])),
        bm.verts.new((loc[0] - sx, loc[1] + sy, loc[2])),
    ]
    bm.faces.new(verts)
    return obj_from_bmesh(name, bm, material)


def add_rect_decal_yz(name, material, size, loc, side=1):
    sy, sz = size[0] * 0.5, size[1] * 0.5
    bm = bmesh.new()
    x = loc[0]
    verts = [
        bm.verts.new((x, loc[1] - sy, loc[2] - sz)),
        bm.verts.new((x, loc[1] + sy, loc[2] - sz)),
        bm.verts.new((x, loc[1] + sy, loc[2] + sz)),
        bm.verts.new((x, loc[1] - sy, loc[2] + sz)),
    ]
    if side < 0:
        verts = list(reversed(verts))
    bm.faces.new(verts)
    return obj_from_bmesh(name, bm, material)


def add_rect_decal_xz(name, material, size, loc, front=True):
    sx, sz = size[0] * 0.5, size[1] * 0.5
    bm = bmesh.new()
    y = loc[1]
    verts = [
        bm.verts.new((loc[0] - sx, y, loc[2] - sz)),
        bm.verts.new((loc[0] + sx, y, loc[2] - sz)),
        bm.verts.new((loc[0] + sx, y, loc[2] + sz)),
        bm.verts.new((loc[0] - sx, y, loc[2] + sz)),
    ]
    if front:
        verts = list(reversed(verts))
    bm.faces.new(verts)
    return obj_from_bmesh(name, bm, material)


def add_hangar_bay(parts, decals, mats):
    shell, dark, gold, glow, copper, metal = (
        mats["shell"], mats["dark"], mats["gold"], mats["glow"],
        mats["copper"], mats["metal"])
    parts.append(add_cube_obj(
        "ventradi_cruiser_forward_armored_hangar_box", shell,
        (2.62, 2.34, 1.42), (0, -2.72, 1.04), bevel=0.12))
    parts.append(add_cube_obj(
        "ventradi_cruiser_faceted_upper_nose_plate", dark,
        (2.26, 0.24, 0.28), (0, -3.98, 1.62),
        rot=(math.radians(0), 0, 0), bevel=0.04))
    parts.append(add_cube_obj(
        "ventradi_cruiser_faceted_lower_nose_plate", dark,
        (2.26, 0.22, 0.26), (0, -4.00, 0.46), bevel=0.04))
    for sx in (-1, 1):
        parts.append(add_cube_obj(
            f"ventradi_cruiser_black_triangular_nose_guard_{sx}", dark,
            (0.24, 0.58, 0.88), (sx * 1.34, -3.74, 1.02),
            rot=(0, 0, math.radians(10 * -sx)), bevel=0.04))
        parts.append(add_cube_obj(
            f"ventradi_cruiser_yellow_corner_armor_{sx}", gold,
            (0.20, 0.34, 0.52), (sx * 1.42, -4.04, 0.70),
            rot=(0, 0, math.radians(22 * -sx)), bevel=0.035))
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_copper_side_lock_{sx}", copper,
            0.18, 0.08, (sx * 1.36, -1.66, 1.28), segs=28,
            scale=(1.0, 1.0), bevel=True))
    # The legacy render reads the digger bay as a large side-lit yellow
    # cylinder/window. The front face stays mostly armored and dark.
    parts.append(add_cube_obj(
        "ventradi_cruiser_armored_front_dark_inset", dark,
        (1.72, 0.045, 0.72), (0, -4.20, 1.04), bevel=0.035))
    parts.append(add_cube_obj(
        "ventradi_cruiser_front_yellow_edge_glow", glow,
        (1.36, 0.022, 0.08), (0, -4.235, 0.70), bevel=0.018))
    for i, (x, z, r) in enumerate(((-0.54, 1.33, -10), (0.20, 0.78, 8),
                                   (0.58, 1.18, 14))):
        parts.append(add_cube_obj(
            f"ventradi_cruiser_hangar_yellow_scuff_{i}", dark,
            (0.22, 0.018, 0.035), (x, -4.232, z),
            rot=(0, 0, math.radians(r)), bevel=0.006))
    parts.append(add_cube_obj(
        "ventradi_cruiser_luminous_side_hangar_window", glow,
        (0.045, 1.84, 0.82), (-1.345, -2.92, 1.08), bevel=0.055))
    parts.append(add_cylinder_y(
        "ventradi_cruiser_side_hangar_grey_endcap", metal,
        0.36, 0.20, (-1.37, -1.88, 1.08), segs=32,
        scale=(0.55, 1.0), bevel=True))
    parts.append(add_cube_obj(
        "ventradi_cruiser_top_black_equipment_panel", dark,
        (1.86, 0.72, 0.08), (0, -3.18, 1.77), bevel=0.04))
    for x in (-0.66, -0.38, -0.10, 0.18, 0.46, 0.74):
        parts.append(add_cube_obj(
            f"ventradi_cruiser_top_panel_raised_slot_{x}", metal,
            (0.07, 0.36, 0.055), (x, -3.18, 1.835),
            rot=(0, 0, math.radians(-8)), bevel=0.015))
    for sx in (-1,):
        for y in (-3.58, -2.78):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_side_yellow_cargo_pod_{sx}_{y}",
                gold, (0.34, 0.70, 0.30), (sx * 1.50, y, 0.50),
                bevel=0.08))
    for y in (-3.54, -2.80):
        parts.append(add_cylinder_x(
            f"ventradi_cruiser_starboard_yellow_side_tank_{y}", gold,
            0.20, 0.78, (1.48, y, 1.12), segs=28,
            scale=(0.9, 1.0), bevel=True))


def add_mid_mining_bay(parts, decals, mats):
    shell, dark, gold, metal = (
        mats["shell"], mats["dark"], mats["gold"], mats["metal"])
    parts.append(add_cylinder_y(
        "ventradi_cruiser_cylindrical_dark_mining_core", shell,
        0.78, 3.58, (0, 0.18, 1.02), segs=48, scale=(1.42, 1.0),
        bevel=True))
    parts.append(add_cube_obj(
        "ventradi_cruiser_lower_flat_mining_bay_chord", dark,
        (2.30, 3.55, 0.52), (0, 0.18, 0.58), bevel=0.06))
    # Four heavy yellow retaining ribs, now curved around the bay.
    for i, y in enumerate((-1.03, -0.22, 0.58, 1.38)):
        parts.append(add_curved_rib_band(
            f"ventradi_cruiser_curved_yellow_retaining_rib_{i}", gold, y))
        for j, x in enumerate((-0.70, 0.12, 0.62)):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_rib_chipped_paint_{i}_{j}", dark,
                (0.15, 0.026, 0.026), (x, y - 0.12, 1.84),
                rot=(0, 0, math.radians(16 - j * 13)), bevel=0.004))
        for sx in (-1, 1):
            parts.append(add_cylinder_y(
                f"ventradi_cruiser_rib_bolt_{i}_{sx}_upper", metal,
                0.045, 0.035, (sx * 0.90, y - 0.13, 1.62),
                segs=16, scale=(1.0, 1.0)))
            parts.append(add_cube_obj(
                f"ventradi_cruiser_lower_rib_bracket_{i}_{sx}", dark,
                (0.22, 0.32, 0.34), (sx * 0.92, y, 0.36), bevel=0.035))
    for sx in (-1, 1):
        for y in (-1.38, -0.62, 0.18, 0.98, 1.78):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_dark_side_socket_{sx}_{y}", dark,
                (0.20, 0.34, 0.36), (sx * 1.30, y, 0.86),
                bevel=0.05))
    for y in (-1.48, -0.72, 0.08, 0.88, 1.66):
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_grey_side_tank_port_{y}", metal,
            0.18, 0.52, (-1.18, y, 0.60), segs=24, scale=(1.0, 0.8),
            bevel=True))
    # Coarse mottled/tread marks from the original TIFF, kept low and dark so
    # they read as legacy surface noise rather than modern clean armor.
    idx = 0
    for y in (-1.58, -1.34, -1.10, -0.86, -0.62, -0.38, -0.14,
              0.10, 0.34, 0.58, 0.82, 1.06, 1.30):
        for x in (-0.82, -0.55, -0.28, 0.0, 0.28, 0.55, 0.82):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_legacy_mottle_tread_{idx}", metal,
                (0.035, 0.12, 0.018), (x, y, 1.815),
                rot=(0, 0, math.radians(38 if idx % 2 else -38)),
                bevel=0.006))
            idx += 1


def add_aft_engine_section(parts, mats):
    shell, dark, metal, blue, purple, red, copper = (
        mats["shell"], mats["dark"], mats["metal"], mats["blue"],
        mats["purple"], mats["red"], mats["copper"])
    parts.append(add_cube_obj(
        "ventradi_cruiser_aft_diamond_plate_neck", dark,
        (1.42, 1.18, 0.92), (0, 2.48, 0.92), bevel=0.07))
    for x in (-0.45, -0.15, 0.15, 0.45):
        for y in (2.12, 2.44, 2.76):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_aft_neck_tread_{x}_{y}", metal,
                (0.07, 0.22, 0.035), (x, y, 1.40),
                rot=(0, 0, math.radians(45)), bevel=0.01))
    for y in (2.00, 2.38):
        parts.append(add_torus_y(
            f"ventradi_cruiser_blue_energy_ring_{y}", blue,
            0.54, 0.035, (0, y, 0.92)))
    for y, z in ((2.08, 1.06), (2.08, 0.72)):
        parts.append(add_cylinder_x(
            f"ventradi_cruiser_legacy_blue_cross_fin_{z}", blue,
            0.055, 2.35, (0, y, z), segs=18, scale=(1.0, 0.55),
            bevel=True))
    for sx in (-1, 1):
        parts.append(add_cube_obj(
            f"ventradi_cruiser_exposed_engine_rail_outer_{sx}", dark,
            (0.28, 1.42, 0.46), (sx * 0.48, 3.48, 0.92), bevel=0.06))
        parts.append(add_cube_obj(
            f"ventradi_cruiser_exposed_engine_rail_inner_{sx}", dark,
            (0.18, 1.34, 0.30), (sx * 0.20, 3.46, 0.92), bevel=0.04))
        for y in (2.95, 3.18, 3.41, 3.64, 3.87):
            parts.append(add_cylinder_x(
                f"ventradi_cruiser_engine_coil_{sx}_{y}", copper,
                0.035, 0.34, (sx * 0.34, y, 0.92), segs=12,
                scale=(0.75, 1.0)))
        parts.append(add_capsule_y(
            f"ventradi_cruiser_twin_engine_housing_{sx}", shell,
            0.22, 0.76, (sx * 0.36, 3.82, 0.92), segs=28, scale_x=0.74))
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_engine_nozzle_{sx}", metal,
            0.20, 0.20, (sx * 0.36, 4.28, 0.92), segs=32, scale=(0.90, 0.90),
            bevel=True))
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_purple_engine_glow_{sx}", purple,
            0.26, 0.10, (sx * 0.36, 4.42, 0.92), segs=32, scale=(1.0, 1.0)))
    # Blue machinery blocks just forward of the engines seen in the top/side refs.
    for sx in (-1, 1):
        for z in (0.58, 1.20):
            parts.append(add_cube_obj(
                f"ventradi_cruiser_blue_aft_equipment_{sx}_{z}", blue,
                (0.24, 0.50, 0.13), (sx * 0.70, 2.28, z), bevel=0.03))
    for sx in (-1, 0, 1):
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_red_aux_thruster_{sx}", red,
            0.075, 0.12, (sx * 0.18, 4.48, 0.52), segs=18,
            scale=(0.72, 1.9)))


def add_underslung_industrial_parts(parts, mats):
    dark, gold, metal = mats["dark"], mats["gold"], mats["metal"]
    for sx in (-1, 1):
        parts.append(add_capsule_y(
            f"ventradi_cruiser_underslung_mining_tank_{sx}", gold,
            0.22, 1.35, (sx * 0.82, -2.20, 0.38), segs=28, scale_x=0.85))
    parts.append(add_cube_obj(
        "ventradi_cruiser_lower_machinery_keel", dark,
        (0.92, 2.20, 0.32), (0, 0.98, 0.42), bevel=0.06))
    for sx in (-1, 1):
        parts.append(add_cylinder_y(
            f"ventradi_cruiser_lower_grey_pipe_{sx}", metal,
            0.12, 2.70, (sx * 0.43, 0.65, 0.30), segs=18, scale=(0.75, 1.0)))
    for y in (-0.95, -0.18, 0.58, 1.32):
        parts.append(add_cube_obj(
            f"ventradi_cruiser_lower_hanging_bracket_{y}", dark,
            (0.42, 0.20, 0.36), (0, y, 0.16), bevel=0.035))


def build_cruiser():
    mats = {
        "shell": mat("mat_ventradi_cruiser_charcoal_mottled",
                     (0.055, 0.056, 0.050), rough=0.86, metallic=0.12),
        "dark": mat("mat_ventradi_cruiser_black_machinery",
                    (0.006, 0.007, 0.008), rough=0.70, metallic=0.18),
        "gold": mat("mat_ventradi_cruiser_ochre_panels",
                    (0.80, 0.68, 0.06), rough=0.62, metallic=0.10),
        "glow": mat("mat_ventradi_cruiser_yellow_hangar_glow",
                    (1.0, 0.88, 0.03), rough=0.18,
                    emission=((1.0, 0.86, 0.02), 3.0)),
        "metal": mat("mat_ventradi_cruiser_gunmetal",
                     (0.28, 0.27, 0.24), rough=0.54, metallic=0.38),
        "copper": mat("mat_ventradi_cruiser_burnished_copper",
                      (0.45, 0.18, 0.09), rough=0.48, metallic=0.45),
        "blue": mat("mat_ventradi_cruiser_blue_equipment",
                    (0.02, 0.08, 1.0), rough=0.26,
                    emission=((0.02, 0.08, 1.0), 1.9)),
        "purple": mat("mat_ventradi_cruiser_purple_engine_glow",
                      (0.65, 0.04, 0.95), rough=0.18,
                      emission=((0.82, 0.05, 1.0), 5.0)),
        "red": mat("mat_ventradi_cruiser_red_aux_glow",
                   (1.0, 0.05, 0.04), rough=0.18,
                   emission=((1.0, 0.04, 0.02), 4.6)),
    }
    parts = []
    decals = []
    add_hangar_bay(parts, decals, mats)
    add_mid_mining_bay(parts, decals, mats)
    add_aft_engine_section(parts, mats)
    add_underslung_industrial_parts(parts, mats)

    bpy.ops.object.select_all(action="DESELECT")
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    ship = bpy.context.view_layer.objects.active
    ship.name = "prop_ventradi_cruiser_A"
    ship.data.name = "prop_ventradi_cruiser_A_mesh"
    for poly in ship.data.polygons:
        poly.use_smooth = True
    for decal in decals:
        decal.parent = ship
        if hasattr(decal, "visible_shadow"):
            decal.visible_shadow = False
        if hasattr(decal, "cycles_visibility"):
            decal.cycles_visibility.shadow = False
    return ship


def render_review(review_dir):
    os.makedirs(review_dir, exist_ok=True)
    scene = bpy.context.scene
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = candidate
            break
        except TypeError:
            continue

    world = bpy.data.worlds.new("ventradi_cruiser_review_space")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.0, 0.0, 0.0, 1.0)
    scene.world = world

    for name, energy, rot in (
        ("key", 4.6, (55, 0, -35)),
        ("rim", 2.0, (88, 0, 145)),
        ("low_fill", 0.8, (-25, 0, 35)),
    ):
        light = bpy.data.lights.new(name, type="SUN")
        light.energy = energy
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.rotation_euler = tuple(math.radians(v) for v in rot)

    cam_data = bpy.data.cameras.new("review_cam")
    cam = bpy.data.objects.new("review_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 650
    target = Vector((0, 0, 0.95))

    views = {
        "top": (0, 0.01, 17.5),
        "bottom": (0, 0.01, -17.5),
        "left": (-10.2, 0, 1.25),
        "front": (0, -10.2, 1.10),
        "back": (0, 10.2, 1.10),
        "action": (-6.2, -7.8, 3.0),
    }
    for name, pos in views.items():
        cam.location = pos
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = 8.8
        if name == "top":
            cam.rotation_euler = (0.0, 0.0, math.radians(180))
            cam_data.ortho_scale = 14.0
        elif name == "bottom":
            cam.rotation_euler = (math.radians(180), 0.0, 0.0)
            cam_data.ortho_scale = 14.0
        else:
            direction = target - Vector(pos)
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        if name == "action":
            cam_data.type = "PERSP"
            cam_data.lens = 36
            cam.location = (8.6, -10.8, 3.6)
            direction = target - Vector(cam.location)
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
            cam.rotation_euler.rotate_axis("Z", math.radians(-10))
        scene.render.filepath = os.path.join(review_dir,
                                             f"ventradi_cruiser_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("[build_ventradi_cruiser] review wrote", scene.render.filepath)


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    ship = build_cruiser()
    print(f"[build_ventradi_cruiser] joined: {len(ship.data.polygons)} polys, "
          f"{len(ship.material_slots)} materials")

    glb = out_stem + ".glb"
    print(f"[build_ventradi_cruiser] Exporting {glb}")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                              use_selection=False)

    usdc = out_stem + ".usdc"
    print(f"[build_ventradi_cruiser] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=False,
                              export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)

    if args.review_dir:
        render_review(args.review_dir if os.path.isabs(args.review_dir)
                      else os.path.join(os.getcwd(), args.review_dir))
    print("[build_ventradi_cruiser] Done.")


if __name__ == "__main__":
    main()
