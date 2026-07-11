# Orlando-El-Bastardo

Deterministic 3D animation pipeline: a local LLM translates story intent into
schema-validated scene specs, resolved against approved assets and exported to
Blender, Godot, and USD. Asset- and rig-based, no generative video. Built and
verified by a tiered roster of qualified LLM agents. PolyForm Noncommercial
1.0.0 license.

A screenplay goes in one end; rendered scenes, an episode cut, and an honest
ticket list of everything the asset library still lacks come out the other —
one command, no prompting, no improvisation.

## Documentation

- **[Project wiki](https://github.com/twgmichael/Orlando-El-Bastardo/wiki)** —
  the readable tour: architecture, schema design, standards, plans, and the
  project journal. Mirrored from `docs/` by `tools/sync_wiki.py`.
- **[`docs/`](docs/README.md)** — the canonical source, version-locked to the
  code: [architecture](docs/ARCHITECTURE.md), [schema](docs/SCHEMA.md),
  [rigging standard](docs/RIGGING.md), [asset provenance](docs/PROVENANCE.md),
  [locked decisions](docs/DECISIONS.md), and the plans under
  [`docs/planning/`](docs/planning/).
- **[PROJECT-TODO.md](PROJECT-TODO.md)** / **[PROJECT-DONE.md](PROJECT-DONE.md)**
  — the living roadmap and the day-by-day build journal.

## How it works, in one paragraph

`tools/producer.py --script scripts/<episode>/<script>.md` parses an industry
screenplay deterministically (sluglines, shots, dialogue — no LLM in
structure), sweeps its vocabulary against the asset library (stand-ins render
now and ticket the real asset; unknowns block with a NEEDED ticket), has the
local LLM condense each scene's action into beat descriptions, then runs every
scene through the validated pipeline: intent → resolver → validator → Blender
export → render → QA → episode cut with a production report.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md) — Copyright 2026 Michael Sweeney.
Third-party CC0 asset sources are recorded in
[docs/PROVENANCE.md](docs/PROVENANCE.md).
