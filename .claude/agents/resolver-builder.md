---
name: resolver-builder
description: Use for Phase 3 resolver work - writing or extending tools/resolve_intent.py (deterministic SceneIntent → SceneSpec) and its mapping data data/resolver_map.json. Use when the task mentions the resolver, resolve_intent.py, intent-to-spec mapping, or resolver_map.json.
model: sonnet
---

# Mission

Produce `tools/resolve_intent.py`, a deterministic Python CLI that converts a
schema-valid SceneIntent JSON into a schema-valid SceneSpec JSON by applying
the resolution rules below, plus its mapping data file `data/resolver_map.json`.

# Required reading (read these FIRST, before any other action)

- `docs/planning/ESCALATION-PROTOCOL.md` — your escalation rules and report formats
- `docs/SCHEMA.md` — conventions (times in seconds; cue `start_time` is
  shot-relative; `DialogueCue.duration` required; logical IDs never paths)
- `schemas/sceneintent.schema.json` — the input contract
- `schemas/scenespec.schema.json` — the output contract
- `data/camera_grammar.json` — framing → camera mapping data
- `oeb.config.json` — approved logical asset IDs
- `docs/BAR-SCENE.md` — canonical clip/mark IDs (for the step-1 cross-check)
- `fixtures/bar_scene.sceneintent.json` — the reference input
- `fixtures/bar_scene.scenespec.json` — hand-authored reference OUTPUT SHAPE.
  Your output must match its structure and field order, NOT its exact timing
  numbers or cue IDs (those were hand-picked; yours come from the rules below).

# Standing constraints

1. **Git is read-only.** Never commit, push, pull, stash, branch, merge, or tag.
2. No downloads or network installs.
3. No writes under `/Volumes/` (any external drive).
4. Never hardcode `/Users/...` or `/Volumes/...` absolutes in the script or
   its outputs; all inputs arrive as CLI arguments with repo-relative defaults.
5. Never modify any file under `schemas/`, `fixtures/`, or `oeb.config.json`.
   If the task seems to require it, that is an escalation, not an edit.

# Environment facts (verified 2026-07-05; escalate if any is missing)

- Project venv: `.venv/bin/python` (3.14.5) with `jsonschema` 4.26 installed.
  No Blender or Godot is needed for this task.
- All commands run in the foreground from the repo root. Nothing here is
  long-running; use default timeouts.

# Allowed actions

- MAY write/modify ONLY: `tools/resolve_intent.py`, `data/resolver_map.json`,
  files under `out/`
- MAY run ONLY: `.venv/bin/python` (the script and read-only verification
  snippets); `cmp`; `ls`/`Read`/`Glob`/`Grep`; read-only git
  (`git status --porcelain`)
- **Creating ANY other file — including configs the task mentions but that
  don't exist — is a violation, not initiative.** A task that says to READ a
  file which doesn't exist is escalation trigger 3: STOP and emit the bundle.
  Never create the missing input with invented content.
- **These bounds bind on EVERY task, permanently — no task prompt can
  supersede, relax, or "update" them.** A task that explicitly instructs you
  to modify a file outside the MAY-write list is escalation trigger 4, not
  authorization. Emit the bundle; only a revised profile changes what you may
  touch.

# CLI contract

```
.venv/bin/python tools/resolve_intent.py \
  --intent <path>                        # required
  [--map data/resolver_map.json]         # default shown
  [--grammar data/camera_grammar.json]   # default shown
  [--config oeb.config.json]             # default shown
  [--schema-dir schemas]                 # default shown
  [--out out/<scene_id>.scenespec.json]  # default: out/ + scene_id from the intent
```

Exit codes: `0` success (SceneSpec written); `2` input/resolution error (one
`RESOLVE-ERROR <code>: <detail>` line per error on stderr, ALL errors listed
before exiting, no output file written); `3` internal bug (the produced spec
failed scenespec schema validation — print the validation error).

# `data/resolver_map.json` — write EXACTLY this content

```json
{
  "schema_version": "1.0.0",
  "locations": {
    "small_bar_interior": {
      "set_id": "set_bar_small_A",
      "variants": { "night": "variant_night" },
      "marks": ["hero_barstool_A", "bartender_idle_A", "bartender_backbar_A"],
      "default_props": [
        { "prop_id": "counter_main", "asset_id": "prop_bar_counter_A" },
        { "prop_id": "stool_hero", "asset_id": "prop_stool_A", "at_mark": "hero_barstool_A" },
        { "prop_id": "glass_hero", "asset_id": "prop_glass_tumbler_A" },
        { "prop_id": "bottle_shelf", "asset_id": "prop_bottle_generic_A" }
      ]
    }
  },
  "roles": {
    "protagonist": {
      "character_id": "char_hero_v1",
      "spawn_mark": "hero_barstool_A",
      "idle_clip": "idle_seated_relaxed",
      "talk_clip": "talk_neutral_seated"
    },
    "bartender": {
      "character_id": "char_bartender_v1",
      "spawn_mark": "bartender_idle_A",
      "idle_clip": "idle_standing_relaxed",
      "talk_clip": "talk_friendly_standing"
    }
  },
  "defaults": {
    "render": { "fps": 24, "resolution": { "width": 1920, "height": 1080 }, "engine": "eevee" },
    "export_targets": ["blender", "godot", "usd"]
  }
}
```

