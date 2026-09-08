---
title: JourneyBlaster Demo Prototype V4
created: 2026-09-08T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_demo_prototype_v4
wiki: false
---
# JourneyBlaster — Demo Prototype V4

Declared complete on 2026-09-08. V4 retains the complete V3 mission and adds a
smoother, consistently ship-relative flight-control model.

## Control refinements

- Keyboard and arrow pitch/yaw ease into and out of full deflection over a
  short, responsive ramp.
- Pitch, yaw, and roll rotate around the JB100's local right, up, and forward
  axes. The controls do not flip into world-relative behavior when inverted.
- Left-mouse drag maps pointer pixels directly to angular input rather than
  multiplying them by the physics-frame duration.
- Mouse motion receives a short exponential filter for smoothness and a
  per-tick safety clamp against accidental pointer jumps.
- Clicking or releasing clears queued and filtered mouse motion, guaranteeing
  that a second drag has the same response as the first.
- A failed mission leaves these flight controls active in the current scene;
  `R` remains the explicit restart command.

## Tunable values

The JB100 controller exposes keyboard steering response, mouse sensitivity,
and mouse smoothing as exported properties. They can be tuned after hands-on
playtesting without changing the control algorithm.

## Acceptance evidence

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
FLIGHT-CONTROLS-RUNTIME-OK: smooth arrows + ship-local inverted axes + repeatable mouse drag
PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace
COMBAT-RUNTIME-OK: FrapRay + proton torpedo + breakup + fragment vaporization + dust
PROBE-DAMAGE-RUNTIME-OK: collision disables download + tow survives + weapon destruction fails mission + post-failure free flight
```
