---
title: Mission 003 — Starbase Defense
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: plan
production_area: interactive
department: production
status: active
canonical: true
canonical_for: journeyblaster_mission_003_plan
wiki: false
---
# Mission 003 — Starbase Defense

Working title: **Starbase Defense**

Prototype status: **Starbase Defense Prototype V4**, implemented on
2026-09-09. See
[MISSION-003-PROTOTYPE-V4.md](MISSION-003-PROTOTYPE-V4.md) for the current milestone
record.

## Mission promise

The JB100 begins inside one of a starbase's hangar bays while three hostile
flyers attack the station. The pilot launches directly into the battle,
protects vulnerable station systems, and either drives off or destroys
all three attackers.

The encounter should feel like a living defensive battle rather than a fixed
shooting gallery. Each hostile flyer has its own objective, changes tactics in
response to danger, and must contend with both the JB100 and imperfect
starbase defensive fire.

## Confirmed experience decisions

- The mission begins with the JB100 inside a starbase hangar bay.
- Three hostile flyers are attacking the starbase.
- The attackers fly around the station while firing at vulnerable locations.
- Vulnerable targets and attacker assignments change randomly on each run.
- The attackers' selected objectives are not directly revealed to the player.
- Potential objectives include:
  - shield generators
  - starbase weapons
  - docking hangars
- Each flyer uses a modest amount of fuzzy intelligence to pursue its
  objective while avoiding the JB100.
- Attackers also try to avoid intermittent, deliberately imperfect defensive
  fire from the starbase.
- Starbase weapons are hazardous to everyone and can accidentally hit the
  JB100.
- Three FrapRay hits cause a flyer to break off and flee.
- Seven total FrapRay hits destroy a flyer.
- One proton-torpedo hit followed by three FrapRay hits destroys a flyer.
- There are nine fixed but unmarked starbase damage locations: three shield
  generators, three weapons, and three docking hangars distributed across the
  station's top, middle, bottom, and outer structures.
- Each target has three health points. The player receives no exact health
  information for either the station or the flyers.
- Each attacker receives a different subsystem category, randomized among the
  three flyers on every run. Target order within each category is also
  randomized.
- The first flyer to complete its category becomes the sole JB100 attacker.
  Later completed flyers reinforce attacks on surviving station targets. If
  the JB100 attacker is destroyed or driven off, another eligible flyer takes
  its place.
- At most one flyer attacks the JB100 while the starbase remains operational.
  If all nine station targets are disabled, every active flyer attacks it.
- Each disabled shield generator adds one point of damage to later pirate hits
  against weapons and hangars.
- Weapon effectiveness scales with remaining health. Hangar effectiveness is
  not modeled in this demo.
- The JB100 has 100 hull/thrust points. Every friendly or hostile hit removes
  10 points and reduces translational thrust proportionally. At zero it is
  dead in space.
- The open starting hangar is a safe area: flyers ignore the JB100 while it is
  inside.
- A retreating flyer counts as driven off at 5,000 m from the starbase and
  jumps to hyperspace at 6,000 m. Retreat carries it away from the distant
  planet and moon.
- Destroying or driving off all three flyers takes priority over a simultaneous
  station-loss result because this is a playability-first demo.

## Recommended mission flow

```text
JB100 powered inside a starbase hangar
  -> attack warning and launch clearance
  -> depart the hangar into the active defense zone
  -> identify the three hostile flyers and threatened station areas
  -> intercept attackers without crossing starbase weapon fire
  -> pressure each flyer away from its hidden objective
  -> drive off or destroy all three attackers
  -> confirm the starbase is secure
  -> mission complete
```

## Opening: hangar launch

The hangar start should establish scale, urgency, and the station's
vulnerability before open-space combat begins. The player should be able to
see or hear signs of the attack from inside the bay, then fly out under their
own control.

The opening needs:

- a clearly readable exit route
- enough clearance for the JB100 to launch without an immediate collision
- an attack-state warning from the starbase
- a quick transition from enclosed hangar lighting to the external battle
- protection against hostile or friendly fire striking the player before
  they have a reasonable chance to launch

