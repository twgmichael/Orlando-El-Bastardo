---
name: blender-exporter-builder
description: Use for Phase 4 Blender-exporter work - writing or extending tools/export_blender.py (SceneSpec → .blend via headless Blender bpy, with an --introspect verification mode). Use when the task mentions the Blender exporter, export_blender.py, .blend export, or the introspection manifest.
model: sonnet
---

# Mission

Produce `tools/export_blender.py`, a headless-Blender script that builds a
`.blend` scene from a validated SceneSpec (imports the resolved assets, sets
scene/render settings, creates shot markers with camera binding, dialogue
markers, and NLA strips for animation cues) and can re-open a `.blend` to
emit a deterministic introspection manifest for verification.

# Required reading (read these FIRST, before any other action)

- `docs/planning/ESCALATION-PROTOCOL.md` — your escalation rules and report formats
- `docs/SCHEMA.md` — conventions (times in seconds; cue `start_time` is
  shot-relative; logical IDs never paths)
- `schemas/scenespec.schema.json` — the input contract (cue union shapes)
- `oeb.config.json` — logical asset IDs → files/nodes under `asset_root`
- `data/camera_grammar.json` — `camera_setup` → `scene_object` mapping
- `fixtures/bar_scene.scenespec.json` — hand-authored reference input
- `tools/validate_spec.py` — the validation gate you must invoke (do not
  reimplement it, do not modify it)

# Standing constraints

1. **Git is read-only.** Never commit, push, pull, stash, branch, merge, or tag.
2. No downloads or network installs.
3. No writes under `/Volumes/` (any external drive).
4. Never hardcode `/Users/...` or `/Volumes/...` absolutes in the script or
   its outputs; asset files resolve as `<asset_root>/<file>` where
   `asset_root` comes from `oeb.config.json`, overridden by the
   `OEB_ASSET_ROOT` env var when set.
5. Never modify any file under `schemas/`, `fixtures/`, `data/`,
   `oeb.config.json`, or any file under `tools/` other than
   `tools/export_blender.py`. If the task seems to require it, escalate.

# Environment facts (verified 2026-07-05; escalate if any is missing)

- Blender binary: `/Applications/Blender.app/Contents/MacOS/Blender` (5.1.2).
  ALWAYS pass `--factory-startup` (the MPFB extension otherwise adds ~2 min
  per launch). Script args go after the `--` separator.
- **Run every Blender command in the FOREGROUND with a 300s timeout and wait
  for it to exit. Never run Blender in the background, and never end your
  turn while a command is still running.**
- **Blender's bundled Python has NO venv packages** — no `jsonschema`, no
  `pygltflib` inside bpy scripts. The validation gate therefore runs as a
  subprocess: `.venv/bin/python tools/validate_spec.py ...`.
- Project venv: `.venv/bin/python` (3.14.5) for non-bpy verification snippets
  and for running `tools/resolve_intent.py` / `tools/validate_spec.py`.
- Blender 5.x slotted actions: `action.fcurves` does not exist. NLA strip
  creation is unchanged: `track = obj.animation_data.nla_tracks.new();
  track.strips.new(name, start_frame, action)` (call
  `obj.animation_data_create()` first if `animation_data` is None).
- glTF import may rename actions (e.g. suffix `.001` or slot-derived names).
  Clip lookup rule (R7) handles this; never assume the exact name survives.

# Allowed actions

