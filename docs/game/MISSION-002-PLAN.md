---
title: Mission 002 — Planetfall
created: 2026-09-08T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: plan
production_area: interactive
department: production
status: active
canonical: true
canonical_for: journeyblaster_mission_002_plan
wiki: false
---
# Mission 002 — Planetfall

Working title: **Planetfall**

Prototype status: **Planetfall Prototype V1**, implemented on 2026-09-08.
See [MISSION-002-PROTOTYPE-V1.md](MISSION-002-PROTOTYPE-V1.md) for the
milestone record.

## Mission promise

The JB100 arrives in-system and discovers a large asteroid on a collision
course with an inhabited planet. The pilot intercepts it, flies around its
rotating surface to place demolition explosives at HUD-assisted fracture
points, detonates the charges, and pursues the resulting pieces toward the
planet. Every dangerous fragment must be broken down and vaporized before it
penetrates too deeply into the atmosphere.

Mission 002 should contrast two kinds of piloting:

1. A deliberate, close-range demolition operation around a massive moving
   object.
2. A fast pursuit in which the pilot prioritizes, destroys, and atomizes a
   widening field of planet-bound fragments.

## Confirmed experience decisions

- The mission is flown from the JB100 cockpit and builds on the current flight,
  weapon, sensing, aiming, destruction, towing, and mission-state systems.
- The primary asteroid is moving toward a planet throughout the mission. This
  is a pursuit rather than a stationary shooting gallery.
- The player must fly around the primary asteroid in a pattern to reach
  multiple HUD-assisted explosive-placement targets.
- Explosives are placed before the fragment chase begins.
- The existing tow beam is reused in reverse as the explosive-placement beam.
  Instead of pulling an object toward the JB100, it projects from the ship to
  the selected point and deposits a charge on the asteroid surface.
- Mouse click-and-drag always steers the JB100; placement aim follows the
  ship's forward vector exactly like FrapRay aiming.
- `/` or `?` toggles between FrapRay and reverse tow-beam modes. `Space` fires
  the selected system, while `G` is reserved for charge detonation.
- The explosive-placement reticle is the blue circle used earlier in the
  prototype.
- The weapon indicators remain visually distinct:
  - blue circle: explosive-placement point
  - red dots: paired FrapRay trajectories
  - red X: proton-torpedo trajectory
- Placement requires line of sight. Targets on the far side of the asteroid
  cannot be reached through its body, requiring the player to fly around it.
- At defined points in the approach, the asteroid or some of its major pieces
  may break apart naturally, making destruction somewhat easier while also
  producing more targets.
- After the mission fails, the JB100 remains freely flyable in the current
  scene. `R` is the explicit restart command.

## Recommended mission flow

```text
arrival and Senso-Globe warning
  -> intercept the planet-bound primary asteroid
  -> match its course and enter placement range
  -> toggle from FrapRay to reverse tow-beam mode
  -> fly around the rotating asteroid
  -> place charges at the HUD-assisted fracture points
  -> clear the blast area and detonate
  -> pursue the major fragments
  -> survive or exploit staged natural breakups
  -> destroy major fragments with FrapRay fire and proton torpedoes
  -> descend into the upper atmosphere
  -> vaporize every dangerous small fragment
  -> confirm the impact corridor is clear
  -> mission complete
```

## Phase 1 — Detection and interception

The Senso-Globes detect the incoming body and establish the stakes before the
player reaches it. Recommended readouts are:

- time to atmospheric entry
- distance to intercept
- estimated mass
- projected impact zone
- closing velocity
- current threat classification

This phase gives the player room to understand the target's direction and
match its course before precision flying begins.

## Phase 2 — Demolition placement

Once the JB100 is close enough and moving at a safe relative speed, the
pilot selects tow-beam mode with `/` or `?`. The red weapon indicators are
suppressed and the blue circular placement reticle appears.

