---
title: JourneyBlaster
created: 2026-07-13T19:47:00-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: design_record
production_area: vehicles
department: art
status: active
canonical: true
canonical_for: journeyblaster_design
wiki: true
wiki_group: Design
wiki_page: JourneyBlaster
wiki_order: 40
---
# JourneyBlaster — ship design record (JB5K + JB100)

Recorded 2026-07-13. The Yakara Starcraft sport-attack line, rebuilt from
primitives as deterministic build scripts (`tools/build_jb5k.py`,
`tools/build_jb100.py`; every measurement an editable constant). Owner's
original 1995 Infini-D designs; Tier 1 provenance.

## Research & discovery

- Sources: 10 reference renders (2000–2001, incl. 4K frames) in local
  reference storage; the 1995 Infini-D source folder (scene files remain
  locked). Reference sheets read aft-LEFT / fore-RIGHT.
- The original was built as TWO HALVES, not one obloid: a short
  flat-bottom bowl below and a flatter top shell that overhangs it
  (slight lip), the overlap hiding the seam — the signature edge.
- The side view's "boom" is the ENGINE in profile (no aft antenna
  exists); the front view's "grommets" are the frap-ray muzzle rings.
- Render pipeline discovery: Blender's AgX view transform desaturates
  the era-correct vibrant colors (senso-globe yellow washed to cream);
  preview rigs use the Standard transform. Scene renders will face the
  same choice.
- Scale discovery: the salvaged DXF guy stands 1.70 m, the dressed hero
  1.82 m; the DXF rig barely bends when "seated," so furniture sized to
  him dwarfed the hero. Cockpit furniture is sized to the DRESSED hero.
  Verified in motion 2026-07-13: pilot renders correctly seated in the
  JB100 cockpit in both `tmp_jb100_space_action.py` and
  `tmp_jb100_barrel_roll.py`.
- Library gap: no sci-fi chairs exist in any CC0 pack (House Interior's
  four wooden dining chairs + stool only).

## Decisions (owner canon)

| Topic | Decision |
|---|---|
| Hull | Two halves; flat-bottom bowl + aft-swelling top shell with lip overhang; JB100 adds a CONCAVE belly recess (0.1 deep, r 2.85) |
| Bubble | Hollow PERFECT half-globe, no rim extrusion, rides high, seals inside the ribbed tub at the cup's lip (not against the red hull); < half total ship height as staging rule; thin-shell glass (zero thickness) |
| Cockpit | Circular tub: flat floor, fine vertical striping (20 shallow flutes), rounded floor corner, rim conforms to the deck with a flared lip |
| Seats | JB5K tandem two-seater; JB100 SINGLE seat. Primitives L-chair kept deliberately (simple shapes, scales with pilot). Oxygen tanks on the chair back; control panel at chest height reaching over the knees |
| Weapons | Twin frap-ray cannons lying ALONG the fore hull, muzzles straight forward inside the rim, 3 rings per barrel, exhaust ports 90° outboard |
| Engines | Twin slim pods on the aft deck pointing STRAIGHT BACK; red-cored vents, orange emissive tips; no end flange |
| Senso-globes | Four per side riding the hull profile, proudest AFT; VIBRANT YELLOW (hot core) |
| Belly | 16 white thruster discs ringing the belly near the edge; JB100: mounted inside the concave recess, nothing protruding past the hull line. Rotating thrusters (cooperative/individual) modeled as static stubs — individually animatable version needs separate nodes (later variant) |
| Conventions | Nose −Y (move-cue steerable); flat belly at z = 0; pilot/scale figures live in review rigs, never in the ship asset |
| Materials | `mat_jb100_tanks` (O2 tanks on chair back) is SEPARATE from `mat_jb100_disc` (belly thruster discs) — allows independent color overrides in render scripts (tanks currently set dark blue via `bpy.data.materials.get("mat_jb100_tanks")`) |

## Recommendations (open)

- Restore the JB5K's glass (its builder still carries the solid-white
  debug bubble) and back-port the JB100 refinements the line shares
  (concave belly, yellow globes) if the JB5K stays in service.
- Separate-node thruster/gimbal variant when flight animation lands.
- Yakara logo, hull dents ("does not respect warranties"), cockpit
  greebles — detail pass when a scene demands close-ups.
- Deep-space environment spec is locked (docs/world-building/SPACESCAPE.md)
  and confirmed working in two render scripts. Pipeline integration
  (set asset, camera marks, `setup_space_env()` shared module) is the
  remaining step before Episode 1 EXT scenes.

## Process notes

Thirty-plus review iterations, each: constant edit → deterministic
rebuild → six-view render sheet (top/bottom/port/front/back/action, plan
views framed aft-left) → owner markup. Two recurring failure modes worth
remembering: silent no-op patches (fixed — all script edits assert the
match before writing) and the two-character salvage GLB leaking the
green bartender into review rigs (fixed — strip everything not parented
to the hero).
