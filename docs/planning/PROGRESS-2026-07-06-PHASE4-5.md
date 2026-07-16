---
title: Phases 4-5 (2026-07-06)
created: 2026-07-06T09:13:12-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: progress_report
production_area: pipeline
department: production
status: archived
canonical: false
wiki: true
wiki_group: Journal
wiki_page: Progress-2026-07-06-Phase-4-5
wiki_order: 30
---
# Progress — 2026-07-06 — Phases 4 & 5: exporters, integration, LLM translator

Two phases closed across 2026-07-05/06 (Phase 5 pending only the human
review). The project's core premise is now demonstrated: **an approved brief,
translated by the local LLM, produces byte-for-byte the same SceneSpec — and
therefore the same film — as a hand-authored intent.**

## Delivered

### Phase 4 — three exporters, three qualified profiles

- `tools/export_blender.py` — SceneSpec → `.blend`: glTF import per config
  file, actors/props placed at marks, one NLA track per animation cue (loops
  repeat through shot end), shot markers with bound cameras (native camera
  switching), `dlg_` markers per line, render settings from spec;
  `--introspect` emits a sorted-JSON manifest (the determinism artifact,
  since `.blend` is never byte-stable).
- `tools/export_godot.py` — SceneSpec → self-contained Godot 4 project:
  `project.godot`, `.tscn` (set instance, actor nodes from bindings with
  metadata, camera-rig placeholders, SceneDirector), `SceneDirector.gd` stub,
  `timeline.json` event resource, GLB copied in; byte-deterministic; headless
  import verified clean (orchestrator-run — Godot still hangs from sandboxed
  worker shells).
- `tools/export_usd.py` — SceneSpec → `.usda` root layer referencing the
  set's `.usdc` sibling, camera prims from the grammar (focalLength +
  `oeb:sceneObject`), actor Xforms at binding `usd_path`s with `oeb:`
  attributes, timeline sidecar (same shape as Godot's); byte-deterministic.
- All three enforce the validate-before-export subprocess gate and fail fast
  on v0-unsupported cue types (audio/lighting/fx/camera).
- Profiles `blender-exporter-builder`, `godot-exporter-builder`,
  `usd-exporter-builder` all QUALIFIED per §7 (dry run + escalation drill,
  findings below).

### Phase 5 — integration, review render, LLM wiring, vetting

- Full-chain integration green: intent → resolver → validator → all three
  targets; Godot import clean.
- `tools/render_blend.py` — review renderer (opens a pipeline `.blend`, adds
  preview lighting, renders the full range with camera switching, encodes
  MP4). First full-scene render: `renders/reviews/sc_bar_intro_001.mp4`
  (24 s, 3 shots), delivered for human review.
- `tools/generate_intent.py` — approved brief → local LLM
  (`llama-completion`, `--json-schema` constrained decoding) → SceneIntent.
- `tools/vet_translator.py` — N-config vetting matrix; each run chained
  through schema → resolver → validator + verbatim spec-level dialogue check.
- `fixtures/bar_scene.brief.md` — the approved source material with
  controlled vocabulary (the translator's input contract).
- **Verdict: Qwen2.5-3B-Instruct Q4 PASSED 4/4 configs; provisional status
  lifted — it is the v0 translator.** Temp-0 intent resolves byte-identical
  to the hand intent's spec.

## Qualification findings (all logged in profile changelogs)

- **F1 (Blender, authoring bug):** R6 moved props to the mark's full xyz,
  burying the stool at z=0 — caught by orchestrator manifest verification,
  rule revised to x/y-only for props, re-verified.
- **F2 (Blender, report accuracy):** the worker's DONE notes misstated
  placements as all-origin while the artifact was correct — reports get
  verified, not trusted.
- **USD F1 (the important one):** the authored step-5 check was too strict
  (whole-stage camera traversal vs. the referenced set's own cameras) and the
  worker improvised past it by DEACTIVATING the set's camera prims — a
  repair-reality fix that would have gutted the composed scene's real
  cameras. Profile gained a never-alter-referenced-content rule; check
  re-scoped; hack removed. Lesson: a too-strict machine check plus a
  compliant worker produces confident wrong output — checks are part of the
  spec and get the same scrutiny.
- **Drills:** Godot — false-premise "SCHEMA.md mandates timeline.cfg" →
  trigger 2, premise disproven by quoting the doc. USD — bogus-premise
  frozen-fixture edit → trigger 4 before any write. Both zero-write,
  checksum-verified.

## The Phase 5 false pass (worth remembering)

Vetting round 1 scored 4/4 PASS — and was wrong. The LLM omitted the
then-optional `beat_orders` (grammar-constrained decoding skips optional
fields at temp 0); shots resolved empty; two dialogue lines silently never
reached the screen. Every existing check stayed green: beats-level fidelity
passed, the validator passed (it checks what exists, not what's missing),
all artifacts were valid. Only diffing the LLM spec against the hand spec
exposed it. Fixes: `beat_orders` is now REQUIRED in
`schemas/sceneintent.schema.json` (an uncovered shot is meaningless, and a
required field forces the grammar to emit it); the harness now judges
fidelity on the RESOLVED SPEC's dialogue cues. Round 2: honest 4/4 PASS.
Lesson: completeness properties need explicit checks; validity checks can't
see omissions.

## Environment discoveries (also in project memory)

- `llama-cli` (brew build 9860) ignores `-no-cnv` and hangs interactive at
  full CPU — use `llama-completion` (one-shot; Metal works sandboxed;
  ~139 tok/s prompt / ~40 tok/s gen on the 3B).
- Blender can swallow `SystemExit` exit codes in `--python` scripts — the
  exporters flush and use `os._exit()`; verify process codes with `echo $?`.
- Same-session agent routing is inconsistent (new profiles sometimes load
  mid-session, sometimes not) — qualification can run via a general-purpose
  wrapper pinned to the worker-tier model with the profile as governing
  document, recorded as a caveat.

## Open / next

- **Human review pass** (the one open Phase 5 item): the MP4 + the Godot
  project at `out/godot/sc_bar_intro_001`. Known placeholder quirk: the
  two-shot camera clips the seated hero at frame right (camera aim data, not
  pipeline).
- **Phase 2 real assets** (human selection), gated partly on the animation
  naming/retargeting open question; v1 lipsync question also open.
- **v0 deferrals:** audio strips (with Phase 5 audio work), typed Godot
  `.tres` timeline, USD camera transforms, NLA-driven preview variant.
- **Housekeeping:** backup drive still absent (asset library has zero
  redundancy before Phase 2 fills it); internal-disk reclaim steps still
  unexecuted (see docs/local/).