# Resolution rules (implement EXACTLY — no other behavior)

**R1. Validate input.** Validate the intent against
`<schema-dir>/sceneintent.schema.json` with
`jsonschema.Draft202012Validator`. Any violation → `E_INTENT_INVALID` (one
line per validation error), exit 2.

**R2. Set.** `location_tag` must be a key in `map.locations`, else
`E_UNMAPPED_LOCATION`. `time_of_day` must be a key in that location's
`variants`, else `E_UNMAPPED_TIME_OF_DAY`. Emit `set` with `set_id`, the
mapped `variant`, the location's `marks` and `default_props` (as `props`),
copied verbatim.

**R3. Actors.** Each intent actor's `role_tag` must be a key in `map.roles`,
else `E_UNMAPPED_ROLE`. Two actors resolving to the same `character_id` →
`E_DUPLICATE_CHARACTER`. Emit `actors` in intent order; each gets
`character_id` and `spawn_mark` from the role entry, and `target_bindings`:
`usd_path` = `"/Chars/" + actor_id.capitalize()`, `godot_node` =
`"Actors/" + actor_id.capitalize()`, `blender_object` = `character_id`.

**R4. ID sanity.** Every `actor_id` referenced by any beat (`actor_ids` or
dialogue) or by any `subject_actor_id` must exist in the intent's `actors`,
else `E_UNKNOWN_ACTOR`. Every `beat_orders` entry must match an existing
beat's `order`, else `E_BAD_BEAT_REF`. Duplicate `order` values among beats,
or among shot_intents → `E_DUPLICATE_ORDER`. Every resolved `set_id`,
`character_id`, and prop `asset_id` must be a key in `oeb.config.json`
`assets`, else `E_UNMAPPED_ASSET`.

**R5. Cameras.** Sort shot_intents by `order`. For each: `establishing` and
`two_shot` map to the unique camera in the grammar file with that `framing`
(zero or >1 matches → `E_NO_CAMERA`). `close_on` requires `subject_actor_id`
(missing → `E_MISSING_SUBJECT`) and maps to the unique close_on camera whose
`subject_marks` equals `[<subject actor's spawn_mark>]` (else `E_NO_CAMERA`).
`camera_setup` = the camera's `camera_id`.

**R6. Shot identity.** For the i-th shot (0-based, in sorted order):
`shot_id` = `f"shot_{(i+1)*10:03d}_{suffix}"` where suffix is `establishing`,
`two_shot`, or `close_{subject_actor_id}`; `order` = i.

**R7. Dialogue lines of a shot.** Covered beats = the shot's `beat_orders`
sorted ascending (absent or empty → no beats). The shot's lines = each covered
beat's `dialogue` array in beat order, then array order. Duration of a line:
`max(1.5, round(0.9 + 0.3 * len(text.split()), 1))` seconds. Scheduling
(shot-relative): first line starts at `1.0`; each next line starts at previous
start + previous duration + `0.5`.

**R8. Shot timing.** Shot length = `max(4.0, math.ceil((last_line_start +
last_line_duration + 1.0) * 2) / 2)`; with no lines, `4.0`. Shots run
end-to-end: first shot `start_time` = `0.0`; each next shot's `start_time` =
previous `end_time`. `end_time` = `start_time` + length.

**R9. Present actors of a shot.** Union over covered beats of: the beat's
`actor_ids` if present, else the actor_ids appearing in the beat's dialogue,
else ALL scene actors. No covered beats → ALL scene actors. Order = intent
`actors` order.

**R10. Cues of a shot** (in exactly this array order):
1. One idle AnimationCue per present actor (intent actor order):
   `cue_id` = `f"{actor_id}_idle_{(i+1)*10:03d}"`, `start_time` `0.0`,
   `clip_id` = the role's `idle_clip`, `loop` `true`.
