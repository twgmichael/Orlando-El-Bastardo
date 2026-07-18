#!/usr/bin/env python3
"""
build_pirate_flyer.py - Headless Blender: Ventradi Elipso Pirate Flyer.

Primitive rebuild of the Ventradi pirate "Elipso Flyer" using the three
legacy reference JPGs in OEB mk2/oeb/htdocs/pics:

  pirateflyertop.jpg   - one-piece wing with arched front, tapered striped hull,
                         front tube, wingtip antennas
  pirateflyerright.jpg - low rectangular/tube side mass, aft-down taper,
                         underslung rocket pod
  pirateflyer.jpg      - action/front strip, contoured tube nose with rounded
                         ends and simple stripe maps

Conventions follow build_jb100.py: nose points toward -Y at identity, origin is
near hull centre, lowest point is z=0, and the final asset is joined into one
canonical node before exporting GLB and USD.

Run from Orlando-El-Bastardo.src:
  blender --background --factory-startup \
    --python tools/build_pirate_flyer.py -- --output assets/ships/pirate_flyer

Optional review renders:
  blender --background --factory-startup \
    --python tools/build_pirate_flyer.py -- \
    --output assets/ships/pirate_flyer --review-dir out/pirate_flyer_review
"""

import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector


# Dimensions are in metres. This keeps the original construction language:
# a handful of blunt primitives with texture-map-like stripes.
WING_SPAN = 3.63
WING_LEN = 3.78
WING_Y = -0.34
WING_ARCH_DEPTH = 1.25
WING_ARC_STEPS = 72
WING_Z = 1.34
HULL_LEN = 4.2
HULL_FRONT_W = 2.02
HULL_AFT_W = 1.12
HULL_H = 0.74
NOSE_Y = -2.06
NOSE_Z = 1.06
ANTENNA_X = 1.92
ANTENNA_Z = 1.34
LENGTH_SCALE = 0.75


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_pirate_flyer")
    p.add_argument("--output", default="assets/ships/pirate_flyer")
    p.add_argument("--review-dir", default=None,
                   help="Optional directory for top/right/action PNG renders.")
    return p.parse_args(argv)


def mat(name, color, rough=0.5, metallic=0.0, emission=None, alpha=None):
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


def add_uv_ellipsoid(name, material, scale, loc, segs=48, rings=18,
                     keep_upper=None):
    bm = bmesh.new()
    res = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings,
                                    radius=1.0)
    if keep_upper is not None:
        doomed = [v for v in res["verts"] if (v.co.z >= 0) != keep_upper]
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0] + loc[0],
                       v.co.y * scale[1] + loc[1],
                       v.co.z * scale[2] + loc[2]))
    return obj_from_bmesh(name, bm, material)


def add_cone_obj(name, material, r1, r2, depth, loc, rot=None, segs=24):
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=r1, radius2=r2, depth=depth)
    for v in res["verts"]:
        co = v.co.copy()
        if rot is not None:
            co = rot @ co
        v.co = co + Vector(loc)
    return obj_from_bmesh(name, bm, material)


