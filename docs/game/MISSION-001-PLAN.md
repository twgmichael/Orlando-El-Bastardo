---
title: Mission 001 — Retrieve the Mining Probe
created: 2026-08-24T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: plan
production_area: interactive
department: production
status: active
canonical: true
canonical_for: journeyblaster_mission_001_plan
wiki: false
---
# Mission 001 — Retrieve the Mining Probe

Milestone status: **Demo Prototype V2**, declared complete on 2026-09-08.
See [DEMO-PROTOTYPE-V2.md](DEMO-PROTOTYPE-V2.md) for the milestone record.

## Goal

Prove that OEB's canonical assets and production variants can drive an
enjoyable first-person JourneyBlaster experience in Godot without creating a
parallel game-asset pipeline.

The player sits at the real pilot viewpoint inside the JB100 hero stand-in,
flies into an asteroid field, locates a mining probe through the Senso-Globes,
downloads its data, attaches the probe to the JB100's tow system, returns to
the field entrance with the probe visibly in tow, and engages hyperspace.

## Player loop

```text
cockpit briefing
  -> enter asteroid field
  -> detect unknown signal
  -> resolve bearing and strength
  -> identify mining probe
  -> approach safely
  -> download data
  -> take probe in tow
  -> turn around and return to entry boundary
  -> clear asteroid field with probe attached
  -> hyperspace
```

The probe is a physical mission object throughout. Downloading its data does
not remove it, and towing does not convert it into inventory.

## Locked experience decisions

- The local `assets/ships/jb100_v38/jb100_v38.glb` is the playable hero
  stand-in. It already includes the canopy and one-pilot cockpit.
- The GLB is a joined visual, so independent gameplay nodes and markers live
  in the Godot wrapper. The editable `.blend` can later provide separately
  animated chair and control geometry without changing gameplay code.
- Senso-Globes are the yellow-orange hemispheres distributed along the JB100
  hull. They gather active and passive environmental information; they are not
  a cockpit globe or screen.
- Cockpit instruments present Senso-Globe data as progressively resolved
  contact information.
- The pilot chair rotates freely through 360 degrees around its pivot and has
  five quick views: forward, forward-up, left side, right side, and straight
  back.
- Pilot-view framing starts exterior-first at approximately 60 percent space
  and 40 percent cockpit context. The forward-up detent looks through the
  canopy rather than down toward the seat.
- Chair orientation never changes ship heading, velocity, plotted course, or
  weapon direction.
- The JB100 fires paired orange FrapRay plasma bolts from its left and right
  hardpoints and limited proton torpedoes with a blue core and fading white
  vapor trail from its torpedo launcher.
- FrapRay paths align with the measured forward-face centers of the named
  cannon meshes in the local v38 Blender source. Their visible bolts begin at
  the exclusion-bubble exit along those exact axes.
- The aiming HUD projects all three actual weapon paths into the active camera:
  red dots identify the two FrapRay paths and a small red X identifies the
  center torpedo path. `Tab` toggles the full set together.
- Large asteroids break into three moving fragments. A subsequent weapon hit
  vaporizes a fragment into an expanding dust cloud that fully disappears.
- Senso-Globe bearings remain ship-relative rather than chair-relative. The
  ship can continue flying while the pilot looks
  elsewhere.
- The local mining probe and five local/generated asteroid variants support
  the prototype. All placeholders remain replaceable through contracts.
- Mission success requires the physical probe—not merely its data—to return
  to the original field entrance in tow.

## Architecture

```text
Canonical Asset
  -> Production Variant
  -> Interactive Asset Contract
  -> validated asset sync
  -> generated Godot GLB + wrapper scene
  -> Godot runtime

Declarative Mission Contract
  -> mission validation
  -> generated Godot mission scene
  -> deterministic MissionRunner state
```

The existing `tools/export_godot.py` remains the exporter for deterministic
SceneSpec timeline playback. Interactive staging uses a separate tool because
mission runtime state is not a SceneSpec cue timeline.

## Interactive asset contract

Every hero and stand-in variant uses the same versioned contract envelope:

- canonical `asset_id` and expected exported root node
- production role and runtime kind
- source orientation and Godot visual correction
- collision shapes
- cockpit camera and field of view
- sensor origin
- centered effect-exclusion bubble for tractor, weapon, and special-effect
  visibility
