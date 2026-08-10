---
title: Spacescape
created: 2026-07-13T16:07:33-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: design_record
production_area: locations
department: art
status: active
canonical: true
canonical_for: spacescape_environment
wiki: true
wiki_group: Design
wiki_page: Spacescape
wiki_order: 50
---
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

**Live in `tools/oeb_blender/space_env.py`'s `setup_space_env(scene, **kwargs)`**
since 2026-08-09 (see Status) -- every constant below is a keyword argument
there, not a value to copy by hand. The values here match that function's
current defaults exactly; if they ever drift apart, the code is authoritative.

### Star sphere

```python
# ── star sphere ───────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=900, segments=64, ring_count=32)
star_sphere = bpy.context.active_object
star_sphere.name = "env_star_sphere"

star_mat = bpy.data.materials.new("mat_env_stars")
star_mat.use_nodes = True
# Faces point outward (default winding); disabling backface culling makes
# the material visible from inside the sphere too, without an Edit Mode
# mode_set() call (avoids a context dependency in headless/background
# Blender that flip_normals() needs).
star_mat.use_backface_culling = False
snt = star_mat.node_tree
for n in list(snt.nodes):
    snt.nodes.remove(n)

s_out   = snt.nodes.new("ShaderNodeOutputMaterial")
s_emit  = snt.nodes.new("ShaderNodeEmission")
s_ramp  = snt.nodes.new("ShaderNodeValToRGB")
s_noise = snt.nodes.new("ShaderNodeTexNoise")
s_coord = snt.nodes.new("ShaderNodeTexCoord")

s_noise.inputs["Scale"].default_value     = 360.0   # star dot size
s_noise.inputs["Detail"].default_value    = 10.0
s_noise.inputs["Roughness"].default_value = 0.62

s_ramp.color_ramp.interpolation        = 'CONSTANT'
s_ramp.color_ramp.elements[0].position = 0.0
s_ramp.color_ramp.elements[0].color    = (0.0, 0.0, 0.0, 1)   # true black, see note below
s_ramp.color_ramp.elements[1].position = 0.70    # density threshold, see note below
s_ramp.color_ramp.elements[1].color    = (1.0, 1.0, 1.0, 1)

s_emit.inputs["Strength"].default_value = 8.0

snt.links.new(s_coord.outputs["Generated"], s_noise.inputs["Vector"])
snt.links.new(s_noise.outputs["Fac"],       s_ramp.inputs["Fac"])
snt.links.new(s_ramp.outputs["Color"],      s_emit.inputs["Color"])
snt.links.new(s_emit.outputs["Emission"],   s_out.inputs["Surface"])
star_sphere.data.materials.append(star_mat)

# World: pure black (sphere provides the stars)
world = bpy.data.worlds.new("space")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1)
scene.world = world
```

**Two values above were changed from the original spec after live-rendered
verification (2026-08-09, Blender 5.1.2, EEVEE and Cycles both checked):**

- **Density threshold 0.88 → 0.70.** The original 0.88 (and the 0.775 an
  earlier draft of this doc had) produced *zero* visible stars: this noise
  texture's Fac output at Detail=10 rarely exceeds ~0.5, so a CONSTANT-ramp
  cutoff that high never triggers, regardless of engine, resolution, or
  sample count. Swept the actual cutoff-vs-visible-pixel curve on a control
  plane with identical noise params: 0.66 → 7.6% bright, 0.70 → 0.53%,
  0.72 → 0.08%. 0.70 is confirmed to render a real, visibly sparse starfield
  on the actual star sphere, not just the control plane.
- **Space color `(0.003, 0.003, 0.006)` → pure black `(0.0, 0.0, 0.0)`.**
  User feedback against real approved 1999 reference renders: that faint
  off-black, multiplied through the emission node at strength 8, rendered
  as a visible blue/purple cast instead of the reference's true black.

### Sun disc

