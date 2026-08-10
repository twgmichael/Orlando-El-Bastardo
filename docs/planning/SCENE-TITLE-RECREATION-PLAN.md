---
title: OEB Scene Title Recreation Plan
created: 2026-08-04T18:58:09-04:00
updated: 2026-08-09T23:02:42-04:00
doc_type: plan
production_area: animation
department: animation
status: draft
canonical: false
wiki: true
wiki_group: Planning
---
# OEB Scene Title Recreation Plan

## Purpose

Recreate the title scene from the original 60-second *Orlando El Bastardo*
teaser as a single continuous Blender shot, using the canonical JB100 and OEB
Logo assets already present in the project.

Reference video (local-only, not tracked in this repo — same convention as
`docs/world-building/SPACESCAPE.md`'s reference clip):

`docs/local/reference/Scene Title NTSC.mp4`

The reference is a 6.433-second, 648 x 486, 4:3 progressive H.264 clip with no
audio. It plays at approximately 30 fps. The recreation should use 29.97 fps
and 193 frames to produce a normalized NTSC-timed result.

## Scene analysis

The scene is one continuous shot with three linked movements:

1. The camera orbits from an almost edge-on view of the logo to its front.
2. The JB100 makes a close foreground dive, loops offscreen, and then crosses
   the completed logo from left to right.
3. The camera accelerates through the title toward a central golden flare,
   ending in a full white-out.

There is no edit between these movements. The logo should remain static in
world space; the opening reveal should be produced by the camera orbit. This
will naturally reproduce the changing ring orientation, text extrusion,
starfield parallax, and perspective seen in the source.

## Required assets

### OEB Logo

Canonical source:

`Orlando-El-Bastardo.src/assets/OEB logo/oeblogo_3d_v1.0.8/oeblogo_3d_v1.0.8.blend`

Append only the seven editable geometry objects:

- `OEB_Globe`
- `Orbit_Ring_1`
- `Orbit_Ring_2`
- `Orbit_Ring_3`
- `Orlando_3D`
- `El_3D`
- `Bastardo_3D`

Do not import the logo asset's camera, world, or studio lights. Preserve the
canonical asset unchanged; use scene-local material copies if look matching
requires darker rings or globe treatment.

### JB100

Canonical source:

`Orlando-El-Bastardo.src/assets/ships/jb100.glb`

Import `prop_jb100_A`. Its nose points along local `-Y`; the engines are on
local `+Y`. Use a root scale between `0.65` and `0.75` relative to the native
logo scale, with the exact value tuned against the reference silhouettes.

### Pilot

Source:

`Orlando-El-Bastardo.src/assets/characters/oeb_dressed_characters.glb`

Use `char_hero_v1` because the cockpit is readable during the close foreground
pass. Parent the pilot to the JB100 using this established placement:

- Local position: `(0, -0.4, 0.23)`
- Local Z rotation: `180 degrees`
- Scale: `1.2`

### Procedural scene assets

The following should be constructed inside the scene and do not require new
external source assets:

- Deep two-layer emissive starfield
- Two violet-blue JB100 engine plumes
- Two engine glow lights
- Golden final flare source
- Concentric flare rings
- Radial flare streaks and final white-out treatment
- Scene-specific lighting rig

Existing implementation references for JB100 orientation, pilot placement,
and engine locations:

- `Orlando-El-Bastardo.src/tools/tmp_jb100_flyby.py`
- `Orlando-El-Bastardo.src/tools/tmp_jb100_flyaway.py`

## Scene hierarchy

```text
SCENE_ROOT
|-- CAMERA_RIG
|   |-- CAMERA_AIM
|   `-- Camera
|-- LOGO_ROOT
|   |-- OEB_Globe
|   |-- Orbit_Ring_1
|   |-- Orbit_Ring_2
|   |-- Orbit_Ring_3
|   |-- Orlando_3D
|   |-- El_3D
|   |-- Bastardo_3D
|   `-- FINAL_FLARE
|-- JB100_ROOT
|   |-- prop_jb100_A
|   |-- char_hero_v1
|   |-- engine_glow_L
|   |-- engine_glow_R
|   |-- engine_plume_L
|   `-- engine_plume_R
|-- STARFIELD_NEAR
|-- STARFIELD_FAR
`-- LIGHT_RIG
```

## Logo placement and pivot

The native logo geometry is approximately 11.54 units wide and 4.13 units
high. The logo must pivot around the globe rather than the center of the text.

Create `LOGO_ROOT` at the asset's globe center:

`(-6.42, 1.08, 0.18)`

Parent all seven logo objects while preserving their world transforms, then
rebase the root so the globe center becomes world origin. Relative to that
pivot, the presentation center of the complete logo is approximately:

`(3.7, 0, 0)`

Place the final flare behind the gap between the two text rows at approximately:

`(4.5, -0.65, -1.2)`

This placement allows the final camera move to pass visually between
"rlando" and "Bastardo" while the letters crop around the flare.

## Camera design

Use a perspective camera with a constant focal length of approximately 42 mm.
The final enlargement must be a physical dolly rather than a focal-length
zoom.

Suggested key placements:

| Beat | Camera position | Aim target |
| --- | --- | --- |
| Opening edge view | `(13.8, 0.2, 3.8)` | `(1.5, 0.2, 0)` |
| Completed logo view | `(6.8, 0.3, 13.2)` | `(3.7, -0.1, 0)` |
| White-out endpoint | `(4.9, -0.55, 1.0)` | Flare at `(4.5, -0.65, -1.2)` |

These are blocking values. Final positions should be tuned using reference
frame overlays.

### Camera movement

- `0.00-3.20s`: Orbit roughly 60-70 degrees from the logo's side toward its
  face. Shift the aim from near the globe toward the logo presentation center.
  Add approximately 7-10 degrees of roll so the title rises toward
  screen-right.
- `3.20-5.35s`: Near-hold with a slight settling drift. This establishes the
  clean JB100/logo hero composition.
- `5.35-6.43s`: Aggressively eased dolly toward the flare. Move the aim from
  the logo center to the flare while reducing camera-to-target distance from
  approximately 13 units to 10, 6, 3, and finally about 1 unit.

## Master timing

Render at 29.97 fps for 193 frames.

| Time / frame | Required image |
| --- | --- |
| `0.00s / f1` | Globe and rings left-of-center; title almost edge-on and visible mainly as thin red protrusions. |
| `1.50s / f46` | JB100 appears just outside the upper-right corner. |
| `1.80s / f55` | Ship dives very close to camera and fills much of the right half. |
| `2.10s / f64` | Ship crosses the lower foreground and exits below/left. |
| `3.20s / f97` | Logo is nearly fully readable; ship begins its second pass from lower-left. |
| `4.05s / f122` | JB100 is centered over the title with canopy and yellow lamps readable. |
| `4.85s / f146` | Ship exits upper-right, leaving two violet-blue trails. |
| `5.05-5.35s / f152-f161` | Brief clean logo hold; golden flare begins faintly. |
| `5.50s / f166` | Dolly accelerates and the logo begins cropping. |
| `5.85s / f176` | Letters fill the frame around the growing flare. |
| `6.20s / f187` | Only title fragments remain at the frame edges. |
| `6.43s / f193` | Full white-out. |

## JB100 flight path

Use one continuous looping path. The first pass travels from upper-right toward
the camera and exits below-left. The turn happens offscreen. The second pass
re-enters from lower-left and climbs toward upper-right across the face of the
logo.

Block the path with camera-normalized screen checkpoints. Coordinates use
top-left `(0,0)` and bottom-right `(1,1)`.

| Time | Screen center `(x, y)` | Approximate camera distance |
| --- | --- | --- |
| `1.50s` | `(1.10, -0.10)` | `12` |
| `1.80s` | `(0.90, 0.45)` | `5.5` |
| `2.10s` | `(0.45, 1.15)` | `4-5` |
| `2.30s` | Offscreen below-left | `6` |
| `3.20s` | `(-0.15, 1.05)` | `11` |
| `3.65s` | `(0.14, 0.83)` | `11` |
| `4.05s` | `(0.40, 0.62)` | `10.5` |
| `4.45s` | `(0.70, 0.55)` | `10` |
| `4.85s` | `(1.15, 0.43)` | `11` |

A camera-space guide empty can be used to author the exact framing. Bake its
evaluated world transforms to `JB100_ROOT` before rendering so lighting,
motion blur, and path-tangent orientation behave consistently.

Orient the JB100 to the path tangent with local `-Y` as the forward axis. Use
auto-clamped Bezier interpolation, adding intermediate offscreen keys to make
the hidden turnaround continuous. The first pass should carry a stronger bank
toward camera. The second pass should show a mostly top-down canopy view with
only a mild bank.

## Engine treatment

Use the established engine tip locations in JB100 local space:

- Left: `(-0.95, 3.01, 1.1)`
- Right: `(0.95, 3.01, 1.1)`

At each location, add:

- A white-hot plume root
- A translucent violet-blue tapered plume
- A low-radius violet-blue point light

The plumes should be most readable during the second pass. Their light should
briefly tint the orbital rings blue as the ship crosses the globe and exits.

## Starfield

Create a dense procedural starfield behind the logo using approximately
700-1,000 emissive points distributed through two depth layers.

- Vary apparent size from roughly 1-4 output pixels.
- Use mostly white stars with a smaller number of cool-gray stars.
- Keep all stars behind the title and ship.
- Use a distant layer for stable coverage and a nearer layer for subtle
  parallax.
- Preserve enough depth for the final camera dolly to drive the stars outward
  radially.

The world should remain nearly black.

## Lighting and materials

Use Eevee to retain the polished legacy-CG appearance of the original.

- Warm upper-left key light for the logo and ship
- Dim cool fill from camera-right
- Red rim light from the globe side
- Violet-blue engine lights parented to the JB100
- Very low world illumination

The reference is substantially darker than the current logo preview. Preserve
the canonical materials, but control their appearance through scene lighting,
exposure, and scene-local material copies. The red lettering should retain
strong bevel highlights without becoming bright scarlet, and the orbital rings
should remain mostly dark until hit by key or engine light.

Use a Standard-style display transform with high contrast and saturated reds
unless testing demonstrates that the production AgX setup matches the source
more closely.

## Final flare and white-out

The flare is a defining feature and must be more structured than generic bloom.
Build it from:

- A visible golden emissive source behind the title
- Fog Glow
- Radial streaks
- Several translucent concentric rings
- Warm orange and faint violet secondary halos
- Rapidly increasing emission and exposure beginning around frame 155
- A final additive white ramp over the last 6-8 frames

The flare should first appear as a small golden point during the clean-logo
hold. As the camera accelerates, it should illuminate the text edges, enlarge
into a ringed radial burst, and finally overwhelm the entire image. Motion blur
should remain restrained during the JB100 passes and become much more apparent
in the final dolly and star streaks.

## Render and delivery settings

Primary match render:

- Resolution: `648 x 486`
- Aspect ratio: `4:3`
- Pixel aspect: `1:1`
- Frame rate: `29.97 fps`
- Frame range: `1-193`
- Progressive scan
- No audio

A higher-resolution 4:3 master may also be rendered at `1296 x 972` and
downsampled, but composition and reference comparisons must remain locked to
the 648 x 486 frame.

## Proposed version package

Create the implementation as a deterministic scene build and package it under:

`Orlando-El-Bastardo.src/scene_versions/oeb_title_reveal_v1.0.0/`

The eventual package should contain:

- Deterministic Blender scene-builder script
- Generated `.blend` scene
- Preview MP4
- README with version notes
- Key comparison stills

## Implementation sequence

1. Create the deterministic scene builder and exact render settings.
2. Append the seven logo geometry objects and establish the globe-centered
   pivot.
3. Import the JB100 and pilot; build the engine-light and plume rig.
4. Create the two-layer procedural starfield and shared lighting.
5. Block the camera at frames 1, 55, 97, 146, 161, 176, 187, and 193.
6. Animate and bake the continuous JB100 loop using the screen checkpoints.
7. Add the flare rig, radial treatment, and final exposure ramp.
8. Compare the eight keyframes directly against the source using overlays.
9. Tune silhouettes, camera roll, exposure, ship scale, and flare timing.
10. Render the complete scene and assemble the version package.

## Acceptance priorities

In order of importance:

1. Globe-centered camera orbit and edge-on title reveal
2. Correct two-part JB100 loop with a very close first pass
3. Readable left-to-right hero pass over the completed logo
4. Brief clean-logo hold before the final move
5. Accelerating physical camera dolly through the text
6. Structured concentric golden flare and complete white-out
7. Dark, dense starfield with appropriate parallax and radial motion
8. Faithful legacy-CG contrast, saturation, and bevel highlights

The largest likely fidelity failure would be replacing the final structured
flare with ordinary bloom. The next largest would be rotating the logo instead
of orbiting the camera, which would weaken the starfield and ship parallax that
make the original shot feel spatial.
