"""Shared deep-space environment setup for OEB headless Blender builders.

Extracted from tools/JB100-pirate-escape.py's setup_space() -- the
implementation that actually matches the locked decision in
docs/world-building/SPACESCAPE.md (star sphere with normals effectively
flipped via use_backface_culling=False, emissive sun sphere, EEVEE
Bloom for the halo). tools/jb100_hyberspace_swarm_draft.py's inline
version predates that decision (no sun sphere, no bloom, hide_render=True
so it never actually rendered, only previewed) and was not used as a
source here.

Per SPACESCAPE.md's "Usage in render scripts" note, this deliberately
does NOT create scene key/fill/rim lights -- those stay per-shot and
independent of the environment. Call this after engine selection,
before camera/lighting setup, then add shot lighting separately.

star_density_cutoff default overridden from the source files' 0.775/
0.88 to 0.70 -- live-rendered verification (2026-08-09, Blender 5.1.2,
both EEVEE and Cycles) found 0.775 produces ZERO visible stars: the
noise texture's Fac output at Detail=10 rarely exceeds ~0.5, so a
CONSTANT-ramp cutoff that high never triggers, regardless of engine or
sample count. Swept the actual cutoff/visible-pixel curve on a control
plane (same noise params): 0.66 -> 7.6% bright, 0.70 -> 0.53%, 0.72 ->
0.08%. Confirmed 0.70 renders a real, visibly sparse starfield on the
actual star sphere, not just the control plane -- unlike the previous
default, which never rendered any stars at all no matter the resolution
or scene it was used in.

star_space_color also overridden from the source files' (0.002, 0.002,
0.006) to pure black -- user feedback 2026-08-09 against real approved
1999 reference renders: that faint off-black, multiplied through the
emission node at star_emission_strength=8, rendered as a visible
blue/purple cast instead of the reference's true black. Confirmed by
re-render: background reads as flat (0,0,0) now.
"""

import bpy


def setup_space_env(
    scene,
    *,
    star_sphere_radius=900.0,
    star_noise_scale=360.0,
    star_noise_detail=10.0,
    star_noise_roughness=0.62,
    star_density_cutoff=0.70,
    star_space_color=(0.0, 0.0, 0.0, 1.0),
    star_emission_strength=8.0,
    sun_radius=22.0,
    sun_location=(-260.0, -520.0, 250.0),
    sun_color=(1.0, 0.74, 0.28, 1.0),
    sun_emission_strength=120.0,
    bloom_threshold=0.55,
    bloom_intensity=0.8,
    bloom_radius=6.0,
):
    """Build the deep-space world + star sphere + sun disc + bloom for
    *scene*, per docs/world-building/SPACESCAPE.md's locked decision.
    Every tunable in that doc's "Tuning Reference" table is a keyword
    argument here, defaulted to tools/JB100-pirate-escape.py's proven
    values, so a caller can art-direct one shot without touching this
    function.

    Returns (star_sphere_obj, sun_obj).
    """
    world = bpy.data.worlds.new("space")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs[1].default_value = 0.0
    scene.world = world

    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=star_sphere_radius, segments=64, ring_count=32)
    star_sphere = bpy.context.active_object
    star_sphere.name = "env_star_sphere"
    star_sphere.visible_shadow = False

    star_mat = bpy.data.materials.new("mat_env_stars")
    star_mat.use_nodes = True
    # Faces point outward (default winding); rather than entering Edit
    # Mode to flip normals, disabling backface culling makes the
    # material visible from inside the sphere too -- same visual
    # result, no mode_set() context dependency in headless/background
    # Blender.
    star_mat.use_backface_culling = False
    snt = star_mat.node_tree
    for node in list(snt.nodes):
        snt.nodes.remove(node)

    s_out = snt.nodes.new("ShaderNodeOutputMaterial")
    s_emit = snt.nodes.new("ShaderNodeEmission")
    s_ramp = snt.nodes.new("ShaderNodeValToRGB")
    s_noise = snt.nodes.new("ShaderNodeTexNoise")
    s_coord = snt.nodes.new("ShaderNodeTexCoord")

    s_noise.inputs["Scale"].default_value = star_noise_scale
    s_noise.inputs["Detail"].default_value = star_noise_detail
    s_noise.inputs["Roughness"].default_value = star_noise_roughness

    s_ramp.color_ramp.interpolation = "CONSTANT"
    s_ramp.color_ramp.elements[0].position = 0.0
    s_ramp.color_ramp.elements[0].color = star_space_color
    s_ramp.color_ramp.elements[1].position = star_density_cutoff
    s_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    s_emit.inputs["Strength"].default_value = star_emission_strength

    snt.links.new(s_coord.outputs["Generated"], s_noise.inputs["Vector"])
    snt.links.new(s_noise.outputs["Fac"], s_ramp.inputs["Fac"])
    snt.links.new(s_ramp.outputs["Color"], s_emit.inputs["Color"])
    snt.links.new(s_emit.outputs["Emission"], s_out.inputs["Surface"])
    star_sphere.data.materials.append(star_mat)

    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=sun_radius, location=sun_location, segments=32, ring_count=16)
    sun_obj = bpy.context.active_object
    sun_obj.name = "env_sun"
    sun_mat = bpy.data.materials.new("mat_env_sun")
    sun_mat.use_nodes = True
    for node in list(sun_mat.node_tree.nodes):
        sun_mat.node_tree.nodes.remove(node)
    sun_emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
    sun_out = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    sun_emit.inputs["Color"].default_value = sun_color
    sun_emit.inputs["Strength"].default_value = sun_emission_strength
    sun_mat.node_tree.links.new(sun_emit.outputs["Emission"], sun_out.inputs["Surface"])
    sun_obj.data.materials.append(sun_mat)

    if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_bloom"):
        scene.eevee.use_bloom = True
        scene.eevee.bloom_threshold = bloom_threshold
        scene.eevee.bloom_intensity = bloom_intensity
        scene.eevee.bloom_radius = bloom_radius

    return star_sphere, sun_obj