Mouse-drag steers the ship in both weapon modes. The blue reticle is projected
along the JB100's forward tow-beam path, so the player aims by flying and
turning rather than moving an independent cursor. Pressing `Space` shoots the
reverse tow beam at an acquired blue torus and attaches its charge. The beam
endpoint follows the visible surface rather than projecting through the
asteroid. Recommended reticle feedback is:

- open blue circle: no valid surface placement point acquired
- tightening or gently pulsing blue circle: valid fracture point acquired
- filled or locked blue circle: charge can be placed
- brief confirmation pulse: charge is attached and secured

The player must reach several points distributed around the asteroid. A
three- or four-point pattern is recommended for the first implementation:

- one forward/leading-side point
- one upper or lower point
- one lateral or rear-side point
- an optional fourth point on the opposite lateral face

The asteroid should rotate slowly enough that the player can reason about the
pattern but quickly enough that course matching and position matter.

### Recommended placement rules

- The target must be inside beam range.
- The target must have a clear line of sight from the JB100.
- Relative speed must be below a safe placement threshold.
- The ship-forward blue reticle must acquire the target before `Space` can
  place a charge.
- The charge remains attached to the rotating asteroid at the selected surface
  position.
- Moving out of range or losing line of sight breaks acquisition but does not
  remove charges already placed.
- The ship-effect exclusion bubble continues to hide the beam inside the
  JB100 hull and reveals it only beyond the hull clearance boundary.

Course Lock may be useful while placing charges, but it should not be required
until hands-on testing determines whether free-flight aiming is too difficult.
A target-relative flight or velocity-matching aid is preferable to an
automatic orbit because the player should still feel responsible for flying
around the asteroid.

## Phase 3 — Detonation and primary breakup

After all required charges are secured, the pilot clears a safe radius and
detonates them. The blast breaks the primary asteroid into approximately three
major fragments.

Recommended breakup presentation:

- a bright multi-point flash at the charge locations
- a large dust and debris cloud that briefly obscures the fragments
- fragment trajectories that diverge without losing their overall motion
  toward the planet
- a clear Senso-Globe warning as the single target becomes several threats

Weapon damage may contribute to an early breakup, but the placed charges are
the planned, reliable way to split the primary body.

## Phase 4 — Fragment pursuit

The player chases the major pieces and chooses an order of engagement. The
Senso-Globes should rank each fragment by its projected danger:

- red: projected to strike a populated area
- orange: dangerous atmospheric trajectory
- yellow: likely to burn up but still uncertain
- gray: no longer dangerous

Each major fragment should require sustained FrapRay fire or a proton torpedo.
Destroying it creates smaller moving pieces. At selected mission distances or
times, one major piece may also break apart naturally. Natural breakup lowers
the durability of the remaining targets but increases their number and spreads
their trajectories.

## Phase 5 — Atmospheric threshold

The surviving fragments enter the upper atmosphere. A detailed planet model
is not required initially; a large sphere, atmospheric glow, haze, and changing
light can establish scale and danger.

Recommended atmospheric changes:

- time-to-entry becomes altitude or atmospheric-depth information
- fragments gain orange heating effects and vapor trails
- some sufficiently small fragments disintegrate naturally
- sensor certainty decreases inside ionized trails
- remaining dangerous targets become more urgent and visually brighter

## Phase 6 — Final vaporization

The final task is to atomize every dangerous small fragment. Small pieces need
only one weapon hit and disappear into expanding dust clouds. The mission ends
only when the Senso-Globes confirm that no fragment remains on a dangerous
impact trajectory.

## Weapon roles

### FrapRay

- unlimited or rapidly renewable fire
- paired orange plasma bolts
- best for precision damage and small-fragment cleanup
- requires the pilot to maintain aim during the pursuit

### Proton torpedoes

- limited ammunition
- blue core with a white vapor trail
- best for breaking a major fragment or handling an urgent high-threat target
- potentially affects nearby fragments, but should not clear the entire field
  with one shot

## Asset strategy

Mission 002 can be prototyped with the assets and runtime systems already
available:

