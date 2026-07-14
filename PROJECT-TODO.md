# PROJECT-TODO — Orlando El Bastardo

3D animation orchestration pipeline. Deterministic, asset/rig-based. LLM is a
translator/constraint layer, not a writer. No generative video.

Status: **Phases 0–6 COMPLETE** (2026-07-11) — the production run works
end-to-end: screenplay in `scripts/<episode>/`, one `tools/producer.py`
command out to rendered scenes, episode cut, and NEEDED tickets, zero
prompting. The pilot teaser (4 shots, walk-in + departure, dressed v3
characters, medium cameras) is delivered. Motion grammar v1 (move cues,
entrances/exits, NLA crossfades) landed through the whole spine. Public
front door live: wiki mirror (`tools/sync_wiki.py`), rebuilt README,
privacy audit passed. **Studio harness RUNNING** (2026-07-14): FastAPI
control plane + PostgreSQL + Ansible role on docker-pi-01; cross-platform
worker agent with OllamaAdapter + BlenderCLIAdapter (script_file + cwd +
output_root live); macOS menu bar app on the Mac mini; pipeline render
scripts dispatching and writing renders to OEB-PROJECT external drive.
Remaining Phase 2: bar furniture, night lighting variant. Next frontier:
publishing plan build (PUBLISHING-PLAN.md), pilot ticket backlog (lounge
dressing, audio), Godot/USD move-cue support, agent bus (AGENT-BUS-PLAN.md),
gaming-PC worker install.

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

## Studio harness (oeb-studio-harness) — control plane LIVE 2026-07-14

Harness spec: `docs/planning/studio-production-pipeline-harness-ansible-spec.json`.
Agent bus plan: `docs/planning/AGENT-BUS-PLAN.md` (PLANNED, not built).
Worker plan: `docs/planning/WORKER-AGENT-PLAN.md`.
Control plane on docker-pi-01 at `http://oeb-studio.docker-pi`; mac-mini
worker running with menu bar app; first job submitted and claimed end-to-end.

- [x] Install worker on Mac mini — DONE 2026-07-14 (menu bar running,
  worker registered, first job claimed)
- [x] Create first project via `POST /api/v1/projects` — DONE 2026-07-14
- [x] Add `script_file` + `cwd` payload support to BlenderCLIAdapter —
  DONE 2026-07-14; pipeline render scripts now dispatch as harness jobs
- [x] Add `output_root` per-worker config + `{output_root}` substitution —
  DONE 2026-07-14; renders write to OEB-PROJECT external drive
- [x] Expose PostgreSQL port 5432 for direct SQL client access — DONE 2026-07-14
- [ ] Install worker on gaming PC (`config-examples/gaming-pc.yml`)
- [ ] Add `pyproject.toml` to worker for clean `pip install -e .` installs
- [ ] Add `oeb-studio.docker-pi` to the `traefik_domains` list in
  project-pi-admin as a committed entry (currently added manually; should be
  declarative so it survives playbook reruns)
- [ ] Agent bus (AGENT-BUS-PLAN.md build checklist):
  - [ ] Human: create GitHub Project + add `project` scope to `gh` auth
  - [ ] `tools/agent_bus.py` (file/claim/report/block/query verbs + payload schema)
  - [ ] Label/field taxonomy in the repo/Project
  - [ ] `tickets.py` extension: NEEDED tickets also file `stream:production` issues
  - [ ] Orchestrator + worker profile amendments: bus verbs in standing instructions
  - [ ] First live run: file pilot-backlog issues, dispatch one to production designer

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
  grey-box props now visibly out-place against the detailed set (House
  Interior pack on disk is the likely donor)
- [x] Character v2 DONE 2026-07-06 (UBC + UAL remap on `oeb_humanoid_v1`),
  then v3 DRESSED 2026-07-11 (SpaceSuit hero w/ bare Casual head, Worker
  bartender; 13 canonical clips incl. stand_from_stool) — see PROJECT-DONE.md
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

- [x] Gitignore `out/` — DONE (verified in the 2026-07-11 privacy audit:
  out/, renders/, llm/, assets/, docs/local/ all ignored; no symlinks tracked)

## Phase 4 — Exporters — DONE 2026-07-06 (see PROJECT-DONE.md)

Design input carried over from the animated-preview test (2026-07-05): a
`(frame, location, heading)` waypoint list worked as the motion
representation between intent verbs and Blender keyframes — consider it for
the exporter cue→keyframe stage (see
docs/planning/PROGRESS-2026-07-05-ANIMATED-PREVIEW.md). Motion grammar will
need elevation-changing verbs (sit/stand/lean), not just horizontal moves.
→ Motion grammar v1 LANDED 2026-07-11 (see PROJECT-DONE.md): MoveCue
(mark→mark + clip + facing) through schema/resolver/validator/Blender
exporter; walk-in entrance via intent `arrives: true`. Godot/USD move
support still open.
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

- [x] P1 Production reports — DONE 2026-07-07: ticketing (`tools/tickets.py`,
  exit 4 = BLOCKED, NEEDED .json/.md + report.json index) + render QA gates
  (duration, non-black frames) + run-time translation fidelity gate
  (verbatim, one seed-retry) + scene-fact stamping in the brief path
  (last-declaration-wins). Polish left: validator name extraction
- [x] P2 Script desk DONE 2026-07-07 (`tools/script_desk.py` + script
  format; chunking made DETERMINISTIC — no LLM; structural scene facts
  stamped over the translator after it silently swallowed an unknown
  location in test 1; ep_001: 2 delivered incl. a brand-new scene verbatim,
  1 blocked with correct ticket)
