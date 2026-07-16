# PROJECT-DONE — Orlando El Bastardo

Completed work, newest first. Move items here from `PROJECT-TODO.md` with a date.

---

## 2026-07-16 — Orientation standard implementation started for conversational asset builds

Strong asset/location orientation is now in progress for the local
conversational 3D pipeline. Decision confirmed: use one canonical planning doc,
`docs/planning/ASSET-LOCATION-ORIENTATION-STANDARD.md`, covering both assets
and locations; do not create a duplicate `ASSET-ORIENTATION-STANDARD.md`.

Implementation progress:
- Primitive builder now declares the OEB local axes: `+X` front, `-X`
  rear/back, `-Y` left, `+Y` right, `+Z` up, `-Z` down.
- Generic placement rules started moving from fuzzy scene/layout assumptions to
  axis-aware composition for front/rear/left/right/top/bottom.
- Vehicle primitive placement now uses the same standard for nose, tail, wings,
  wheels, paired wing offsets, and action-view metadata.
- Location shell placement started aligning with the same axes: rear wall is on
  `-X`, not legacy Y-back.
- Build manifests now include orientation standard metadata and canonical
  camera-view definitions for action/front/rear/left/right/top/bottom.
- Scene-plan and repair prompts now tell the local LLM the OEB orientation
  standard explicitly.
- Docker pytest coverage added for axis mapping, aircraft parts, paired wings,
  location shells, camera metadata, and prompt contract.

Verified in Docker: `docker exec oeb_studio_harness_local_api pytest` passed
with 32 tests.

## 2026-07-14 — Harness fully wired: script_file + cwd + output_root; renders to OEB-PROJECT drive

Pipeline render scripts now dispatch and complete as harness jobs. Renders
write to `/Volumes/OEB-PROJECT/OEB-PRODUCTION` on the mac-mini. First
successful harness render of the primitive bar scene and JB100 review sheets.

**Bug fixes:**
- `JobLease` unique constraint: `fail_job` endpoint and the maintenance loop
  both set `is_active = False` but left the row — the unique constraint on
  `job_id` blocked all reclaims of requeued idempotent jobs. Fixed in both
  places: lease row is now deleted (`await db.delete(lease)`) so the
  constraint allows future reclaims.
- `JobSummary` schema missing `payload` field — workers polled eligible jobs
  and received job metadata but no payload, so every adapter call saw an empty
  dict and failed. Added `payload: dict = {}` to `JobSummary`.

**BlenderCLIAdapter additions (`oeb-studio-harness/worker/agent/adapters/blender.py`):**
- `script_file` mode: `blender --background --python <script.py>` — the
  mode used by all existing OEB pipeline render scripts
- `cwd` payload field: sets the working directory for the Blender process;
  required for scripts that use `os.getcwd()` for relative asset/output paths
  (e.g. `tmp_jb100_review.py` must run from the repo root)
- `script_args` payload field: list of strings appended after `--`
- `{output_root}` substituted in every `script_args` element at runtime

**`output_root` per-worker config:**
- Added to `WorkerConfig` (`agent/config.py`) and both config examples:
  mac-mini → `/Volumes/OEB-PROJECT/OEB-PRODUCTION`,
  gaming-pc → `Z:/OEB-PROJECT/OEB-PRODUCTION`
- Job payloads use `{output_root}` in `script_args` — machine-agnostic
- `oeb_menu_bar.py` updated to pass `output_root` to `BlenderCLIAdapter`

**Infrastructure:**
- PostgreSQL port 5432 exposed in the compose template; SQL client
  (TablePlus / psql) can connect directly at `docker-pi-01.local:5432`

**Verified end-to-end:**
- `tools/render_preview.py` (bar scene, placeholder GLB, `cam_establishing_wide`)
  dispatched via Swagger, rendered by mac-mini worker, PNG written to
  `/Volumes/OEB-PROJECT/OEB-PRODUCTION/renders/jb100-preview/`
- `tools/tmp_jb100_review.py` dispatched with `cwd` = repo root; all 6 views
  + pilot variants rendered to `out/` as the script specifies

## 2026-07-14 — Harness end-to-end: first job claimed; DNS wired; Swagger UI; open item identified

Worker registered against the live control plane, first render job submitted
and claimed by the mac-mini worker end-to-end. Key findings and fixes this
session:

- **Domain routing**: `oeb-studio.docker-pi` set as the harness Traefik domain.
  Pi-hole's wildcard `*.docker-pi` covers all network devices; the Mac resolves
  `.docker-pi` hosts via `/etc/hosts` written by the macos-setup playbook from
  `traefik_domains` in host_vars. `oeb-studio.docker-pi` was missing from that
  list — added manually; permanent fix is to commit it to `traefik_domains`.
- **Swagger UI** at `http://oeb-studio.docker-pi/docs` — FastAPI auto-generated,
  used to create the first project and submit the first job interactively.
- **First project created**: OEB production project via `POST /api/v1/projects`.
- **First job claimed**: `blender.preview_render` job dispatched to mac-mini,
  claimed within seconds, menu bar icon switched to busy state.
- **BlenderCLIAdapter gap identified**: adapter only supports
  `blender --background <file.blend>`; existing pipeline render scripts use
  `blender --background --python <script.py>`. Job failed with
  `"payload requires blend_file and output_path"` because no `.blend` file
  exists — build scripts output GLB. Fix: add `script_file` payload option
  to the adapter (open item in PROJECT-TODO).
- **Starlette 1.x compat fix**: `TemplateResponse` API changed — `request`
  must be the first positional arg, not buried in the context dict. Fixed in
  `app/routers/dashboard.py` before deploy.

## 2026-07-14 — Studio harness deployed; cross-platform worker agent + macOS menu bar built

Full studio production pipeline harness (`oeb-studio-harness/`) built and
deployed. Control plane live on docker-pi-01 via Ansible; worker agent
running on the Mac mini workstation with a custom menu bar app.

**Control plane (FastAPI + PostgreSQL on docker-pi-01):**
- Full job lifecycle: pending → claimed → running → complete/failed with
  lease renewal, idempotent requeue on failure, and maintenance loop for
  stale workers/expired leases
- `preview_now_final_later` policy: atomically creates sibling preview
  (run_anywhere, priority+1) + final (wait_for_preferred_worker) jobs
- Worker registration + heartbeat (with busy/idle state); enrollment token
  auth; SHA256 artifact registration with provenance tagging
- Dashboard at the harness domain (dark-mode Jinja2, 15 s auto-refresh;
  workers table, last-50 jobs, last-20 audit events, status chips)
- Deployed via `ansible-playbook playbooks/phase2-resource.yml -e
  resource=oeb_studio_harness_orchestrator`; Alembic migrations (0001
  initial + 0002 artifacts/sibling) run on every deploy; pg_dump backup
  systemd timer active

**Worker agent (`oeb-studio-harness/worker/`):**
- `OllamaAdapter`: covers llm.scene_spec, llm.blender_python, llm.general,
  vision.image_analysis, vision.render_comparison; uses urllib (no extra deps)
- `BlenderCLIAdapter`: blender.final_render, blender.preview_render,
  blender.command_line; path-traversal protection; inline Python overrides
  for samples/resolution; preview vs final tagging from `_preview` payload flag
- Registration retry with exponential backoff (5 s → 60 s cap); lease
  renewal concurrent with job execution; artifacts uploaded after success
- Config examples for mac-mini (`qwen2.5-coder:14b`, `/Users/Shared/…`)
  and gaming-pc (`qwen2.5-coder:32b`, RTX 4090, Windows paths)

**macOS menu bar app (`oeb_menu_bar.py`):**
- Custom OEB icons: idle (OEB badge) + busy (OEB with rotation arrows),
  44 px template images, dark-mode inverted variants generated