- tow attachment point
- engine emitters and future weapon/damage attachment slots
- controller profile
- animation bindings

Mission 001 validates only the capabilities it needs, but the contract format
allows later combat missions without replacing the wrapper architecture.

### JB100 contract requirements

- Use `prop_jb100_A` / v38 hero stand-in.
- Begin with the v37/v38 cockpit-review viewpoint, then raise the runtime eye
  position to `(0.0, 0.20, 1.86)`, use a shallower `-10` degree camera pitch,
  and widen the Godot field of view to 72 degrees for the exterior-first
  60/40 composition.
- Normalize the asset's Blender `-Y` nose to Godot runtime `-Z` forward.
- Add a conservative hull collision box.
- Expose `cockpit_camera`, `sensor_origin`, `tractor_origin`, and a centered
  `effect_exclusion_center` marker with radius and visibility-clearance data.
- Expose forward, port, starboard, aft, and dorsal Senso-Globe origins as a
  distributed hull sensor array.
- Put the cockpit camera below an independent `SeatPivot`; do not parent ship
  steering to the pilot's view direction.

### Mining probe contract requirements

- Use `prop_mining_probe_1999_A` v1.0.0.
- Preserve the `beacon_blink_loop` animation binding.
- Add conservative collision and interaction volumes.
- Expose `sensor_signature`, `data_port`, and `tow_anchor` markers.

## Mission state machine

```text
BRIEFING
  -> LOCATE
  -> APPROACH
  -> DOWNLOAD_READY
  -> DOWNLOADING
  -> DATA_SECURED
  -> TOW_READY
  -> IN_TOW
  -> RETURN_TO_ENTRY
  -> EXIT_READY
  -> HYPERSPACE
  -> COMPLETE
```

Only deterministic Godot systems may change authoritative mission state.
Presentation and future conversational interfaces may request transitions but
cannot set them directly.

## Initial sensor and interaction tuning

These values are gameplay defaults, not OEB canon:

| State | Initial rule |
|---|---|
| Unknown signal | target within 900 m |
| Coarse bearing | target within 700 m |
| Signal strength | target within 450 m |
| Identification | within 180 m plus 2 s line of sight |
| Visual acquisition | within 80 m |
| Download action | within 12 m, relative speed at most 2.5 m/s |
| Download duration | 3 seconds, interrupted by unsafe separation |
| Tow attachment | within 12 m, relative speed at most 1.5 m/s |
| Tow latch | 1.8-second visible beam extension |
| Tow length | Captured attachment distance, held constant up to a 14 m safety maximum |
| Exit success | JB100 and probe inside the entry-boundary exit volume |

## Prototype controls

| Function | Keyboard and pointer | Gamepad |
|---|---|---|
| Throttle | `W` / `S`; `X` immediately stops the ship | Left stick vertical |
| Yaw and pitch | `A` / `D` or `←` / `→` turn; `↑` / `↓` pitch; left-mouse drag | Left/right sticks |
| Roll | `Q` / `E` | Right stick horizontal |
| Strafe and lift | `Z` / `C`; `R` / `F` | Triggers supplement lift |
| Course lock | `L` | B |
| Interact/download/tow | `G` | A |
| FrapRay blasters | `Space` | X |
| Proton torpedo | `T` | Right-stick press |
| Toggle weapon aiming HUD | `Tab` | — |
| Chair view detents | `1`–`5`; `V` cycles; `Home` returns forward | D-pad and shoulders |
| Free chair rotation | Right-mouse drag | View detents in prototype |
| External debug camera | `F3` | — |
| Hyperspace | `H` | Y |
| Restart | `R` after completion | — |

## Runtime layout

The animation resolver's existing 50 m mark span remains valid for shot
staging but is too compressed for first-person gameplay around a 6.6 m ship
and 10 m asteroids. Mission 001 therefore reuses the canonical asteroid meshes
at mission-authored transforms spread across roughly 900 m of travel. This is
runtime placement, not a mutation of the asset library or resolver map.

The player begins outside the field facing inward. The probe is placed deep in
the field. After attaching the tow, the player reverses course and returns to
the original entrance; the far side is not the mission exit.

## Phase plan

### Phase 1 — Contracts and project boot

Deliver schemas, contracts, validation, staging, wrapper generation, a nested
Godot project, a generated Mission 001 boot scene, and a headless boot test.

