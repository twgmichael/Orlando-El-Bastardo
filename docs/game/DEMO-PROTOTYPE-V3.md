---
title: JourneyBlaster Demo Prototype V3
created: 2026-09-08T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_demo_prototype_v3
wiki: false
---
# JourneyBlaster — Demo Prototype V3

Declared complete on 2026-09-08. V3 contains the complete V2 retrieval and
asteroid-combat prototype and adds consequential mining-probe damage.

## Probe consequences

- A JB100 collision damages the probe's data port and cancels or prevents the
  data download.
- Collision cannot destroy the probe. Its physical hull remains visible and
  can still be taken in tow, returned to the entry boundary, and recovered.
- A FrapRay or proton-torpedo hit destroys the probe immediately in an
  expanding orange flash and dust burst.
- Destroying the probe detaches any tow, marks the Senso-Globe target
  destroyed, and transitions Mission 001 to `FAILED`.
- The JB100 remains freely flyable after failure; `R` restarts the mission
  when the player chooses.

## Runtime architecture

- The probe contract declares a dedicated `probe_destructible.gd` controller
  instead of inheriting asteroid breakup behavior.
- The mission contract explicitly requires collision damage to disable
  download, preserves towing for a damaged probe, and declares `FAILED` as the
  weapon-destruction result.
- The player impact signal includes the collider, allowing Mission 001 to
  distinguish a probe strike from ordinary asteroid impacts.
- Projectile swept-ray collision calls the same weapon-hit protocol already
  used by asteroids, so both weapon types apply the probe consequence without
  special cases in weapon code.

## Acceptance evidence

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
PHASE1-BOOT-OK: cockpit + chair pivot + Senso-Globes + probe + tow + 15 asteroids
PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace
COMBAT-RUNTIME-OK: FrapRay + proton torpedo + breakup + fragment vaporization + dust
PROBE-DAMAGE-RUNTIME-OK: collision disables download + tow survives + weapon destruction fails mission + post-failure free flight
```

## Known follow-up work

- Add authored probe debris and dedicated collision, alarm, and explosion
  audio.
- Tune the minimum damaging collision speed and visual damage language through
  hands-on playtesting.
- Decide whether later missions distinguish data loss from physical-object
  recovery in their scoring and debrief systems.
