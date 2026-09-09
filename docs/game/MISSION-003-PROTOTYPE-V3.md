---
title: JourneyBlaster Mission 003 Starbase Defense Prototype V3
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_mission_003_prototype_v3
wiki: false
---
# Mission 003 — Starbase Defense Prototype V3

Declared complete on 2026-09-09. Prototype V3 gives the pilot more time to
launch and understand the battle by replacing stationary target circling with
discrete, readable pirate strafing runs.

## Attack pattern

- Each flyer moves to an ingress point outside the station before attacking.
- It commits to a tangential lane, takes one shot near the assigned target,
  and continues past the station to a distant egress point.
- From egress it circles back into a new ingress and attacks from the opposite
  direction, producing an alternating sequence of passes.
- Damage cadence is therefore governed by the time required to fly a complete
  pass rather than a short repeating weapon timer.
- The same pass vocabulary is retained when a flyer is reassigned to the
  JB100, while safe-hangar behavior remains unchanged.

## Defensive-fire awareness

Green starbase plasma is no longer ignored by pirate navigation. Each flyer
predicts the closest approach of nearby station-defense bolts. A bolt on an
intercept course adds a temporary evasive vector to the flyer's steering, so
even inaccurate defensive fire influences the attack pattern.

## Acceptance coverage

The Mission 003 runtime test verifies that all three flyers move to ingress,
that ingress-to-target and target-to-egress vectors form one continuous pass,
that a flyer creates exactly one projectile during that pass, and that an
intercepting starbase bolt produces a nonzero evasive response. All previous
Mission 001–003 acceptance checks remain part of the regression suite.