def add_capsule_x(name, material, radius, body_length, loc,
                  segs=32, cap_steps=8):
    """One continuous rounded tube along X, with no cylinder/cap seam."""
    bm = bmesh.new()
    half_body = body_length * 0.5
    xs = []
    for i in range(cap_steps + 1):
        a = math.pi - (math.pi * 0.5) * i / cap_steps
        xs.append((-half_body + radius * math.cos(a),
                   radius * math.sin(a)))
    xs.append((half_body, radius))
    for i in range(1, cap_steps + 1):
        a = math.pi * 0.5 - (math.pi * 0.5) * i / cap_steps
        xs.append((half_body + radius * math.cos(a),
                   radius * math.sin(a)))

    rings = []
    for x, r in xs:
        ring = []
        rr = max(0.001, r)
        for j in range(segs):
            ang = 2 * math.pi * j / segs
            ring.append(bm.verts.new((
                loc[0] + x,
                loc[1] + rr * math.cos(ang),
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


def cockpit_radius_at_x(x, total_half=1.08):
    """Bulged cockpit cross-section: fat center, tapered rounded ends."""
    u = min(1.0, abs(x) / total_half)
    return 0.28 + 0.20 * (math.cos(u * math.pi * 0.5) ** 0.55)


def add_bulged_cockpit_x(name, material, loc, x_steps=28, segs=40):
    """Extruded pod: rounded ends, broad middle bulge, continuous surface."""
    bm = bmesh.new()
    total_half = 1.08
    rings = []
    for i in range(x_steps + 1):
        t = -1.0 + 2.0 * i / x_steps
        x = total_half * t
        r = cockpit_radius_at_x(x, total_half)
        ring = []
        for j in range(segs):
            ang = 2 * math.pi * j / segs
            ring.append(bm.verts.new((
                loc[0] + x,
                loc[1] + r * math.cos(ang),
                loc[2] + r * math.sin(ang),
            )))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for j in range(segs):
            bm.faces.new((a[j], a[(j + 1) % segs],
                          b[(j + 1) % segs], b[j]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    return obj_from_bmesh(name, bm, material)


def add_curved_viewport_x(name, material, loc, x_width=2.04, z_fill=0.97,
                          x_steps=24, z_steps=8):
    """Black front port that follows the bulged pod's front curvature."""
    bm = bmesh.new()
    verts = []
    for ix in range(x_steps + 1):
        x = -x_width * 0.5 + x_width * ix / x_steps
        r = cockpit_radius_at_x(x)
        half_z = r * z_fill
        row = []
        for iz in range(z_steps + 1):
            z = -half_z + 2.0 * half_z * iz / z_steps
            # Slightly proud of the theoretical surface to avoid z-fighting;
            # the black material and curved outline read as the inset port.
            y = -math.sqrt(max(0.0, r * r - z * z)) - 0.012
            row.append(bm.verts.new((loc[0] + x, loc[1] + y, loc[2] + z)))
        verts.append(row)
    for ix in range(x_steps):
        for iz in range(z_steps):
            bm.faces.new((verts[ix][iz], verts[ix + 1][iz],
                          verts[ix + 1][iz + 1], verts[ix][iz + 1]))
    return obj_from_bmesh(name, bm, material)


def add_cube_obj(name, material, size, loc, rot_z=0.0, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "_mesh"
    ob.dimensions = size
    ob.rotation_euler.z = rot_z
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    if bevel:
        mod = ob.modifiers.new(name + "_soft_edges", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def add_rect_decal_obj(name, material, size, loc):
    """Flat one-face rectangular decal, used where texture maps would sit."""
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


def add_tapered_beveled_box(name, material, length, front_width, aft_width,
                            height, loc, bevel=0.16):
    """Beveled cube tapered in X from fore (-Y) to aft (+Y)."""
    ob = add_cube_obj(name, material, (front_width, length, height), loc,
                      bevel=bevel)
    y_min = loc[1] - length * 0.5
    y_max = loc[1] + length * 0.5
    for v in ob.data.vertices:
        wy = (ob.matrix_world @ v.co).y
        t = (wy - y_min) / (y_max - y_min)
        desired_w = front_width + (aft_width - front_width) * t
        v.co.x *= desired_w / front_width
        # Low aft droop visible in the side reference.
        v.co.z -= max(0.0, t - 0.58) * 0.24
    ob.data.update()
    return ob


def add_arch_wing(name, material):
    """One slab across the whole craft, with a semicircular front arch."""
    bm = bmesh.new()
    span = WING_SPAN * 0.5
    y_back = WING_Y + WING_LEN * 0.5
    y_front = WING_Y - WING_LEN * 0.5
    thick = 0.12
    verts_top = []
    outline = []
    # Back edge, then one arched front edge across the span. The centre of
    # the front edge sits forward; the tips sweep back, matching Photo 1.
    outline.append((-span, y_back))
    outline.append((span, y_back))
    for i in range(WING_ARC_STEPS + 1):
        theta = math.pi * i / WING_ARC_STEPS
        x = span * math.cos(theta)
        y = y_front + WING_ARCH_DEPTH * (1.0 - math.sin(theta))
        outline.append((x, y))
    verts_bot = []
    for x, y in outline:
        verts_top.append(bm.verts.new((x, y, WING_Z + thick * 0.5)))
    for x, y in outline:
        verts_bot.append(bm.verts.new((x, y, WING_Z - thick * 0.5)))
    bm.faces.new(verts_top)
    bm.faces.new(list(reversed(verts_bot)))
    n = len(outline)
    for i in range(n):
        bm.faces.new((verts_top[i], verts_top[(i + 1) % n],
                      verts_bot[(i + 1) % n], verts_bot[i]))
    ob = obj_from_bmesh(name, bm, material)
    mod = ob.modifiers.new(name + "_soft_edge", "BEVEL")
    mod.width = 0.06
    mod.segments = 8
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def scale_length(objs, factor):
    """Scale every object along the craft length axis around the origin."""
    for ob in objs:
        ob.location.y *= factor
        for v in ob.data.vertices:
            v.co.y *= factor
        ob.data.update()


def restore_round_y_profile(ob, center_y, factor):
    """Undo length-axis squash for objects that must remain round in Y/Z."""
    for v in ob.data.vertices:
        v.co.y = center_y + (v.co.y - center_y) / factor
    ob.data.update()


def build_flyer():
    mat_shell = mat("mat_pirate_flyer_brown_shell", (0.25, 0.18, 0.12),
                    rough=0.72, metallic=0.06)
    mat_dark = mat("mat_pirate_flyer_black_pod", (0.008, 0.008, 0.01),
                   rough=0.62, metallic=0.08)
    mat_gold = mat("mat_pirate_flyer_ochre_stripes", (0.52, 0.39, 0.10),
                   rough=0.58, metallic=0.05)
    mat_grey = mat("mat_pirate_flyer_grey_roll", (0.50, 0.47, 0.36),
                   rough=0.55, metallic=0.05)
    mat_spar = mat("mat_pirate_flyer_white_spars", (0.88, 0.92, 0.88),
                   rough=0.35, metallic=0.25)
    mat_tip = mat("mat_pirate_flyer_hot_tips", (1.0, 0.48, 0.08),
                  rough=0.18, emission=((1.0, 0.34, 0.04), 1.8))
    mat_flare = mat("mat_pirate_flyer_engine_flare", (0.75, 0.02, 0.01),
                    rough=0.2, emission=((1.0, 0.05, 0.01), 3.2))
    mat_glass = mat("mat_pirate_flyer_smoked_intake", (0.0, 0.0, 0.0),
                    rough=0.1, metallic=0.0, alpha=0.58)

    parts = []
    decals = []

    # Seven-shape read:
    # 1. one-piece wing slab across the whole flyer, arched at the front.
    parts.append(add_arch_wing("pirate_flyer_one_piece_wing", mat_shell))

    # 2. tapered rounded-box hull sitting on top, narrower toward the aft.
    parts.append(add_tapered_beveled_box(
        "pirate_flyer_tapered_hull", mat_shell, HULL_LEN,
        HULL_FRONT_W, HULL_AFT_W, HULL_H, (0, 0.04, NOSE_Z), bevel=0.18))

    # 3. front pod: bulged through the middle and tapering to rounded ends.
    cockpit_pod = add_bulged_cockpit_x(
        "pirate_flyer_front_cockpit_pod", mat_grey, (0, NOSE_Y, NOSE_Z))
    parts.append(cockpit_pod)
    viewport = add_curved_viewport_x(
        "pirate_flyer_front_viewport", mat_dark, (0, NOSE_Y, NOSE_Z),
        x_steps=32, z_steps=14)
    parts.append(viewport)

    # 4/5. two rocket engines slung under the wing.
    pitch_x = Matrix.Rotation(math.radians(90), 3, "X")
    for sx in (-1, 1):
        parts.append(add_cone_obj(
            f"pirate_flyer_underslung_engine_{'l' if sx < 0 else 'r'}",
            mat_dark, 0.29, 0.24, 1.22, (sx * 0.76, 0.82, 1.08),
            rot=pitch_x, segs=24))
        parts.append(add_cone_obj(
            f"pirate_flyer_engine_nozzle_{'l' if sx < 0 else 'r'}",
            mat_grey, 0.24, 0.16, 0.22, (sx * 0.76, 1.50, 1.08),
            rot=pitch_x, segs=24))
        parts.append(add_cone_obj(
            f"pirate_flyer_engine_flare_{'l' if sx < 0 else 'r'}",
            mat_flare, 0.18, 0.03, 0.48, (sx * 0.76, 1.82, 1.08),
            rot=pitch_x, segs=18))

    # 6/7. ray gun antennas protruding from the far end of the wings.
    for sx in (-1, 1):
        parts.append(add_cone_obj(
            f"pirate_flyer_ray_antenna_{'l' if sx < 0 else 'r'}", mat_spar,
            0.045, 0.035, 1.82, (sx * ANTENNA_X, -1.05, ANTENNA_Z),
            rot=pitch_x, segs=12))
        for y, suffix in ((-2.08, "fore"), (-0.18, "aft")):
            parts.append(add_cone_obj(
                f"pirate_flyer_ray_{suffix}_tip_{'l' if sx < 0 else 'r'}",
                mat_tip, 0.075, 0.018, 0.34, (sx * ANTENNA_X, y, ANTENNA_Z),
                rot=pitch_x, segs=10))

    # Simple stripe maps as raised strips: these stand in for the original
    # primitive-era texture maps, not separate structural parts.
    stripe_xs = (-0.42, -0.14, 0.14, 0.42)
    for idx, x in enumerate(stripe_xs):
        decal = add_rect_decal_obj(
            f"pirate_flyer_ochre_spine_{idx}", mat_gold,
            (0.075, 3.35),
            (x, 0.20, NOSE_Z + HULL_H * 0.5 + 0.001))
        if hasattr(decal, "visible_shadow"):
            decal.visible_shadow = False
        if hasattr(decal, "cycles_visibility"):
            decal.cycles_visibility.shadow = False
        decals.append(decal)

    scale_length(parts + decals, LENGTH_SCALE)
    restore_round_y_profile(cockpit_pod, NOSE_Y * LENGTH_SCALE, LENGTH_SCALE)
    restore_round_y_profile(viewport, NOSE_Y * LENGTH_SCALE, LENGTH_SCALE)

    bpy.ops.object.select_all(action="DESELECT")
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    ship = bpy.context.view_layer.objects.active
    ship.name = "prop_pirate_flyer_A"
    ship.data.name = "prop_pirate_flyer_A_mesh"
    for poly in ship.data.polygons:
        poly.use_smooth = True
    for decal in decals:
        decal.parent = ship
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

    world = bpy.data.worlds.new("pirate_flyer_review_space")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.0, 0.0, 0.0, 1.0)
    scene.world = world

    for name, energy, rot in (
        ("key", 4.0, (55, 0, -35)),
        ("fill", 1.4, (120, 0, 140)),
    ):
        light = bpy.data.lights.new(name, type="SUN")
        light.energy = energy
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.rotation_euler = tuple(math.radians(v) for v in rot)

    cam_data = bpy.data.cameras.new("review_cam")
    cam_data.lens = 55
    cam = bpy.data.objects.new("review_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x = 900
    scene.render.resolution_y = 650
    target = Vector((0, 0, 0.65))

    views = {
        "top": (0, 0.01, 15.5),
        "bottom": (0, 0.01, -15.5),
        "left": (-10.5, 0, 1.25),
        "front": (0, -10.5, 1.35),
        "back": (0, 10.5, 1.35),
        "action": (-7.5, -8.5, 3.4),
    }
    for name, pos in views.items():
        cam.location = pos
        if name == "top":
            # Straight plan view: nose/front tube (-Y) at the top of frame,
            # matching the old top reference sheet.
            cam.rotation_euler = (0.0, 0.0, math.radians(180))
            cam_data.lens = 62
        elif name == "bottom":
            cam.rotation_euler = (math.radians(180), 0.0, 0.0)
            cam_data.lens = 62
        else:
            direction = target - Vector(pos)
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
            cam_data.lens = 48 if name == "action" else 55
        if name == "action":
            cam.rotation_euler.rotate_axis("Z", math.radians(-12))
        scene.render.filepath = os.path.join(review_dir,
                                             f"pirate_flyer_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("[build_pirate_flyer] review wrote", scene.render.filepath)


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    ship = build_flyer()
    print(f"[build_pirate_flyer] joined: {len(ship.data.polygons)} polys, "
          f"{len(ship.material_slots)} materials")

    glb = out_stem + ".glb"
    print(f"[build_pirate_flyer] Exporting {glb}")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                              use_selection=False)

    usdc = out_stem + ".usdc"
    print(f"[build_pirate_flyer] Exporting {usdc}")
    try:
        bpy.ops.wm.usd_export(filepath=usdc, export_animation=False,
                              export_materials=True)
    except TypeError:
        bpy.ops.wm.usd_export(filepath=usdc)

    if args.review_dir:
        render_review(args.review_dir if os.path.isabs(args.review_dir)
                      else os.path.join(os.getcwd(), args.review_dir))
    print("[build_pirate_flyer] Done.")


if __name__ == "__main__":
    main()
