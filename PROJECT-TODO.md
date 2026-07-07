# PROJECT-TODO — Orlando El Bastardo

3D animation orchestration pipeline. Deterministic, asset/rig-based. LLM is a
translator/constraint layer, not a writer. No generative video.

Status: **Phases 0–5 COMPLETE**; Phase 2 well underway — characters (1999
salvage) and the set (CC0 kit build) are real, the CC0 asset stack is
converted and registered, and the skeleton standard is locked
(docs/RIGGING.md). Three asset generations have rendered through the
unchanged pipeline. Remaining Phase 2: bar furniture, character v2 on
`oeb_humanoid_v1` + UAL clip remap, night lighting variant. See
docs/planning/PROGRESS-2026-07-06-PHASE4-5.md and PROJECT-DONE.md.

Priorities are ordered highest-first within each phase. Check items off by moving
them to `PROJECT-DONE.md` with a date.

---

## Carryover notes (updated 2026-07-05)

- **Local LLM (Qwen2.5-3B-Instruct Q4) is CONFIRMED** (2026-07-06): passed
  Phase 5 translator vetting 4/4 configs (schema, pipeline, verbatim
  spec-level dialogue); temp-0 output resolves byte-identical to the
  hand-authored intent's spec. No replacement needed for v0.
- **Assistant model / workflow** (decided 2026-07-04, see AGENT-WORKFLOW-PLAN +
  DECISIONS): the reviewer tier orchestrates day-to-day with qualified
  worker-tier agents; the author tier is recalled only to author or revise
  profiles. Roster as of 2026-07-06: 8 qualified profiles (placeholder,
  verifier, reviewer, resolver, validator, and the three exporter builders —
  see `.claude/agents/`). Phase 2 asset work is human-driven and needs no new
  profiles; any Phase 6+ code work starts with author-tier profile authoring.
- Placeholder-asset track (2026-07-03 note) is complete — see Phase 2A in
  PROJECT-DONE.md. Real CC0 assets remain a later drop-in (Phase 2).

---

## Phase 0 — Workstation setup — DONE 2026-07-03/04 (see PROJECT-DONE.md)

Blender 5.1.2, Godot 4.7, Python 3.14.5 venv (+ usd-core, jsonschema,
pygltflib, imageio-ffmpeg), llama.cpp + Qwen2.5-3B, MPFB, git repo, glTF
round-trip verified in both Blender and Godot.

## Phase 1 — Canonical schema (the spine) — DONE 2026-07-04 (see PROJECT-DONE.md)

All schemas in `schemas/` (draft 2020-12), fixtures in `fixtures/`, camera
grammar in `data/camera_grammar.json`, asset resolution in `oeb.config.json`
(+ `OEB_ASSET_ROOT` env override). Verified by pipeline-verifier CHECK-1 ×4.

## Phase 2A — Placeholder assets — DONE 2026-07-04 (see PROJECT-DONE.md)

`tools/make_placeholders.py` generates and exports the full grey-box scene;
verified in Blender (re-import) and Godot 4.7 (headless `--import`, clean).

## Phase 2 — Bar-scene asset pack (real assets, replaces placeholders later)

Already covered elsewhere: camera grammar vocabulary was defined in Phase 1
(`data/camera_grammar.json`); placeholder set marks with the canonical `_A`
IDs exist from Phase 2A — the real set only needs them re-placed in its
geometry.

Characters DONE 2026-07-06 — not via MakeHuman/MPFB but by salvaging the
original 1999/2000 Infini-D assets (see PROJECT-DONE.md): `guy.dxf` →
`assets/characters/oeb_guy_characters.glb` (both `char_hero_v1` blue and
`char_bartender_v1` green from the same geometry, 5-bone armatures, all 12
clips, GLB+USDC); config swapped; test scene rendered. MPFB remains an
option for future distinct characters. Provenance: original works by the
project owner (1996–2003) — no external license needed.

Set DONE 2026-07-06 — built programmatically from the CC0 Modular Sci-Fi kit
(`tools/build_scifi_bar.py` → `assets/sets/bar_scene_scifi.glb`, canonical
node + marks/cameras carried over; see PROJECT-DONE.md). Night-variant
lighting pass still pending. Marks re-placement: not needed — positions
carried verbatim. Provenance register DONE (docs/PROVENANCE.md, all items
recorded). Clip acquisition UNBLOCKED: skeleton decided (docs/RIGGING.md) and
the CC0 Universal Animation Library (43 clips, same skeleton) is on disk.

- [ ] Acquire/kitbash real bar furniture (counter, stool, glass, bottle) —
  grey-box props now visibly out-place against the detailed set
- [ ] Character v2: build hero/bartender from Universal Base Characters on
  `oeb_humanoid_v1` + remap UAL clips to the canonical clip IDs
  (docs/RIGGING.md §4–5; needs `data/bone_maps/` starters + asset-build tool)
- [ ] Night-mood lighting variant for the sci-fi bar (variant_night is still
  a tag only; current review lighting is bright/clinical)

## Optional — Animated preview (nice-to-have, any time after 2A)

Object-motion variant DONE 2026-07-05 (`tools/render_anim_preview.py`,
waypoint-keyed hero walk/turn/sit — see PROJECT-DONE.md).

