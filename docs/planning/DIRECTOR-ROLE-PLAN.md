---
title: Director Role Plan
created: 2026-07-17T00:00:00-04:00
updated: 2026-08-10T17:30:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: active
canonical: true
canonical_for: director_role
wiki: true
wiki_group: Planning
wiki_page: Director-Role-Plan
wiki_order: 24
---
# Director Role Plan

Recorded 2026-07-17 from review of `oeb-text-adventures.md` and follow-up
discussion about the distinction between producer and director responsibilities
inside `oeb-studio-harness`.

**Updated 2026-08-10 — all three built and live-verified**: framing/
subject, blocking, and the mid-scene move-beat mechanism ("flies into
asteroid field") — `tools/director.py`, `schemas/directorplan.schema.json`,
and (for the move mechanism specifically) a real `SceneIntent` schema
change plus `tools/resolve_intent.py` changes. See both "2026-08-10
built" sections below.

**Earlier 2026-08-10 update — real code identified, DirectorPlan
decided.** See "2026-08-10 discussion and discovery" below: `tools/producer.py`'s
`build_intent()` turned out to already be making Director's calls
(camera framing, blocking flags) via dumb deterministic heuristics with
no LLM involved, exactly the role-conflation this document warned
against when it was only speculative. **Decision: `DirectorPlan` is a
genuinely separate artifact, as originally designed below — not folded
into `SceneIntent`'s shape — but it *informs* `SceneIntent`'s existing
`arrives`/`departs`/`framing`/`subject_actor_id` fields** rather than
replacing them or introducing a parallel set of fields downstream has to
learn. `resolve_intent.py`/`SceneSpec` do not change.

## Discovery

The reviewed note described an "AI Director" that would translate teleplay
content into assembled 3D scenes by loading environments and props, placing
characters, assigning motion, framing cameras, applying lighting, maintaining
continuity, and producing editable scenes for final rendering.

That surfaced an important naming and architecture risk in the current project:
the existing "producer" language already covers script-to-render orchestration,
but it does not fully cover creative staging. Treating the producer as both
logistics manager and director would blur two different responsibilities.

The project already has a strong producer pipeline:

- deterministic screenplay parsing;
- local LLM translation under schema constraints;
- resolver and validator gates;
- asset-library enforcement;
- NEEDED tickets for missing locations, props, clips, and capabilities;
- Blender/Godot/USD export targets;
- render QA and episode assembly.

The missing layer is a distinct, constrained director role: a system that turns
scene facts into intentional shot design, blocking, pacing, performance intent,
and continuity before resolution and export.

## Research From Current Project State

The current architecture says the LLM may act as translator, constraint engine,
scene fitting assistant, format conversion layer, or structured extraction
layer. It explicitly rejects the LLM as story author, freeform director, frame
generator, or unvalidated final-file author.

The producer plan says the producer oversees script-to-render production using
only the provided asset library. If a script names anything outside the library,
the producer halts that scene and emits a structured NEEDED report. The producer
does not improvise, substitute, or build missing capabilities.

The studio harness vision says the harness owns workflow, memory, validation,
and orchestration, while models are replaceable specialists. That supports a
director model as a bounded specialist, not as a privileged authority over the
pipeline.

The scene-graph primitive builder plan already points in the same direction for
conversation-driven layout: flexible creative language needs a semantic
intermediate plan, and natural-language relationships like `faces`,
`left_of`, `behind`, and `mounted_on` must survive as structured build
instructions.

## Role Definitions

### Producer

The producer is the logistics and orchestration layer.

The producer answers: "Can this script or request be produced with the current
studio resources, and what jobs must run?"

Producer responsibilities:

- accept a script, scene, or creative request as input;
- split work into scenes or jobs;
- invoke translator, director, resolver, validator, exporter, renderer, and QA
  steps in order;
- consult the asset registry, resolver map, camera grammar, clip library, and
  harness capability registry;
- classify failures as bugs, missing assets, missing vocabulary, or missing
  capabilities;
- emit structured NEEDED tickets when production cannot proceed honestly;
- assemble production reports, artifacts, and episode outputs;
- keep the run deterministic, auditable, and bounded.

The producer must not rewrite the story, silently substitute available assets,
invent props, author shots for taste, bypass validation, or hide gaps.

### Director

The director is the creative staging layer.

The director answers: "Given this scene, how should it play on screen?"

Director responsibilities:

- convert scene facts into a shot plan;
- choose shot purposes such as establishing, reveal, reaction, insert,
  over-shoulder, close-up, medium, or tracking shot;
- define blocking: actor start positions, entrances, exits, movement, facing,
  spacing, following, turning, sitting, standing, and prop interaction;
- define pacing: beat timing, holds, pauses, reaction windows, and emphasis;
- preserve continuity: actor positions across shots, screen direction, eyelines,
  prop state, and entry/exit state;
- express performance intent in broad, mappable terms such as tense, casual,
  hurried, suspicious, comic, restrained, or confrontational;
- choose from approved camera grammar and lighting presets where available;
- produce structured, reviewable direction before final `SceneSpec` resolution.

The director must not create new story events, rewrite dialogue, substitute
unavailable locations or characters, directly author Blender/Godot/USD files,
or decide that missing requirements are acceptable. If direction requires a
camera setup, animation, lighting preset, prop, or set mark that does not exist,
the director should express that requirement structurally so the producer and
resolver can report it.

## 2026-08-10 discussion and discovery

**Finding:** `tools/producer.py`'s `build_intent()` already makes two of
Director's calls, inline, via plain deterministic heuristics with no LLM
involved anywhere:

1. **Camera/shot framing choice** — `shot_intents[].framing` and
   `subject_actor_id`. Selection is a static shot-heading dict lookup
   (`data/standins.json`'s `shot_headings`) plus a hardcoded fallback:
   if a close/medium shot's subject isn't a known cast member, silently
   downgrade to `establishing`. That fallback is a judgment call, made
   today with no judgment behind it.
2. **Blocking flags** — `actors[].arrives`/`departs`, sourced from
   `tools/screenplay.py`'s `detect_arrivals()`/`detect_departures()`
   (keyword-based prose detection, e.g. "walks in"/"exits").

Both populate exactly the `SceneIntent` fields this document already
expected a director layer to inform. Same shape of finding as the
production-designer review the same day: a role this document had
already scoped out got absorbed into Producer's deterministic code
before the role existed to claim it, because showing rendered progress
came first. `resolve_intent.py`/`SceneSpec` are unaffected either way —
they only ever consume `SceneIntent`, which already carries these
fields; only who decides their values changes.

**What's genuinely new, not a relocation** — the concrete gap a real
example exposed ("JB100 flies into asteroid field," from the production-
designer discussion): nothing today translates free-form motion prose
into an actual move cue. `resolve_intent.py`'s entrance/departure
handling only covers scene-start/scene-end walk-in/walk-out, from each
role's single fixed `entrance` mark pair. Mid-scene motion described in
action text ("dives," "breaks free of the debris cloud," "flies into")
has no mechanism at all. This is the real, unbuilt core of `DirectorPlan`
beats' `action`/`from`/`to`/`timing` fields already sketched below — the
schema anticipated this correctly in 2026-07-17; nothing was ever built
against it.

**Decision: `DirectorPlan` is a genuinely separate artifact, as
originally designed — it informs, not replaces.** `SceneIntent` keeps
its current shape (`actors[].arrives`/`departs`,
`shot_intents[].framing`/`subject_actor_id`); `DirectorPlan` is what
*decides* those field values with real reasoning (LLM-assisted, per
"what Director needs to run standalone" below) instead of the
heuristics above, plus produces the new mid-scene move-beat data
`resolve_intent.py` doesn't consume yet. `resolve_intent.py` and
`SceneSpec` do not change shape for this. Where exactly `DirectorPlan`'s
richer beat data (the "flies into asteroid field" case) enters
`SceneSpec` — a new cue path, or additional `SceneIntent` fields
resolve_intent.py learns to read — is not decided here; that is the
schema/build work "Near-Term Work" below still needs to do.

## 2026-08-10 built: framing/subject and blocking, LLM-assisted

Built and live-verified against the real local LLM (the same
`llama-completion` CLI + `qwen2.5-3b-instruct-q4_k_m.gguf` model
`llm_review()` already uses, not a mock):

- **`schemas/directorplan.schema.json`** (new): `dramatic_intent`
  (human-review only), `shots[]` (`order`, `framing` — same four-value
  enum as `SceneIntent.shot_intents[].framing`, no new camera-intent
  vocabulary — `subject_actor`, `purpose`, `motion_note`), `blocking[]`
  (`actor`, `arrives`, `departs`, `evidence`).
- **`tools/director.py`** (new): `direct_scene()` makes one constrained
  local-LLM call per scene, same call/fallback discipline as
  `llm_review()` (grammar-constrained via `--json-schema`, hard failure
  → `(None, note)`, caller falls back to the pre-existing deterministic
  heuristics — a broken/unavailable LLM never blocks a scene).
  `sanitize_plan()` re-validates past the schema boundary: a JSON-schema
  grammar constrains *shape*, not *this scene's actual cast or section
  count*, so any shot/blocking entry referencing something outside the
  real scene data is dropped rather than trusted.
- **`tools/producer.py`**: `build_intent()` takes an optional
  `director_plan` argument. Framing/subject: an explicit author shot
  heading's framing type is never overridden (same "deliberate author
  direction first" principle as slugline resolution,
  `SCREENPLAY-SLUGLINE-ACTOR-PRESENCE-GAP.md`) — the director only
  fills sections the screenplay left open, or supplies a subject when
  the heading's own `subject_raw` didn't resolve to cast. The director
  call happens in `main()`'s scene loop right where the "Answered
  2026-08-10" pipeline slot below says it should, immediately before
  `build_intent()`; the plan is persisted to
  `out/production/<episode>/scenes/<scene_id>/director_plan.json` for
  human review (Recommendation 4).
- **Real reliability finding, not a hypothetical concern — changed the
  design:** live-testing `direct_scene()` against a realistic bar scene
  ("The Hero walks in... The Hero finishes the drink and walks out.")
  showed the local 3B model is not reliable enough to safely *replace*
  `screenplay.py`'s keyword-based `detect_arrivals()`/`detect_departures()`
  for blocking. First pass: the model asserted `bartender.arrives=true`
  with no textual basis (hallucination) while missing `hero.departs`
  that the keyword regex catches cleanly. Adding an `evidence` field to
  the schema (requiring a quote from the scene's own action text,
  checked as a real substring before a flag is trusted — a grounding
  check that accepts free-form phrasing the keyword list would miss,
  without trusting an unverified assertion) fixed the hallucination but
  swung the other way: the model then defaulted both actors to
  false/false, missing the "walks in"/"walks out" evidence that was
  right there in the text it was given. **Resulting design: blocking is
  a UNION, not a replacement** — an actor arrives/departs if EITHER the
  keyword regex OR the grounded director plan says so. The regex stays
  as the reliability floor (the plan's own "reuse existing rails"
  recommendation, applied literally); the director can only ADD
  coverage for phrasing the regex misses, never remove coverage the
  regex already correctly provides. Confirmed via a full
  `producer.py --no-render` run: the hero's `arrives`/`departs` came
  through correctly in the final `SceneIntent` from the regex floor
  even on a run where the director's own plan asserted neither.
- **Superseded below**: the mid-scene move-beat mechanism ("flies into
  asteroid field") was left unbuilt as of this section; see "2026-08-10
  built: mid-scene move-beat mechanism" further down for what shipped.

## 2026-08-10 built: mid-scene move-beat mechanism

**Decision, resolving the "not decided here" open question above:**
`SceneIntent` gains one new optional field — `beats[].moves[]`
(`actor_id`, `to_mark`, optional `clip_id`/`duration_s`), schema change
in `schemas/sceneintent.schema.json`. `resolve_intent.py` resolves each
into a standard `move` `SceneSpec` cue — the exact same cue type
entrances/departures already emit (`type: "move", from_mark, to_mark,
duration, clip_id?, facing`) — no new cue type, no exporter change:
`export_blender.py`/`blueprint_interpreter.py` need nothing new, since
a `move` cue with no `clip_id` was already a supported transform-only
move for both actors and placeholder props.

- **`tools/resolve_intent.py`**: tracks each actor's *current* mark
  across the shot loop (`current_mark`, seeded from `spawn_mark`,
  updated whenever a beat move places the actor elsewhere) — new
  resolver state; nothing before this needed to know "where is this
  actor right now" mid-scene. A beat move resolves to a `move` cue
  scheduled after that shot's dialogue (same anchor R14 departures
  already use), `from_mark` = the actor's tracked current mark,
  `to_mark` = the beat's own field, `facing: "travel"`, `duration`
  defaulting to 2.0s. **Real correctness fix as a side effect**: a
  departure in the same shot as a prior move now correctly rises from
  the actor's *actual* current mark instead of always their original
  `spawn_mark` — `build_departure_cues()`'s mark argument changed from
  `resolved_roles[aid]["spawn_mark"]` to `current_mark[aid]`. Verified
  live: a synthetic scene with both a move and a departure in the same
  shot produces `rise: from=<the move's to_mark>`, not the old spawn
  mark.
- **No new mark vocabulary invented.** `to_mark` must be exactly one of
  the resolved location's own registered marks
  (`data/resolver_map.json`'s `locations[location_tag].marks`) — for
  placeholder-tier locations that's the entry/center/exit vocabulary
  this document anticipated below, but the mechanism reads whatever
  marks a location actually has (a real hand-built set like the bar has
  semantic mark names, not entry/center/exit) rather than hardcoding
  that one vocabulary. An invalid `to_mark` isn't resolver-checked
  directly — it falls through to `tools/validate_spec.py`'s existing
  `unknown_mark` check, same discipline as every other cue's marks, no
  duplicated validation.
- **`tools/director.py`**: `direct_scene()` takes a new
  `location_marks` parameter (the list above) and prompts the model to
  propose a per-shot `move` (`actor`, `to_mark`, `evidence`) only when
  the action text clearly describes it and a real mark plausibly
  matches. `schemas/directorplan.schema.json` gained the matching
  `shots[].move` object. Same evidence-grounding discipline the
  blocking fix above established: `sanitize_plan()` discards a proposed
  move unless `to_mark` is literally one of `location_marks` (not just
  well-formed) AND `evidence` is a real substring of the scene's own
  action text — an ungrounded or invented-mark move is dropped exactly
  like an ungrounded arrival/departure flag was.
- **`tools/producer.py`**: passes the resolved location's marks into
  `direct_scene()`; `build_intent()` turns a validated
  `plan_shots[j]["move"]` into `beats[j]["moves"]`.
- **Verified, full chain, real screenplay parse**: a synthetic scene
  ("The Journeyblaster flies into the asteroid field...") parsed for
  real via `tools/screenplay.py`, run through `director.sanitize_plan()`
  with a well-formed plan, `producer.build_intent()`, and
  `resolve_intent.resolve_intent()` — produced a real, schema-valid
  `move` cue (`from: ..._center`, `to: ..._exit`, `facing: travel`).
  Same reliability caveat as the blocking fix: a *live* local-3B-model
  call against this same scene did not itself propose a move (the
  model's own known section-indexing unreliability, already documented
  above for framing/blocking — `sanitize_plan()` correctly dropped the
  malformed shot rather than trusting it). The wiring is proven
  correct; the local model's proposal rate for this specific judgment
  call is not — same honest gap as the blocking union fix, not
  something this pass tried to solve. A full 7-scene real-teaser
  regression run (`--primitive-fallback --no-render`) delivered 7/7
  after the `resolve_intent.py` changes, confirming no regression to
  existing entrance/departure behavior. Full `oeb-studio-harness/server`
  pytest suite (382 tests) unaffected; `tools/security_sweep.py` clean.

**What Director needs to run standalone:**

- Factual scene data — the parsed screenplay sections/action/dialogue,
  already produced deterministically today; no change needed there.
- The *resolved* location's marks, from whatever Production Designer
  and Producer have already registered — blocking can't choose a `to`
  mark without knowing what marks exist. For rough blocking, every
  location today only has `entry`/`center`/`exit`, a small, naturally
  LLM-friendly vocabulary to select from without inventing new marks.
- `data/camera_grammar.json`, for camera_intent → literal camera
  lookup. Director picks the framing purpose; the resolver still does
  the literal camera-object match, unchanged.
- A constrained local-LLM call point with its own schema
  (`directorplan.schema.json`, sketched below, never drafted for real)
  and its own vetting matrix — the same discipline Producer's existing
  `llm_review()` step already uses (schemas/scenereview.schema.json),
  not a new pattern.
- A pipeline slot: after Production Designer resolves assets for a
  scene, before `resolve_intent.py`'s `SceneSpec` resolution — matching
  this document's own "Recommended shape" below. "Near-Term Work"'s
  "decide where the director step runs in `tools/producer.py`" is now
  answered: immediately after the production-designer loop's
  continuation trigger (`tools/producer.py --scenes N`), before
  `build_intent()` runs — `build_intent()` itself is what loses the two
  heuristics above once `DirectorPlan` exists to inform them instead.

## Proposed Pipeline Position

Current simplified shape:

```text
script
  -> scene intent / structured extraction
  -> resolver
  -> validator
  -> exporter
  -> render
```

Recommended shape:

```text
script scene
  -> factual scene extraction
  -> DirectorPlan
  -> resolver
  -> validator
  -> exporter
  -> render
```

In this shape:

- `SceneIntent` records what the script says happened.
- `DirectorPlan` records how the scene should be staged, shot, paced, and kept
  continuous.
- `SceneSpec` records the resolved, validated production instructions.
- The producer orchestrates the movement between those artifacts.

## DirectorPlan Sketch

`DirectorPlan` should be a constrained intermediate artifact, not a replacement
for `SceneIntent` or `SceneSpec`.

Example shape:

```json
{
  "scene_id": "engineering_engines_online",
  "dramatic_intent": "urgent command",
  "shots": [
    {
      "shot_id": "wide_entry",
      "purpose": "establish location and movement",
      "camera_intent": "wide_establishing",
      "beats": [
        {
          "actor": "captain",
          "action": "enter",
          "from": "door",
          "to": "console",
          "timing": "0-4s"
        },
        {
          "actor": "engineer",
          "action": "follow",
          "from": "door",
          "to": "behind_captain",
          "timing": "1-5s"
        }
      ]
    },
    {
      "shot_id": "captain_closeup",
      "purpose": "emphasize order",
      "camera_intent": "closeup_front",
      "continuity_from": "wide_entry",
      "beats": [
        {
          "actor": "captain",
          "action": "speak",
          "dialogue": "Bring the engines online.",
          "timing": "5-7s"
        }
      ]
    }
  ],
  "continuity": {
    "captain_position_after_scene": "console",
    "engineer_position_after_scene": "behind_captain",
    "screen_direction": "captain_moves_left_to_right"
  }
}
```

Open schema work:

- decide whether `DirectorPlan` is a new schema or a named section within the
  planned schema consolidation;
- define a small camera-intent vocabulary that maps cleanly to
  `data/camera_grammar.json`;
- define a small blocking vocabulary that maps cleanly to marks, movement cues,
  animation clips, and scene relationships;
- define continuity fields that are cheap enough to validate in early versions;
- define how missing direction requirements become NEEDED tickets.

## Recommendations

1. Add a distinct `DirectorPlan` layer between factual scene extraction and
   resolver/export.
2. Keep the director constrained to structured direction, not direct file
   authoring or asset invention.
3. Preserve the producer as the logistics owner: job dispatch, feasibility,
   failure classification, reports, and tickets.
4. Make the director output human-reviewable before render. This gives the
   project an explicit place to revise staging without touching exporter code.
5. Treat the initial director as a small vocabulary system: shot purpose,
   blocking, pacing, continuity, performance intent, camera intent, and lighting
   mood.
6. Reuse existing project rails: schema validation, resolver mapping, approved
   asset IDs, camera grammar, clip libraries, and NEEDED ticket behavior.
7. Avoid adding generative video or unconstrained animation systems to the core
   path. External motion or facial-animation tools may later feed the asset and
   clip library, but they should not bypass the producer/resolver/validator
   chain.

## Decisions

- The producer and director are distinct roles.
- The producer owns orchestration, feasibility, reporting, and tickets.
- The director owns shot design, blocking, pacing, performance intent, and
  continuity.
- The director is constrained and schema-bound; it is not a freeform AI
  filmmaker.
- The director must not invent unavailable assets, rewrite story facts, or
  directly author target files.
- Missing director requirements should become structured requirements that the
  producer/resolver can surface as NEEDED work.
- **2026-08-10: `DirectorPlan` is a genuinely separate artifact (not
  folded into `SceneIntent`'s shape) that informs `SceneIntent`'s
  existing `arrives`/`departs`/`framing`/`subject_actor_id` fields**,
  rather than resolve_intent.py/SceneSpec learning a second shape.
  `tools/producer.py`'s `build_intent()` currently sets those same
  fields via plain heuristics with no LLM involved (shot-heading dict
  lookup, keyword-based arrival/departure detection) — that is the code
  `DirectorPlan` replaces, not new scope.
- **2026-08-10: the mid-scene move-beat mechanism gets a real
  `SceneIntent` schema addition (`beats[].moves[]`), not a workaround
  to avoid touching the schema** — the "resolve_intent.py/SceneSpec do
  not change shape" constraint from the decision above was scoped to
  the framing/blocking work specifically; this document always left the
  move mechanism's own shape "not decided" until built. `SceneSpec`
  itself is genuinely unchanged: the new field resolves into the
  already-existing `move` cue type.
- The recommended architecture is:

```text
script scene
  -> factual scene extraction
  -> DirectorPlan
  -> resolved SceneSpec
  -> validation
  -> export/render/QA
  -> production report
```

## Near-Term Work

- Add `DirectorPlan` to the schema consolidation discussion alongside
  `SceneIntent`, conversational scene plans, primitive build specs, and
  `SceneSpec`.
- **Built 2026-08-10**: `schemas/directorplan.schema.json` — see
  "2026-08-10 built" above for the actual (deliberately conservative)
  vocabulary shipped.
- Create one fixture from the pilot or bar scene showing factual extraction,
  director plan, and resolved scene spec side by side.
- **Answered 2026-08-10**: the director step runs in `tools/producer.py`
  immediately after the production-designer loop's continuation trigger,
  before `build_intent()` — see "2026-08-10 discussion and discovery"
  above. `build_intent()` loses its framing/arrival-departure heuristics
  once `DirectorPlan` exists to inform those fields instead.
- Add a qualification drill: one in-library scene should produce useful staged
  direction; one scene needing an unavailable camera, mark, or clip should
  produce a clean NEEDED path rather than a hidden substitution. Still
  open — not built.
- **Still open**: the local 3B model's proposal *rate* for both blocking
  and moves is genuinely low (documented in both "2026-08-10 built"
  sections above) — the wiring is correct and safe (ungrounded/invalid
  proposals are dropped, never a crash or a bad cue), but a stronger
  local model, a better-tuned prompt, or a small few-shot example in
  the system prompt (Recommendation 7's "worked examples" rule) would
  likely raise how often Director actually contributes something beyond
  the deterministic floor. Not attempted this pass.
