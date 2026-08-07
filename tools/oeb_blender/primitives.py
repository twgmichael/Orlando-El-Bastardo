"""Shared primitive-geometry helpers for OEB headless Blender builders.

Extracted from tools/primitive_asset_builder.py so tools/blueprint_interpreter.py
(and any future builder) can reuse the same primitive-creation code instead
of duplicating it -- see docs/planning/REVIEW-AUDIT.md section 13 item 1.
"""

import math

import bpy


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
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


def hemisphere(name, location, radius, mat, segments=32, rings=8):
    """Create a capped +Z hemisphere for generic half/hemisphere intent."""
    vertices = [(0.0, 0.0, radius)]
    for ring_index in range(1, rings + 1):
        angle = (math.pi / 2.0) * (ring_index / rings)
        ring_radius = radius * math.sin(angle)
        z = radius * math.cos(angle)
        for segment_index in range(segments):
            segment_angle = (2.0 * math.pi) * (segment_index / segments)
            vertices.append((
                ring_radius * math.cos(segment_angle),
                ring_radius * math.sin(segment_angle),
                z,
            ))

    faces = []
    first_ring = 1
    for segment_index in range(segments):
        next_segment = (segment_index + 1) % segments
        faces.append((0, first_ring + segment_index, first_ring + next_segment))
    for ring_index in range(rings - 1):
        current_ring = 1 + (ring_index * segments)
        next_ring = current_ring + segments
        for segment_index in range(segments):
            next_segment = (segment_index + 1) % segments
            faces.append((
                current_ring + segment_index,
                next_ring + segment_index,
                next_ring + next_segment,
                current_ring + next_segment,
            ))
    bottom_ring = 1 + ((rings - 1) * segments)
    faces.append(tuple(bottom_ring + segment_index for segment_index in reversed(range(segments))))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
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
