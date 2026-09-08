---
title: JourneyBlaster Demo Prototype V1
created: 2026-09-08T00:00:00-04:00
updated: 2026-09-08T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_demo_prototype_v1
wiki: false
---
# JourneyBlaster — Demo Prototype V1

Declared complete on 2026-09-08.

Demo Prototype V1 is the first complete playable Mission 001 loop. The player
sits inside the local JB100 v38 hero stand-in, navigates the asteroid field,
uses the hull-mounted Senso-Globes to locate and identify the mining probe,
downloads its data, takes the probe in tow, returns to the entry boundary, and
engages hyperspace.

## Included

- Local JB100 v38 cockpit and exterior visual
- Damped six-axis arcade flight with keyboard, pointer, and gamepad paths
- Left/right turning on `A` / `D` and `←` / `→`
- Independent pilot-chair view with five detents and free 360-degree yaw
- Exterior-first 60/40 cockpit framing and corrected forward-up view
- Fifteen-obstacle asteroid field using five replaceable placeholder variants
- Progressive active/passive Senso-Globe contact resolution
- Probe identification, safe approach, interruptible data download, physical
  tow, return validation, hyperspace completion, and restart
- Mission HUD, cockpit telemetry, deterministic starfield, probe beacon, and
  visible tow beam

## Acceptance evidence

```text
INTERACTIVE-VALIDATION-OK assets=7 missions=1
INTERACTIVE-SYNC-OK assets=7 missions=1
PHASE1-BOOT-OK: cockpit + chair pivot + Senso-Globes + probe + tow + 15 asteroids
PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace
PERFORMANCE-OK: 1920x1080, 86.4 measured FPS, 89.5 sampled average FPS
```

## Known follow-up work

- Replace placeholder asteroids when the external canonical asset drive is
  available.
- Separate the joined JB100 chair/frame/control geometry for an unobstructed
  straight-back view and animated cockpit controls.
- Add restrained engine, beacon, download, impact, tow, and hyperspace audio
  and visual feedback.
- Add local playtest telemetry and complete formal control-comprehension and
  mission-completion playtests.
- Improve the external tow camera framing and label a 180-degree sensor bearing
  as aft.

This milestone is a declared project state, not a packaged release. Canonical
assets remain in the Studio asset tree; Godot runtime staging remains generated.