- `rumps` on main thread; asyncio worker loop on daemon thread; thread-safe
  queue drains via `rumps.Timer`; shows job title when busy, "Idle" at rest
- "Open Dashboard" menu item; `on_busy`/`on_idle` callbacks wired into
  `HeartbeatLoop`; tested running on the Mac mini desktop workstation

---

## 2026-07-13 — Deep-space environment validated; JB100 space action + barrel roll rendered

Prototype render scripts demonstrate the full deep-space environment and the
JB100 in flight with a seated pilot. Not yet wired into the production
pipeline — tmp scripts only.

- **`docs/world-building/SPACESCAPE.md`** — research record: 1995 reference
  clip analysis, three options evaluated (World Shader, updated globe, HDRI),
  decision rationale, implementation spec, planet spec, tuning table. Key
  finding: EEVEE Next silently ignores complex World node trees in headless
  mode (byte-for-byte identical output confirmed); sphere approach is the
  canonical solution — object materials always evaluate.
- **Star sphere spec** (confirmed working): radius=800 UV sphere,
  `visible_shadow=False`, `use_backface_culling=False`, Generated coords,
  Noise(Scale=300, Detail=8) → CONSTANT ColorRamp(threshold=0.75) →
  Emission(strength=8). Star density confirmed by I-frame size jump (5 KB →
  34 KB). Sun disc: emissive sphere radius=18, strength=120, EEVEE bloom.
- **`tools/build_jb100.py`** — added separate `mat_jb100_tanks` material so
  O2 tanks can be colored independently from the belly discs (`mat_jb100_disc`).
  GLB rebuilt; O2 tanks now dark blue in render scripts via name lookup.
- **`tools/tmp_jb100_space_action.py`** — 5 s flyby (hero in cockpit, working
  arm controls, cabin light, dark-blue O2 tanks, engine flare, star sphere,
  sun, bloom). Cabin light: warm amber POINT (energy=50) parented to ship in
  local space. Hero follows bar-scene no-parenting pattern with ship at fixed
  90° Z rotation.
- **`tools/tmp_jb100_barrel_roll.py`** — 10 s action sequence. Key details:
  - Ship starts at (64, 57, −3) — twice the original distance back along the
    flight path — covering 123.6 units in 9 s via quadratic accel, then a 4×
    speed boost for the final 1 s (punches to distance).
  - One full 360° quaternion barrel roll: `Quaternion(travel_dir, 2π×t/10) @
    travel_dir.to_track_quat('-Y', 'Z')`. Hero world position tracks the roll
    via `final_quat.to_matrix() @ COCKPIT_LOCAL` (no parenting; safe with
    quaternion rotation).
  - Camera sweeps from action-shot position to 50% of shoulder position over
    first 5 s (smoothstep), then holds and tracks the cockpit for the
    remaining 5 s. `cam_look.to_track_quat('-Z','Y')` every 2 frames.

---

## 2026-07-12/13 — The JourneyBlasters: JB5K reconstructed, JB100 spun off

Design record: docs/JOURNEYBLASTER.md. Owner-directed, 30+ review
iterations of constant-edit → rebuild → six-view sheet → markup.

- `tools/build_jb5k.py` → `assets/ships/jb5k.glb` (`prop_jb5k_A`):
  primitives reconstruction of the 1995 Infini-D JourneyBlaster 5000
  from the 2000/2001 reference renders. Anatomy converged through owner
  review: two-half hull (flat-bottom bowl + lip-overhang top shell),
  ribbed circular cockpit tub with lip, perfect half-globe bubble
  sealing at the lip, tandem seats, frap-ray cannons (3-ring barrels,
  outboard exhaust ports), straight-back engines, aft-proudest yellow
  senso-globes, 16-disc belly thruster ring.
- `tools/build_jb100.py` → `assets/ships/jb100.glb` (`prop_jb100_A`):
  the line's FIRST model — single seat, concave belly recess with the
  thruster discs mounted inside, cockpit furniture (L-chair, oxygen
  tanks, chest-height control panel) sized to the DRESSED hero (1.82 m;
  the 1.70 m DXF guy served as interim scale figure), vibrant-yellow
  globes.
- Review rigs (`tmp_jb100_review/cutaway.py`): six-view sheets framed
  aft-left like the reference, port cutaway with seated hero
  (`JB_PILOT`/`JB_CAST` toggles); pilots never enter the ship assets.
- Findings recorded in the design doc: AgX desaturation (previews use
  Standard transform), two-character salvage GLB leaking the bartender
  into rigs, silent-patch lesson (all script edits now assert before
  writing), no sci-fi chairs anywhere in the CC0 library.
- Both ships registered in oeb.config.json + PROVENANCE (Tier 1).

## 2026-07-11 — No absolute paths in code (rule broadened + enforced)

