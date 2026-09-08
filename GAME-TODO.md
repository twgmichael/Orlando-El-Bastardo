---
title: Interactive Game Roadmap
created: 2026-08-24T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: register
production_area: interactive
department: production
status: active
canonical: true
canonical_for: game_roadmap
wiki: false
---
# GAME-TODO — JourneyBlaster Interactive

The first interactive OEB runtime is a native Godot experience built inside
this Studio repository. The Studio remains the asset and world factory; Godot
owns input, flight, collision, sensors, interaction, mission state, and
real-time presentation.

The archived browser experiment at `../jb100-test-game/` is a control and HUD
reference only. It is not the runtime foundation.

## Mission 001 — Retrieve the Mining Probe

Player promise:

> Sit in the cockpit of the JB100 hero stand-in, fly into the asteroid field,
> locate the mining probe through progressively improving sensor information,
> download its data, take the physical probe in tow, and fly it back out of the
> field before engaging hyperspace.

Canonical plan: [`docs/game/MISSION-001-PLAN.md`](docs/game/MISSION-001-PLAN.md)

Current milestone: **Demo Prototype V2**, declared complete on 2026-09-08.
Milestone record: [`docs/game/DEMO-PROTOTYPE-V2.md`](docs/game/DEMO-PROTOTYPE-V2.md)

### Phase 1 — Contracts and project boot

- [x] Define strict interactive-asset and interactive-mission schemas.
- [x] Add contracts for the JB100, mining probe, five asteroid variants, and
  their runtime attachment/collision metadata.
- [x] Add a declarative Mission 001 definition with the full download-and-tow
  return flow.
- [x] Add a deterministic validator for contracts, mission references, source
  assets, transforms, and mission step ordering.
- [x] Add a deterministic sync tool that stages canonical GLBs into Godot,
  writes provenance hashes, and generates wrapper scenes.
- [x] Create a nested Godot 4 project at `interactive/journeyblaster/`.
- [x] Boot into the real JB100 pilot-view camera with the probe and asteroid
  assets present in the scene.
- [x] Add headless validation for staged resources and the boot scene.

Exit gate: deterministic sync, headless Godot import, and the headless boot
test open a valid Mission 001 scene using only registered OEB assets and
contract-authored runtime metadata.

Status: complete on 2026-08-24. The validator reports seven assets and one
mission; Godot imports all seven staged GLBs; the headless boot test verifies
the cockpit camera, probe interaction markers, tow markers, and five asteroids.

### Phase 2 — First-person flight and asteroid navigation

- [x] Add a damped arcade-space `CharacterBody3D` flight controller.
- [x] Support pitch, yaw, roll, throttle, and lateral thrust with keyboard,
  pointer, and gamepad input.
- [x] Preserve the real JB100 cockpit view while keeping an external debug
  camera available.
- [x] Add an independent 360-degree pilot-chair camera with forward,
  forward-up, left, right, and straight-back detents.
- [x] Tune the starting detents to approximately 60 percent exterior view and
  40 percent cockpit context; make forward-up look through the canopy.
- [x] Keep ship heading and velocity independent from pilot-chair orientation.
- [x] Build a gameplay-scale 15-obstacle asteroid layout from the five
  canonical meshes.
- [x] Add stable collision, impact deflection, speed loss, and recovery.
- [ ] Tune the flight model so a new player understands it within one minute.

Exit gate: the player can enter, navigate, collide, recover, turn around, and
leave the field from the JB100 cockpit.

### Phase 3 — Senso-Globe search and data download

- [x] Treat the yellow-orange hull hemispheres as the JB100's distributed
  active/passive Senso-Globe array; cockpit instruments are readouts only.
- [x] Implement progressive sensor states: unknown signal, coarse bearing,
  signal strength, identification, visual acquisition, and action range.
- [x] Keep the probe free of a permanent exact waypoint before identification.
- [x] Play the probe's canonical beacon animation with a runtime light cue.
- [x] Add line-of-sight and relative-speed requirements.
- [x] Add contextual `DOWNLOAD DATA` with a short, interruptible transfer.

Exit gate: the player can discover and identify the probe through sensors and
complete the data transfer without the mission behaving like waypoint chase.

### Phase 4 — Tow, return, and hyperspace

- [x] Add contextual `TAKE IN TOW` after the data download completes.
- [x] Keep the probe physically visible behind the JB100; do not convert it
  into inventory.
- [x] Add a stable damped tow constraint, visible tow beam, and collision-safe
  tow length.
- [x] Require the player to return to the original entry boundary with the
  probe still attached.
- [x] Unlock hyperspace only after ship and probe clear the asteroid field.
- [x] Add completion, restart, and deterministic state reset.

Exit gate: the complete loop works from cockpit entry to probe return and
hyperspace completion.

### Phase 5 — Vertical-slice presentation and playtesting

- [x] Add minimal cockpit instrumentation, Senso-Globe readout, context prompt,
  and mission objective UI.
- [ ] Add restrained engine, beacon, download, tow, impact, and hyperspace
  audio/visual feedback.
- [ ] Track completion time, collisions, search time, failed actions, and tow
  breaks in a local debug report.
- [ ] Validate 60 FPS at 1080p on the Mac mini.
- [ ] Run one-minute control-comprehension and five-minute mission-completion
  playtests.
- [ ] Prove a production-variant swap without gameplay code changes.

### Demo Prototype V2 — Asteroid combat

- [x] Promote the JB100 FrapRay and proton-torpedo markers to an enforced
  weapon-source contract.
- [x] Fire paired orange plasma FrapRay bolts with `Space` from the physical
  left and right cannon muzzles.
- [x] Launch limited proton torpedoes with blue cores and fading white vapor
  trails with `T`.
- [x] Give all five asteroid variants destructible runtime wrappers.
- [x] Break destroyed large asteroids into three moving, shootable fragments.
- [x] Vaporize fragments into expanding, disappearing dust clouds.
- [x] Add weapon readiness, torpedo ammunition, and controls to the HUD.
- [x] Replace the fixed green plus with a `Tab`-toggleable aiming HUD that
  projects the actual twin FrapRay and center torpedo firing paths.
- [x] Move course lock to `L` and make `X` immediately zero throttle and
  velocity.
- [x] Add collision-level automated coverage for both weapons, breakup, and
  fragment vaporization.

## Explicit Mission 001 non-goals

- Shields, enemy AI, ship-to-ship combat damage, and subsystem targeting
- Conversational or networked LLM integration
- Inventory, economy, save games, menus, or release packaging
- Atmospheric flight or realistic orbital physics
- A second asset-production pipeline inside Godot

## Later mission vocabulary

`LOCATE / APPROACH / SCAN / DOWNLOAD / RETRIEVE / DOCK / PROTECT / ESCORT /
DISABLE / DESTROY / TRACTOR / EXIT`

Mission 001 exercises `LOCATE / APPROACH / DOWNLOAD / TRACTOR / EXIT`.