```python
# ── sun disc (emissive sphere + EEVEE bloom = halo) ───────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=22, location=(-260, -520, 250),
                                      segments=32, ring_count=16)
sun_obj = bpy.context.active_object
sun_obj.name = "env_sun"
sun_mat = bpy.data.materials.new("mat_env_sun")
sun_mat.use_nodes = True
for n in list(sun_mat.node_tree.nodes):
    sun_mat.node_tree.nodes.remove(n)
sun_emit = sun_mat.node_tree.nodes.new("ShaderNodeEmission")
sun_out  = sun_mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
sun_emit.inputs["Color"].default_value    = (1.0, 0.74, 0.30, 1)
sun_emit.inputs["Strength"].default_value = 120.0
sun_mat.node_tree.links.new(sun_emit.outputs["Emission"], sun_out.inputs["Surface"])
sun_obj.data.materials.append(sun_mat)

if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'use_bloom'):
    scene.eevee.use_bloom       = True
    scene.eevee.bloom_threshold = 0.55
    scene.eevee.bloom_intensity = 0.8
    scene.eevee.bloom_radius    = 6.0
```

`use_bloom` doesn't exist at all on `scene.eevee` in Blender 5.1.2 (this
guard's `hasattr` check is load-bearing, not defensive boilerplate) -- the
sun currently renders as a hard-edged flat disc, no halo, until that
Blender-version gap is separately addressed.

### Lighting caveat: this environment provides no actual light source

`env_sun` above is a purely emissive **mesh** (self-illuminating only), not
a Blender Light -- it does not illuminate anything else in the scene. With
a fully black world and no added light, every other object (ships, actors,
asteroids, props) renders pure black and invisible, confirmed live
2026-08-09 rendering the asteroid-field scenes. Callers must add at least
one real light after calling `setup_space_env()`. `tools/render_blend.py`'s
`setup_lighting()` does this for the review-render path: one SUN lamp aimed
from `env_sun`'s direction, plus a second soft SUN lamp aimed from the
camera's direction (a single hard light with zero ambient only lights
whichever face happens to align with it, which can leave a prop's
camera-facing side dark purely because of how it happens to be rotated).

### Usage in render scripts

Add both blocks after engine selection, before camera/lighting setup, then
add at least one real light per the caveat above. The scene key and fill
lights (SUN lamps) remain separate so shot lighting is independent of the
environment.

## Planet Spec (when needed)

UV sphere, radius 6–10, placed 1200+ units from origin.

Material mix:
- Principled BSDF base for surface (procedural noise for land/ocean color)
- Layer Weight (Fresnel) → Emission node for atmospheric rim glow
- Atmosphere color: blue-green matching the reference clip

Planet is an asset (`env_planet_A`), not part of `setup_space_env()`, so its
position can be art-directed per shot without changing the env function.

## Tuning Reference

This table's previous Conservative/Current-spec/Pushed values were never
live-rendered before 2026-08-09 and turned out not to match either the
Implementation Spec code block above or any working render script -- the
old "Current spec" cutoff (0.985) is even further into the "renders zero
stars" range than the 0.88/0.775 already found broken (see note above the
star sphere code block). Replaced with only what's actually been rendered
and confirmed; no Conservative/Pushed alternatives have been tried yet, so
none are listed rather than inventing untested numbers.

| Parameter | Shipped default (live-verified 2026-08-09) |
|---|---|
| Noise Scale | 360 |
| Star cutoff | 0.70 |
| Star brightness | 8.0 |
| Sun emission | 120 |
| Bloom threshold | 0.55 (no-op in this Blender version, see caveat) |
| Bloom intensity | 0.8 (no-op in this Blender version, see caveat) |

## Status

- Decision locked: 2026-07-13
- `setup_space_env()` extracted to `tools/oeb_blender/space_env.py`
  (2026-08-09) and wired into the deterministic pipeline: `tools/
  export_blender.py` calls it when a SceneSpec's `set.environment` is
  `"deep_space"`; `data/resolver_map.json`'s `deep_space` and
  `asteroid_field` locations set that field.
- Live-verified end-to-end 2026-08-09 against the real JourneyBlaster
  teaser script: true-black starfield, lit sun disc, lit asteroid/actor/
  ship placeholders, all 7 scenes rendered.
- Two spec values fixed after that verification (star cutoff, space
  color) -- see notes above the star sphere code block. Bloom does not
  currently work at all in this project's Blender 5.1.2 (no `use_bloom`
  attribute); sun renders as a flat disc, no halo.
- Planet asset not yet built; NASA Blue Marble Earth texture pulled to
  `assets/textures/planets/earth/` (2026-08-09) as a future source.
