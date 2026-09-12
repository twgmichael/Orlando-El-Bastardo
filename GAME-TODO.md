---
title: Interactive Game Roadmap
created: 2026-08-24T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
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

Current milestone: **Mission 003 Starbase Defense Prototype V4**, declared
complete on 2026-09-09. Milestone record:
[`docs/game/MISSION-003-PROTOTYPE-V4.md`](docs/game/MISSION-003-PROTOTYPE-V4.md)

- [x] Standardize mission announcements across all playable demos: large blue
  `GO` for the first three seconds, persistent green `SUCCESS` on completion,
  and persistent red `FAILED` on failure.

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
- [x] Animate a 1.8-second beam extension and latch, then preserve the captured
  tow distance with a world-space trailing constraint instead of snapping the
  probe behind the ship.
- [x] Route the tow beam from the JB100 hull center and reveal it only 0.10 m
  beyond a 3.25 m ship-effect exclusion sphere, preventing cockpit clipping.
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
  left and right cannon axes, revealing them beyond the ship-effect bubble.
- [x] Launch limited proton torpedoes with blue cores and fading white vapor
  trails with `T`.
- [x] Give all five asteroid variants destructible runtime wrappers.
- [x] Break destroyed large asteroids into three moving, shootable fragments.
- [x] Vaporize fragments into expanding, disappearing dust clouds.
- [x] Add weapon readiness, torpedo ammunition, and controls to the HUD.
- [x] Replace the fixed green plus with a toggleable aiming HUD that
  projects the actual twin FrapRay and center torpedo firing paths, using red
  dots for the two FrapRay impacts and a small red X for the center aim point.
- [x] Move course lock to `L` and make `X` immediately zero throttle and
  velocity.
- [x] Add collision-level automated coverage for both weapons, breakup, and
  fragment vaporization.

### Demo Prototype V3 — Probe consequences

- [x] Make ship collision damage the mining probe's data port without
  destroying the physical probe.
- [x] Prevent data download after collision damage while preserving the tow
  and return path.
- [x] Make either weapon immediately destroy the probe in an explosion and
  transition Mission 001 to `FAILED`.
- [x] Keep free-flight controls active after mission failure and expose `R` as
  the explicit restart.
- [x] Add contract, mission-schema, and collision-level runtime coverage for
  both damage outcomes.

### Demo Prototype V4 — Flight-control refinement

- [x] Ease keyboard and arrow steering into and out of full deflection.
- [x] Apply pitch, yaw, and roll around the JB100's local axes so controls keep
  their pilot-relative meaning when the ship is inverted.
- [x] Make pointer-drag aim frame-rate independent, faster, and smoothly
  filtered without carrying stale movement into the next drag.
- [x] Add automated coverage for steering ramps, inverted local yaw, and
  identical first/second mouse-drag response.

## Mission 002 — Planetfall

Canonical plan: [`docs/game/MISSION-002-PLAN.md`](docs/game/MISSION-002-PLAN.md)

### Planetfall Prototype V1 — Intercept, charges, and debris chase

- [x] Present a lightweight procedural planet with a single Fresnel atmosphere
  shell rather than volumetric rendering.
- [x] Scale an existing asteroid into a mission-sized primary body that falls
  toward the planet while slowly toppling and spinning.
- [x] Add three surface fracture targets distributed around the rotating body.
- [x] Reuse the tow beam in reverse as a blue explosive-placement beam that
  remains outside the JB100 effect-exclusion bubble.
- [x] Use `/` or `?` to toggle between FrapRay and reverse tow-beam modes;
  preserve mouse-drag ship steering in both modes.
- [x] Project the blue circle along the JB100's actual forward tow-beam path
  and use `Space` to shoot a charge onto an acquired blue torus.
- [x] Replace the procedural placed-charge box with the canonical one-meter
  `prop_explosive_pack_A` Blender asset and play its synchronized alternating
  warning-beacon animation after tow-beam attachment.
- [x] Reserve `G` for detonation after all charges are placed and the JB100 has
  reached safe distance.
- [x] Require a safe detonation distance after all three charges are placed.
- [x] Break the primary into three existing-asset major fragments with
  independent falling trajectories.
- [x] Trigger one staged natural breakup during the chase.
- [x] Allow FrapRay and proton-torpedo fire to break major debris into smaller
  pieces and atomize every remaining fragment.
- [x] Complete when no dangerous returns remain; fail if a dangerous body
  crosses the atmospheric safety boundary while preserving free flight.