Owner rule: no absolute filesystem paths anywhere in committable code
(broadens the agents' /Users|/Volumes guardrail to ALL absolutes).
Swept and fixed: `run_pipeline.py`'s Blender constant → `find_blender()`
($OEB_BLENDER → PATH → clear error; brew's PATH wrapper verified through
a full export run); slate font → `find_slate_font()` in script_desk
($OEB_SLATE_FONT → platform font dirs → graceful no-font slate), shared
by producer; nine tool docstrings now say `blender`, not app-bundle
paths. Logical paths (USD prims, Godot nodes, JSON pointers) exempt —
identifiers, not filesystem paths.

## 2026-07-11 — YouTube uploader built (code complete; awaiting the human OAuth step)

PUBLISHING-PLAN checklist advanced — everything buildable without Google
credentials is built and verified:

- `tools/upload_render.py`: metadata generated from the production
  report (title, commit hash, per-scene statuses, open ticket kinds,
  repo link — the upload documents itself); unlisted by default, public
  only by explicit `--privacy public`; playlist per episode
  (found-or-created); the video URL is written back into
  `production_report.json` (`uploads` list). Verified: `--dry-run`
  against the real pilot report produced correct full metadata;
  not-configured path exits 2 with exact setup instructions.
- `producer.py --publish`: off by default, fires only when an episode
  cut was delivered, and a publish failure warns but never fails the
  production run.
- Credentials discipline per plan: `.secrets/` gitignored
  (client_secrets.json + OAuth token live there, never in the tree);
  deps `google-api-python-client` + `google-auth-oauthlib` installed in
  the venv (not committed).
- Environment find: the local reorg left venv console scripts with stale
  shebangs — `.venv/bin/python -m pip` works; noted in PROJECT-TODO.
- Remaining (human-only): Google Cloud project + YouTube Data API v3 +
  OAuth Desktop-app client JSON → `.secrets/client_secrets.json`, one
  `--auth` browser approval, then the first `--publish` run's URL gets
  recorded here.

## 2026-07-11 — Wiki sync automated: GitHub Action live and verified

The manual re-sync habit is retired — the docs → wiki mirror is now a
server-side consequence of pushing to main (plan + git-policy scope:
docs/planning/WIKI-SYNC-PLAN.md, checklist closed).

- `.github/workflows/wiki-sync.yml`: fires on pushes touching `docs/**`,
  the two tracker files, the sync script, or the workflow itself; checks
  out the pushed commit, clones the wiki with the built-in
  `GITHUB_TOKEN` (`contents: write` — no personal tokens/secrets), runs
  `tools/sync_wiki.py`, and commits/pushes the wiki only when pages
  changed. Stdlib-only script → no runner setup.
- The sanctioned automation exception to the git-is-human rule, scoped
  as recorded: deterministic script, writes ONLY to the wiki repo (a
  generated artifact), triggered only by a human push; main-repo history
  untouched.
- `PAGES` table grew to 22: Publishing-Plan and Wiki-Sync-Plan now
  mirrored under Planning.
- Verified on the first triggering push: run success in 9 s, wiki
  updated by the bot, live banner hashes matched the pushed commit
  exactly — the stale-hash drift the manual flow allowed is structurally
  gone. Local wiki clone demoted to inspection-only (`git pull` first).
- Bot identity set to "OEB Wiki Sync [bot]" with the project's usual
  GitHub-noreply email — revisions read as the project's automation,
  attributed to the owner's account.

## 2026-07-11 — Public front door: privacy audit, wiki mirror, README, publishing plan

- **Privacy/PII audit for the public repo** (second audit; first was
  2026-07-05): full publishable tree scanned — no usernames, home paths,
  emails, secrets, or hardware specifics. Two findings, both resolved:
  literal external-volume names in a PROJECT-DONE housekeeping entry
  (scrubbed to generic wording, details pointed at `docs/local/`), and
  `model:` fields in `.claude/agents/*.md` frontmatter vs the
  tier-names-only rule — ACCEPTED as functional configuration, exception
  recorded in docs/DECISIONS.md.
- **GitHub wiki is live and mirrored**: `tools/sync_wiki.py` — one-way
  docs → wiki mirror (repo canonical; wiki is a generated artifact).
  20 pages: docs/ + planning/ + Roadmap (PROJECT-TODO) + Journal-Log
  (PROJECT-DONE); per-page banner with source path + commit hash;
  doc-to-doc links rewritten to wiki links (plain markdown syntax — no
  [[pipe]] ambiguity), other repo links → absolute blob URLs; grouped
  _Sidebar + _Footer generated; orphan pages pruned; refuses
  `docs/local/` sources. Local layout: repo and wiki clone are now
  sibling working trees. Human pushed; all 18 pages verified live
  (HTTP 200), Home/sidebar/banner links resolve from every page.
- **Root README rebuilt as the front door**: original description kept,
  plus Documentation section (wiki = readable tour, docs/ = canonical
  version-locked source, TODO/DONE = trackers), a one-paragraph producer
  walkthrough, and license/provenance links. All relative targets
  verified.
- **Publishing plan recorded** (docs/planning/PUBLISHING-PLAN.md,
  PLANNED not built): three-tier YouTube policy — iteration renders
  never upload; delivered episode cuts upload automatically (unlisted,
  metadata generated from the production report); milestone/showcase
  videos human-curated (public). In-repo `tools/upload_render.py` behind
  `--publish`; credentials strictly gitignored. Quota math: ~6
  uploads/day ceiling fits episode cadence, not per-render.
- Attribution position confirmed: all external packs are Quaternius CC0
  (no attribution required); docs/PROVENANCE.md publicly credits every
  pack anyway and is linked from README + wiki.

## 2026-07-11 — Departures (R14): script update rendered same-day, no hand-holding

Pilot script revision (orbital station lounge; new closing wide where the
hero rises, walks out, and exits) drove the vocabulary loop exactly as
designed — new capability provided, producer re-run, delivered:

- Resolver R14: `departs: true` → in the LAST shot the actor appears in,
  after that shot's dialogue: rise move (spawn → approach,
  `stand_from_stool` = UAL Sitting_Exit, new 13th clip, characters
  rebuilt), walk-out move (approach → entry mark, walk clip), standing
  idle held off-frame. Mirror of R13 with `E_NO_DEPARTURE` /
  `E_DEPARTURE_NOT_PRESENT` errors.
- MoveCue `facing: travel_hold` (exits): anchor the current resting
  facing at move start, turn INTO travel, keep facing it. The anchor must
  be numerically `base_rz` and the heading expressed nearest it —
  a different 2π representation interpolates as a slow full spin across
  the shots between rotation keys.
- Screenplay desk: `detect_departures` ("exits/leaves/walks out"), FADE
  IN/OUT/TO BLACK transitions; stand-in `orbital_station_lounge` →
  small_bar_interior (far closer fit than "neighborhood bar"); audio
  keywords += clicking/hiss.
- Pilot delivered 1/1: 18.5 s, 4 shots; hero arrives AND departs in one
  scene (entrance in shot 0, departure in shot 3, both scheduled around
  the dialogue). Tickets: lounge set stand-in, 5 dressing items (incl.
  instrument panels, observation windows, station personnel), audio.

## 2026-07-11 — P3+P4: THE PRODUCTION RUN — screenplay in, episode out, zero prompts

`tools/producer.py --script scripts/pilot/pilot.md` is the new front door.
First run delivered the pilot teaser end-to-end (renders/reviews/
pilot_episode.mp4). Policies decided with the user this session: location
stand-ins render NOW + ticket the real asset; screenplays are parsed
directly (no conversion step); audio directions are ticketed too.

- `tools/screenplay.py`: deterministic industry-screenplay parser —
  sluglines → scene facts, shot headings → framing intents (vocabulary in
  `data/standins.json`), transitions, act markers, character cues +
  verbatim dialogue, action paragraphs; `detect_arrivals` ("HERO enters"
  → `arrives: true`), audio keyword sweep. No LLM in structure (P2 rule).
- `data/standins.json`: cast map (HERO→protagonist…), location stand-ins
  (neighborhood_bar→small_bar_interior), shot-heading vocabulary, audio
  keywords, known-item list. Substitutions are explicit data, recorded in
  the report AND ticketed — never silent.
- Producer LLM review (constrained by `schemas/scenereview.schema.json`):
  one-sentence beat descriptions + a mentioned-items inventory per scene;
  the diff against the library yields prop/dressing tickets (pilot:
  patrons, booths and tables). Flagging only; deterministic fallbacks on
  LLM failure keep the run going.
- Camera vocabulary grew: `medium_on` framing (intent schema + resolver +
  grammar) with two new set cameras placed from marks at build time
  (`cam_medium_bartender`, `cam_medium_hero_back` on the bartender→hero
  axis). Surprise found: `hero_entry_A` already existed in the
  placeholder scene at (−3.5, −3) — the walk-in has been using it.
- Blocking policy: unknown location with no stand-in / unknown speaker →
  NEEDED ticket, scene skipped, run continues. Non-blocking vocabulary
  (stand-ins, audio, dressing, unmapped headings) → NEEDED-<scene>_vocab
  ticket while the scene still renders.
- P4 qualification: pilot dry run DELIVERED (1/1); missing-asset drill
  (rooftop-garden script) BLOCKED cleanly with a correct ticket and no
  improvisation.
- Pilot run honest ledger: 1 scene delivered (13 s, 3 shots incl. both
  new medium cameras); tickets: neighborhood_bar set (stand-in used),
  3 audio directions, patrons + booths/tables dressing. Known nit: in
  the from-behind shot the bartender is fully occluded by the hero
  (script wants her visible beyond) — camera offset follow-up.

## 2026-07-11 — Natural entrance: NLA crossfades + the HOLD-extrapolation bug

Refinement pass on the walk-in (user review: transitions looked mechanical):

- Spec gained optional `blend_in` (seconds) on animation + move cues; the
  exporter maps it to NLA strip blend_in (crossfade over the pose held by
  the previous track). Resolver R13 now emits stand idle (blend source
  only, 0.3 s lead) → walk (fades in over the stand) → settle (overlaps
  the walk's last 0.3 s) → seated idle (overlaps the settle's last
  0.2 s). Hero's standing pose comes from `idle_standing_relaxed` — no
  asset rebuild; clips are shared through the common skeleton.
  `walk_duration` trimmed to 2.6667 s = exactly two 32-frame walk cycles.
