---
title: Resources
created: 2026-07-05T14:33:30-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: reference
production_area: operations
department: production
status: active
canonical: true
canonical_for: resource_policy
wiki: true
wiki_group: Standards
wiki_page: Resources
wiki_order: 50
---
# Resources needed to get started

## Software (install on the primary machine)

- **Blender** — latest LTS. Primary DCC.
- **Godot 4.x** — realtime playback/runtime.
- **Python 3.11+** — schema, resolver, validator, exporters. Use a project virtualenv.
- **OpenUSD tooling** — `usd-core` via pip for a start; full OpenUSD build if needed.
- **Local LLM runtime** — llama.cpp or equivalent, plus one small-to-mid model that fits the primary machine's memory.
- **glTF tooling** — bundled with Blender/Godot; verify round-trip.
- **git** — version control.
- **MPFB (MakeHuman)** — Blender extension for humanoid base characters. Since 2.0.8 install via the extension platform (https://extensions.blender.org/add-ons/mpfb/), not a standalone zip. Headless install:
  `Blender --online-mode --command extension install -s -e blender_org.mpfb`

## Hardware

Machine inventory and roles live in `docs/local/MACHINE-NOTES.md` (local
only, gitignored). Summary: one Apple-silicon primary dev/authoring machine
(not a render farm), one secondary portable, one optional render node later.

## Asset sources

Starter stack: **Poly Haven, Quaternius, MakeHuman / MPFB, Kenney.**

| Source | Strength | License position |
|---|---|---|
| Poly Haven | Textures, HDRIs, environment support | CC0-friendly default |
| Kenney | Prototype-friendly stylized assets | CC0-friendly default |
| Quaternius | Low-poly environments, modular kits | CC0-friendly default |
| MakeHuman / MPFB | Base humanoid characters | Strong fit for reusable performers |
| BlenderKit | Convenience layer inside Blender | Approved supplement; not cleanest pure OSS base |
| Sketchfab | Broad catalog | Approved; per-asset license vetting |
| OpenGameArt | Mixed | Use with aggressive license filtering |
| Mixed marketplaces | Mixed | Caution: style drift + license inconsistency |

## Acquisition/licensing policy

- **Tier 1 (default):** CC0 assets wherever possible.
- **Tier 2 (exceptions):** royalty-free with clear records and approved provenance.
- **Tier 3 (blocked / review required):** attribution-heavy without tracking, undesired share-alike, GPL-style art complications, unclear provenance.

Record provenance + license for every acquired asset.
