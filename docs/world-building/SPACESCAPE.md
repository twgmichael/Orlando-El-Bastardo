# Spacescape / Starfield Environment

Deep-space environment for JourneyBlaster and other space-set sequences.

## Origin

The OEB universe was rendered in 1995 using a large UV sphere with inverted
normals and a starfield texture painted on the inside. A single strong light
source represented the system star. All ships and stations were placed inside
the sphere. It was practical and produced a convincing read.

Reference: `docs/local/reference/Scene One NTSC.mp4`

Visible in the reference:
- Deep black space, star dots of varying brightness and size
- Bright yellow-orange sun with a soft volumetric halo/glow
- Blue-green planet with atmospheric rim glow
- Subtle lens flare artifacts on the sun
- Atmospheric brightening around celestial bodies

## Options Evaluated

### 1. World Shader (procedural, no geometry)

Blender's World node tree renders as the infinite background directly.

Node chain:
```
Texture Coordinate (Generated)
  → Noise Texture (Scale 800–1200, Detail 16, Roughness 0.8)
  → Color Ramp (hard cutoff at ~0.98 for sparse white dots)
  → Emission (strength 2–4)
  → World Output (Background)
```

Pros:
- No geometry, no UV seam, no camera escape risk
- Stars rotate with a Mapping node — keyframeable or locked per shot
- Works identically in EEVEE and Cycles
- Fully controllable from Python (`world.node_tree`)

Cons:
- Slightly more node setup than a texture file

### 2. Updated 1995 Globe (large UV sphere, inverted normals)

Direct modern equivalent of the original approach:
```python
bpy.ops.mesh.primitive_uv_sphere_add(radius=1500, segments=64, ring_count=32)
# flip normals in Edit Mode
# apply emission material with Noise → Color Ramp star chain
```

Pros:
- Identical mental model to the 1995 workflow
- Easy to understand and inspect in the viewport

Cons:
- Camera can exit the sphere if it moves far
- UV seam visible at some angles
- Heavier than the World shader for identical visual output

### 3. HDRI

Drop a high-resolution space HDRI as the World background image.

Pros:
- Zero node setup, photorealistic result
- Works immediately

Cons:
- No procedural control over star density or color
- Locked composition — stars don't move with the scene
- Requires sourcing a suitable file

## Decision

**Star sphere (1995 method updated) + emissive sun sphere + EEVEE Bloom.**

World Shader was the original recommendation, but confirmed non-functional in
Blender 5.1.2 / EEVEE Next: the renderer silently ignores complex World node
trees. Byte-identical encode output on two attempts — zero pixels changed.
`world.use_nodes` carries a Blender 6.0 deprecation warning; in EEVEE Next the
property has no effect on which node tree the renderer evaluates.

Fallback to the sphere approach was confirmed working: I-frame size jumped from
5 KB to 34 KB (encoder detected fine detail — stars present).

Rationale for sphere approach:
- Object materials always evaluate in EEVEE regardless of world settings
- Identical mental model to the 1995 workflow — easy to understand and modify
- Full Python control: radius, noise scale, star density all editable constants
- Sun sphere + Bloom still applies on top for the halo/glow effect

## Implementation Spec

### Star sphere

```python
# ── star sphere ───────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=800, segments=64, ring_count=32)
star_sphere = bpy.context.active_object
star_sphere.name = "env_star_sphere"
bpy.context.view_layer.objects.active = star_sphere
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.flip_normals()       # faces point inward; camera stays inside
bpy.ops.object.mode_set(mode='OBJECT')

star_mat = bpy.data.materials.new("mat_env_stars")
star_mat.use_nodes = True
snt = star_mat.node_tree
for n in list(snt.nodes):
    snt.nodes.remove(n)

s_out   = snt.nodes.new("ShaderNodeOutputMaterial")
s_emit  = snt.nodes.new("ShaderNodeEmission")
s_ramp  = snt.nodes.new("ShaderNodeValToRGB")
s_noise = snt.nodes.new("ShaderNodeTexNoise")
s_coord = snt.nodes.new("ShaderNodeTexCoord")

s_noise.inputs["Scale"].default_value     = 300.0   # star dot size
s_noise.inputs["Detail"].default_value    = 8.0
s_noise.inputs["Roughness"].default_value = 0.6

s_ramp.color_ramp.interpolation        = 'CONSTANT'
s_ramp.color_ramp.elements[0].position = 0.0
s_ramp.color_ramp.elements[0].color    = (0.003, 0.003, 0.006, 1)  # space
s_ramp.color_ramp.elements[1].position = 0.88    # density threshold
s_ramp.color_ramp.elements[1].color    = (1.0, 1.0, 1.0, 1)

s_emit.inputs["Strength"].default_value = 2.0

snt.links.new(s_coord.outputs["UV"],      s_noise.inputs["Vector"])
snt.links.new(s_noise.outputs["Fac"],     s_ramp.inputs["Fac"])
snt.links.new(s_ramp.outputs["Color"],    s_emit.inputs["Color"])
snt.links.new(s_emit.outputs["Emission"], s_out.inputs["Surface"])
star_sphere.data.materials.append(star_mat)

# World: pure black (sphere provides the stars)
world = bpy.data.worlds.new("space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)
scene.world = world
```

### Sun disc

```python
# ── sun disc (emissive sphere + EEVEE bloom = halo) ───────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=18, location=(300, 500, 250),
                                      segments=32, ring_count=16)
sun_obj = bpy.context.active_object
sun_obj.name = "env_sun"
sun_mat = bpy.data.materials.new("mat_env_sun")
sun_mat.use_nodes = True
for n in list(sun_mat.node_tree.nodes):
    sun_mat.node_tree.nodes.remove(n)
sun_emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
sun_out  = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
sun_emit.inputs["Color"].default_value    = (1.0, 0.78, 0.30, 1)
sun_emit.inputs["Strength"].default_value = 120.0
sun_mat.node_tree.links.new(sun_emit.outputs["Emission"], sun_out.inputs["Surface"])
sun_obj.data.materials.append(sun_mat)

if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_bloom'):
    scene.eevee.use_bloom       = True
    scene.eevee.bloom_threshold = 0.6
    scene.eevee.bloom_intensity = 0.8
    scene.eevee.bloom_radius    = 6.0
```

### Usage in render scripts

Add both blocks after engine selection, before camera/lighting setup. The scene
key and fill lights (SUN lamps) remain separate so shot lighting is independent
of the environment.

## Planet Spec (when needed)

UV sphere, radius 6–10, placed 1200+ units from origin.

Material mix:
- Principled BSDF base for surface (procedural noise for land/ocean color)
- Layer Weight (Fresnel) → Emission node for atmospheric rim glow
- Atmosphere color: blue-green matching the reference clip

Planet is an asset (`env_planet_A`), not part of `setup_space_env()`, so its
position can be art-directed per shot without changing the env function.

## Tuning Reference

| Parameter | Conservative | Current spec | Pushed |
|---|---|---|---|
| Noise Scale | 600 | 1000 | 1400 |
| Star cutoff | 0.97 | 0.985 | 0.993 |
| Star brightness | 1.5 | 3.0 | 6.0 |
| Sun emission | 60 | 120 | 200 |
| Bloom threshold | 0.8 | 0.6 | 0.4 |
| Bloom intensity | 0.4 | 0.8 | 1.2 |

## Status

- Decision locked: 2026-07-13
- `setup_space_env()` spec written; not yet extracted into a shared module
- First integration target: `tmp_jb100_flyby.py` and `tmp_jb100_flyaway.py`
- Planet asset not yet built