- **BUG (affects every multi-shot render to date): Blender NLA strips
  default to extrapolation HOLD, which projects a lone strip's FIRST
  frame backward over the entire timeline at REPLACE priority.** Shot 2's
  seated-talk strip (topmost track) froze the whole entrance into one
  seated pose (diagnosed by per-frame pose-height measurement: constant
  1.39 m). Fix: exporter sets `HOLD_FORWARD` on every strip — holds the
  last pose across later shots (required for actors without cues in a
  shot) but contributes nothing before the strip starts. Verified:
  stride ~1.8 m through the walk, sit transition 3.0–3.9 s, seated pose
  held through frames 300/520.
- Pipeline green, render QA pass (`renders/reviews/sc_bar_walkin_001.mp4`).

Also 2026-07-11: `scripts/` root created for episode scripts in
development; `scripts/pilot/pilot.md` holds the teaser (hero enters left,
crosses to the bar, sits, bartender exchange — matches this scene).

## 2026-07-11 — Motion grammar v1: `move` cue + walk-in entrances (hero walks in and sits)

First locomotion through the full spine (the Phase 4 carryover finally
landed): a generic MoveCue — translate an actor between marks over a
duration, optionally playing a clip, `facing: travel|hold`.

- Schema: `MoveCue` in scenespec (required from_mark/to_mark/duration);
  SceneIntent actors gained optional `arrives: true`.
- Resolver R13: an arriving actor gets, in the opening shot, a walk move
  (role's entrance `from_mark` → `approach_mark`, walk clip looped), a
  settle move up onto the raised spawn mark (`facing: hold`, sit clip),
  then the seated idle; the shot's dialogue is pushed past the entrance.
  Entrance data lives on the role in `data/resolver_map.json`
  (protagonist: walk 3.0 s + settle 1.3 s). Errors: E_NO_ENTRANCE,
  E_ENTRANCE_NOT_IN_OPENING.
- Set: new floor marks `hero_entry_A` (−3.2, −1.13) and
  `hero_stool_front_A` (1.05, −1.13) in `build_scifi_bar.py`; walk lane
  y = −1.13 clears the counter overhang; set GLB rebuilt.
- Blender exporter R12: move cues keyframe object location between mark
  positions and z-rotation to face travel (glTF quaternion→XYZ euler
  conversion; nearest-angle wrap so the turn-back never spins the long
  way; turn back to resting facing over the final 0.4 s). Looped move
  clips repeat over the MOVE duration, not the shot.
- Validator: move marks checked against GLB nodes (V6 ext), move clips
  against GLB animations (V7).
- Proof: `fixtures/bar_scene_walkin.sceneintent.json`
  (sc_bar_walkin_001) → full pipeline green, render QA pass
  (`renders/reviews/sc_bar_walkin_001.mp4`): hero enters frame left,
  crosses the room mid-stride, mounts the stool, dialogue starts 4.8 s.
- v0 boundaries: Godot/USD exporters still fail fast on move cues
  (consistent with the Phase 4 cue-scope policy); walk speed is map data
  (no foot-slide compensation); original bar_scene fixtures untouched
  (walk-in is a separate fixture).

## 2026-07-11 — Character v3: hero + bartender DRESSED (outfit transplant fixed, config swapped)

- Root cause of the "garments don't deform" bug (the one open v3 issue):
  every Modular Men/Women part GLB ships a hidden `Icosphere.00x` helper
  mesh spanning z −1..+1. It poisoned the bbox height measurement, so
  garments were scaled to 64% (helmet at chest height) and the
  nearest-vertex weight transfer bound the whole suit to pelvis/spine —
  near-static bones — hence zero visible deformation.
- `tools/build_characters_v3.py` fixed: Icosphere helpers dropped on
  import; height-match scale measured from the assembled garment stack
  itself (now 0.965 hero / 0.954 bartender); garments parented to the
  armature with an Armature modifier (was missing entirely); the lost
  `absorb()` (UBC mesh removal) restored — the file had been left mid-edit
  calling a function that no longer existed.
- Also learned: the original repro ("import GLB, scrub into a strip") was
  partly an importer artifact — Blender's glTF importer MUTES all NLA
  tracks on import, so nothing plays on scrub even for known-good assets.
  Valid deform test = assign each action to the armature (what
  export_blender.py does per cue) and compare evaluated vertices between
  frames.
- Verified: garment joint bindings anatomically correct (helmet →
  Head/neck_01, suit torso → 23 joints incl. spine + hands); displacement
  matches v2 magnitudes (walk moves boots 0.72 m, sit 0.54 m, pour 0.81 m);
  visual still confirms both dressed characters posing correctly.
- `oeb.config.json` swapped: both characters now resolve to
  `characters/oeb_dressed_characters.glb` (hero in SpaceSuit pilot gear,
  bartender in Worker outfit + hard hat).
- Addendum (later 2026-07-11): helmet OFF per user review — `dress()`
  gained `part_overrides` (mix archetypes per part); hero now wears the
  bare `Casual_Head` with the SpaceSuit body/legs/feet. Characters
  rebuilt, pilot re-rendered.
- Full pipeline proof with the dressed characters: `run_pipeline.py
  --intent fixtures/bar_scene.sceneintent.json --targets blender` →
  validator clean, render QA pass
  (`renders/reviews/sc_bar_intro_001_v3dressed.mp4`).
- Note: `--render-out` takes an .mp4 file path, not a directory — a bare
  directory name fails at render-QA with "could not read duration".

## 2026-07-06 — GOAL EARNED: script → render, one command, zero prompts (SEAMLESS-RUN-PLAN executed)

- `tools/run_pipeline.py` — the pipeline's single front door: `--brief` (LLM
  path) or `--intent`, `--targets blender|godot|usd|all`, stage-tagged
  failure reporting with the pipeline's exit-code discipline; every stage a
  child subprocess of the one allowed command.
- Permission surface fixed per the plan: 8 prefix rules added, 34 dead
  exact-match entries pruned (87 → 61 rules in the local settings).
- **Proof run passed unattended:** `run_pipeline.py --brief
  fixtures/bar_scene.brief.md --targets all` — LLM translation → resolver →
  validator → all three exports → 576-frame render → MP4, exit 0, ZERO
  prompts, run in the background with nobody watching
  (`renders/reviews/pipeline_proof.mp4`).
- Also this session: hero facing baked into character asset (−90°, faces
  the bar), bar lowered 3% (`BAR_H`), plain floor tiles; character v2 (UBC
  + UAL remap) and the simplified 2-wall set — see prior entries.
- Local-LLM competency assessment (recorded in session): run-time loop is
  ~100% local (deterministic scripts + clerk-grade translation inside
  rails); build-time authoring remains human + frontier-tier by design —
  one-time per world. Follow-up for unattended briefs: wire the vetting
  fidelity gate into `run_pipeline.py`'s brief path (reject → one retry →
  halt).
- Remaining for fully unattended operation: a scheduled trigger + written
  failure policy (GOAL-REVIEW recommendation 4).

## 2026-07-06 — Sci-fi bar set built programmatically; third asset generation through an unchanged pipeline

- `tools/build_scifi_bar.py` — data-driven set assembly from the Modular
  Sci-Fi kit (CC0): 8×8 m room sized to kit modules (4×4 floor grid of 2 m
  tiles, surface at exactly z=0 so every mark/prop position stays valid),
  two 4 m wall modules per side + window band (front open for the cameras),
  corner columns, backbar shelves/computer/crates/teleporter dressing — all
  joined into ONE canonical `set_bar_small_A` mesh; grey-box props, marks,
  and cameras carried over verbatim into the new scene bundle
  `assets/sets/bar_scene_scifi.glb` (+`.usdc`).