- [x] P3 Producer driver DONE 2026-07-11 (`tools/producer.py` +
  `tools/screenplay.py` + `data/standins.json`): industry-screenplay
  parsing (deterministic), vocabulary sweep with stand-in+ticket policy,
  LLM scene review (beat descriptions + item inventory, constrained by
  `schemas/scenereview.schema.json`), per-scene pipeline, episode cut,
  production report — see PROJECT-DONE.md
- [x] P4 Producer qualification DONE 2026-07-11: dry run (pilot teaser →
  scene delivered end-to-end) + missing-asset drill (`rooftop_garden`
  script → clean NEEDED ticket, no improvisation, run continued)

Phase 6 CLOSED 2026-07-11. Follow-on capabilities landed same day:
departures (R14) + `travel_hold` facing; `medium_on` framing + two set
cameras; orbital-lounge stand-in. Pilot ticket backlog is the open work
(see Publishing + Pilot backlog below).

## Publishing + public surface (opened 2026-07-11)

Plan: docs/planning/PUBLISHING-PLAN.md (three-tier YouTube policy — auto
unlisted per delivered episode cut; human-curated public milestones;
iteration renders never upload).

- [ ] Human: Google Cloud project + enable YouTube Data API v3 + OAuth
  "Desktop app" client → download JSON to `.secrets/client_secrets.json`,
  then run `tools/upload_render.py --auth` once (browser); first real
  upload: re-run the pilot with `--publish`, record the URL in
  PROJECT-DONE
- [x] `tools/upload_render.py` BUILT 2026-07-11 (metadata from the
  production report incl. commit hash + scene statuses + ticket kinds;
  playlist per episode; URL recorded back into the report; `--dry-run` ✓;
  graceful not-configured exit ✓) + `producer.py --publish` hook (off by
  default, never fatal) + `.secrets/` gitignored. Note: venv scripts have
  stale shebangs since the reorg — use `.venv/bin/python -m pip`
- [x] Wiki sync AUTOMATED 2026-07-11 (`.github/workflows/wiki-sync.yml`):
  pushes to main touching docs/trackers regenerate and push the wiki
  server-side; verified live (run success, banner hash = pushed commit).
  Manual re-sync habit retired; local wiki clone is now inspection-only
  (`git pull` before use). Both plan docs mirrored.

## JourneyBlaster backlog (docs/JOURNEYBLASTER.md; opened 2026-07-13)

- [ ] Restore JB5K glass bubble (builder still has the solid-white
  debug material) + decide whether to back-port JB100 refinements
  (concave belly, yellow globes) or retire the JB5K asset
- [x] Deep-space environment: spec LOCKED 2026-07-13 (docs/world-building/
  SPACESCAPE.md) — star sphere (radius=800, Generated coords, threshold=0.75,
  emission=8) + emissive sun sphere + EEVEE bloom. Confirmed working in two
  render scripts. EEVEE Next World shader non-functional (documented).
  Pipeline integration (set asset, camera marks, prop registration) still
  pending.
- [ ] Integrate deep-space environment into the production pipeline: extract
  `setup_space_env()` into a shared module, register as a set asset, add
  camera marks for EXT shots
- [ ] Separate-node thruster/gimbal variant for flight animation
- [ ] Detail pass when close-ups demand it: Yakara logo, hull dents,
  cockpit greebles
- [ ] Decide scene-render color policy: AgX (current pipeline default)
  washes the ships' era-correct saturated colors; previews use Standard

## Pilot backlog (tickets from out/production/pilot/)

- [ ] Orbital-lounge dressing pass: instrument panels, observation
  windows, booths/tables, station personnel (extras — no third
  character exists yet)
- [ ] Real `orbital_station_lounge` set (stand-in ticket; sci-fi bar is
  a close fit — could be a variant rather than a new build)
- [ ] Audio bed: jukebox/life-support hum, footsteps, stool scrape
  (audio cues fail fast everywhere in v0 — needs the Phase 5 audio work)
- [ ] From-behind medium shot: bartender fully occluded by the hero
  (script wants her visible beyond) — offset `cam_medium_hero_back`
  slightly off the bartender→hero axis

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

Creative queue (recorded 2026-07-07):

- [ ] Night-mood lighting variant for the sci-fi bar (`variant_night` is
  still a tag only; current review lighting is bright/clinical)
- [x] Hair + outfits for the v2 characters — DONE 2026-07-11 (see
  PROJECT-DONE.md): the no-deform bug was the vendor Icosphere helper mesh
  poisoning the height-match scale (garments at 64%, weights bound to
  pelvis/spine). Fixed in `tools/build_characters_v3.py`; config now points
  at `oeb_dressed_characters.glb`; pipeline render QA green.
- [ ] Real `nod_small` / `shrug_small` / `wipe_glass_loop` clips (v0 doubles
  reuse talking/hold loops — see build_characters_v2.py REMAP notes)
- [ ] Elbows-on-the-bar seated pose (custom `idle_bar_lean` clip; object
  transforms can't produce it)
- [ ] `rooftop_garden` location build — standing NEEDED ticket from ep_001
  (out/production/ep_001/tickets/)
- [ ] JB5K spaceship reconstruction (plan: `elmo` chunk mining + silhouette
  tracing from the 1999/2000 renders; Space Kit ships as kitbash donors)
- [ ] Two-shot camera reframe (clips the seated hero at frame right —
  placeholder aim carried into the sci-fi set)

- [ ] Add a separate Backup drive and mirror the external asset library + project source to it (see docs/local/STORAGE-PLAN.md, local only). Until then the library drive has zero redundancy — do not put un-redownloadable data on it.
