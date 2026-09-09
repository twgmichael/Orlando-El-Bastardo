---
title: JourneyBlaster Mission 003 Starbase Defense Prototype V2
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_mission_003_prototype_v2
wiki: false
---
# Mission 003 — Starbase Defense Prototype V2

Declared complete on 2026-09-09. Prototype V2 preserves the full Starbase
Defense V1 encounter and corrects the pirate flyers appearing stationary.

## Movement correction

The pirate flyer wrapper is an `AnimatableBody3D`. Its default physics
transform synchronization was restoring the prior transform after each
scripted AI update, so the flight logic ran without producing visible travel.
The flyer now disables that synchronization at startup, leaving its fuzzy AI
in sole control of movement and rotation.

## Acceptance coverage

The Mission 003 runtime test records all three pirate positions, runs live AI
for several physics frames, and requires every flyer to move before continuing
with the deterministic combat and mission-state checks. This protects the
visible flight behavior from regressing while retaining all V1 acceptance
coverage.

## Inherited V1 experience

Prototype V2 retains the JB100 hangar launch, distant planet-and-moon vista,
three hidden pirate objectives, nine station targets, station defense and
friendly fire, pursuable retreat and hyperspace departure, safe hangar,
post-result free flight, and `R` restart behavior documented in
[MISSION-003-PROTOTYPE-V1.md](MISSION-003-PROTOTYPE-V1.md).
