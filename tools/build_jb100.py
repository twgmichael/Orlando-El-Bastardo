#!/usr/bin/env python3
"""
build_jb100.py — Headless Blender: the JourneyBlaster 100 from primitives.

Current asset pass: v38 (2026-08-24), pilot-free hero stand-in promotion.

The JourneyBlaster 100 — the FIRST version of Yakara Starcraft's
legendary sport attack craft line. Forked 2026-07-12 from the JB5K
reconstruction (see build_jb5k.py, whose hull/anatomy notes
(anatomy corrected 2026-07-12 per owner review, iteratively): built as
TWO HALVES like the 1995 original — the bottom a short flat-bottom BOWL
(tub profile: flat floor, rounded corner, short wall) and the top shell
extending slightly OVER it, the overhang lip + rounded bottom edge
hiding the seam and giving the distinctive edge detail (v18); the top
swells toward the aft (engine deck); centered smoked-glass bubble
canopy with a cockpit TUB — flat floor and flat ribbed sides joined by a rounded
corner (v14, "less cereal bowl, more cockpit") — visible through the
top shell's HOLLOW centre, holding ONE low reclining crash seat plus a
three-display analog dashboard, dual thigh sticks, physical throttle,
and minimal side controls (v37); promoted without a baked pilot as the
production hero stand-in in v38; bowl and bubble
are simple CIRCLES in plan; the bubble is a hollow HALF-GLOBE shell (it is a
single-seat sport attack craft; seated characters read waist/shoulders/head
through the glass, and the bubble stays under HALF the ship's total
height — v8 proportions rule); FOUR amber "senso-globes" per side riding the hull profile,
protruding MORE at the aft and less toward the bow; twin FRAP-RAY
cannons LYING ALONG the hull at the front corners (short — halved in
v5), barrels protruding straight out past the rim with 3 evenly spaced
rings; twin SLIM engine pods on the aft deck pointing STRAIGHT BACK, ring
vents with red cores aft and orange emissive tips (there is NO separate antenna — the 4K top view showed
the "boom" was the engines in profile). The flat belly carries 16
white discs in a ring close to the plate edge, each with a rotating
thruster — they track cooperatively but
can spin individually; modeled at rest pointing straight down (a joined
static mesh: individually animatable thrusters would need separate
nodes, a later variant). Reference sheets read aft-LEFT / fore-RIGHT.

Conventions: nose toward -Y at identity (matches the character facing
convention, so exporter move cues steer it correctly if it ever becomes
an actor); origin at hull center with the lowest point at z = 0.

Run from repo root:
  blender --background --factory-startup \
    --python tools/build_jb100.py -- --output assets/ships/jb100
"""

import sys
import os
import argparse
import json
import math

import bpy
import bmesh
from mathutils import Matrix, Vector

# ── Dimensions (metres) ──────────────────────────────────────────────────────
HULL_D = 6.5          # saucer diameter
BOT_TOP = 0.337       # bottom half: short flat-bottom bowl height (−10%, v36)
BOT_FILLET = 0.18     # rounded corner joining bottom to side wall
LIP = 0.12            # top hull overhangs the bottom bowl by this much
DOME_H = 0.903        # top half height at centre (+5%, v35)
DOME_AFT = 0.4        # aft bias: dome swells toward the back (engine deck)
CANOPY_R = 1.35       # bubble canopy radius
BOWL_R = 1.15         # corrugated cockpit bowl sunk below the bubble
HOLE_R = 1.05         # hollow centre of the top shell (cockpit opening)
POD_L = 2.16          # engine pod length (+20% again, v33)
POD_R = 0.43          # engine pod radius (+20% again, v33)
POD_X = 0.95          # pod lateral offset (aft deck beside canopy)
POD_Y = 1.93          # pod aft offset (+Y is aft)
POD_YAW = 0.0         # engines point STRAIGHT BACK (v10)
GLOBE_R = 0.37        # senso-globe radius (+20% again, v34)
# Senso-globes: (y position, sink into hull) — protrusion grows toward
# the AFT (owner correction 2026-07-12); bases ride the hull profile.
GLOBES = [(1.35, 0.01), (0.55, 0.03), (-0.35, 0.05), (-1.25, 0.08)]
GLOBE_SPREAD = 0.74   # lateral placement: fraction of half-width at y
CANNON_X = 1.5        # frap-ray cannon lateral offset
CANNON_Y = -1.9       # body position — up on the front hull (v12)
CANNON_OUT = -0.2     # muzzle stays INSIDE the rim, no protrusion (v12)
CANNON_RINGS = 3      # evenly spaced rings around the barrel
DISC_N = 16           # white maneuvering discs circling the flat belly
DISC_RING_R = 2.55    # ring radius — close to the bottom-plate edge (v7)
DISC_R = 0.2          # disc radius
THRUSTER_R = 0.07     # rotating thruster stub in each disc centre
BUILD_VERSION = 38


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(prog="build_jb100")
    p.add_argument("--output", default="assets/ships/jb100")
    p.add_argument("--versioned-output",
                   default="assets/ships/jb100_v38/jb100_v38")
    p.add_argument("--working-blend",
                   default="assets/ships/jb100_v38/jb100_v38.blend")
    return p.parse_args(argv)


