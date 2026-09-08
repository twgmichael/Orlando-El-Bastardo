---
title: JourneyBlaster Demo Prototype V2
created: 2026-09-08T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_demo_prototype_v2
wiki: false
---
# JourneyBlaster — Demo Prototype V2

Declared complete on 2026-09-08. V2 contains the complete V1 probe-retrieval
loop and adds optional asteroid combat and destruction.

## Combat systems

- `Space` fires paired FrapRay bolts from the JB100's port and starboard
  hardpoints. The bolts are bright orange plasma energy with local glow.
- `T` launches one of eight proton torpedoes from the center launcher. Each
  torpedo has a blue energy core and a fading white vapor trail.
- Weapon direction follows the JB100 hull, not the independently rotating
  pilot chair.
- A proton torpedo or two paired FrapRay bursts break a large asteroid into
  three moving, collidable fragments.
- A weapon hit on a fragment vaporizes it into an expanding dust cloud. Every
  dust puff fades and the effect removes itself after 1.65 seconds.
- The HUD reports FrapRay readiness, proton-torpedo ammunition, and fire keys.
- The fixed green plus is removed. A `Tab`-toggleable aiming HUD projects the
  actual left cannon, right cannon, and torpedo paths into the active camera.
  Red dots mark the two FrapRay impacts; a smaller red X marks the center path.
- Tow activation visibly extends to the probe for 1.8 seconds before latching.
  The tether then holds the captured distance while the probe trails through
  ship pivots and turns rather than snapping rigidly behind the JB100.
- A centered 3.25 m effect-exclusion sphere keeps the tow beam and weapon
  visuals out of the JB100 hull. Effects first become visible 0.10 m beyond
  the sphere along their actual travel direction.
- `L` toggles course lock and `X` immediately zeros throttle and velocity.

## Runtime architecture

- The JB100 contract declares `weapon_source` and is validated to contain both
  FrapRay hardpoints and the proton-torpedo launcher.
- FrapRay muzzle positions are measured from the named cannon meshes in the
  local v38 `.blend` source: lateral offsets of `±1.4919`, height `0.9571`,
  and runtime-forward position `-2.8263` metres.
- Visible weapon effects remain aligned with those muzzle axes but begin only
  after exiting the centered ship-effect bubble.
- All five asteroid contracts declare `destructible`; their generated wrappers
  receive the common asteroid destruction controller.
- Projectiles use swept physics ray tests between frames to avoid tunneling at
  combat speed.
- Fragment geometry and dust are procedural runtime stand-ins, allowing the
  system to operate without new Blender exports.

## Acceptance evidence

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
PHASE1-BOOT-OK: cockpit + chair pivot + Senso-Globes + probe + tow + 15 asteroids
PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace
COMBAT-RUNTIME-OK: FrapRay + proton torpedo + breakup + fragment vaporization + dust
```

## Known follow-up work

- Replace procedural fragment stand-ins with production asteroid fragment
  variants when their canonical Blender models are available.
- Add firing, impact, breakup, and vaporization audio.
- Tune weapon cadence, ammunition, asteroid integrity, fragment velocity, and
  dust lifetime through hands-on playtesting.
- Add hostile targets, shields, and ship damage only in a later combat-focused
  mission; they are outside this demo milestone.