- [x] Add end-to-end automated coverage for placement acquisition, effect
  clearance, controlled and natural breakup, live weapon fire, and atomization.

## Mission 003 — Starbase Defense

Canonical plan: [`docs/game/MISSION-003-PLAN.md`](docs/game/MISSION-003-PLAN.md)

### Starbase Defense Prototype V1 — Hangar launch and pirate defense

- [x] Start the JB100 v38 inside Starbase 86 v1.1's real open hangar and face
  the player toward a readable launch exit.
- [x] Present a lightweight distant planet, atmosphere, moon, and starfield.
- [x] Make every procedural starfield purely emissive and disable both shadow
  casting and shadow reception on its backdrop geometry.
- [x] Spawn three accepted Ellipso pirate flyers with unique randomized hidden
  subsystem objectives and randomized target order.
- [x] Add three shield, three weapon, and three hangar damage locations without
  exposing station or flyer health to the pilot.
- [x] Implement fuzzy objective flight, attack runs, JB100 avoidance,
  flyer separation, and individual behavioral variation.
- [x] Restrict pirate weapons to fixed forward fire: flyers must make a
  nose-on station approach, align within three degrees, fire along their
  actual forward axis, and then break into the evasive portion of the pass.
- [x] Give each pirate flyer three torpedoes; each may launch straight forward
  or aft only at JB100 after a two-second alignment and only within 300 m.
- [x] Give pirate torpedoes terminal guidance inside 100 m of the JB100 while
  preserving their straight fore/aft launch vector outside that range.
- [x] Keep every pirate outside a conservative 185 m Starbase collision
  envelope and route post-shot egress laterally around the station rather than
  through its core, hangar supports, or structural struts.
- [x] Add dedicated top and bottom Starbase weapon arcs, linked to the existing
  damageable weapon systems, to punish polar loitering dead zones.
- [x] Keep exactly one flyer attacking the JB100 whenever at least one other
  combat-capable flyer remains on station attack; send the final pirate back
  to accelerated station strafing.
- [x] Add imperfect, close-range-accurate starbase defensive fire with a
  one-in-twenty chance of deliberately targeting the exposed JB100; station
  fire cannot damage the station itself.
- [x] Count the two projectiles in every FrapRay volley independently: six
  bolt hits drive off a flyer; twelve bolt hits, one torpedo plus six bolt hits,
  or two torpedoes destroy it.
- [x] Count flyers as driven off at 5,000 m and show their hyperspace departure
  at 6,000 m while keeping retreat speed pursuable.
- [x] Scale station-weapon effectiveness with health and amplify weapon/hangar
  damage for each disabled shield generator.
- [x] Track live JB100 shields: plasma costs 10%, pirate torpedoes cost 25%,
  flyer/starbase collisions cost 50%, recharge is 2%/s, and zero shields fails
  the mission while preserving post-failure flight.
- [x] Map backtick to a fixed 25-percent reverse-thrust preset.
- [x] Preserve the established HUD, controls, weapon reticles, safe-hangar,
  post-failure free-flight, and `R` restart conventions.
- [x] Show a large centered `FAILED` notice for every Mission 003 failure while
  preserving post-failure free flight and cockpit instrumentation.
- [x] Add a hidden post-success hangar re-entry event that launches the docked
  Earth Starfighter into a continuous orbit around Starbase 86.
- [x] Add end-to-end automated coverage for hero assets, hangar launch, hidden
  objectives, station systems, pirate damage states, retreat, friendly fire,
  success, station loss, and JB100 disablement.

### Starbase Defense Prototype V2 — Live pirate flight

- [x] Give scripted pirate AI sole ownership of flyer transforms by disabling
  `AnimatableBody3D` physics transform synchronization.
- [x] Add a runtime assertion that all three flyers move under live AI control
  immediately after the mission starts.

### Starbase Defense Prototype V3 — Strafing passes and danger avoidance

- [x] Replace target-circling fire with readable ingress, single-shot strafe,
  fly-past, and return phases.
- [x] Keep each strafing lane outside the station body and alternate directions
  between successive passes.
- [x] Treat nearby station-defense bolts on an intercept course as hazards and
  blend evasive steering into the current pass.
- [x] Add runtime coverage for continuous fly-past geometry, one shot per pass,
  and defensive-fire avoidance.

### Starbase Defense Prototype V4 — Cockpit instrumentation mockup

- [x] Move mission telemetry from large floating HUD panels onto overlays fitted
  to the JB100's left, middle, and right cockpit screens.