def mat(name, color, rough=0.4, metallic=0.0, emission=None,
        alpha=None):
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
            m.blend_method = 'BLEND'
        m.use_backface_culling = False
    return m


def add_sphere(bm, radius, scale, offset, segs=32, rings=16):
    res = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings,
                                    radius=radius)
    for v in res["verts"]:
        v.co = Vector((v.co.x * scale[0] + offset[0],
                       v.co.y * scale[1] + offset[1],
                       v.co.z * scale[2] + offset[2]))
    return res["verts"]


def add_cone(bm, r1, r2, depth, offset, rot=None, segs=24):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=r1, radius2=r2, depth=depth)
    for v in res["verts"]:
        co = v.co.copy()
        if rot:
            co = rot @ co
        v.co = co + Vector(offset)
    return res["verts"]


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


def bevel_object(obj, width=0.025, segments=2):
    """Apply a small production-friendly bevel to a primitive assembly."""
    mod = obj.modifiers.new(name="softened_edges", type='BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.select_set(False)


def main():
    args = parse_args()
    out_stem = args.output if os.path.isabs(args.output) \
        else os.path.join(os.getcwd(), args.output)
    os.makedirs(os.path.dirname(out_stem), exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    mat_hull = mat("mat_jb100_hull", (0.72, 0.02, 0.02), rough=0.32,
                   metallic=0.15)
    mat_glass = mat("mat_jb100_canopy", (0.05, 0.06, 0.08), rough=0.02,
                    metallic=0.05, alpha=0.22)
    mat_pod = mat("mat_jb100_pod", (0.02, 0.02, 0.02), rough=0.45)
    mat_gold = mat("mat_jb100_intake", (0.85, 0.62, 0.12), rough=0.25,
                   metallic=0.9)
    mat_lamp = mat("mat_jb100_lamp", (1.0, 0.82, 0.0), rough=0.12,
                   emission=((1.0, 0.6, 0.0), 2.2))
    mat_burn = mat("mat_jb100_exhaust", (0.35, 0.02, 0.02), rough=0.4,
                   emission=((0.85, 0.04, 0.02), 0.8))
    mat_dark = mat("mat_jb100_interior", (0.035, 0.04, 0.05), rough=0.82)
    mat_panel = mat("mat_jb100_panel", (0.055, 0.06, 0.07), rough=0.66,
                    metallic=0.12)
    mat_frame = mat("mat_jb100_seat_frame", (0.025, 0.028, 0.032),
                    rough=0.48, metallic=0.38)
    mat_harness = mat("mat_jb100_harness", (0.48, 0.015, 0.012),
                      rough=0.58)
    mat_screen_green = mat("mat_jb100_screen_nav", (0.008, 0.045, 0.014),
                           rough=0.2, emission=((0.02, 0.45, 0.06), 0.9))
    mat_screen_amber = mat("mat_jb100_screen_weapons", (0.06, 0.025, 0.003),
                           rough=0.2, emission=((0.75, 0.18, 0.01), 0.8))
    mat_indicator_green = mat("mat_jb100_indicator_green", (0.01, 0.35, 0.04),
                              rough=0.2, emission=((0.03, 1.0, 0.12), 2.0))
    mat_indicator_amber = mat("mat_jb100_indicator_amber", (0.55, 0.12, 0.005),
                              rough=0.2, emission=((1.0, 0.28, 0.01), 2.0))
    mat_indicator_red = mat("mat_jb100_indicator_red", (0.48, 0.005, 0.005),
                            rough=0.2, emission=((1.0, 0.01, 0.01), 2.2))
    mat_white = mat("mat_jb100_disc", (0.92, 0.92, 0.95), rough=0.35,
                    emission=((1.0, 1.0, 1.0), 0.3))
    mat_tanks = mat("mat_jb100_tanks", (0.92, 0.92, 0.95), rough=0.35)
    mat_seat = mat("mat_jb100_seat", (0.075, 0.08, 0.09), rough=0.72)

    # Two-half hull (v18, like the 1995 original): flat-bottom bowl
    # below, top shell overhanging it by LIP
    hull_a, hull_b = HULL_D * 0.48, HULL_D * 0.5
    dome_a, dome_b = hull_a, hull_b
    seam_z = BOT_TOP - 0.04   # top shell base tucks under the bowl edge

    def aft_bias(y):
        return 1.0 + DOME_AFT * max(0.0, y / dome_b)

    def deck_z(x, y):
        """Top-shell surface height at (x, y): flat dome with aft bias."""
        u = 1 - (x / dome_a) ** 2 - (y / dome_b) ** 2
        return seam_z + DOME_H * math.sqrt(max(0.0, u)) * aft_bias(y)

    z0 = BOT_TOP

    # Bottom half: short flat-bottom bowl (lathed tub profile, like the
    # cockpit), radius LIP smaller than the top shell
    rb = hull_b - LIP
    RECESS, R_REC = 0.1, 2.85     # concave belly: recessed centre panel
    bm = bmesh.new()
    profile = [(0.02, RECESS), (R_REC - 0.12, RECESS), (R_REC, 0.0),
               (rb - BOT_FILLET, 0.0)]
    for k in range(1, 5):
        a = math.pi / 2 * k / 4
        profile.append((rb - BOT_FILLET + BOT_FILLET * math.sin(a),
                        BOT_FILLET - BOT_FILLET * math.cos(a)))
    profile.append((rb, BOT_TOP))
    prev = None
    edges = []
    for r, z in profile:
        vtx = bm.verts.new((r, 0.0, z))
        if prev is not None:
            edges.append(bm.edges.new((prev, vtx)))
        prev = vtx
    bmesh.ops.spin(bm, geom=list(bm.verts) + edges, cent=(0, 0, 0),
                   axis=(0, 0, 1), angle=2 * math.pi, steps=48,
                   use_merge=True)
    for v in bm.verts:
        v.co.x *= hull_a / hull_b
    bowl_bottom = obj_from_bmesh("jb100_hull_bottom", bm, mat_hull)

    # Top half: flat dome swelling toward the aft engine deck, HOLLOW
    # centre, base extending over the bottom bowl (the lip)
    bm = bmesh.new()
    res = bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24,
                                    radius=1.0)
    hole_verts = []
    for v in res["verts"]:
        if v.co.z < 0:
            v.co.z = 0.0
        z = DOME_H * v.co.z * aft_bias(v.co.y * dome_b)
        v.co = Vector((v.co.x * dome_a, v.co.y * dome_b, seam_z + z))
        if (v.co.x ** 2 + v.co.y ** 2) < HOLE_R ** 2:
            hole_verts.append(v)
    bmesh.ops.delete(bm, geom=hole_verts, context='VERTS')
    hull = obj_from_bmesh("jb100_hull", bm, mat_hull)

    # Canopy: hollow HALF-GLOBE shell riding HIGH on the top hull,
    # slightly smaller than the cockpit opening ring; rim conformed
    # down into the deck to seal (v25)
    bm = bmesh.new()
    res = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20,
                                    radius=1.0)
    low = [v for v in res["verts"] if v.co.z < 0.0]
    bmesh.ops.delete(bm, geom=low, context='VERTS')
    for v in bm.verts:                 # PERFECT half globe, no rim
        v.co = Vector((v.co.x * 1.15, v.co.y * 1.15,
                       v.co.z * 1.208 + 1.12))
    canopy = obj_from_bmesh("jb100_canopy", bm, mat_glass)  # into the tub

    # Cockpit: corrugated open bowl sunk below the bubble (simple
    # shapes, like the '95 original), one low seat and compact controls.
    # Tub profile (v14): flat floor, flat vertical wall, rounded corner
    # joining them — lathed around Z, ribbing applied to the wall only
    bm = bmesh.new()
    FLOOR_Z, FILLET, WALL_TOP = 0.22, 0.16, 1.09
    profile = [(0.0, FLOOR_Z), (BOWL_R - FILLET, FLOOR_Z)]
    for k in range(1, 5):                      # quarter-round corner
        a = math.pi / 2 * k / 4
        profile.append((BOWL_R - FILLET + FILLET * math.sin(a),
                        FLOOR_Z + FILLET - FILLET * math.cos(a)))
    profile += [(BOWL_R, z) for z in (0.45, 0.62, WALL_TOP)]
    prev = None
    edges = []
    for r, z in profile:
        vtx = bm.verts.new((r, 0.0, z))
        if prev is not None:
            edges.append(bm.edges.new((prev, vtx)))
        prev = vtx
    bmesh.ops.spin(bm, geom=list(bm.verts) + edges, cent=(0, 0, 0),
                   axis=(0, 0, 1), angle=2 * math.pi, steps=100,
                   use_merge=True)
    # fine vertical striping on the wall only — circle preserved from
    # lip to rounded floor (v28: shallow, high-frequency)
    for v in bm.verts:
        r = math.hypot(v.co.x, v.co.y)
        if r > 0.1 and FLOOR_Z + FILLET * 0.6 < v.co.z < WALL_TOP - 0.06:
            ang = math.atan2(v.co.y, v.co.x)
            f = 1.0 + 0.018 * math.cos(20 * ang)
            v.co.x *= f
            v.co.y *= f
    for v in bm.verts:                         # rim rises past the deck
        if v.co.z > WALL_TOP - 0.01:
            v.co.z = deck_z(v.co.x, v.co.y) + 0.09
    # LIP: flare the cup's top ring outward into a collar proud of the
    # hull — the glass seals against THIS, not the red metal (v27)
    # Only flare the outer/top boundary. Earlier passes also caught the tiny
    # floor-centre boundary, accidentally pulling it upward into a cone.
    rim_edges = [e for e in bm.edges if e.is_boundary and
                 all(v.co.z > WALL_TOP - 0.01 for v in e.verts)]
    ret = bmesh.ops.extrude_edge_only(bm, edges=rim_edges)
    for g in ret["geom"]:
        if isinstance(g, bmesh.types.BMVert):
            r = math.hypot(g.co.x, g.co.y)
            f = (r + 0.12) / r
            g.co.x *= f
            g.co.y *= f
            g.co.z = deck_z(g.co.x, g.co.y) + 0.01   # flange lands ON
    cockpit = obj_from_bmesh("jb100_bowl", bm, mat_dark)  # the deck (v29)
    # Keep the shallow tub floor optically flat. Smooth interpolation across
    # the lathed centre ring can otherwise read as a phantom cone in closeups.
    for poly in cockpit.data.polygons:
        if all(abs(cockpit.data.vertices[i].co.z - FLOOR_Z) < 0.005
               for i in poly.vertices):
            poly.use_smooth = False

    cockpit_parts = [cockpit]

    def add_box(bm, size, center, rot=None):
        """Add a box, optionally rotated around its own centre."""
        res = bmesh.ops.create_cube(bm, size=1.0)
        for v in res["verts"]:
            co = Vector((v.co.x * size[0], v.co.y * size[1],
                         v.co.z * size[2]))
            if rot is not None:
                co = rot @ co
            v.co = co + Vector(center)
        return res["verts"]

    def add_beam(bm, start, end, width, depth=None):
        """Rectangular beam used for belts, levers, and display marks."""
        a, b = Vector(start), Vector(end)
        delta = b - a
        depth = width if depth is None else depth
        rot = delta.to_track_quat('Z', 'Y').to_matrix()
        return add_box(bm, (width, depth, delta.length), (a + b) * 0.5, rot)

    # v37 cockpit set.  The pilot faces -Y.  Furniture is deliberately
    # compact and mechanical: one reclined Barka predecessor seat, a curved
    # three-display dashboard, two thigh sticks, and a separate left throttle.
    seat_y = 0.24
    back_rot = Matrix.Rotation(math.radians(-13.0), 3, 'X')

    # Structural chair frame and low pedestal.
    bm = bmesh.new()
    add_box(bm, (0.54, 0.46, 0.10), (0, seat_y + 0.04, 0.34))
    add_box(bm, (0.12, 0.48, 0.18), (-0.25, seat_y + 0.10, 0.45))
    add_box(bm, (0.12, 0.48, 0.18), (0.25, seat_y + 0.10, 0.45))
    add_box(bm, (0.64, 0.11, 0.78), (0, seat_y + 0.32, 0.91), back_rot)
    frame = obj_from_bmesh("jb100_cockpit_seat_frame", bm, mat_frame)
    bevel_object(frame, 0.028, 2)
    cockpit_parts.append(frame)

    # Chunky crash padding: low cushion, back pad, headrest, and bolsters.
    bm = bmesh.new()
    add_box(bm, (0.56, 0.57, 0.14), (0, seat_y - 0.02, 0.52))
    add_box(bm, (0.54, 0.14, 0.66), (0, seat_y + 0.28, 0.91), back_rot)
    add_box(bm, (0.50, 0.17, 0.22), (0, seat_y + 0.41, 1.30), back_rot)
    for sx in (-1, 1):
        add_box(bm, (0.11, 0.50, 0.20), (sx * 0.30, seat_y, 0.57))
        add_box(bm, (0.10, 0.14, 0.54),
                (sx * 0.29, seat_y + 0.28, 0.91), back_rot)
    padding = obj_from_bmesh("jb100_cockpit_seat_padding", bm, mat_seat)
    bevel_object(padding, 0.045, 3)
    cockpit_parts.append(padding)

    # Four-point red harness with a compact mechanical buckle.
    bm = bmesh.new()
    add_beam(bm, (-0.17, seat_y + 0.38, 1.24),
             (-0.08, seat_y + 0.18, 0.63), 0.055, 0.025)
    add_beam(bm, (0.17, seat_y + 0.38, 1.24),
             (0.08, seat_y + 0.18, 0.63), 0.055, 0.025)
    add_beam(bm, (-0.29, seat_y - 0.03, 0.60),
             (-0.03, seat_y + 0.12, 0.63), 0.055, 0.025)
    add_beam(bm, (0.29, seat_y - 0.03, 0.60),
             (0.03, seat_y + 0.12, 0.63), 0.055, 0.025)
    add_box(bm, (0.12, 0.06, 0.10), (0, seat_y + 0.12, 0.63))
    harness = obj_from_bmesh("jb100_cockpit_harness", bm, mat_harness)
    bevel_object(harness, 0.012, 2)
    cockpit_parts.append(harness)

    # Oxygen bottles stay on the aft face of the seat, clear of the pilot.
    bm = bmesh.new()
    for tx in (-0.14, 0.14):
        add_cone(bm, 0.095, 0.095, 0.60,
                 (tx, seat_y + 0.49, 0.91), segs=14)
        add_cone(bm, 0.045, 0.028, 0.10,
                 (tx, seat_y + 0.49, 1.26), segs=10)
    tanks = obj_from_bmesh("jb100_cockpit_oxygen", bm, mat_tanks)
    cockpit_parts.append(tanks)

    # Curved dashboard shell: three faceted sections are readable from above
    # but leave the pilot's knees and canopy sight line unobstructed.
    bm = bmesh.new()
    add_box(bm, (0.54, 0.18, 0.43), (0, -0.82, 1.13))
    for sx in (-1, 1):
        wing_rot = Matrix.Rotation(math.radians(-sx * 14.0), 3, 'Z')
        add_box(bm, (0.43, 0.17, 0.37),
                (sx * 0.46, -0.73, 1.10), wing_rot)
        add_box(bm, (0.20, 0.29, 0.18),
                (sx * 0.72, -0.57, 0.98), wing_rot)
    add_box(bm, (1.44, 0.12, 0.11), (0, -0.70, 0.91))
    panel_shell = obj_from_bmesh("jb100_cockpit_instrument_panel", bm, mat_panel)
    bevel_object(panel_shell, 0.035, 2)
    cockpit_parts.append(panel_shell)

    # Three inset displays: NAV/radar, system status, weapons/targeting.
    bm = bmesh.new()
    add_box(bm, (0.32, 0.025, 0.24), (-0.39, -0.628, 1.16))
    nav_screen = obj_from_bmesh("jb100_display_nav", bm, mat_screen_green)
    bevel_object(nav_screen, 0.012, 2)
    cockpit_parts.append(nav_screen)

    bm = bmesh.new()
    add_box(bm, (0.32, 0.025, 0.24), (0, -0.716, 1.16))
    sys_screen = obj_from_bmesh("jb100_display_systems", bm, mat_screen_green)
    bevel_object(sys_screen, 0.012, 2)
    cockpit_parts.append(sys_screen)

    bm = bmesh.new()
    add_box(bm, (0.32, 0.025, 0.24), (0.39, -0.628, 1.16))
    weapon_screen = obj_from_bmesh("jb100_display_weapons", bm, mat_screen_amber)
    bevel_object(weapon_screen, 0.012, 2)
    cockpit_parts.append(weapon_screen)

    # Display graphics and chunky indicator bars (no text/UI dependency).
    bm = bmesh.new()
    for x in (-0.47, -0.39, -0.31):
        add_box(bm, (0.012, 0.012, 0.18), (x, -0.609, 1.16))
    add_box(bm, (0.26, 0.012, 0.012), (-0.39, -0.609, 1.16))
    for row in range(4):
        for col in range(3):
            h = 0.025 + 0.018 * ((row + col) % 3)
            add_box(bm, (0.045, 0.012, h),
                    (-0.09 + col * 0.09, -0.697, 1.08 + row * 0.055))
    green_marks = obj_from_bmesh("jb100_display_green_marks", bm,
                                 mat_indicator_green)
    cockpit_parts.append(green_marks)

    bm = bmesh.new()
    add_box(bm, (0.25, 0.012, 0.012), (0.39, -0.609, 1.16))
    add_box(bm, (0.012, 0.012, 0.18), (0.39, -0.609, 1.16))
    for x, z in ((0.31, 1.08), (0.47, 1.24), (0.45, 1.10)):
        add_box(bm, (0.028, 0.014, 0.028), (x, -0.605, z))
    amber_marks = obj_from_bmesh("jb100_display_amber_marks", bm,
                                 mat_indicator_amber)
    cockpit_parts.append(amber_marks)

    # Physical switch bank below displays and warning lamps on the wings.
    bm = bmesh.new()
    for x in (-0.52, -0.39, -0.26, -0.13, 0.0, 0.13, 0.26, 0.39, 0.52):
        add_box(bm, (0.055, 0.055, 0.055), (x, -0.635, 0.96))
    switches = obj_from_bmesh("jb100_cockpit_switch_bank", bm, mat_tanks)
    bevel_object(switches, 0.008, 1)
    cockpit_parts.append(switches)

    for name, sx, material in (
            ("left", -1, mat_indicator_red),
            ("right", 1, mat_indicator_amber)):
        bm = bmesh.new()
        for z in (1.00, 1.11, 1.22):
            add_sphere(bm, 0.035, (1.0, 0.45, 1.0),
                       (sx * 0.67, -0.545, z), segs=12, rings=6)
        lamps_panel = obj_from_bmesh(f"jb100_panel_lamps_{name}", bm, material)
        cockpit_parts.append(lamps_panel)

    # Dual thigh sticks. Left: thrust/translation/systems. Right:
    # pitch/roll/yaw/weapons. Both get a broad base and red thumb trigger.
    for name, sx in (("left", -1), ("right", 1)):
        bm = bmesh.new()
        add_cone(bm, 0.16, 0.13, 0.10, (sx * 0.49, -0.08, 0.37), segs=18)
        add_cone(bm, 0.055, 0.045, 0.49, (sx * 0.49, -0.10, 0.66), segs=14)
        add_sphere(bm, 0.09, (0.72, 1.18, 0.72),
                   (sx * 0.49, -0.12, 0.92), segs=16, rings=8)
        stick = obj_from_bmesh(f"jb100_control_stick_{name}", bm, mat_frame)
        bevel_object(stick, 0.012, 2)
        cockpit_parts.append(stick)
        bm = bmesh.new()
        add_sphere(bm, 0.032, (1.0, 0.7, 0.55),
                   (sx * 0.49, -0.18, 0.96), segs=12, rings=6)
        trigger = obj_from_bmesh(f"jb100_control_trigger_{name}", bm,
                                 mat_indicator_red)
        cockpit_parts.append(trigger)

    # Separate physical throttle, preserving the screenplay's pull action.
    bm = bmesh.new()
    add_box(bm, (0.20, 0.45, 0.14), (-0.77, 0.24, 0.43))
    throttle_base = obj_from_bmesh("jb100_throttle_quadrant", bm, mat_panel)
    bevel_object(throttle_base, 0.03, 2)
    cockpit_parts.append(throttle_base)
    bm = bmesh.new()
    add_box(bm, (0.035, 0.30, 0.025), (-0.77, 0.23, 0.505))
    add_beam(bm, (-0.77, 0.22, 0.50), (-0.77, 0.34, 0.78), 0.045)
    add_box(bm, (0.15, 0.10, 0.075), (-0.77, 0.35, 0.80))
    throttle = obj_from_bmesh("jb100_throttle_lever", bm, mat_harness)
    bevel_object(throttle, 0.016, 2)
    cockpit_parts.append(throttle)

    # Minimal side panels: port NavComp/comms and starboard emergency systems.
    for name, sx in (("navcomp", -1), ("emergency", 1)):
        side_rot = Matrix.Rotation(math.radians(sx * 9.0), 3, 'Y')
        bm = bmesh.new()
        add_box(bm, (0.12, 0.48, 0.28),
                (sx * 0.91, 0.03, 0.68), side_rot)
        side_panel = obj_from_bmesh(f"jb100_side_panel_{name}", bm, mat_panel)
        bevel_object(side_panel, 0.025, 2)
        cockpit_parts.append(side_panel)
        bm = bmesh.new()
        for row in range(3):
            for col in range(2):
                add_box(bm, (0.028, 0.052, 0.035),
                        (sx * 0.84, -0.10 + col * 0.14,
                         0.61 + row * 0.075))
        side_controls = obj_from_bmesh(f"jb100_side_controls_{name}", bm,
                                       mat_indicator_amber if sx < 0
                                       else mat_indicator_red)
        cockpit_parts.append(side_controls)

    # Senso-globes: four per side riding the hull's side profile;
    # sink shrinks toward the AFT so the rear globes protrude the most.
    bm = bmesh.new()
    for y, sink in GLOBES:
        half_w = dome_a * math.sqrt(max(0.0, 1 - (y / dome_b) ** 2))
        for sx in (-1, 1):
            x = sx * GLOBE_SPREAD * half_w
            add_sphere(bm, GLOBE_R, (1, 1, 0.9),
                       (x, y, deck_z(x, y) - sink), segs=16, rings=8)
    lamps = obj_from_bmesh("jb100_lamps", bm, mat_lamp)

    # Engine pods: SLIM bodies on the aft deck, splayed outward so the
    # vents point straight out and away; ring vent + red core + orange
    # emissive tip at each aft end. (No forward intakes; no antenna —
    # these ARE the side view's "boom".)
    pitch = Matrix.Rotation(math.radians(90), 3, 'X')
    pod_objs = []
    for sx in (-1, 1):
        px = sx * POD_X
        pz = deck_z(px, POD_Y) - 0.03
        yaw = Matrix.Rotation(math.radians(-sx * POD_YAW), 3, 'Z')
        centre = Vector((px, POD_Y, pz))
        bm = bmesh.new()
        res = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12,
                                        radius=1.0)
        for v in res["verts"]:
            co = Vector((v.co.x * POD_R, v.co.y * POD_L * 0.5,
                         v.co.z * POD_R))
            v.co = yaw @ co + centre
        pod = obj_from_bmesh(f"jb100_pod_{'l' if sx < 0 else 'r'}",
                             bm, mat_pod)
        pod_objs.append(pod)
        aft = centre + yaw @ Vector((0, POD_L * 0.5, 0))
        bm = bmesh.new()
        add_cone(bm, POD_R * 0.62, POD_R * 0.5, 0.1,
                 aft + yaw @ Vector((0, -0.03, 0)), rot=yaw @ pitch,
                 segs=16)                                      # red core
        burn = obj_from_bmesh(f"jb100_exhaust_{'l' if sx < 0 else 'r'}",
                              bm, mat_burn)
        pod_objs.append(burn)
        bm = bmesh.new()
        add_cone(bm, 0.086, 0.029, 0.35,
                 aft + yaw @ Vector((0, 0.2, 0)), rot=yaw @ pitch,
                 segs=10)                                      # orange tip
        tip = obj_from_bmesh(f"jb100_venttip_{'l' if sx < 0 else 'r'}",
                             bm, mat_lamp)
        pod_objs.append(tip)

    # Belly ring: 16 white discs embedded at the inner edge of the flat
    # bottom, a rotating thruster stub in each centre (rest: straight
    # down, tracking cooperatively)
    bm = bmesh.new()
    bmt = bmesh.new()
    for k in range(DISC_N):
        ang = 2 * math.pi * k / DISC_N
        dx, dy = DISC_RING_R * math.cos(ang), DISC_RING_R * math.sin(ang)
        add_cone(bm, DISC_R, DISC_R, 0.08, (dx, dy, 0.12), segs=18)
        add_cone(bmt, THRUSTER_R, THRUSTER_R * 0.55, 0.1,
                 (dx, dy, 0.07), segs=10)   # stub inside the recess
    discs = obj_from_bmesh("jb100_belly_discs", bm, mat_white)
    pod_objs.append(discs)
    thrusters = obj_from_bmesh("jb100_belly_thrusters", bmt, mat_pod)
    pod_objs.append(thrusters)

    # Frap-ray cannons: bodies LYING ALONG the hull slope at the front
    # corners, barrels protruding straight out past the rim, 3 evenly
    # spaced rings around each barrel
    cannon_parts = []
    for sx in (-1, 1):
        cx = sx * CANNON_X
        zb = deck_z(cx, CANNON_Y) + 0.07        # resting on the deck
        rim_y = -hull_b * math.sqrt(max(0.0, 1 - (cx / hull_a) ** 2))
        muzzle_y = rim_y - CANNON_OUT
        length = CANNON_Y - muzzle_y
        bm = bmesh.new()
        add_cone(bm, 0.065, 0.045, length,
                 (cx, CANNON_Y - length / 2, zb), rot=pitch, segs=12)
        for k in range(CANNON_RINGS):
            ry = CANNON_Y - length * (k + 1) / (CANNON_RINGS + 1.5)
            add_cone(bm, 0.1, 0.1, 0.07, (cx, ry, zb),
                     rot=pitch, segs=14)                           # ring
        add_cone(bm, 0.075, 0.075, 0.1, (cx, muzzle_y + 0.05, zb),
                 rot=pitch, segs=12)                               # muzzle
        # exhaust port: the L's short leg at the barrel rear, spun 90°
        # from down to point straight OUTBOARD (v16)
        side = Matrix.Rotation(math.radians(sx * 90.0), 3, 'Y')
        add_cone(bm, 0.055, 0.05, 0.24,
                 (cx + sx * 0.14, CANNON_Y + 0.04, zb),
                 rot=side, segs=10)
        centroid = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
        for v in bm.verts:                       # +20% about centroid
            v.co = centroid + (v.co - centroid) * 1.44  # 1.2 x 1.2 (v34)
        cannon = obj_from_bmesh(
            f"jb100_cannon_{'l' if sx < 0 else 'r'}", bm, mat_pod)
        cannon_parts.append(cannon)

    # Save the editable v38 source before producing the legacy single-node
    # interchange asset.  The bubble is intentionally hidden in this working
    # file so cockpit set-dressing remains unobstructed in viewport and renders.
    parts = [hull, bowl_bottom, canopy, *cockpit_parts, lamps,
             *cannon_parts, *pod_objs]
    for part in parts:
        part["jb100_build_version"] = BUILD_VERSION
        part["production_role"] = "hero_stand_in"
        part["pilot_included"] = False
    canopy.hide_set(True)
    canopy.hide_viewport = True
    canopy.hide_render = True
    canopy["working_visibility"] = "hidden_for_cockpit_build"
    scene = bpy.context.scene
    scene["asset_id"] = "prop_jb100_A"
    scene["asset_version"] = f"v{BUILD_VERSION}"
    scene["cockpit_pass"] = "minimal_one_pilot_attack_recon"
    scene["production_role"] = "hero_stand_in"
    scene["pilot_included"] = False
    working_blend = (args.working_blend if os.path.isabs(args.working_blend)
                     else os.path.join(os.getcwd(), args.working_blend))
    os.makedirs(os.path.dirname(working_blend), exist_ok=True)
    print(f"[build_jb100] Saving editable cockpit source {working_blend}")
    bpy.ops.wm.save_as_mainfile(filepath=working_blend)

    # Canonical GLB/USDC remain one mesh for existing scene scripts that look
    # up and transform prop_jb100_A directly.
    canopy.hide_set(False)
    canopy.hide_viewport = False
    canopy.hide_render = False
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = hull
    bpy.ops.object.join()
    ship = bpy.context.view_layer.objects.active
    ship.name = "prop_jb100_A"
    ship.data.name = "prop_jb100_A_mesh"
    ship["asset_version"] = f"v{BUILD_VERSION}"
    ship["cockpit"] = "one pilot; dual sticks; physical throttle; canopy"
    ship["production_role"] = "hero_stand_in"
    ship["pilot_included"] = False
    print(f"[build_jb100] joined: {len(ship.data.polygons)} polys, "
          f"{len(ship.material_slots)} materials")

    versioned_stem = (args.versioned_output
                      if os.path.isabs(args.versioned_output)
                      else os.path.join(os.getcwd(), args.versioned_output))
    os.makedirs(os.path.dirname(versioned_stem), exist_ok=True)
    export_stems = [out_stem]
    if os.path.normpath(versioned_stem) != os.path.normpath(out_stem):
        export_stems.append(versioned_stem)
    for stem in export_stems:
        glb = stem + ".glb"
        print(f"[build_jb100] Exporting {glb}")
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB',
                                  use_selection=False, export_extras=True)
        usdc = stem + ".usdc"
        print(f"[build_jb100] Exporting {usdc}")
        try:
            bpy.ops.wm.usd_export(filepath=usdc, export_animation=False,
                                  export_materials=True)
        except TypeError:
            bpy.ops.wm.usd_export(filepath=usdc)

    corners = [ship.matrix_world @ Vector(corner) for corner in ship.bound_box]
    bounds_min = [min(point[i] for point in corners) for i in range(3)]
    bounds_max = [max(point[i] for point in corners) for i in range(3)]
    dimensions = [bounds_max[i] - bounds_min[i] for i in range(3)]
    manifest = {
        "asset_id": "prop_jb100_A",
        "display_name": "JourneyBlaster 100 Hero Stand-In",
        "version": f"v{BUILD_VERSION}",
        "previous_version": "v37",
        "production_role": "hero_stand_in",
        "maturity": "approved_stand_in",
        "change_summary": (
            "Promoted the approved one-pilot cockpit build as the JB100 hero "
            "stand-in; pilot remains a separately cast scene actor."),
        "pilot_included": False,
        "canopy_included": True,
        "style": "simple smooth 1990s CGI; minimal analog attack cockpit",
        "files": {
            "blend": os.path.basename(working_blend),
            "glb": os.path.basename(versioned_stem) + ".glb",
            "usdc": os.path.basename(versioned_stem) + ".usdc",
            "canonical_glb": "../jb100.glb",
            "canonical_usdc": "../jb100.usdc",
        },
        "review": {
            "front_action": "review/jb100_v38_bubble_front_action.png",
            "back_action": "review/jb100_v38_bubble_back_action.png",
            "left_action": "review/jb100_v38_bubble_left_action.png",
            "right_action": "review/jb100_v38_bubble_right_action.png",
            "canopy_state": "visible_transparent",
            "pilot_included": False,
        },
        "evaluated_bounds": {
            "min": [round(value, 6) for value in bounds_min],
            "max": [round(value, 6) for value in bounds_max],
            "dimensions": [round(value, 6) for value in dimensions],
        },
        "orientation_standard": {
            "front_axis": "-Y",
            "rear_axis": "+Y",
            "left_axis": "-X",
            "right_axis": "+X",
            "up_axis": "+Z",
            "origin_policy": "hull center; lowest belly point at z=0",
        },
        "construction": {
            "root_node": "prop_jb100_A",
            "joined_export": True,
            "editable_named_parts": len(parts),
            "materials": sorted(slot.material.name for slot in ship.material_slots
                                if slot.material),
            "cockpit": {
                "crew": 1,
                "seat": "low reclining Barka predecessor with four-point harness",
                "controls": "dual thigh sticks plus separate physical throttle",
                "displays": 3,
            },
        },
    }
    manifest_path = versioned_stem + ".manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"[build_jb100] Wrote {manifest_path}")
    print("[build_jb100] Done.")


if __name__ == "__main__":
    main()