- [ ] NLA-driven variant: same renderer playing the placeholder keyed actions
  (e.g. hero `idle_seated_relaxed` + bartender `wipe_glass_loop`) instead of
  object motion

## Phase 3 — Resolver + validator — DONE 2026-07-05 (see PROJECT-DONE.md)

Resolver: `tools/resolve_intent.py` + `data/resolver_map.json`. Validator:
`tools/validate_spec.py` (checks V1–V12 incl. the three warning types;
GLB contents via pygltflib are ground truth). Intent → resolver → validator
chain verified end-to-end on the bar-scene fixture. Both worker profiles
(`resolver-builder`, `validator-builder`) QUALIFIED and in the roster;
validator-builder's failed drill 1 produced the protocol-wide "profile
outranks the task" rule.

- [ ] Gitignore `out/` (human git action) before more resolver output lands

## Phase 4 — Exporters — DONE 2026-07-06 (see PROJECT-DONE.md)

Design input carried over from the animated-preview test (2026-07-05): a
`(frame, location, heading)` waypoint list worked as the motion
representation between intent verbs and Blender keyframes — consider it for
the exporter cue→keyframe stage (see
docs/planning/PROGRESS-2026-07-05-ANIMATED-PREVIEW.md). Motion grammar will
need elevation-changing verbs (sit/stand/lean), not just horizontal moves.
Worker profiles for the exporters need author-tier authoring first
(AGENT-WORKFLOW-PLAN §6 suggests one `exporter-dev` profile parameterized by
target).

Blender exporter DONE 2026-07-05 (`tools/export_blender.py` — see
PROJECT-DONE.md): scene name, cameras via marker binding, shot + dialogue
timeline markers, action assignments as per-cue NLA strips, render settings,
actor/prop placement at marks, validate-before-export gate, deterministic
introspection manifest. v0 boundaries: audio/lighting/fx/camera cues fail
fast (audio strips land with Phase 5 audio work); assets imported, not
linked. Profile `blender-exporter-builder` QUALIFIED 2026-07-05.

Godot exporter DONE 2026-07-06 (`tools/export_godot.py` — see
PROJECT-DONE.md): self-contained importable project (.tscn with set
instance, actor + camera-rig nodes, SceneDirector node), SceneDirector.gd
stub, timeline.json event resource, GLB copied in; headless import verified
clean. USD exporter DONE 2026-07-06 (`tools/export_usd.py`): .usda root
layer referencing the set .usdc, camera prims from the grammar, actor prims
at binding usd_paths, timeline sidecar; composed stage verified. Profiles
`godot-exporter-builder` and `usd-exporter-builder` QUALIFIED 2026-07-06.
All three exporters share the validate-before-export gate and byte-
deterministic verification artifacts. Phase 4 v0 boundaries: audio/lighting/
fx/camera cues fail fast everywhere; typed Godot .tres resource and USD
camera transforms deferred.

## Phase 6 — The Producer (script → rendered scenes, provided assets only)

Plan: docs/planning/PRODUCER-PLAN.md (recorded 2026-07-07). The local LLM is
now "the producer" — it oversees script → render using ONLY the provided
asset library, and emits an obvious structured NEEDED report when a script
names anything the library lacks. Building assets stays human + crew work.

- [ ] P1 Production reports — ticketing DONE 2026-07-07 (`tools/tickets.py`
  + `run_pipeline.py --episode`, exit 4 = BLOCKED, NEEDED .json/.md +
  report.json index; all paths tested). Remaining: render QA gates,
  run-time translation fidelity gate, validator name-extraction polish
- [ ] P2 Script desk: script → scene-brief chunking (constrained LLM
  extraction), per-scene runs, episode assembly + config snapshot
- [ ] P3 Producer driver (`tools/producer.py`): the deterministic loop,
  halt-and-report policy, final production report
- [ ] P4 Producer qualification: dry run (in-library script → all scenes
  rendered) + missing-asset drill (clean NEEDED report, no improvisation)

## Phase 5 — First integration test — DONE 2026-07-06 (see PROJECT-DONE.md)

Pipeline run, LLM wiring, and translator vetting DONE 2026-07-06: full chain
green on all three targets; Qwen2.5-3B PASSED vetting 4/4 configs and is the
v0 translator. Human review ACCEPTED 2026-07-06 — scoped as proof of concept
for the static-shot test (grey-box placeholders, fixed cameras); production
sign-off waits on Phase 2 real assets. Phase 5 closed.

---

## Open questions (resolve before/as they block work — see docs/OPEN-QUESTIONS.md)

Four of six were decided 2026-07-04 and are recorded in docs/DECISIONS.md +
PROJECT-DONE.md: seated-only v0; explicit dialogue durations
(`DialogueCue.duration` required); camera grammar as JSON data; LLM emits
SceneIntent only.

- [x] First animation naming convention + retargeting standard? — DECIDED
  2026-07-06: `oeb_humanoid_v1` (UE-mannequin/Quaternius; docs/RIGGING.md).
  Unblocks the Phase 2 clip work.
- [ ] v1 lipsync: none, coarse mouth states, or phoneme/viseme?

---

## Eventually (no date, not blocking)

- [ ] Add a separate Backup drive and mirror the external asset library + project source to it (see docs/local/STORAGE-PLAN.md, local only). Until then the library drive has zero redundancy — do not put un-redownloadable data on it.