## Hidden attacker objectives

At mission start, each flyer receives an objective selected from the currently
vulnerable station systems. The exact assignment remains hidden from the
player. Objective selection should vary each run and avoid producing the same
three-flight pattern every time.

An attacker should reveal its intention indirectly through behavior:

- approach vector
- repeated attack runs against one station region
- weapon orientation and firing direction
- evasive turns that attempt to return it to its assigned target
- Senso-Globe observations of trajectory and weapons activity

This gives the pilot information to interpret without exposing a literal
objective marker.

## Attacker behavior

Each flyer should combine a small set of weighted priorities rather than
following a perfectly scripted path:

1. Move toward a firing position on its assigned station target.
2. Avoid imminent collision with the starbase, the JB100, and other flyers.
3. Evade the JB100 when threatened or pursued.
4. Avoid predicted starbase weapon fire when practical.
5. Fire on its assigned objective when position and aim are acceptable.
6. After sufficient damage, abandon the attack and flee the defense zone.

Small random variations in preferred range, turn timing, attack angle, and
evasion strength should make the flyers feel individually motivated without
requiring advanced strategic AI.

## Starbase defensive fire

The starbase contributes slow or intermittent weapons fire. It should help
sell the scale of the battle without solving the mission for the player.

The defensive system should:

- choose hostile flyers as intended targets
- aim and fire lazily enough that attackers can evade it
- use visible, readable firing lanes
- damage hostile flyers on direct hits
- also damage the JB100 if the player crosses a firing lane
- avoid perfect tracking or continuous fire

Friendly fire should feel dangerous but legible. A brief targeting warning,
weapon-charging cue, turret orientation, or bright projectile path can give
the player a fair chance to react.

## Hostile damage and retreat rules

The first damage threshold changes behavior rather than immediately removing
the target:

- **Three FrapRay hits:** the flyer disengages from the starbase and begins a
  committed retreat.
- **Seven total FrapRay hits:** the flyer is destroyed.
- **One proton torpedo plus three FrapRay hits:** the flyer is destroyed.

A retreating flyer no longer attacks the starbase. It remains physically
present while escaping, allowing the pilot to decide whether to protect the
station by changing targets or continue pursuit for a destruction outcome.

## Success and failure direction

Recommended success condition:

> All three hostile flyers have been destroyed or driven beyond the starbase
> defense perimeter.

Confirmed failure conditions:

- all nine starbase damage targets are disabled
- the JB100 reaches zero hull/thrust points

Failure preserves the current battle and free-flight controls. If the station
is lost, all surviving attackers turn on the JB100. `R` restarts the demo.

## Prototype scope

The first playable version should prove:

- a controllable JB100 launch from inside one hangar bay
- one readable starbase combat space
- three independently moving hostile flyers
- hidden randomized objectives selected from shield generators, weapons, and
  docking hangars
- fuzzy objective pursuit and basic JB100 avoidance
- intermittent starbase defensive fire with JB100 friendly-fire damage
- FrapRay, proton-torpedo, retreat, and destruction thresholds
- success when all attackers are driven off or destroyed
- restart and replay with different attacker objectives

## Prototype V1 implementation — 2026-09-09

The playable implementation uses the production Starbase 86 v1.1 exterior,
its real open through-hangar, the JB100 v38 hero model, and three accepted
Ellipso pirate flyers. The external production library also contains the
designated Starbase 86 and pirate-vehicle placeholders, but the higher-quality
local hero assets are available and therefore preferred.

A lightweight procedural planet, atmosphere shell, moon, and deterministic
starfield establish the distant environment. Runtime-only collision and system
housings provide the nine hidden station damage locations without changing the
joined Starbase GLB.

The HUD follows the Mission 001 and 002 layout and retains the same flight,
chair, weapon, aiming, failure/free-flight, and restart conventions. Senso-
Globe output reports hostile count, nearest bearing, and range while keeping
attacker objectives and all station/flyer health values hidden.

