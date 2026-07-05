# PROJECT-TODO — Orlando El Bastardo

3D animation orchestration pipeline. Deterministic, asset/rig-based. LLM is a
translator/constraint layer, not a writer. No generative video.

Status: Phases 0, 1, 2A, and 3 complete — the intent → resolver → validator
chain runs end-to-end against the placeholder scene. Next code work: Phase 4
(exporters; worker profiles need authoring first). Phase 2 (real assets) is
gated on human asset selection and can run in parallel. See `docs/` and
PROJECT-DONE.md for detail.

Priorities are ordered highest-first within each phase. Check items off by moving
them to `PROJECT-DONE.md` with a date.

---

## Carryover notes (updated 2026-07-05)

- **Local LLM (Qwen2.5-3B-Instruct Q4) is provisional.** Installed and inference-
  verified, but not yet vetted for the SceneIntent→SceneSpec task. Treat as a
  placeholder pick; re-evaluate at Phase 5.
- **Assistant model / workflow** (decided 2026-07-04, see AGENT-WORKFLOW-PLAN +
  DECISIONS): the reviewer tier orchestrates day-to-day with qualified worker-tier agents;
  the author tier is recalled only to author or revise agent profiles. No Phase 3
  worker profile exists yet — under this workflow, authoring one is the first
  step of Phase 3.
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

- [ ] Acquire bar interior set (`set_bar_small_A`, night variant) — CC0 first
- [ ] Acquire/build 2 characters (`char_hero_v1`, `char_bartender_v1`) via MakeHuman/MPFB
- [ ] Acquire props (counter, stool, glass tumbler, bottle) — Quaternius/Kenney/CC0
- [ ] Re-place set marks/spawn points in the real set (hero_entry_A, hero_barstool_A, bartender_idle_A, bartender_backbar_A)
- [ ] Build/acquire 6–10 reusable animation clips per the hero/bartender lists (blocked on the animation naming/retargeting open question)
- [ ] Record asset provenance + license for every item (acquisition policy in docs/RESOURCES.md)

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

## Phase 4 — Exporters

Design input carried over from the animated-preview test (2026-07-05): a
`(frame, location, heading)` waypoint list worked as the motion
representation between intent verbs and Blender keyframes — consider it for
the exporter cue→keyframe stage (see
docs/planning/PROGRESS-2026-07-05-ANIMATED-PREVIEW.md). Motion grammar will
need elevation-changing verbs (sit/stand/lean), not just horizontal moves.
Worker profiles for the exporters need author-tier authoring first
(AGENT-WORKFLOW-PLAN §6 suggests one `exporter-dev` profile parameterized by
target).

- [ ] Author + qualify exporter worker profile(s) (author tier)
- [ ] Blender exporter (scene name, linked collections, cameras, timeline markers, action assignments by frame, audio strips, render settings)
- [ ] Godot exporter (.tscn, actor nodes, set instance, camera rig nodes, SceneDirector controller, event timeline resource)
- [ ] USD exporter (root layer, set/character/prop references, camera prims, timeline sidecar JSON)

## Phase 5 — First integration test

- [ ] Run full pipeline on the bar scene end-to-end
- [ ] Human review pass in Blender and Godot
- [ ] Wire local LLM to emit SceneIntent for the bar scene and run it through the pipeline
- [ ] Vet the local translator LLM against the SceneIntent→SceneSpec task; replace provisional Qwen2.5-3B if it underperforms

---

## Open questions (resolve before/as they block work — see docs/OPEN-QUESTIONS.md)

Four of six were decided 2026-07-04 and are recorded in docs/DECISIONS.md +
PROJECT-DONE.md: seated-only v0; explicit dialogue durations
(`DialogueCue.duration` required); camera grammar as JSON data; LLM emits
SceneIntent only.

- [ ] First animation naming convention + retargeting standard? (blocks the Phase 2 clip-acquisition item)
- [ ] v1 lipsync: none, coarse mouth states, or phoneme/viseme?

---

## Eventually (no date, not blocking)

- [ ] Add a separate Backup drive and mirror the external asset library + project source to it (see docs/local/STORAGE-PLAN.md, local only). Until then the library drive has zero redundancy — do not put un-redownloadable data on it.