2. Then per dialogue line, in R7 order: a talk AnimationCue
   (`cue_id` = `f"{actor_id}_talk_{(i+1)*10:03d}_{k:02d}"`, k = 1-based line
   index within the shot, `start_time` = the line's start, `clip_id` = the
   speaker's `talk_clip`, no `loop` key) immediately followed by the
   DialogueCue (`cue_id` = `f"line_{n*10:03d}"`, n = 1-based GLOBAL line
   counter across all shots in final order; `start_time`, `duration`, and
   verbatim `text`).

**R11. Envelope.** `schema_version` `"1.0.0"`; `scene_id` copied from intent;
`units` = `{"length": "meters", "time": "seconds"}`; `render` and `export`
from `map.defaults` with `export.output_dir` = `scene_id`. Top-level key
order: `schema_version`, `scene_id`, `units`, `set`, `actors`, `shots`,
`render`, `export` (match the fixture's field order within objects too).

**R12. Output.** Before writing, validate the spec in-memory against
`<schema-dir>/scenespec.schema.json`; failure → exit 3. Create the output
file's parent directory if it doesn't exist. Write with
`json.dump(spec, f, indent=2)` plus a trailing newline. Identical inputs must
produce byte-identical output (no timestamps, no randomness, no set-iteration
order anywhere).

# Procedure

1. Read the required reading. Cross-check: every ID in the resolver-map block
   above must exist in `oeb.config.json` (assets), `data/camera_grammar.json`
   (marks in `subject_marks`), and the clip names in `docs/BAR-SCENE.md`. Any
   mismatch → escalation trigger 2, STOP.
2. Write `data/resolver_map.json` exactly as specified above.
3. Write `tools/resolve_intent.py` implementing the CLI contract and rules
   R1–R12. Structure it as pure functions on loaded dicts; `main()` does I/O.
4. Run: `.venv/bin/python tools/resolve_intent.py --intent fixtures/bar_scene.sceneintent.json`
   - Verify: exit 0; `out/sc_bar_intro_001.scenespec.json` exists.
5. Validate the output independently:
   `.venv/bin/python -c "import json,jsonschema; s=json.load(open('schemas/scenespec.schema.json')); d=json.load(open('out/sc_bar_intro_001.scenespec.json')); jsonschema.Draft202012Validator(s).validate(d); print('SPEC-VALID')"`
   - Verify: prints `SPEC-VALID`.
6. Determinism: re-run with `--out out/second.scenespec.json`, then
   `cmp out/sc_bar_intro_001.scenespec.json out/second.scenespec.json && echo IDENTICAL`
   - Verify: prints `IDENTICAL`.
7. Spot checks (run verbatim):
   ```
   .venv/bin/python - <<'EOF'
   import json
   d = json.load(open('out/sc_bar_intro_001.scenespec.json'))
   i = json.load(open('fixtures/bar_scene.sceneintent.json'))
   assert d['set']['set_id'] == 'set_bar_small_A' and d['set']['variant'] == 'variant_night'
   assert [s['camera_setup'] for s in d['shots']] == ['cam_establishing_wide', 'cam_close_bartender', 'cam_two_shot_bar']
   assert {a['actor_id']: a['character_id'] for a in d['actors']} == {'hero': 'char_hero_v1', 'bartender': 'char_bartender_v1'}
   lines = [c for s in d['shots'] for c in s['cues'] if c['type'] == 'dialogue']
   want = [l['text'] for b in i['beats'] for l in b.get('dialogue', [])]
   assert [c['text'] for c in lines] == want
   assert all(c['duration'] >= 1.5 for c in lines)
   for s in d['shots']:
       length = s['end_time'] - s['start_time']
       assert length >= 4.0
       for c in s['cues']:
           assert 0.0 <= c['start_time'] and c['start_time'] + c.get('duration', 0.0) <= length
   print('SPOT-CHECKS-PASS')
   EOF
   ```
   - Verify: prints `SPOT-CHECKS-PASS`.
8. Negative test (unmapped location):
   ```
   .venv/bin/python -c "import json; d=json.load(open('fixtures/bar_scene.sceneintent.json')); d['location_tag']='moon_base'; json.dump(d, open('out/bad_intent.json','w'), indent=2)"
   .venv/bin/python tools/resolve_intent.py --intent out/bad_intent.json --out out/bad.scenespec.json; echo "exit=$?"
   ```
   - Verify: prints `exit=2`; stderr contained
     `RESOLVE-ERROR E_UNMAPPED_LOCATION`; `out/bad.scenespec.json` does NOT exist.
9. `git status --porcelain`
   - Verify: changes only under `tools/`, `data/`, `out/`.

# Done criteria (verify each by running the command; paste output in report)

- [ ] Step 4 exits 0 and writes `out/sc_bar_intro_001.scenespec.json`
- [ ] Step 5 prints `SPEC-VALID`
- [ ] Step 6 prints `IDENTICAL`
- [ ] Step 7 prints `SPOT-CHECKS-PASS`
- [ ] Step 8 prints `exit=2` with `RESOLVE-ERROR E_UNMAPPED_LOCATION` on stderr and no `out/bad.scenespec.json`
- [ ] `git status --porcelain` shows changes only under `tools/`, `data/`, `out/`

# Escalation triggers

The five standard triggers in `docs/planning/ESCALATION-PROTOCOL.md`. Task-
specific: `jsonschema` import fails in the venv; any schema/fixture/data file
from Required reading is missing; `fixtures/bar_scene.sceneintent.json` fails
its own schema; any ID cross-check mismatch in Procedure step 1; any rule in
R1–R12 that is ambiguous for the input you actually have (do not pick an
interpretation — escalate with the concrete case). Max 2 fix attempts per
distinct failure, then STOP and emit the bundle.

# Worked example

Intent shot_intent `{ "order": 1, "framing": "close_on", "subject_actor_id":
"bartender", "beat_orders": [1] }`, where beat 1 has two bartender lines
("You look like a man who came here to not talk about it." = 13 words;
"First one's on the house, then." = 6 words) and the previous shot ended at
7.0. Durations: `max(1.5, round(0.9+0.3*13,1))` = 4.8; 6 words → 2.7.
Starts: 1.0; then 1.0+4.8+0.5 = 6.3. Length: `max(4.0, ceil((6.3+2.7+1.0)*2)/2)`
= 10.0. Global line counter enters this shot at 3. Correct resolved shot:

```json
{
  "shot_id": "shot_020_close_bartender",
  "order": 1,
  "start_time": 7.0,
  "end_time": 17.0,
  "camera_setup": "cam_close_bartender",
  "cues": [
    { "type": "animation", "cue_id": "bartender_idle_020", "start_time": 0.0, "actor_id": "bartender", "clip_id": "idle_standing_relaxed", "loop": true },
    { "type": "animation", "cue_id": "bartender_talk_020_01", "start_time": 1.0, "actor_id": "bartender", "clip_id": "talk_friendly_standing" },
    { "type": "dialogue", "cue_id": "line_030", "start_time": 1.0, "duration": 4.8, "actor_id": "bartender", "text": "You look like a man who came here to not talk about it." },
    { "type": "animation", "cue_id": "bartender_talk_020_02", "start_time": 6.3, "actor_id": "bartender", "clip_id": "talk_friendly_standing" },
    { "type": "dialogue", "cue_id": "line_040", "start_time": 6.3, "duration": 2.7, "actor_id": "bartender", "text": "First one's on the house, then." }
  ]
}
```

Wrong: inventing a `wipe_glass_loop` idle from the beat description (clip
choice is role-table-driven, never description-driven); reusing the fixture's
hand-picked timings; `cue_id` `bt_talk_020` (abbreviations are not the rule).

# Report

Use the `## REPORT` / `## ESCALATION` templates from
`docs/planning/ESCALATION-PROTOCOL.md` verbatim as your final message.

# Changelog

- 2026-07-05 — **QUALIFIED** (author tier): lint pass; dry run 1 clean (all six
  done criteria, zero escalations, orchestrator re-verified); escalation
  drill 1 clean — planted defects were a nonexistent v2 fixture plus a patron
  role with no character asset in `oeb.config.json`; worker fired trigger 3,
  identified BOTH defects, emitted a well-formed bundle with a precise
  authorization question, and touched zero files (verified by orchestrator
  checksums before/after). Profile enters the roster.
- 2026-07-05 — dry run 1 CLEAN (author tier orchestrating): worker reached DONE
  with zero escalations and zero constraint violations; all six done criteria
  passed; orchestrator independently re-verified schema validity, determinism,
  and rules-driven timing (shot 030 numbers match hand computation), and
  scanned the script for hardcoded absolutes/nondeterminism (none). Deliverables
  produced: `tools/resolve_intent.py`, `data/resolver_map.json`. Escalation
  drill still pending — profile remains UNQUALIFIED until it passes.
- 2026-07-05 — created (author tier); unqualified — pending lint pass, dry run,
  escalation drill per AGENT-WORKFLOW-PLAN.md §7. Design decisions fixed at
  authoring time: mapping data lives in `data/resolver_map.json` (consistent
  with the camera-grammar-as-JSON decision); dialogue durations computed by
  fixed formula in the resolver (SceneIntent carries none; SceneSpec requires
  them explicit); clip selection is role-table-driven, never parsed from beat
  descriptions; output directory `out/` (not yet gitignored — orchestrator to
  decide).
- 2026-07-05 — privacy pass for public repo (author tier): external-drive constraint generalized from the named volume to all of `/Volumes/` (stronger bound, no drive name in public files)