- JB100 v38 cockpit and exterior model
- five asteroid variants
- scaling and rotation to create distinct primary, major, and small bodies
- FrapRay and proton-torpedo projectiles
- asteroid breakup, moving fragments, and dust-cloud vaporization
- Senso-Globe detection and target readouts
- blue placement circle plus the red weapon indicators
- tow-beam geometry and ship-effect exclusion bubble
- mission HUD and state framework
- deterministic starfield
- a runtime placeholder planet sphere, atmospheric shell, haze, and lighting

The primary asteroid can initially be assembled from scaled existing asteroid
variants. A bespoke Blender model with authored fracture regions, charge
sockets, and breakup pieces would be a later production upgrade, not a
prototype dependency.

## Recommended first playable scope

- one large primary asteroid
- three required explosive-placement points
- ship-forward reverse tow-beam placement with the blue circular reticle,
  `/` or `?` mode toggle, and `Space` firing
- one manual charge detonation
- three major fragments
- one scripted natural breakup during pursuit
- several small fragments per major fragment
- a placeholder planet and visible atmospheric boundary
- Senso-Globe threat prioritization
- success, failure, post-failure free flight, and restart states

This is enough to test the mission's central rhythm: intercept, match course,
circle and place, detonate, pursue, prioritize, and vaporize.

## Success and failure

Recommended success condition:

> The primary asteroid has been broken apart and every fragment capable of a
> damaging planetary impact has been destroyed or reduced to material that
> will burn up safely.

Recommended failure condition:

> At least one dangerous fragment passes the final atmospheric safety boundary
> on a damaging trajectory.

Failure should stop mission progression and preserve the consequences already
visible in the scene, while leaving the JB100 flyable until the player presses
`R` to restart.

## Open tuning questions

- Three or four required charge locations?
- Does placement mode automatically engage Course Lock, merely recommend it,
  or leave it entirely manual?
- Should the reverse tow beam carry a visible physical charge or represent a
  directed energy explosive embedded into the surface?
- How close must the JB100 fly for placement to feel dangerous without making
  the asteroid's scale unreadable?
- Can weapon fire trigger the primary breakup before all charges are placed,
  and what consequence should abandoned charges have?
- How many fragments can remain readable and performant from the cockpit?
- Should a mission with only unpopulated-area impacts count as success, partial
  success, or failure in a later scoring system?

## Prototype V1 implementation — 2026-09-08

The first playable implementation uses the existing round asteroid variant at
nine-times wrapper scale for the slowly tumbling primary. Three blue fracture
targets rotate with its surface. `/` or `?` toggles between FrapRay and reverse
tow-beam modes, while left-mouse drag steers the JB100 in either mode. The blue
placement circle follows the ship-forward beam path. Pressing `Space` on an
acquired torus projects the reverse tow beam from 0.10 m beyond the JB100's
3.25 m effect-exclusion sphere and attaches the charge. `G` remains dedicated
to detonation.
The interception and placement clock begins when the pilot starts the mission
and provides three minutes before the primary reaches the atmospheric failure
boundary; the briefing screen does not consume this window.
Completing placement ends that clock. Charge detonation begins a separate
one-minute debris-chase clock, including the controlled-breakup animation, so
time spent placing charges does not reduce the pursuit phase.

All three charges unlock a safe-distance check and manual `G` detonation. The
controlled breakup replaces the primary with three differently scaled existing
asteroid variants on independent planetfall trajectories. Major bodies retain
the shared destructible-asteroid behavior, so live FrapRay and proton-torpedo
hits split them into smaller moving debris and subsequent hits atomize those
pieces into dust. One surviving major body naturally breaks apart after a
timed chase interval.

The planet uses one 64-by-32 procedural surface sphere and one matching
Fresnel-only transparent atmosphere shell. This produces readable curvature,
continents, and limb glow without volumetrics or large scene coordinates.
Dangerous bodies crossing the atmospheric safety plane fail the mission; an
empty threat list completes it. Both outcomes leave the established restart
behavior intact, including post-failure free flight.

Automated acceptance evidence:

```text
MISSION-002-RUNTIME-OK: intercept + blue-reticle charges + controlled breakup + debris atomization + planetfall
```
