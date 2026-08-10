#!/usr/bin/env python3
"""Build Starbase 86's 500-meter action-orbit review animation.

The camera makes one 360-degree orbit at a constant 500-meter distance from
an Empty placed on the station's center column.  A Track To constraint keeps
that point in the exact middle of the frame for the entire move.

Run from the repository root:
  blender --background --factory-startup \
    --python tools/build_starbase_86_action_orbit.py
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "assets/locations/starbase_86_v1.1.0/starbase_86_v1.1.0.glb"
BLEND_PATH = ROOT / "scene_versions/starbase_86_action_orbit_500m_v002.blend"
PREVIEW_DIR = ROOT / "out/starbase_86_action_orbit_500m_v002_preview"

FPS = 30
FRAME_START = 1
FRAME_END = 360
ORBIT_KEYFRAME_END = FRAME_END + 1
CAMERA_DISTANCE_METERS = 500.0
CAMERA_ELEVATION_DEGREES = 12.0
START_AZIMUTH_DEGREES = -55.0
TARGET_XY = (0.0, 0.0)


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


def import_asset() -> bpy.types.Object:
    if not ASSET_PATH.exists():
        raise FileNotFoundError(f"Starbase hero asset not found: {ASSET_PATH}")
    bpy.ops.import_scene.gltf(filepath=str(ASSET_PATH))
    root = bpy.data.objects.get("prop_starbase_86_A")
    if root is None:
        raise RuntimeError("Imported asset is missing root node prop_starbase_86_A")
    for obj in bpy.context.scene.objects:
        if obj.animation_data:
            obj.animation_data_clear()
    return root


def mesh_bounds() -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    found = False
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        found = True
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
    if not found:
        raise RuntimeError("Starbase asset contains no mesh geometry")
    return minimum, maximum


def configure_scene(scene: bpy.types.Scene) -> None:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = False
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 48
        if hasattr(scene.eevee, "use_bloom"):
            scene.eevee.use_bloom = False
        if hasattr(scene.eevee, "use_motion_blur"):
            scene.eevee.use_motion_blur = False
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass


def add_space_background(scene: bpy.types.Scene) -> None:
    world = bpy.data.worlds.new("starbase_orbit_world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        background.inputs["Strength"].default_value = 0.0
    scene.world = world

    bpy.ops.mesh.primitive_uv_sphere_add(radius=1800.0, segments=64, ring_count=32)
    sphere = bpy.context.object
    # render_blend.py recognizes this name and preserves the scene lighting.
    sphere.name = "env_star_sphere"
    sphere.visible_shadow = False

    material = bpy.data.materials.new("starbase_orbit_stars")
    material.use_nodes = True
    material.use_backface_culling = False
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise = nodes.new("ShaderNodeTexNoise")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 300.0
    noise.inputs["Detail"].default_value = 2.5
    noise.inputs["Roughness"].default_value = 0.6
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.color_ramp.elements[1].position = 0.735
    ramp.color_ramp.elements[1].color = (0.72, 0.77, 0.86, 1.0)
    emission.inputs["Strength"].default_value = 2.8
    material.node_tree.links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    material.node_tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    material.node_tree.links.new(ramp.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    sphere.data.materials.append(material)


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_lighting(scene: bpy.types.Scene, center: Vector, radius: float) -> None:
    sun_data = bpy.data.lights.new("orbit_sun", type="SUN")
    sun_data.energy = 2.3
    sun_data.color = (0.93, 0.96, 1.0)
    sun = bpy.data.objects.new("orbit_sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(45.0), 0.0, math.radians(35.0))

    key_data = bpy.data.lights.new("orbit_key", type="AREA")
    key_data.energy = max(350.0, radius * radius * 60.0)
    key_data.size = max(3.0, radius * 1.6)
    key_data.color = (0.94, 0.97, 1.0)
    key = bpy.data.objects.new("orbit_key", key_data)
    scene.collection.objects.link(key)
    key.location = center + Vector((radius * 1.4, -radius * 1.8, radius * 1.5))
    point_at(key, center)

    fill_data = bpy.data.lights.new("orbit_fill", type="AREA")
    fill_data.energy = max(80.0, radius * radius * 18.0)
    fill_data.size = max(4.0, radius * 2.2)
    fill_data.color = (0.72, 0.79, 0.94)
    fill = bpy.data.objects.new("orbit_fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = center + Vector((-radius * 1.6, radius * 1.5, radius * 1.1))
    point_at(fill, center)


def add_orbit_camera(scene: bpy.types.Scene, target_z: float) -> tuple[bpy.types.Object, bpy.types.Object]:
    target = bpy.data.objects.new("Starbase_86_Center_Column_Target", None)
    target.empty_display_type = "SPHERE"
    target.empty_display_size = 4.0
    target.location = (TARGET_XY[0], TARGET_XY[1], target_z)
    target["framing_contract"] = "center column locked to frame center"
    scene.collection.objects.link(target)

    rig = bpy.data.objects.new("Starbase_86_500m_Orbit_Rig", None)
    rig.location = target.location
    rig.rotation_mode = "XYZ"
    scene.collection.objects.link(rig)

    camera_data = bpy.data.cameras.new("Starbase_86_Action_Orbit_Camera")
    camera_data.lens = 42.0
    camera_data.sensor_width = 36.0
    camera_data.clip_start = 1.0
    camera_data.clip_end = 5000.0
    camera = bpy.data.objects.new("Starbase_86_Action_Orbit_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.parent = rig

    elevation = math.radians(CAMERA_ELEVATION_DEGREES)
    horizontal_radius = CAMERA_DISTANCE_METERS * math.cos(elevation)
    vertical_offset = CAMERA_DISTANCE_METERS * math.sin(elevation)
    camera.location = (horizontal_radius, 0.0, vertical_offset)

    tracking = camera.constraints.new(type="TRACK_TO")
    tracking.name = "Center_Column_Frame_Lock"
    tracking.target = target
    tracking.track_axis = "TRACK_NEGATIVE_Z"
    tracking.up_axis = "UP_Y"
    camera["distance_meters"] = CAMERA_DISTANCE_METERS
    camera["elevation_degrees"] = CAMERA_ELEVATION_DEGREES
    camera["target_object"] = target.name

    # Blender 5.x stores curves in slotted Actions rather than action.fcurves.
    # Setting the insertion preference works across both old and new Actions.
    edit_preferences = bpy.context.preferences.edit
    previous_interpolation = edit_preferences.keyframe_new_interpolation_type
    edit_preferences.keyframe_new_interpolation_type = "LINEAR"
    try:
        rig.rotation_euler.z = math.radians(START_AZIMUTH_DEGREES)
        rig.keyframe_insert(data_path="rotation_euler", index=2, frame=FRAME_START)
        rig.rotation_euler.z = math.radians(START_AZIMUTH_DEGREES + 360.0)
        rig.keyframe_insert(data_path="rotation_euler", index=2, frame=ORBIT_KEYFRAME_END)
    finally:
        edit_preferences.keyframe_new_interpolation_type = previous_interpolation

    scene.camera = camera
    marker = scene.timeline_markers.new("Starbase_86_Action_Orbit", frame=FRAME_START)
    marker.camera = camera
    return camera, target


def render_previews(scene: bpy.types.Scene) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    old_x = scene.render.resolution_x
    old_y = scene.render.resolution_y
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    for frame in (1, 91, 181, 271):
        scene.frame_set(frame)
        scene.render.filepath = str(PREVIEW_DIR / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    scene.render.resolution_x = old_x
    scene.render.resolution_y = old_y
    scene.frame_set(FRAME_START)


def main() -> None:
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene)
    root = import_asset()
    minimum, maximum = mesh_bounds()
    target_z = (minimum.z + maximum.z) * 0.5
    center = (minimum + maximum) * 0.5
    radius = max((maximum - minimum).length * 0.5, 1.0)
    add_space_background(scene)
    add_lighting(scene, center, radius)
    camera, target = add_orbit_camera(scene, target_z)

    scene["asset_id"] = "prop_starbase_86_A"
    scene["asset_version"] = "1.1.0"
    scene["camera_distance_meters"] = CAMERA_DISTANCE_METERS
    scene["center_column_target"] = tuple(target.location)
    root["orbit_review_scene"] = True

    scene.frame_set(FRAME_START)
    bpy.context.view_layer.update()
    measured_distance = (camera.matrix_world.translation - target.matrix_world.translation).length
    print(f"[starbase86-orbit] target: {tuple(round(v, 3) for v in target.location)}")
    print(f"[starbase86-orbit] camera distance: {measured_distance:.3f} m")
    print(f"[starbase86-orbit] duration: {FRAME_END / FPS:.2f} s at {FPS} fps")

    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    render_previews(scene)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print(f"[starbase86-orbit] blend: {BLEND_PATH}")
    print(f"[starbase86-orbit] previews: {PREVIEW_DIR}")


if __name__ == "__main__":
    main()