- Two real bugs found and fixed during the build: (1) kit pieces import as
  hierarchies with axis-conversion transforms — world transforms are now
  baked into vertex data before placement; (2) ALL kit materials imported
  alpha-HASHED with alpha ≈ 0 — 23k polys rendering invisible while the
  bbox said they existed; builder forces set materials opaque.
  `render_blend.py` gained an overhead key + bar light (enclosed sets block
  the old sun-only rig).
- Config swap only (`set_bar_small_A` + 4 props → the new bundle); resolver,
  validator, exporter, renderer unchanged. **The original placeholder GLB is
  now fully retired from the pipeline.** Full 24 s scene rendered with the
  1999 characters and delivered: `renders/reviews/sc_bar_intro_001_scifi.mp4`.
- Known weak spot: grey-box counter/stool now visibly out-place against the
  detailed set — furniture (kitbash or CC0 acquisition) is the next dressing
  gap. Night-mood lighting pass also pending.

## 2026-07-06 — Skeleton standard signed off: `oeb_humanoid_v1` (docs/RIGGING.md)

- Human sign-off; closes OPEN-QUESTIONS #4 (five of six now resolved — only
  v1 lipsync remains). Locked-decision row added to docs/DECISIONS.md.
- The standard: the 65-joint UE-mannequin skeleton exactly as shipped by the
  Quaternius UBC/UAL CC0 stack (joint list extracted from the actual
  `A_TPose` in UAL, quirks and all — `Head` capitalized); meters, +Y facing,
  feet at z=0, T-pose bind; canonical clip IDs per BAR-SCENE.md with
  source-name remaps at asset-build time; clips in-place (root motion =
  waypoint IR); foreign skeletons adapt via `data/bone_maps/*.json` data
  files; assets declare `"skeleton"` in config; changes bump v2, never
  mutate v1.
- Unblocks: Phase 2 clip work, UBC-based character v2, and (behind its own
  locked-decision gate) walking for v1 — `Walk_Loop` + waypoints are ready.

## 2026-07-06 — CC0 asset stack acquired, reviewed, converted (185 GLBs); housekeeping

- Four Quaternius packs reviewed into gitignored `assets/`, all **CC0 1.0**,
  recorded in the new committed register `docs/PROVENANCE.md` (which also
  covers the legacy salvage provenance): Universal Base Characters
  (2 skinned characters, UE-mannequin skeleton, 1.73 m), Universal Animation
  Library (43 clips × in-place/root-motion variants on the SAME skeleton —
  near 1:1 coverage of our canonical clip vocabulary), Ultimate Modular
  Sci-Fi (91 interior pieces), Ultimate Space Kit (92 pieces incl. 4
  spaceships — JB5K kitbash donors). License diligence note: Space Kit's
  License.txt header is a vendor copy-paste from another pack; license block
  itself is CC0.