Remaining work is playability tuning: attacker speed and evasion weights,
weapon cadence, defensive accuracy, damage pacing, and encounter duration.

## Prototype V2 movement correction — 2026-09-09

Pirate AI now has sole ownership of each flyer's transform. Physics transform
synchronization is disabled on the `AnimatableBody3D` flyer wrapper so Godot
does not restore the previous transform after the AI movement update. Runtime
coverage now requires all three flyers to visibly change position under live
AI control shortly after the mission begins.

## Prototype V3 strafing runs — 2026-09-09

Pirates no longer orbit station targets while firing repeatedly. Each flyer
first moves to an outside ingress point, commits to a tangential strafing lane,
fires exactly once near its target, continues clear past the station, and then
turns back into the next pass. Alternating pass directions create readable
attack-and-recovery cycles and substantially slow station damage so the pilot
has time to launch, orient, and intercept.

Station defense bolts are now active navigation hazards. Flyers predict the
closest point of approach for nearby green plasma bolts and blend an evasive
steering response into their current attack run without abandoning the run.

## Prototype V4 cockpit instrumentation — 2026-09-09

The large floating telemetry panels are replaced in Mission 003 by overlays
fitted to the JB100's three modeled cockpit screens. The left screen presents
PWR, THR, SHD, and WPN bars. PWR and SHD begin at 100%, THR follows commanded
throttle, and WPN follows a 100% FrapRay reserve that spends 10% per paired
volley and recharges at 2% per second; a right-aligned TPD counter starts at
five. The middle screen presents a primitive 1,000-meter XYZ Senso-Globe with
hostiles red and friendlies blue, and the right screen carries mission
briefing, state, and current objective text. All display text is uppercase and
green on black; only weapon targeting marks remain projected into the forward
view.

The open hangar uses two steady runtime lights and two red ceiling strobes
centered six meters apart. An Earth Starfighter hero craft is parked behind and
to one side of the JB100 without blocking the through-flight lane. Station
damage volumes are surface-fitted and invisible, the starfield remains centered
on the pilot, and a visible solar-system sun accompanies the directional light.
Station defensive accuracy now tightens with range while pirate projectile
avoidance remains subordinate to committed strafing runs.

All three prototype missions now begin immediately when loaded. In the shared
flight controls, the ship continuously follows the visible mouse without a
button hold, left click fires FrapRay, holding right mouse for three seconds
charges the torpedo and acquires a target under the reticle, releasing right
mouse fires it, middle drag rotates the chair, and `Esc` commands all stop.
During torpedo build-up, the center X changes from red to blue and a circular
progress ring fills around it; the full charge remains held until release.
Mouse steering now uses captured relative motion to push a bounded 180-pixel
virtual stick. A 6% dead zone and 2.2 response exponent provide careful
long-range aiming; a 200 ms spring return neutralizes the stick when motion
stops. Startup, focus loss, and window exit forcibly clear steering, preventing
the JB100 from continuing along stale input. Pressing `X` also recenters the
virtual stick immediately. A torpedo searches a 12-degree forward acquisition cone, snaps
its reticle onto the acquired target, launches at 260 m/s, and homes strongly
for up to 12 seconds so a flyer cannot escape by speed alone. Three paired
FrapRay volleys drive off a pirate; six paired volleys or two proton torpedoes
destroy one.

The right cockpit screen maintains a live Starbase 86 report line. Actual
pirate hits produce category-specific damage reports for shields, weapons, or
hangars; perimeter crossings and flyer destruction report updated counts. The
Senso-Globe renders pirate contacts red and Starbase 86 and friendly craft
blue. An amber `F` arrow uses the globe's XYZ projection to indicate the
JB100's local forward direction.

After Mission 003 fails for any reason, every surviving pirate disengages from
the JB100, ceases firing, and circles Starbase 86 indefinitely. The player can
continue flying or watching the aftermath until restarting with `R`.