- [x] Add four green-on-black systems bars: PWR and SHD begin at 100%, THR
  tracks commanded throttle, and WPN tracks rechargeable FrapRay power beside
  a live five-torpedo TPD counter.
- [x] Add a primitive XYZ Senso-Globe displaying contacts within 1,000 meters.
- [x] Move briefing, mission state, and current objective text to the right
  screen while preserving only weapon targeting marks in the forward view.
- [x] Render all cockpit instrumentation text in uppercase.
- [x] Center two red emergency ceiling strobes six meters apart and preserve
  two steady open-bay lights.
- [x] Park an Earth Starfighter behind the JB100 without blocking the open
  hangar's through-flight lane.
- [x] Hide and tighten station damage volumes, restore camera-relative stars,
  and add a visible solar-system sun.
- [x] Scale station-defense accuracy by pirate range while keeping defensive
  fire avoidance inside committed strafing behavior.
- [x] Remap `1`–`5` to fixed thrust presets and `-`/`+` to the ordered cockpit
  view cycle.
- [x] Begin Missions 001, 002, and 003 immediately without an Enter gate.
- [x] Map stationary left click to FrapRay, left drag to steering, held right
  click to torpedo load/fire and middle drag to chair look.
- [x] Give FrapRay a 100% reserve, 10% paired-volley cost, and 2%/s recharge;
  begin with five torpedoes.
- [x] Replace held-button mouse steering with continuous pointer-follow
  steering; reserve left click for FrapRay and require a three-second right
  click hold to charge/acquire, followed by release to launch a torpedo.
- [x] Replace absolute cursor latching with a bounded relative virtual stick,
  captured cursor, automatic spring return, and forced neutral on startup,
  focus loss, or window exit.
- [x] Map `X` to center the mouse-flight control and immediately clear residual
  turn input.
- [x] Map `Tab` to all stop, `Esc` to release mouse capture, and the next safe
  click to recapture without firing; move aiming-HUD toggle to `\`.
- [x] Add a macOS-standard `Control-Command-F` fullscreen shortcut with no
  visible button, persist fullscreen preference, show `CLICK TO RESUME FLIGHT`,
  and release capture on focus loss.
- [x] Turn the center torpedo X blue during its build-up and surround it with a
  circular three-second fill indicator.
- [x] Scale the blue torpedo lock reticle and charge ring down as a tracked
  target leaves reliable lock range, then restore their size when it returns.
- [x] Require one target to remain continuously in view and reliable range for
  the full three-second JB100 torpedo load/lock cycle; reset immediately on
  range loss, break instantly on view loss, and prohibit all dumbfire.
- [x] On torpedo impact, hide and remove the projectile immediately and replace
  its endpoint with a brief, intense blue-white flash.
- [x] Add torpedo proximity cleanup for disabled targets, triple the impact
  flash's size and brightness, and double the accompanying damage cloud.
- [x] Persistently acquire a target near the torpedo reticle, snap the lock
  marker to it, and give the launched torpedo fast, long-lived homing pursuit.
- [x] Add right-screen reports for shield, weapon, and hangar damage plus
  pirate retreats and destruction.
- [x] Replace the overwriteable report with a same-frame three-event station
  alert queue covering actual hits, system disablement, retreats, and kills.
- [x] Compact and clip the right-screen alert feed so its three newest events
  remain inside the cockpit display bezel.
- [x] Color hostile Senso-Globe contacts red and friendly contacts blue.
- [x] Add an amber Senso-Globe arrow projected along the JB100's local forward
  axis without a text label.
- [x] Correct the Senso-Globe coordinate convention to X lateral, Z vertical,
  and Y front/back; map Godot local `-Z` forward toward display `+Y` for both
  the amber arrow and sensor contacts.
- [x] Remove destroyed pirate roots from the Senso-Globe immediately so combat
  effect lifetime cannot leave red sensor ghosts.
- [x] Make PWR a shared generator reserve driven by throttle, shield recovery,
  and weapon recovery, with low PWR reducing thrust and both recharge rates.
- [x] Balance pirate defeat using individual projectile impacts rather than
  paired volleys: six FrapRay bolts to retreat; twelve bolts, one torpedo plus
  six bolts, or two torpedoes to destroy.
- [x] Preserve JB100 weapon cadence and feel while doubling pirate durability
  after playtesting showed the original three/six-bolt thresholds were too
  fragile.
- [x] On mission failure, make every surviving pirate disengage from the JB100
  and circle Starbase 86 without firing.

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
