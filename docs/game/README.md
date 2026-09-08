---
title: Interactive Game Documentation
created: 2026-08-24T00:00:00-04:00
updated: 2026-08-24T00:00:00-04:00
doc_type: reference
production_area: interactive
department: production
status: active
canonical: true
canonical_for: game_documentation_index
wiki: false
---
# Interactive Game Documentation

OEB Interactive extends the existing Studio with a Godot runtime. It does not
replace the production pipeline or create an independent asset library.

## Active documents

- [DEMO-PROTOTYPE-V2.md](DEMO-PROTOTYPE-V2.md) — current playable milestone,
  including asteroid combat and destruction.
- [DEMO-PROTOTYPE-V1.md](DEMO-PROTOTYPE-V1.md) — declared playable milestone,
  included feature set, acceptance evidence, and known follow-up work.
- [MISSION-001-PLAN.md](MISSION-001-PLAN.md) — architecture, mission flow,
  milestones, contracts, validation gates, and acceptance criteria for the
  first JourneyBlaster mission.
- [../../GAME-TODO.md](../../GAME-TODO.md) — ordered implementation roadmap.

## Governing boundary

The Studio owns canonical geometry, materials, animation, attachment points,
asset identity, production variants, and exports. Godot owns input, flight,
collision response, sensors, interaction, mission logic, and runtime state.

Generated Godot staging files carry hashes and provenance. They are disposable
runtime inputs, never canonical production assets.