### Phase 2 — First-person flight

Implement damped arcade flight, cockpit and debug cameras, gameplay-scale
asteroid placement, collision response, and an independent rotating-chair
camera rig.

### Phase 3 — Locate and download

Implement progressive Senso-Globe information, line of sight, identification,
safe approach, and interruptible data transfer.

### Phase 4 — Tow and return

Implement physical visible towing, return-to-entry validation, hyperspace
unlock, completion, and reset.

### Phase 5 — Presentation and playtesting

Add the minimal cockpit display, sound and effects, telemetry, performance
validation, and player-comprehension tuning.

## Playable prototype implementation — 2026-09-08

Implemented in the nested Godot project:

- local JB100 v38 visual and cockpit viewpoint
- damped six-axis arcade flight with keyboard, pointer, and gamepad paths
- independent `SeatPivot` with five detents, free 360-degree yaw, and external
  debug camera
- corrected forward-up pitch and exterior-first 60/40 pilot-view framing
- five contract-authored Senso-Globe origins and progressive sensor readout
- deterministic 15-obstacle field using five replaceable asteroid variants
- probe identification dwell, line-of-sight, safe-speed download, beacon,
  animated beam latch, distance-preserving trailing tow, return check,
  hyperspace, and restart
- deterministic starfield, mission HUD, objective, flight, chair, and sensor
  telemetry

Remaining prototype work is experiential rather than structural: hands-on
flight tuning, audio and stronger impact/hyperspace effects, performance
measurement, telemetry export, and production-model swap validation.

Automated acceptance evidence:

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
PHASE1-BOOT-OK: cockpit + chair pivot + Senso-Globes + probe + tow + 15 asteroids
PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace
COMBAT-RUNTIME-OK: FrapRay + proton torpedo + breakup + fragment vaporization + dust
```

## Demo Prototype V2 combat expansion — 2026-09-08

The JB100 weapon hardpoints are now enforced contract capabilities. Runtime
combat adds paired orange FrapRay bolts, blue-core proton torpedoes with white
vapor trails, staged asteroid breakup, moving fragments, disappearing dust,
weapon HUD status, ammunition, cooldowns, and collision-level regression
coverage. Combat remains optional to the probe-retrieval mission flow.

V2 control and targeting refinement replaces the fixed center plus with a
toggleable camera-projected aiming display, moves FrapRay fire to `Space`,
moves course lock to `L`, assigns immediate dead stop to `X`, and places both
FrapRay spawn points at the exact v38 cannon muzzle centers measured from the
editable `.blend` source.

The aiming display now distinguishes the paired FrapRay paths with red dots
from the center red-X target while keeping all three under the same `Tab`
toggle. Towing now visibly extends and latches over 1.8 seconds, captures the
attachment distance, and lets the probe trail in world space when the ship
pivots instead of snapping it into a rigid ship-relative position.

The JB100 now defines a 3.25 m spherical effect-exclusion bubble centered on
the hull collision center. Tow beams, projectiles, and future special effects
remain hidden inside it and first appear 0.10 m beyond its surface. The tow
beam calculates that surface exit dynamically toward the probe, eliminating
the fixed-point path that could cross the cockpit.

## Phase 1 acceptance gate

- Both schemas reject unknown properties and invalid IDs/transforms.
- Every Mission 001 reference resolves to a validated interactive asset.
- Every staged GLB is byte-for-byte identical to its canonical source.
- The staging manifest records SHA-256 provenance.
- Generated wrappers contain collision and required markers.
- The generated mission scene instances the JB100, probe, and asteroid set.
- Godot imports the project without missing-resource or parse errors.
- A headless test loads the boot scene, finds the pilot camera and tow markers,
  verifies every staged GLB and visual, verifies the mission definition, and
  exits successfully.

### Phase 1 evidence — 2026-08-24

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
MISSION-001-BOOT-OK: Retrieve the Mining Probe
PHASE1-BOOT-OK: cockpit + probe + tow markers + 5 asteroids
```

Godot 4.7 also launched the generated main scene headlessly without a missing
resource, scene parse, or script error.

## Mission 001 non-goals

Enemies, ship-to-ship combat damage, shields, inventory, conversational LLM
integration, atmospheric flight, menus, save games, and release packaging are
deliberately deferred.