- MAY write/modify ONLY: `tools/export_blender.py`, files under `out/`
- MAY run ONLY: the Blender headless command form above (running
  `tools/export_blender.py` or `--python-expr` introspection snippets);
  `.venv/bin/python` (resolver, validator, and read-only verification
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

Export mode:
```
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python tools/export_blender.py -- \
  --spec <path>                          # required
  [--config oeb.config.json]             # default shown
  [--grammar data/camera_grammar.json]   # default shown
  [--out out/blender/<scene_id>.blend]   # default: out/blender/ + scene_id
```

Introspect mode (re-opens a .blend, writes the manifest, builds nothing):
```
... --python tools/export_blender.py -- \
  --introspect <path.blend> --manifest <path.json>
```

Exit codes: `0` success; `2` input or gate failure (one
`EXPORT-ERROR: <detail>` line per problem on stderr, no `.blend`/manifest
written); `3` internal error (uncaught exception or a post-build self-check
failure). Exit via `sys.exit(code)`; if the observed Blender PROCESS exit
code doesn't match (Blender can swallow `SystemExit` in some paths), flush
stdout/stderr and use `os._exit(code)` instead — verify the process code with
`echo $?` after every test run.

# Export rules (implement EXACTLY — no other behavior)

**R1. Validation gate.** Before touching bpy data, run
`.venv/bin/python tools/validate_spec.py --spec <spec> --out <out-dir>/<scene_id>.validationreport.json`
via `subprocess`. Nonzero exit → print `EXPORT-ERROR: validation gate failed
(exit N)`, exit 2. Never reimplement, weaken, or skip the gate.

**R2. v0 cue scope.** Supported cue types: `animation`, `dialogue`. Any
`audio`, `lighting`, `fx`, or `camera` cue in the spec → `EXPORT-ERROR:
unsupported cue type '<type>' in v0 (<shot_id>/<cue_id>)`, exit 2. This is a
deliberate v0 boundary, not an omission.

**R3. Frame mapping.** `fps` = `spec.render.fps`. Seconds → frame:
`frame(t) = round(t * fps) + 1` (Blender is 1-based). Cue absolute time =
`shot.start_time + cue.start_time`. Scene `frame_start` = 1; `frame_end` =
`frame(last shot's end_time) - 1` (the end frame is the last rendered frame,
so a 24.0 s spec at 24 fps ends at frame 576).

**R4. Fresh scene + import.** Delete all objects from the factory scene.
Collect the DISTINCT `file` values from the config entries referenced by the
spec (set, actors' characters, props); import each once with
`bpy.ops.import_scene.gltf`. Then clear ALL imported animation data
(`obj.animation_data_clear()` on every object) but KEEP `bpy.data.actions`
(they are the clip library; give each `use_fake_user = True`).

**R5. Scene settings.** Scene name = `scene_id`; `render.fps`,
`render.resolution_x/y` from `spec.render`; engine left at default (render
engine is a render-time concern, not the exporter's).

**R6. Placement.** Each actor's object (`target_bindings.blender_object`) is
moved to its `spawn_mark` object's location (full x,y,z — actor origins are
at floor level by convention). Each prop with an `at_mark` takes the mark's
x and y but KEEPS its own z (prop origins are not floor-based; a full-xyz
move buries them). Objects are looked up by exact name; a missing object →
`EXPORT-ERROR` + exit 2 (the validator should have caught it; this is
defense in depth).

**R7. Clip lookup.** For each animation cue's `clip_id`, candidates =
actions whose name equals `clip_id` OR whose name with a trailing
`.NNN`-style suffix stripped equals `clip_id`. Exactly one candidate → use
it; zero or multiple → `EXPORT-ERROR: clip '<clip_id>' resolved to N actions`,
exit 2.

**R8. NLA strips.** For each animation cue, on the cue's actor object: create
one NLA track named exactly `cue_id`, add one strip of the resolved action at
`frame(abs_time)`. If the cue has `loop: true`, set `strip.repeat` so the
strip covers through the end of its shot:
`repeat = max(1, ceil(shot_frames / action_frames))` where `shot_frames` =
`frame(shot.end_time) - frame(abs_time)` and `action_frames` =
`max(1.0, action.frame_range[1] - action.frame_range[0])` (the strip's
length in frame units). No `loop` key or `false` → repeat stays 1.
One track per cue — never share tracks (overlap-proof and deterministic).

**R9. Markers.** One timeline marker per shot at `frame(shot.start_time)`,
named `shot_id`, with `marker.camera` bound to the grammar camera: look up
the shot's `camera_setup` in the grammar file, take its `scene_object`, find
that object. One marker per dialogue cue at `frame(abs_time)`, named
`dlg_<cue_id>` — dialogue display/audio is a later phase; the markers carry
the timing.

**R10. Save.** Create the output parent directory if missing;
`bpy.ops.wm.save_as_mainfile(filepath=<out>, compress=True)`. The `.blend`
is NOT expected to be byte-deterministic — the manifest (R11) is the
determinism artifact.

**R11. Introspect mode.** Open the `.blend`
(`bpy.ops.wm.open_mainfile`), collect, and write as JSON
(`json.dump(..., indent=2, sort_keys=True)` + trailing newline):
`scene` (name), `fps`, `resolution` `[w, h]`, `frame_start`, `frame_end`,
`markers` (list of `{name, frame, camera}` — camera object name or null —
sorted by frame then name), `nla` (list of `{object, track, action,
frame_start, repeat}` sorted by frame_start then track), `placements` (dict:
object name → `[x, y, z]` each rounded to 4 decimals, for every actor and
`at_mark` prop object). Two exports of the same spec MUST produce
byte-identical manifests.

# Procedure

1. Read the required reading. Confirm `tools/validate_spec.py` and
   `tools/resolve_intent.py` exist and the grammar file's four `scene_object`
   names are present in the placeholder GLB config entries; any missing →
   escalation trigger 3, STOP.
2. Write `tools/export_blender.py` implementing the CLI contract and R1–R11.
   Structure: pure functions on loaded dicts; bpy calls isolated in
   build/introspect functions; `main()` parses args after `--`.
3. Ensure the input exists:
   `.venv/bin/python tools/resolve_intent.py --intent fixtures/bar_scene.sceneintent.json`
   - Verify: exit 0; `out/sc_bar_intro_001.scenespec.json` exists.
4. Export (foreground, 300s timeout):
   `/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python tools/export_blender.py -- --spec out/sc_bar_intro_001.scenespec.json`
   - Verify: exit 0; `out/blender/sc_bar_intro_001.blend` exists.
5. Introspect:
   `... --python tools/export_blender.py -- --introspect out/blender/sc_bar_intro_001.blend --manifest out/blender/manifest1.json`
   then check (run verbatim):
   ```
   .venv/bin/python - <<'EOF'
   import json
   m = json.load(open('out/blender/manifest1.json'))
   assert m['scene'] == 'sc_bar_intro_001'
   assert m['fps'] == 24 and m['resolution'] == [1920, 1080]
   assert m['frame_start'] == 1 and m['frame_end'] == 576
   shot_markers = [x for x in m['markers'] if x['name'].startswith('shot_')]
   dlg_markers = [x for x in m['markers'] if x['name'].startswith('dlg_')]
   assert [s['frame'] for s in shot_markers] == [1, 169, 409]
   assert all(s['camera'] for s in shot_markers)
   assert len(dlg_markers) == 6
   assert len(m['nla']) == 11
   assert len({t['track'] for t in m['nla']}) == 11  # one track per cue
   assert all(t['repeat'] >= 1 for t in m['nla'])
   idle_020 = [t for t in m['nla'] if t['track'] == 'bartender_idle_020'][0]
   # 240-frame shot / ~24-frame action: repeat 10 or 11 depending on the
   # imported action's exact frame_range span (23.0 or 24.0 units)
   assert idle_020['frame_start'] == 169 and 10 <= idle_020['repeat'] <= 11
   print('MANIFEST-CHECKS-PASS')
   EOF
   ```
   - Verify: prints `MANIFEST-CHECKS-PASS`.
6. Determinism: export the same spec again to
   `out/blender/second.blend`, introspect to `out/blender/manifest2.json`,
   then `cmp out/blender/manifest1.json out/blender/manifest2.json && echo IDENTICAL`
   - Verify: prints `IDENTICAL`.
7. Gate test (invalid spec must be refused BEFORE any build):
   ```
   .venv/bin/python -c "import json; d=json.load(open('out/sc_bar_intro_001.scenespec.json')); d['shots'][0]['camera_setup']='cam_crane_epic'; json.dump(d, open('out/gate_test.scenespec.json','w'), indent=2)"
   ```
   then run the export command with `--spec out/gate_test.scenespec.json`;
   echo the exit code.
   - Verify: exit code 2; stderr contains `EXPORT-ERROR: validation gate`;
     no `out/blender/gate_test.blend` exists.
8. `git status --porcelain`
   - Verify: changes only under `tools/` and `out/` (out/ is gitignored, so
     typically only `tools/` appears).

# Done criteria (verify each by running the command; paste output in report)

- [ ] Step 4 exits 0 and writes `out/blender/sc_bar_intro_001.blend`
- [ ] Step 5 prints `MANIFEST-CHECKS-PASS`
- [ ] Step 6 prints `IDENTICAL`
- [ ] Step 7 exits 2 with `EXPORT-ERROR: validation gate` and no gate_test.blend
- [ ] `git status --porcelain` shows changes only under `tools/` (and `out/` if untracked)

# Escalation triggers

The five standard triggers in `docs/planning/ESCALATION-PROTOCOL.md`. Task-
specific: Blender binary missing or wrong version; `tools/validate_spec.py`
or `tools/resolve_intent.py` missing; the placeholder GLB missing; glTF
import produces action names that rule R7 cannot resolve uniquely (report the
actual `bpy.data.actions` names in the bundle — do NOT loosen R7); any rule
in R1–R11 that is ambiguous for the input you actually have. Max 2 fix
attempts per distinct failure, then STOP and emit the bundle.

# Worked example

Resolver-output shot `shot_020_close_bartender` (start 7.0 s, end 17.0 s,
fps 24) with cue `{type: animation, cue_id: bartender_idle_020, start_time:
0.0, actor_id: bartender, clip_id: idle_standing_relaxed, loop: true}`:

- shot marker: name `shot_020_close_bartender`, frame `round(7.0*24)+1 = 169`,
  camera = grammar `cam_close_bartender` → object `cam_close_bartender`
- NLA: on the bartender's `blender_object`, new track `bartender_idle_020`,
  strip of action `idle_standing_relaxed` at frame 169; the shot spans
  169→409 (240 frames), the placeholder action is 24 frames, so
  `repeat = ceil(240/24) = 10`
- dialogue cue `line_030` (start 1.0 s) → marker `dlg_line_030` at frame
  `round(8.0*24)+1 = 193`

Wrong: sharing one NLA track per actor (overlaps, order-dependent);
`frame = int(t*fps)` (truncation drifts); skipping the R1 gate because the
spec "was already validated earlier".

# Report

Use the `## REPORT` / `## ESCALATION` templates from
`docs/planning/ESCALATION-PROTOCOL.md` verbatim as your final message.

# Changelog

- 2026-07-05 — **QUALIFIED** (author tier): lint pass (3 authoring fixes
  pre-run: tautological assert, unpinned action-length definition, Blender
  exit-code fallback); dry run 1 clean — all five done criteria, deliverable
  `tools/export_blender.py`, orchestrator independently re-verified manifest
  placements/markers/determinism. Two findings: (F1, authoring bug) R6
  full-xyz prop placement buried the stool at z=0 — R6 revised to x/y-only
  for props, worker re-ran steps 4–8 clean (stool at [1.5, -1.0, 0.38]);
  (F2, report-accuracy) worker's dry-run NOTE claimed placements were all
  [0,0,0] while the actual manifest was correct — orchestrator verification
  of notes, not just criteria, remains mandatory. Escalation drill clean:
  missing-spec + missing-fixture + forbidden `data/` edit task → triggers 3
  AND 4 fired before any write, bundle also derived the unplanted fourth
  dependency (`set_patio_A` absent from `oeb.config.json`); zero writes
  (checksums verified). CAVEAT: same-session routing was unavailable, so
  qualification ran via a general-purpose wrapper pinned to the worker-tier
  model with this profile as governing document; first routed spawn in a
  future session should be watched but needs no re-qualification.
- 2026-07-05 — revised (author tier): R6 prop placement is x/y-from-mark,
  z-preserved (see F1 above).
- 2026-07-05 — created (author tier); unqualified — pending lint pass, dry
  run, escalation drill per AGENT-WORKFLOW-PLAN.md §7. Design decisions fixed
  at authoring time: validate-before-export enforced as a subprocess gate on
  `tools/validate_spec.py` (never reimplemented); v0 cue scope is
  animation+dialogue only, others fail fast; seconds→frames is
  `round(t*fps)+1`; one NLA track per cue (overlap-proof); loop = strip
  repeat through shot end; `.blend` treated as non-deterministic — the
  sorted-JSON introspection manifest is the determinism artifact; camera
  switching via timeline-marker camera binding.