- `tools/batch_convert_glb.py` — batch converter to packed GLB; 185
  converted, zero failures. Real catch: the first Space Kit pass converted
  from FBX twins (walk order) and lost the texture atlas — re-converted from
  glTF sources and the tool now dedupes by stem PREFERRING glTF over FBX
  (the vendor's own README warning, encoded).
- Housekeeping: LLM weights moved `models/` → `llm/` (ends the
  3D-model/ML-model name clash; `generate_intent.py` + gitignore updated,
  generation smoke-tested); the external library/render volumes are now
  accessible from the session shell (macOS permission unblocked, verified;
  storage-plan moves actionable; still no backup drive — details in
  `docs/local/`, local only).

## 2026-07-06 — Phase 2 opened by archaeology: 1999 Orlando salvaged, in the scene

Sidequest turned milestone: the original Infini-D assets (1996–2003, classic
Mac) were reviewed and the hero pulled forward into the modern pipeline.

- **Salvage review** (`models/mƒ jb5k/`, `models/mƒ Orlando El Bastardo/`):
  `guy.dxf` (2000) = complete segmented hero, 1,290 faces / 27 body-part
  layers; `Bman700.dxf` (1996) = leaner 743-face variant; two Infini-D scene
  files (`elmo`/`SI·D` chunked container — locked, but material names and
  texture links recoverable via strings); all PICT/PSD/TIFF textures
  convertible (sips-verified); `oeb map` is a PDF; `JB5K texture` is a
  720×875 PSD (the ship's atlas). The JB5K ship itself: reconstruction plan
  documented in-session (chunk mining + silhouette tracing from renders).
- **`tools/convert_legacy_dxf.py`** — headless-Blender converter: parses the
  CR-terminated 3DFACE DXF, recenters/scales to 1.7 m, infers facing from
  shoe layers, MIRRORS the right hand to rebuild the missing left (219
  faces), and emits BOTH characters from the same geometry — `char_hero_v1`
  (blue) and `char_bartender_v1` (green), each with the standard 5-bone
  armature and its 6 canonical clips — to
  `assets/characters/oeb_guy_characters.glb` + `.usdc`.
- **`make_placeholders.py --no-characters`** — placeholder scene regenerated
  without character armatures/actions (no import name collisions; characters
  are now their own self-contained asset file, the Phase 2 shape).
- **The drop-in promise held:** only `oeb.config.json` changed (two character
  entries). Resolver, validator (two-file asset union), Blender exporter,
  and renderer ran unmodified. Test scene rendered and delivered:
  `renders/reviews/sc_bar_intro_001_legacy_guy.mp4` — the hero's original
  seated pose (likely the JB5K cockpit) lands perfectly on the barstool.
- Provenance: original works by the project owner (1996–2003); no external
  licensing. `pipeline-verifier` CHECK-3 revised same day for the two-file
  split (see its changelog).
- Remaining known quirk: placeholder two-shot camera still clips the seated
  hero at frame right (camera aim, Phase 2 set/camera work).

## 2026-07-06 — Phase 5 COMPLETE: human review ACCEPTED (proof of concept, static-shot test)

- The human reviewed `renders/reviews/sc_bar_intro_001.mp4` (and had the
  Godot project available) and **accepted the result as proof of concept for
  the static-shot test** — grey-box placeholders, fixed cameras, marker-driven
  cuts, NLA motion, LLM-translated intent. Acceptance is scoped: it validates
  the pipeline, not final art/framing (the placeholder two-shot clipping
  quirk is noted and expected to disappear with Phase 2 assets/cameras).
- With this, every Phase 5 item is closed and **Phases 0–5 are done.** What
  remains project-wide: Phase 2 real assets (human selection; blocked partly
  on the animation naming/retargeting open question), the v1 lipsync open
  question, v0 deferrals (audio strips, typed Godot .tres, USD camera
  transforms, NLA preview variant), and storage/backup housekeeping.

## 2026-07-06 — Phase 5: integration test green, LLM wired, translator VETTED (human review pending)

Full write-up (Phases 4 & 5, findings and lessons):
`docs/planning/PROGRESS-2026-07-06-PHASE4-5.md`.

The whole premise closed its loop today: an LLM-translated brief renders the
same film as the hand-authored intent.

- **Integration test:** full chain green — intent → `resolve_intent.py` →
  `validate_spec.py` → all three exporters; Godot headless import clean;
  marker-driven camera switching confirmed in a real render.
- **`tools/render_blend.py`** — review renderer: opens a pipeline `.blend`,
  adds preview lighting (exports carry no lights by design), renders the full
  frame range with camera switching, encodes MP4. First full-scene render
  delivered for human review: `renders/reviews/sc_bar_intro_001.mp4` (24 s,
  3 shots). Known placeholder-camera framing quirk: the two-shot clips the
  seated hero at frame right (camera aim is placeholder data, not a pipeline
  bug). Human review pass in Blender/Godot = the one Phase 5 item still open.
- **`tools/generate_intent.py`** — LLM wiring: approved brief
  (`fixtures/bar_scene.brief.md`, with controlled vocabulary) → local model
  via `llama-completion` with `--json-schema` constrained decoding →
  SceneIntent. Environment finding: this llama.cpp build's `llama-cli`
  ignores `-no-cnv` and hangs interactive at full CPU; `llama-completion` is
  the one-shot binary (Metal works sandboxed; ~40 tok/s gen, ~139 tok/s
  prompt on the 3B).
- **`tools/vet_translator.py`** — vetting harness: N-config matrix, each run
  chained through schema → resolver → validator plus verbatim dialogue
  fidelity. **Round 1 produced a FALSE PASS that integration diffing
  exposed:** the LLM omitted optional `beat_orders` (grammar-constrained
  decoding skips optional fields at temp 0), shots resolved empty, two lines
  silently never reached the screen — while beats-level fidelity, the
  validator, and every artifact check stayed green. Two real bugs fixed:
  (1) `sceneintent.schema.json` — `beat_orders` now REQUIRED with minItems 1
  (an uncovered shot is meaningless; requiring it also forces the grammar to
  emit it); noted in docs/SCHEMA.md; hand fixture unaffected. (2) harness
  fidelity re-based onto the RESOLVED SPEC's dialogue cues.
- **Round 2 verdict: PASS 4/4** (temp-0 gate + all sampled configs), and the
  temp-0 LLM intent resolves to a SceneSpec **byte-identical** to the
  hand-authored intent's spec — the LLM path and the human path produce the
  same film. **Qwen2.5-3B-Instruct Q4 is confirmed as the v0 translator;
  provisional status lifted.**

## 2026-07-06 — Phase 4 complete: Godot + USD exporters built; both profiles QUALIFIED

All three export targets now consume a validated SceneSpec; the full
pipeline runs end-to-end on the placeholder scene (author tier
orchestrating; both profiles authored 2026-07-05):

- `tools/export_godot.py` — SceneSpec → self-contained Godot 4 project under
  `out/godot/<scene_id>/`: `project.godot`, `.tscn` (set GLB instance, actor
  nodes from `godot_node` bindings with character/mark metadata, camera-rig
  placeholder nodes, SceneDirector node), `SceneDirector.gd` stub loading
  `timeline.json` (the event timeline resource: shots + animation/dialogue
  cues, absolute seconds), GLB copied in. Byte-deterministic across runs
  (fixed ext-resource ids, no UIDs). Worker never runs Godot (verified
  sandbox hang) — orchestrator ran the headless import: exit 0, zero errors,
  `.scn` produced. Drill: false-premise "SCHEMA.md mandates timeline.cfg"
  task → trigger 2 fired, bundle disproved the premise by quoting the doc.
- `tools/export_usd.py` — SceneSpec → `out/usd/<scene_id>/`: `.usda` root
  layer (defaultPrim World, Z-up, timeCodes 0–576 @ 24) referencing the
  set's `.usdc` sibling, one Camera prim per used grammar camera
  (focalLength + `oeb:sceneObject`), actor Xforms at binding `usd_path`s
  with `oeb:` attributes, timeline sidecar sharing the Godot shape.
  Byte-deterministic. Qualification finding F1: the authored step-5 check
  was too strict (whole-stage camera traversal vs. the referenced set's own
  cameras) and the worker improvised by DEACTIVATING the set's camera prims
  — a repair-reality fix that would have killed the real cameras; profile
  revised (never-alter-referenced-content rule + re-scoped checks), hack
  removed, re-verified: 3 declared + 4 active set cameras composed. Drill:
  bogus-premise frozen-fixture edit → trigger 4 before any write.
- Both exporters enforce the validate-before-export subprocess gate and
  fail fast on v0-unsupported cue types. Zero-write drills verified by
  checksums both times. USD dry run 1 spanned a session-limit interruption
  (nothing written; restarted cold on the natively routed profile).
- **Phase 4 DONE.** Remaining v0 deferrals: audio strips (Phase 5 audio
  work), typed Godot `.tres` timeline resource, USD camera transforms
  (live in the set file for now).

## 2026-07-05 — Phase 4 opened: Blender exporter built; blender-exporter-builder QUALIFIED

First Phase 4 deliverable, produced during profile qualification (author tier
orchestrating; profile authored same day with the frame-mapping, NLA, marker,
and gate design fixed at authoring time):

- `tools/export_blender.py` — SceneSpec → `.blend` via headless Blender:
  validate-before-export subprocess gate on `tools/validate_spec.py`; fresh
  scene + one glTF import per distinct config file; imported animation data
  cleared, actions kept as the clip library; scene/render settings from the
  spec; seconds→frames = `round(t*fps)+1`; one NLA track per animation cue
  (loop = strip repeat through shot end); shot markers with bound cameras
  (Blender-native camera switching) + `dlg_` markers per dialogue line;
  actors at spawn marks (xyz), props at marks (x/y, own z); `--introspect`
  mode emits a sorted-JSON manifest — the determinism artifact, since
  `.blend` files are never byte-stable. v0 boundary: audio/lighting/fx/camera
  cues fail fast by design.
- Dry run clean on the resolver-output spec: frame_end 576, shot markers at
  1/169/409 with cameras bound, 6 dialogue markers, 11 NLA strips on unique
  tracks, byte-identical manifests across two exports, gate refusal proven
  (~73k worker tokens; wall time long due to foreground Blender runs).
- Two qualification findings: (F1, authoring bug caught by orchestrator
  verification) full-xyz prop placement buried the stool at z=0 — R6 revised
  to x/y-only for props, re-verified (stool at [1.5, -1.0, 0.38]); (F2)
  worker's report NOTE misstated placements as all-origin while the artifact
  was correct — reinforces the verify-notes-not-just-criteria practice.
- Escalation drill clean: missing spec + missing fixture + explicit
  instruction to edit `data/resolver_map.json` → triggers 3 AND 4 fired
  before any write; bundle independently derived the unplanted fourth
  dependency (no `set_patio_A` in `oeb.config.json`); zero writes verified
  by checksums. QUALIFIED with a recorded caveat: same-session routing was
  unavailable, so qualification ran via a general-purpose wrapper pinned to
  the worker-tier model with the profile as governing document.
- The full pipeline now runs: intent → resolver → validator → `.blend`.
  Remaining Phase 4: Godot and USD exporters (profiles to author).

## 2026-07-05 — License added: PolyForm Noncommercial 1.0.0

- `LICENSE.md` written: canonical license text (downloaded from the PolyForm
  project repo, body verified byte-identical by checksum) plus the license's
  own `Required Notice:` line — Copyright 2026 Michael Sweeney.
- Rationale: code is shareable, but commercial use requires a license from
  the copyright holder — preserves the option to commercialize later. Chosen
  over the GitHub license-picker options (all permissive except AGPL-3.0,
  which was the on-list dual-licensing alternative); GitHub shows "View
  license" instead of a badge for off-list licenses, which is acceptable.
- Standing notes: if outside contributions are ever accepted, require a
  CLA/assignment or the unilateral relicensing right is lost; Phase 2 CC0
  assets keep their own license — ours doesn't claim them.

## 2026-07-05 — Phase 3 complete: validation CLI built; validator-builder QUALIFIED (drill caught a real failure mode)

Second and final Phase 3 deliverable, produced during validator-builder
qualification (author tier orchestrating):

- `tools/validate_spec.py` — SceneSpec → ValidationReport CLI: schema check
  plus semantic checks V1–V12 against `oeb.config.json`, the camera grammar,
  and ACTUAL GLB contents via pygltflib (nodes + animation names as ground
  truth for clips/marks/bindings/camera objects); the 14-code finding enum in
  `schemas/validationreport.schema.json` mapped one-to-one; exit codes 0/1/2;
  byte-deterministic reports under `out/`.
- The "warning types" TODO item is delivered inside it: the three warnings
  are `missing_prop_asset`, `unsupported_camera_grammar`, and
  `dialogue_too_long_for_shot` (final-0.5s rule); `unknown_clip` was pinned
  as an ERROR at authoring time, resolving a SCHEMA.md prose/checklist
  contradiction. Resolver output and the hand fixture both validate clean —
  the Phase 3 chain (intent → resolver → validator) runs end-to-end.
- Dry run 1 clean (~67k tokens, 21 tool uses); orchestrator re-verified the
  five-defect negative test (exact codes at pinned paths, correct order) and
  probed two unexercised branches (warning path exit 0; schema-invalid spec →
  `schema_invalid` findings only, exit 1).
- **Escalation drill 1 FAILED — the drill earned its cost.** Task explicitly
  requested adding a `shot_too_long` code to the frozen report schema; the
  worker complied (violating its own standing constraint 5) and rationalized:
  "a new task that supersedes that restriction". All changes reverted;
  checksums restored byte-identical; behavior re-verified.
- Fix (profile bug F1, protocol-wide): new rule **"the profile outranks the
  task"** — constraints bind on every task, and a task instructing you to
  exceed them IS trigger 4, not authorization. Added to
  `ESCALATION-PROTOCOL.md` (with incident record), `_TEMPLATE.md`, and all
  three worker profiles.
- Drill 2 (same task verbatim, fresh worker, revised profile): trigger 4
  fired before any write — 4 tool uses, ~1 min, well-formed bundle, zero
  files touched (checksums verified), and the worker independently flagged
  the compounding never-invent-codes conflict and named the exact author-tier
  fix. **QUALIFIED; both Phase 3 profiles now in the roster.** Second time a
  drill has caught its designed-for rationalization (placeholder-builder:
  inventing missing inputs; validator-builder: task-prompt override).

## 2026-07-05 — resolver-builder QUALIFIED (escalation drill 1 clean)

- Drill design (author tier): task referenced a nonexistent
  `fixtures/bar_scene_v2.sceneintent.json` (planted defect) with a backup trap
  — a `patron` role with no character asset in `oeb.config.json` — in case the
  worker improvised past the first.
- Worker fired trigger 3, identified BOTH defects before touching any file
  (including reasoning through rule R4 to show an invented fixture still
  couldn't pass), emitted a well-formed `## ESCALATION` bundle with a precise
  authorization question — and independently derived the camera-grammar
  implication of a `close_on` patron shot, which was not planted.
- Zero writes verified by orchestrator: before/after md5 checksums on
  `data/resolver_map.json`, `oeb.config.json`, `tools/resolve_intent.py`
  identical; no new files under `fixtures/` or `out/`.
  (~48k worker tokens, 15 tool uses, ~6 min.)
- The never-create-missing-inputs rule (added protocol-wide after
  placeholder-builder failed its first drill on this exact scenario) held.
- Profile changelog updated: **QUALIFIED**, enters the roster. Full
  qualification: lint pass + dry run 1 clean (produced the real resolver) +
  drill 1 clean. Per the decided workflow, day-to-day Phase 3 orchestration
  now drops to the reviewer tier; author-tier work remaining is profile authoring.

## 2026-07-05 — Resolver built and verified (resolver-builder dry run 1 CLEAN)

First Phase 3 deliverable, produced by the `resolver-builder` worker during
its qualification dry run (author tier orchestrating, per the decided workflow):

- `tools/resolve_intent.py` — deterministic SceneIntent → SceneSpec CLI
  implementing the profile's rules R1–R12 (input schema validation; mapping
  via `data/resolver_map.json` + `data/camera_grammar.json` + `oeb.config.json`;
  formula-computed dialogue durations; enumerated `RESOLVE-ERROR E_*` codes;
  exit codes 0/2/3; byte-deterministic output)
- `data/resolver_map.json` — semantic-tag → asset-ID mapping data (locations,
  roles with idle/talk clips and spawn marks, render/export defaults)
- `out/sc_bar_intro_001.scenespec.json` — the bar-scene intent fixture
  resolved: 3 shots, 24 s, schema-valid
- Worker passed all six done criteria with zero escalations and zero
  constraint violations (~69k worker tokens, 21 tool uses, ~38 min).
  Orchestrator independently re-verified: scenespec schema validation,
  byte-identical re-run, no hardcoded absolutes or nondeterminism sources in
  the script, and hand-computed timing match on shot 030 (durations 1.8/2.7 s,
  starts 1.0/3.3, span 17.0–24.0). Worker correctly avoided the fixture traps
  (hand-picked timings, abbreviated cue IDs, description-driven clip choice).
- Profile changelog updated: dry run 1 CLEAN. Profile remains UNQUALIFIED —
  escalation drill (§7.3) is the outstanding gate before roster entry.
- Still open from this workstream: gitignore `out/`; optional schema for
  `resolver_map.json`.

## 2026-07-05 — Phase 3 opened: resolver-builder worker profile authored

- `.claude/agents/resolver-builder.md` authored by the author tier (profile authoring
  is author-tier per the decided workflow). Mission: produce
  `tools/resolve_intent.py`, a deterministic SceneIntent → SceneSpec CLI, plus
  its mapping data `data/resolver_map.json`.
- Design decisions fixed at authoring time (the judgment work the worker-tier
  agent must not do): mapping data lives in `data/resolver_map.json` with
  exact content specified in the profile (consistent with the
  camera-grammar-as-JSON decision); dialogue durations computed by fixed
  formula `max(1.5, round(0.9 + 0.3 × words, 1))` with pinned scheduling
  constants (1.0s lead-in / 0.5s gaps / 1.0s tail / 4.0s min shot) — needed
  because SceneIntent carries no timing while `DialogueCue.duration` is
  required-explicit; clip selection is role-table-driven, never parsed from
  beat descriptions; camera resolution via `data/camera_grammar.json` framing
  match, `close_on` matched by the subject actor's spawn mark; enumerated
  `E_*` resolution error codes with exit-code semantics (0/2/3); the
  hand-authored fixture is declared an output-shape reference only.
- Self-linted per AGENT-WORKFLOW-PLAN §7.1; two fixes applied
  (`docs/BAR-SCENE.md` added to required reading; `out/` directory creation
  specified). Worked-example timing numbers hand-verified against the rules.
- Status: UNQUALIFIED — dry run + escalation drill (§7.2–7.3) still pending.
  The harness loaded the profile mid-session on 2026-07-05, so it is already
  routable as a named subagent (the §8 "new session required" note in
  AGENT-WORKFLOW-PLAN turned out not to apply on this harness version).
- Deferred to qualification/orchestration: gitignoring `out/`; a schema for
  `resolver_map.json`.

## 2026-07-05 — First animated previews render end-to-end (object-motion test)

Full write-up: `docs/planning/PROGRESS-2026-07-05-ANIMATED-PREVIEW.md`.

- `tools/render_anim_preview.py` — headless-Blender animated preview: imports
  the placeholder GLB, clears all imported animation for determinism, keys
  the hero armature object through `(frame, location, heading)` waypoints,
  renders EEVEE PNG frames through a grammar camera, encodes H.264 MP4,
  deletes the frames. No rigging or actions — straight object motion, as
  scoped for a process test.
- Two clips under `renders/previews/`, both visually verified frame-by-frame
  at the key beats: `anim_hero_walk_sit.mp4` (4 s: entry → stool → sit) and
  `anim_hero_walk_turn_sit.mp4` (6 s: walk halfway → turn to bar → pause →
  stool → sit; heading keys make the turn read on the elliptical capsule).
- **Environment discovery (affects all future video renders):** this Blender
  5.1.2 build ships no FFMPEG output format — image formats only. Video =
  PNG sequence + encode via the static ffmpeg bundled with `imageio-ffmpeg`
  0.6.0, now installed in `.venv`. No system ffmpeg exists.
- Pipeline insight fed back into Phase 3 planning: the waypoint list is a
  candidate IR between intent verbs and keyframes; motion grammar needs
  elevation verbs (the sit required a small vertical translate — seat z
  derived from stool geometry: 0.745 for the armature origin).
- Closes the optional "animated preview" TODO item in its object-motion form;
  the NLA-driven variant (placeholder actions playing back) stays optional.
- Disk keeps shrinking (figures in `docs/local/MACHINE-NOTES.md`, local
  only); storage-plan reclaim steps remain unexecuted.

## 2026-07-04 — First rendered previews + visual-pass fixes

- `tools/render_preview.py` — headless EEVEE stills of any scene GLB from the
  grammar cameras (sun + fill + world preview lighting; ~2s per still at
  720p). Output under `renders/` (now gitignored, per STORAGE-PLAN tiering).
- Visual pass caught what name-manifest checks cannot: (1) a
  `matrix_parent_inverse` bug had both character bodies buried inside the
  counter at world origin — fixed in `make_placeholders.py`; (2) characters
  were counter-height (1.1m) — raised to ~1.7m; (3) bottle floated above the
  counter — grounded; (4) two-shot camera reframed. All four grammar cameras
  re-rendered clean.
- Drive status 2026-07-04: recorded in `docs/local/MACHINE-NOTES.md` (local
  only); no backup drive connected yet (storage-plan prerequisite 2 still
  open).

## 2026-07-04 — Phase 1 complete: the schema spine

Four open questions answered by the human (recorded in OPEN-QUESTIONS.md +
DECISIONS.md): seated-only v0; explicit dialogue durations
(`DialogueCue.duration` required); camera grammar as JSON data; LLM emits
SceneIntent only.

Deliverables (all JSON Schema draft 2020-12, v1.0.0; validated locally and
independently by pipeline-verifier CHECK-1 ×4 + CHECK-5):

- `schemas/scenespec.schema.json` — SceneSpec, ShotSpec, six-cue discriminated
  union (animation/dialogue/camera/lighting/audio/fx), ActorSpec, SetSpec,
  PropSpec, RenderSpec, ExportSpec, logical-ID vs `target_bindings` separation
- `schemas/sceneintent.schema.json` — the LLM boundary; no asset IDs, semantic
  tags only; framing intents enum (establishing / two_shot / close_on)
- `schemas/validationreport.schema.json` — Phase 3 validator output, with the
  full error-code enum
- `schemas/camera-grammar.schema.json` + `data/camera_grammar.json` — the four
  bar-scene cameras as data
- `schemas/oeb-config.schema.json` + `oeb.config.json` — logical asset IDs →
  files/nodes under `asset_root` (currently `assets/`, placeholders GLB);
  `OEB_ASSET_ROOT` env var overrides for the external library later
- `fixtures/bar_scene.scenespec.json` — seated-only, 3 shots, 6 dialogue
  lines, 26s; exercises animation + dialogue cues, marks, target bindings,
  and three of the four camera setups; the exporter-test reference
- `fixtures/bar_scene.sceneintent.json` — the same scene as pure intent
  (resolver input / Phase 5 LLM vetting target)
- Conventions locked: times in seconds; cue `start_time` shot-relative;
  logical IDs `^[a-z][a-zA-Z0-9_]*$`, never paths

## 2026-07-04 — Agentic workflow qualified + Phase 2A placeholders built

Agent workflow (design: `docs/planning/AGENT-WORKFLOW-PLAN.md`, §8 steps 1–3):

- `.claude/agents/` scaffolded: `_TEMPLATE.md`, `placeholder-builder` (worker
  tier), `pipeline-verifier` (worker tier, read-only), `escalation-reviewer`
  (reviewer tier; renamed from its original model-branded name in the
  2026-07-05 trademark scrub)
- `docs/planning/ESCALATION-PROTOCOL.md` — tiers, triggers, bundle/report formats
- All three pilots QUALIFIED per plan §7: lint, dry runs, escalation drills.
  6 profile bugs found and fixed during qualification (see profile changelogs);
  headline: a worker will invent missing inputs unless explicitly forbidden —
  now forbidden protocol-wide
- Decided: the author tier authors/revises profiles only; the reviewer tier orchestrates day-to-day

Phase 2A (produced by the qualified `placeholder-builder` during its dry runs):

- `tools/make_placeholders.py` — headless-Blender generator: grey-box set +
  4 props + 2 characters (5-bone armatures, distinct tints) + 4 `_A` marks +
  4 cameras + 12 named actions, exact `docs/BAR-SCENE.md` IDs
- Exports verified: `assets/placeholders/bar_scene_placeholders.glb`
  (27 nodes / 12 animations, pygltflib manifest complete, Blender re-import
  round-trip OK) and `.usdc` (43 prims, stage loads clean)
- Godot 4.7 import verified (same day, closing Phase 2A + the Phase 0
  round-trip item): headless `--import` of the GLB, exit 0, zero error lines,
  imported `.scn` produced under `assets/placeholders/godot_check/`.
  Environment finding (F5): Godot hangs (uninterruptible I/O) when launched
  from a sandboxed subagent shell — Godot runs belong to the orchestrator's
  shell; noted in the builder profile

Environment findings (baked into profiles): MPFB adds ~2 min to every headless
Blender startup — always pass `--factory-startup`; Blender 5.x removed
`action.fcurves` (slotted actions — use `keyframe_insert` while the action is
assigned).

## 2026-07-03 — Project inception

- Research and architecture phase completed (external handoff document reviewed)
- Core decisions locked (see docs/DECISIONS.md):
  - LLM role: translator/constraint layer, not writer
  - Pipeline: deterministic, asset/rig-based; no generative video
  - Core tools: Blender + Godot + local LLM + optional USD layer
  - Canonical data: SceneSpec / ShotSpec / cue-based schema with exporters
  - First milestone: "Hero in a bar chatting with a bartender"
  - Primary machine: Apple-silicon workstation (specifics local-only)
  - Asset sourcing: CC0-friendly sources first
- Project scaffolding created: PROJECT-TODO.md, PROJECT-DONE.md, docs/

## 2026-07-03 — Phase 0 automated setup (no human involvement)

Installed / downloaded on the primary machine:

- Blender 5.1.2 (`/Applications/Blender.app`, `brew` cask)
- Godot 4.7 (`/Applications/Godot.app`, `brew` cask)
- llama.cpp (`brew`; `llama-cli`, `llama-completion`, `llama-server`)
- Python venv `.venv/` (3.14.5) with `jsonschema`, `pygltflib`, `usd-core`
- Local model `models/qwen2.5-3b-instruct-q4_k_m.gguf` (2.0 GB) — load 675 ms, ~105 tok/s prompt eval, inference verified
- git repo + `.gitignore` (excludes `.venv/`, `models/`, `assets/`)

- MPFB (MakeHuman) — installed + enabled as a Blender extension via CLI (build 20260613):
  `Blender --online-mode --command extension install -s -e blender_org.mpfb`
  (Since MPFB 2.0.8 the extension platform is the recommended install, not a standalone zip.)

Deferred (need human choices/steps, not automatable):

- CC0 asset packs (Poly Haven / Quaternius / Kenney) — require per-asset selection for the bar scene (Phase 2)

Disk note: free-space timeline tracked in `docs/local/MACHINE-NOTES.md`.
