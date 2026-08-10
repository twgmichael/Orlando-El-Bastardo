---
title: Studio Chat / Production Pipeline Unification — Plan
created: 2026-08-09T21:53:36-04:00
updated: 2026-08-10T16:05:00-04:00
doc_type: plan
production_area: pipeline
department: pipeline
status: active
canonical: true
canonical_for: blueprint_pipeline_unification
wiki: true
wiki_group: Planning
---
# Studio Chat / Production Pipeline Unification — Plan

Date: 2026-08-08 (updated 2026-08-10)

Status: **phases 1-9 (section 12) implemented and live-verified**,
including sections 6-8's wiring into real request flow (registry
resolution, missing-asset fallback, the load-X chooser UI, screenplay
entity resolution + scene composition, the placeholder-promotion
review UI, the motion-grammar library consolidation, and the Blueprint
actor-clip-motion vocabulary closing section 11 item 3's gap). Also
live-verified against a real, full production script for the first
time (`scripts/pilot/`, not a synthetic fixture): `producer.py
--primitive-fallback` (section 7 item 7, 2026-08-09) delivers the full
7-scene JourneyBlaster teaser end-to-end, real rendered `.mp4` files
and a real episode cut, including a deep-space environment
(`setup_space_env()`, wired into `export_blender.py`, section 8), five
asteroid placeholder props, JB100 identified as the JourneyBlaster
5000's tier-1 real-asset stand-in (swapped in for the crude cube it
was previously mapped to), and the mining probe hero asset registered
with its beacon-blink animation working through the full pipeline
(section 7 item 7). Fixing that blink also closed a systemic gap:
props previously had no mechanism to trigger their own baked animation
at all — now generic for every prop, not special-cased. Remaining:
prop builder profile authoring (section 11 item 2); `resolve_intent.
py`'s full `SceneIntent → Blueprint` retargeting (section 11 item 3's
retargeting-itself part, vocabulary gap now closed); the multi-object
effect-cue type needed to register the Hyperspace Effect hero VFX
asset is built and live-verified (section 7 item 7 / section 8), but
only against the default squashed-sphere payload — no hero ship has
been fitted via `attach_ship.py --ship` and exported yet;
`blueprint_interpreter.py`'s `set_environment` operation delegates to
the corrected `setup_space_env()` (section 8) but the mining-probe-
style beacon/material-animation gap has not been swept for other
existing assets that may share it. **Re-run end-to-end 2026-08-10 with
all of the above in place: 7 of 7 scenes delivered**, real per-scene
renders (JB100 and the mining probe each confirmed by raycast, not
just by eye) and a real reassembled episode cut (451KB, 1:43). The
first full-teaser attempt was killed externally partway through (not
by anything in this session); recovered without a full re-render by
running just the missing scene and calling `producer.py`'s own
`episode_cut()` directly against the seven already-real per-scene
files. Synthesizes the design discussion
that followed [Studio Chat / Blender MCP Review — Discussion
Audit](REVIEW-AUDIT.md) section 19 (build-path unification) into a
forward architecture and phased build order. `REVIEW-AUDIT.md` remains
the discussion/evidence trail this plan is derived from — read it for
the reasoning; read this for the destination.

**Update 2026-08-10: Set Designer and Director split out of Producer
and built, live-verified.** Section 5 below anticipated "set designer"
as `PRODUCTION-DESIGNER-PLAN.md`'s worker-agent role; what actually
happened first was the same shape of finding this whole document is
built on — `producer.py`'s `--primitive-fallback` (location resolution)
and `build_intent()` (camera framing, blocking flags) had each already
absorbed a not-yet-built specialist role's job inline, under time
pressure to keep showing progress. Both are now relocated: real,
detailed writeups and decisions live in
`docs/planning/PRODUCTION-DESIGNER-PLAN.md` and
`docs/planning/DIRECTOR-ROLE-PLAN.md`'s own 2026-08-10 sections; short
version here since this doc is the index —
`tools/set_designer.py` resolves an unmapped location (stand-in, else
primitive) and re-triggers `producer.py --scenes N`, dispatched by
Producer enqueueing a job on the **existing**
`oeb-studio-harness/worker/` job queue at ticket-write time (not the
GitHub Issues/Project bus section 5 assumed — that stays unbuilt/
aspirational; live-verified against the real harness end-to-end,
including a real worker claiming and completing the job);
`tools/director.py` decides per-shot camera framing/subject and actor
arrival/departure blocking via a constrained local-LLM call, informing
`SceneIntent`'s existing fields rather than replacing them. Also new:
`tools/tickets.py` `clear_ticket()` deletes a scene's NEEDED ticket
once it's no longer blocked, so file tickets don't pile up indefinitely
now that a real job queue sits alongside them. Not built: Set
Designer's kitbash tier, Director's mid-scene move-beat mechanism (the
"flies into asteroid field" case) — motion text is captured for human
review but nothing resolves it into a move cue yet.

## 1. Goal

One creative loop, not two systems. Studio Chat (conversational,
asset-and-scene work) and the teleplay-to-render production pipeline
(screenplay-driven, automatic) are today separate systems built at
different times with different formats. The goal is a single loop —
one schema, one build engine, one asset registry, one primitive/
operation vocabulary — that runs at different **autonomy levels**:
attended and conversational at one end, unattended and automatic at the
other, differing in *how* work enters (chat message vs. screenplay line)
and *how much authority the output carries* (iterative draft vs.
hands-off rough draft vs. reviewed production truth — see section 4).
Not renderer-specific: nothing in the core schema may assume Blender or
any other engine; execution happens behind a translator, per section 3,
and Blueprint itself — not any translator-specific derived
representation — is the one thing every part of this system agrees on.

## 2. Architecture decision: one schema, not two pipelines

**Decision: Blueprint absorbs scene composition. Blueprint is the only
conceptual architecture — nothing else sits beside it as a peer format.**

Today: `Blueprint` (`tools/blueprint_interpreter.py`) builds one
Canonical Asset from primitives + operations. `SceneSpec`
(`schemas/scenespec.schema.json`) composes already-built assets
(referenced by `character_id`/`set_id`/prop IDs) into a shot — actors,
cameras, timeline — consumed by the three exporters
(`export_blender.py`/`export_usd.py`/`export_godot.py`). These are two
different schemas serving overlapping purposes, bridged only by hand
(`tools/resolve_intent.py`'s `SceneIntent → SceneSpec` resolver) or not
at all (Studio Chat has no scene concept today — see `REVIEW-AUDIT.md`
section 16).

Blender's own data model doesn't distinguish "asset" from "scene" at the
structural level — everything is `bpy.data`; a Scene is mostly a set of
*references* to Object/Collection datablocks plus scene-only state
(active camera, render settings, world). An "asset" is just an
object/collection hierarchy marked reusable (Blender's Asset Browser:
`.asset_mark()`) and linked/appended into other files rather than
rebuilt. This is the model to follow, generalized past Blender
specifically: **Blueprint becomes the one authoring format for both
single-object assets and whole scenes.** A scene-scoped Blueprint's
`primitives` list is mostly `"type": "import"` entries (assets placed by
`canonical_id` — the exact mechanism already built and live-verified in
section 18/19) plus scene-only elements: multiple cameras/shots, set
dressing built the same way asset geometry already is, and (per section
7 below) lighting/environment.

**SceneSpec is one derived execution representation of Blueprint —
not an output, not a pipeline stage, and not a permanent architectural
dependency.** Calling it Blueprint's "output" would wrongly imply
SceneSpec is a second thing this architecture is conceptually built
around; it isn't. SceneSpec happens to already be the shared derived
representation the three existing exporters (Blender/USD/Godot) all
consume, so those three keep working unchanged by having it generated
from Blueprint rather than hand-authored. That is a fact about *those
three translators today*, not a rule about the architecture. A
translator — one of these three, or a future one — is always free to
derive whatever execution representation it actually needs directly
from Blueprint; nothing requires SceneSpec to exist in that path.
Blueprint → SceneSpec must not calcify into a mandatory intermediate
that every future translator is assumed to depend on.

**Decision: `tools/resolve_intent.py` is retargeted universally to
`SceneIntent → Blueprint`.** Every scene goes through Blueprint —
deterministic, screenplay-driven scenes included, not only
Studio-Chat-touched ones. There is no separate `SceneSpec`-authoring
path left standing anywhere in the pipeline; SceneSpec generation
becomes something the Blender/USD/Godot translators derive for their
own purposes when they need it, per section 2's framing above, not a
step every path is routed through. The deterministic motion-grammar
work `resolve_intent.py` already carries (walk-in entrances, NLA
crossfades) gets salvaged into the one consolidated motion library
described in section 8, rather than reimplemented.

Today's concrete chain, specific to the three existing translators:
**Blueprint → (derived) SceneSpec → {Blender, USD, Godot exporters}.**
This is a description of what those three translators currently do, not
a statement of required architecture — a differently-shaped translator
is not obligated to reproduce it.

## 3. The translator boundary

**Decision: formalize the core-spec / execution-engine split now, even
with only one execution engine (Blender) behind it.**

`tools/blueprint_interpreter.py` today conflates two things: the
Blueprint JSON (already tool-agnostic in principle — primitives,
transforms, operations, no Blender API surface in the data itself) and
its execution (`bpy` calls, hardcoded into the same file that parses the
JSON). "We aren't targeting Blender or 3D software... swap out any tool
with only changing a translator" requires separating these explicitly:
a **core spec** (Blueprint/SceneSpec schemas + validation, engine-blind)
and a **translator** (a concrete interpreter — Blender today, something
else later — that consumes the spec and produces engine-native output).

Concretely: define a translator interface (what operations a target
engine must implement — the `OPERATIONS` dict pattern already in
`blueprint_interpreter.py` is most of this, generalized to an
interface); keep `tools/blueprint_interpreter.py` as the Blender
translator implementing it, not the schema's only reference
implementation. No second translator is being built now — this is
about not baking Blender assumptions into the schema or into any code
that isn't explicitly the translator layer, so a second translator is
additive later rather than a rewrite.

The interface contract is Blueprint in, engine-native output out — it
does not require producing SceneSpec or any other intermediate along
the way. Whether a translator's internal implementation happens to
derive SceneSpec (as the Blender/USD/Godot family does today, per
section 2) is that translator's own business, not part of what makes
something a valid translator.

**Decision (2026-08-09): the operation vocabulary stays fixed and
closed, not a plugin architecture, as scenes need increasingly
complicated rigging/animation (characters and objects both).** A
plugin structure — translators dynamically discovering/registering
their own operations — would let different translators support
different capability subsets, directly reopening the Blender-coupling
problem this section exists to prevent: "one schema every translator
agrees on" stops being true the moment operation support can diverge
per translator. Instead, new rigging/animation capability (e.g. the
clip-driven actor-motion gap in section 11 item 3) becomes a new named
operation added deliberately to the closed enum in
`schemas/blueprint.schema.json` — reviewed, versioned via
`schema_version`, and implemented uniformly across every translator
that claims to support it — the same pattern `set_keyframe`/
`set_material`/`set_shape_detail`/`set_environment` already followed.
This is intentionally an ongoing series of updates as real needs
surface, not a flaw to design away: `blueprint_interpreter.py`'s own
documented convention is already "one operation at a time, when an
actual need surfaces," never speculative. The cost is periodic
stop-and-design-a-new-operation moments (like section 11 item 3);
the return is a small, auditable, uniformly-implemented vocabulary
instead of engine-specific plugin drift.

## 4. One creative loop, different autonomy levels

**Decision: the automatic teleplay pipeline and Studio Chat are not two
systems bridged together — they are one creative loop, run at different
autonomy levels.** There is no "Studio Chat" and "the teleplay
renderer" as separate named things in this architecture; there is one
build loop, and how much of it runs unattended is a dial, not a fork.

- **Attended:** a chat message triggers propose → validate → repair (the
  loop already proven in `resolve_primitive_spec`/
  `resolve_asset_intent_normalization`, `services/studio_chat.py:1555-1814`),
  a human present throughout, iterating.
- **Unattended:** `tools/producer.py` stays the top-level orchestrator —
  it keeps using the tools it already has for moving a text teleplay
  through the production process (`tools/screenplay.py`,
  `tools/script_desk.py`, `tools/tickets.py`, `data/standins.json`,
  `validate_spec.py`, the exporters), unchanged. Studio Chat is simply
  one more tool in that existing toolbox — the one Producer now uses,
  specifically, to turn a scene's teleplay text into rough-draft
  Blueprint/render output.

  **Producer is a literal Studio Chat client, not a privileged bypass.**
  It drives real threads and messages through the same conversational
  API and audit trail a human uses, tagged as an agent actor. A human
  can open the exact thread Producer built and keep working in it — full
  continuity of the conversation, not just of the resulting Blueprint
  objects. When Studio Chat would stop and ask a human a clarifying
  question (`needs_clarification`, or a multi-match "load X" chooser,
  section 6), Producer answers it with its own judgment, logs the
  choice for later human review, and keeps going — it never blocks
  waiting for a clarification the way a human conversation naturally
  would.

  This produces a fast, low-fidelity ("draft" quality — reusing the
  existing draft/preview/final tier language from
  `docs/planning/HARNESS-RENDER-QUALITY-LANGUAGE.md`, not a new quality
  concept) result a producer/director/artist can then open and keep
  working on *attended*, in the same thread, on the exact same
  Blueprint objects the unattended pass produced. No format handoff
  between the two ends of the dial — they're the same objects, in the
  same conversation, at different points in one editing lifecycle.

This is the concrete application of the principle now written into
`docs/ARCHITECTURE.md` ("Key principles" and "LLM role"), which
supersedes the older, stricter line at the top of `PROJECT-TODO.md`
("LLM is a translator/constraint layer, not a writer"):

> Automation may lower fidelity, substitute assets, simplify motion,
> invent provisional staging, and make provisional creative decisions.
> It may not silently convert those decisions into canonical truth.

The model can write the draft; humans decide what becomes production
truth. Concretely: an unattended pass is allowed to make real creative
judgment calls — which assets, what motion, how things are staged — but
its output carries no authority of its own. It becomes production truth
only through the same human review/promotion step Canonical Assets
already require (`REVIEW-AUDIT.md` section 12, decision 2), never by
default and never silently. Nothing in the deterministic, already-shipped
Phase 1-6 pipeline (script parsing, vocabulary sweep, ticketing, QA
gates) changes; what changes is that its output can now also come from
an unattended Blueprint-driven pass instead of only from
`resolve_intent.py`'s existing deterministic mapping.

**Guardrails, stated explicitly, not left implicit:**

- **No story invention.** Producer and every other chat agent work
  strictly within the teleplay's own language and scene boundaries.
  What counts as a scene stays exactly what the deterministic
  `screenplay.py`/`script_desk.py` chunking already says it is —
  unattended agents never add scenes, beats, or plot content the
  teleplay text doesn't contain. This is the same constraint already
  written into `docs/ARCHITECTURE.md`'s "LLM role" ("Rejected: story
  authorship... beyond the human-authored source"), restated here for
  the agent family specifically.
- **No inventing hero or production assets.** Speeding up a rough draft
  with existing assets, stand-ins, and primitives (section 7) is the
  job. Using that same generative capability to freehand a detailed,
  finished-looking design for a hero character, ship, or other
  production asset is not — that is real asset design, and it stays
  exclusively human/artist-directed. This binds section 7's tier-2
  placeholder specifically: it must always read as obviously
  provisional, never as a plausible finished answer, regardless of how
  narratively important the missing asset is — the line is about
  whether the fallback could pass for real design work, not about
  which asset happens to be missing.

## 5. Producer and the wider agent family

**Decision: this extends the existing, unbuilt `docs/planning/AGENT-BUS-PLAN.md`
and `docs/planning/PRODUCTION-DESIGNER-PLAN.md`, rather than describing a
parallel system.** Both already exist in this codebase, both are
directly relevant, and the overlap isn't coincidental:
`AGENT-BUS-PLAN.md` already defines a **Producer** role identically to
how this plan uses it — "FILES production issues from NEEDED tickets...
never designs and never commands agents" — and
`PRODUCTION-DESIGNER-PLAN.md` already defines a **production designer**
worker agent that surveys the asset library and composes sets. "Set
designer," in this plan's terms, is that same role. "Prop builder" is a
new sibling worker-agent profile in the same family. More
production-role agents will be added over time (named examples, not an
exhaustive roster) as the same kind of profile.

The GitHub Issues/Project bus, ticket-dispatch, and verifier-gate
discipline `AGENT-BUS-PLAN.md` already specifies — state machine
(`queued → claimed → in-progress → needs-verify → verified → done`),
structured result comments with a mandatory `summary` field, nothing
reaches `done` without verifier evidence — stays the coordination
substrate for this whole family. This plan doesn't replace that
protocol; it adds what a dispatched worker agent is now allowed to
*do* once it claims a task.

**Every agent in this family gets "first level access"** — real, direct
access to the existing toolchain (asset index, set assembler, Studio
Chat, tickets, validators, exporters), not a sandboxed or proxied
subset — **paired with full audit of every use.** Confirmed: this
extends the Agent Bus's already-established structured-result/audit
discipline to cover Studio Chat usage specifically — a dispatched
agent's Studio Chat thread (itself already fully traced via
`studio_chat_trace_events`, the append-only ledger Studio Chat
Milestone 1 already built) gets cross-referenced and cited, with a
timely summary, directly in the Agent Bus's structured completion
comments — the same evidentiary role build artifacts and commit
references already play, and the same discipline as the "nothing
reaches `done` without verifier evidence" rule.

**`PRODUCTION-DESIGNER-PLAN.md`'s stated non-goal — "No generative
geometry/textures; composition of approved assets only" — is lifted,
not narrowed.** It existed because generative construction wasn't
trustworthy when that plan was written (2026-07-11, well before the
Blueprint work in `REVIEW-AUDIT.md` sections 13-19). Blueprint's
propose → validate → repair loop, plus the full audit trail above, is
exactly the trust mechanism that makes generative construction safe to
allow now. Set designer and prop builder profiles may use Studio Chat
for real generative work, not only the deterministic
`tools/build_set.py` kitbashing path — subject to the same guardrails
as Producer (section 4): no story invention, no freehanding a
finished-looking hero or production asset. Composing from the approved
library remains the preferred, still-supported path where it already
covers what's needed; Studio Chat access is additive, not a replacement
for `build_set.py`.

Producer's own division of labor is unchanged by any of this: it still
never designs and never commands other agents
(`PRODUCTION-DESIGNER-PLAN.md`'s standing principle). Its new capability
is narrowly the rough-draft assembly work described in section 4 —
composition within guardrails, not design authority.

**Prop builder is aspirational, not scoped for building yet.** Unlike
set designer, it has no build order, no profile file, no qualification
drill — it's documented here only as a stated future agent role in the
same family, to be scoped in detail when it's actually picked up.

**Update 2026-08-10:** set designer's rough tier is now real (see the
top status block's 2026-08-10 update). It did **not** end up dispatched
through the GitHub Issues/Project bus this section describes —
`AGENT-BUS-PLAN.md` remains unbuilt/aspirational for that tier.
Instead, per direct discussion, it extends the **existing**
`oeb-studio-harness/worker/` Postgres-backed job queue
(`docs/planning/WORKER-AGENT-PLAN.md`): Producer enqueues a job at
ticket-write time, the existing `BlenderCLIAdapter` runs it, no new
adapter. The kitbash tier (real library composition, human sign-off)
is still designed against the ticket-dispatch model above and remains
unbuilt, so this section's GitHub Issues/Project framing is still the
live design for that tier specifically — just not for the rough tier
that shipped first.

## 6. Semantic asset resolution and "load X"

Two related capabilities, one resolver:

- **Chat command:** "load jb100" / "load latest pirate escape scene" —
  a name/phrase resolves against the asset and scene registries
  (section 9) to a specific canonical_id or scene identity, becoming the
  thread's active target for further conversational operations.
- **Automatic composition:** a screenplay line like *"JB100 flies past
  chased by Ellipso Flyers and Ventradi cruiser"* — each named/described
  entity in the sentence resolves independently to the closest matching
  registered asset (or triggers the fallback in section 7), and the
  resolved set becomes `"import"` primitives in a scene-scoped Blueprint
  with plausible spatial/motion relationships (JB100 passing camera,
  flyers and cruiser trailing) via the animation vocabulary in section
  8.

**Decision: resolution is tag/keyword lookup against the registry, not
fuzzy guessing.** "JB100" and "pirate flyer" are tags and keywords on
registry entries — matching is a direct lookup against those, the same
kind of registry data `oeb.config.json` already carries, not embedding
similarity or open-ended LLM judgment as the primary mechanism. There
should be no need to guess when the registry itself can answer the
question directly.

**Multiple ambiguous matches present a chooser backed by each
candidate's existing hero/review render.** Reuses the existing
`needs_clarification` compiler outcome (Milestone 17,
`services/studio_chat.py`) rather than inventing a new interaction
pattern — the mechanism that already stops a build and asks the user a
structured question is the same mechanism a "did you mean X or Y" asset
chooser needs. The chooser shows the actual review-render image already
generated for each candidate (Milestone 12's gallery-ready thumbnails),
not just text labels — a visual pick, not a name guess.

## 7. Missing-asset fallback: two-tier, ticket always

Directly clarified in discussion, not inferred: **the primitive
vocabulary this whole effort has been building toward is the mechanism
for cheap, non-blocking placeholders**, not just a construction method
for deliberate Studio Chat builds.

1. **Tier 1 — existing real-asset stand-in.** `data/standins.json`'s
   current substitution mechanism (e.g. the sci-fi bar standing in for
   `orbital_station_lounge`) is tried first, unchanged, when a
   reasonably close existing Canonical Asset exists.
2. **Tier 2 — primitive placeholder, only if tier 1 finds nothing
   close.** A crude Blueprint gets composed via the same propose →
   validate → repair loop already proven this session (not a
   keyword/deterministic fallback) — e.g. *cup → small cylinder with a
   simple torus/bent handle*; *alien ship → a rough cluster of blocks
   suggesting a hull*. Deliberately simple — the primitive vocabulary
   (cube/cylinder/cone/sphere/torus/plane/wedge/hemisphere +
   bevel/mirror/array) already exists and was built exactly for this:
   fast, recognizable-enough, not production-quality geometry.
3. **A generated placeholder is reused, not regenerated, for
   repeated occurrences of the same missing asset.** The first time
   "motorcycle" is needed and nothing close exists, tier 2 builds it
   once; every later scene that needs a "motorcycle" reuses that same
   placeholder rather than generating a new one. It gets a real entry
   in the same registry (`oeb.config.json` — no separate
   placeholder-specific store, consistent with one registry throughout
   this plan), explicitly flagged with an **unapproved** status,
   distinct from a Canonical Asset that has cleared artistic review.
4. **NEEDED ticket always files, and is explicitly linked to the
   placeholder — never orphaned in either direction.** `tools/tickets.py`'s
   existing mechanism, unchanged, still files the ticket regardless of
   which tier resolved the fallback. What's new: the ticket carries a
   direct link/reference to the generated placeholder's registry entry
   for review, and the registry entry carries a reference back to the
   ticket. A human reviewing either one can always find the other — no
   auto-generated asset exists without a ticket pointing at it, and no
   ticket exists without a reference to what was actually generated for
   it. The rough render never blocks waiting for that review to happen.
5. **Human review of an unapproved placeholder has three outcomes, not
   two:**
   - **Rejected** — discarded; the next occurrence of the same missing
     asset generates a fresh placeholder rather than reusing the
     rejected one.
   - **Approved as a standing draft-tier fallback** — stays reusable
     (per item 3) without needing regeneration or re-review each time,
     but stays permanently draft-tier: it can never appear in a final
     delivered render, same restriction as any tier-2 placeholder.
     Approving it this way is not the same as satisfying the underlying
     need — the NEEDED ticket stays open, tracking that a real asset is
     still wanted.
   - **Promoted to a real Tier-1 Canonical Asset** — for a simple
     enough case (a plain cup is the concrete example that came up), a
     human may decide the auto-generated geometry is actually good
     enough to go through the same artistic-review/promotion gate any
     asset requires (`REVIEW-AUDIT.md` section 12, decision 2) and
     become genuine production-usable art, not just a permanent stand-in.
     This is the one path that resolves the NEEDED ticket, since the
     real need is now actually satisfied.
6. **A tier-2 placeholder must never resemble finished design work at
   the point it's generated.** Direct application of section 4's
   guardrail: deliberately crude, obviously provisional, regardless of
   whether the missing asset is a background prop or something the
   teleplay treats as a hero object. The primitive vocabulary's job
   here is legibility at rough-draft speed, not a plausible stand-in
   for real asset design — whether something later turns out simple
   enough to be *promoted* (item 5) is a separate, explicit human
   decision, not something the generation step should aim for.
7. **`tools/producer.py --primitive-fallback` (2026-08-09): the
   deterministic, offline sibling of `--studio-chat-fallback`,
   answering section 11 item 4's gap.** `--studio-chat-fallback` only
   ever covers `run_pipeline.py` returning `EXIT_BLOCKED` -- it never
   fires on `producer.py`'s own, earlier vocabulary-sweep block
   (missing location/role, `tools/producer.py`'s vocab-sweep loop),
   which live testing confirmed is the more common blocking path for
   genuinely new script content. `--primitive-fallback` targets that
   exact block instead, and is deliberately a different mechanism, not
   a second caller of the same one: `tools/placeholder_blueprint.py`
   is pure/stdlib-only (no bpy, no FastAPI/SQLAlchemy import chain) and
   writes directly into the same file-based registry the deterministic
   pipeline already reads (`oeb.config.json` / `data/resolver_map.json`
   / `data/standins.json`, each entry tagged `"placeholder": true`) --
   no live harness/DB round trip needed, unlike
   `oeb-studio-harness/server/app/services/missing_asset_fallback.py`'s
   Postgres-backed tier-2 path for the chat/registry-resolution side.
   The two are intentionally separate, small implementations rather
   than a shared abstraction forced across a real architectural
   boundary (DB-backed vs. file-based registries serving different
   callers).

   Placeholder *locations* also get three auto-generated mark objects
   (entry/center/exit, fixed symmetric offsets) via a new Blueprint
   primitive type, `"empty"` (section 3's fixed-vocabulary decision --
   a plain marker object, `tools/oeb_blender/primitives.py`'s
   `empty()`), so a placeholder actor has somewhere to move from/to
   even when the whole location is placeholder-tier too, not just the
   actor. Placeholder *roles* get a synthesized entrance with timing
   fields (`walk_duration`/`settle_duration`/`rise_duration`) but no
   clip-name fields (`walk_clip`/`settle_clip`/`stand_clip`/`rise_clip`/
   `idle_clip`/`talk_clip`) -- `tools/motion_library.py` and
   `tools/resolve_intent.py` were made tolerant of a missing clip name
   (treated as "transform-only move", the same convention
   `export_blender.py`'s cue execution already used for a move cue with
   no `clip_id`), verified byte-identical against the real bar-scene
   fixture for actors that do have clips.

   **Live-verified 2026-08-09** against the real JourneyBlaster teaser
   script (`scripts/pilot/Orlando-El-Bastardo-Episode-01-The-Pilot-
   teaser-scene.md`): brand-new locations (`journeyblaster_cockpit`,
   `asteroid_field`) and roles (`ship_ai`, `casey`) got real crude
   primitives built through `tools/blueprint_interpreter.py`,
   registered into the live project files, and cleared their
   vocabulary-sweep blocks on rerun. A hand-built placeholder scene
   (real `.blend`, real headless-Blender inspection) showed exactly the
   "oblong crosses the room and stops at the mark" motion the original
   bar-scene proof of concept demonstrated -- confirmed frame-by-frame:
   entry mark at frame 1, smooth interpolation, holding at the center
   mark, walking back out toward the end.

   Two real, honest limitations surfaced by that same live run,
   neither one a bug in this new mechanism:
   - A pre-existing, unrelated data bug: `data/standins.json` already
     mapped `"orlando": "protagonist"` before this session touched
     anything, so "Orlando" resolves straight to the real bar-scene
     hero role (`spawn_mark: "hero_barstool_A"`) instead of ever being
     seen as a missing role -- `--primitive-fallback` never gets a
     chance to act, because producer's vocabulary sweep never flags it
     as blocking. The failure only surfaces later, at
     `validate_spec.py`'s mark-resolution stage (`"actor 'orlando'
     spawn_mark 'hero_barstool_A' not found in GLB library nodes"`), a
     different point than what this flag currently patches -- the same
     *shape* of gap as item 4 above (works for genuinely new entities,
     not for an already-resolved-but-wrong mapping), not yet addressed.
     Fixing the cast mapping itself is a one-line content decision, not
     a code change.
   - A pre-existing SceneIntent schema limitation, unrelated to
     placeholders: `actors` requires `minItems: 1`. A pure ship/vehicle
     shot with no on-camera named character (three of the teaser's
     seven real shots) fails assembly with `"[] should be non-empty"`
     regardless of any fallback mechanism. Not attempted here.

   **Plan to clear both, to get real rough-draft renders of the full
   teaser (2026-08-09) — both done, real renders achieved:**
   1. **Stale `orlando` cast mapping** — removed the `"orlando":
      "protagonist"` entry from `data/standins.json`'s `cast` map, so
      Orlando becomes a genuinely-new role to producer's vocabulary
      sweep, exactly like `ship_ai`/`casey` already were. A
      content/data fix, not a code change.
   2. **Actor-less pure-ship shots** — `register_vehicle_placeholder()`
      (`tools/producer.py`) extracts candidate proper-noun phrases from
      the scene's action text (reusing `screenplay_entity_resolution
      .extract_entity_candidates`, section 6) and registers the
      *most-repeated* one as a placeholder vehicle actor when a scene
      would otherwise assemble zero actors. First cut picked the
      first-seen candidate rather than the most-repeated one, and
      grabbed "Black" (the scene-opening void description, "Black.")
      over "JourneyBlaster" for exactly this teaser's sc01 — fixed by
      preferring occurrence count, since a genuine recurring subject
      gets mentioned more than once and an incidental scene-opener word
      doesn't. `SceneIntent.actors` keeps its `minItems: 1` requirement
      unweakened; the vehicle placeholder satisfies it honestly.

      A third, unplanned fix was needed to get an actual **render**,
      not just a validated SceneSpec: `render_blend.py` hard-requires
      *some* camera bound to a timeline marker, but a placeholder
      location's `.glb` carries no camera at all (Blueprint's reserved
      "camera" is excluded from geometry export by design). Fixed in
      `export_blender.py`'s R9 camera-binding step: when no
      `camera_grammar` scene_object is found anywhere in the scene, a
      simple fallback camera is now created once and bound to every
      otherwise-unbound marker, instead of just warning and leaving
      shots with no camera at all.

      **Live-verified 2026-08-09** against the real 7-shot JourneyBlaster
      teaser with all three fixes in place: 2 of 7 scenes fully
      delivered with real rendered video (crude primitives only, real
      timed dialogue markers, real camera coverage) and assembled into
      a real 51-second episode cut by producer's existing
      episode-assembly logic, unchanged.

      **A fourth, deeper limitation surfaced by that same run — fixed
      2026-08-09:** a role's `spawn_mark` in `data/resolver_map.json`
      was a single fixed value, but Orlando (and the JourneyBlaster)
      appear across *multiple different placeholder locations* in this
      script (deep space, the cockpit, the asteroid field) —
      `register_placeholder_role()` only registered a role once,
      against whichever location triggered it first, and never
      revisited an already-known role for a scene set somewhere else.
      The other 4 scenes stayed blocked on exactly this (`"actor
      'orlando' spawn_mark '...journeyblaster_cockpit_A_center' not
      found"` in a deep-space scene). This was a structural limitation
      of the role model itself, not specific to placeholders — the
      original bar-scene design never needed a character with more
      than one home location.

      Fixed by changing every role in `data/resolver_map.json` from a
      singular `spawn_mark`/`entrance` to `spawn_marks`/`entrances`
      dicts keyed by `location_tag` (all six existing roles migrated,
      real ones included — one shape, not two parallel ones).
      `tools/resolve_intent.py` resolves the per-location value down to
      the old singular shape *once*, right where a role is first
      matched to an actor (using the scene's own `location_tag`, already
      in scope there), so every downstream site keeps reading
      `role_entry["spawn_mark"]` / `role_entry.get("entrance")`
      unchanged — a normalize-once fix, not a sweep through every call
      site. `placeholder_blueprint.register_placeholder_role()` now
      merges a new location's mark/entrance into an existing role
      instead of overwriting the whole role.

      A second, previously-hidden gap surfaced immediately once this
      landed: producer's own vocabulary sweep only ever flagged a role
      as *blocking* when it was completely unknown to `data/
      standins.json`'s cast map — an already-cast role (e.g. `orlando`,
      registered from an earlier scene) that simply lacked a spawn_mark
      for *this* scene's location sailed through the sweep with "0
      blocker(s)" and only failed much later, at the resolve stage,
      too late for `--primitive-fallback` to help. Fixed by adding a
      second sweep check (`tools/producer.py`): for every already-cast
      actor present in the scene (same dialogue-or-named-in-action-text
      rule `present_actors()` already uses), if their role has no
      `spawn_marks` entry for this scene's `location_tag`, that's now a
      new blocking-item kind (`role_location`), handled by
      `primitive_fallback()` with a cheap path that just extends the
      existing role's marks — no placeholder rebuild, no re-registering
      an asset that already exists.

      **Live-verified 2026-08-09** (dry run, `--no-render`, real
      teaser): before this fix, 2 of 7 scenes delivered; after, 6 of 7
      — the resolver_map now correctly shows `orlando` with spawn_marks
      for both `journeyblaster_cockpit` and `deep_space`, and
      `journeyblaster` with spawn_marks for all three locations it
      appears in. The one remaining failure (sc05) is unrelated: a
      genuinely actor-less shot referring to "the red ship" (lowercase,
      not a proper noun), which `register_vehicle_placeholder()`'s
      candidate extraction correctly declines to guess at — the
      already-documented actor-less-scene heuristic limitation above,
      not a new one. Regression check: `tools/resolve_intent.py`
      against the real `bar_scene`/`bar_scene_walkin` fixtures is
      byte-identical to a true pre-edit baseline (HEAD's resolve_intent.
      py + resolver_map.json); full test suite (380, +1 new) passes.

      **Confirmed with a real render 2026-08-09** (not just `--no-render`):
      the same 6 of 7 scenes DELIVERED with real rendered `.mp4` files
      (`renders/reviews/pilot_pilot_sc0{1,2,3,4,6,7}.mp4`, 25KB-245KB
      each, real sizes not stubs) and a real assembled episode cut
      (`renders/reviews/pilot_episode.mp4`, 263KB). sc05 is the one
      confirmed-unrelated failure (the actor-less "the red ship"
      heuristic gap above). `producer.py` exits 1 whenever any scene
      fails, by its own convention (`sys.exit(0 if n["FAILED"]==0 else
      1)`) — that is not a crash and shouldn't be read as one.

      **sc05 fixed 2026-08-09** by renaming "the red ship" to "The
      JourneyBlaster" directly in the script (already-cast, named
      subject instead of an ungrammatical heuristic guess) — **teaser
      now delivers 7 of 7 scenes**, real files, real episode cut.

      **Deep-space environment wired into the real render path, same
      day.** `SetSpec.set.environment` (new optional field,
      `schemas/scenespec.schema.json`) carries a preset name (`"deep_
      space"` today) from `data/resolver_map.json`'s `deep_space`/
      `asteroid_field` locations, through `resolve_intent.py`, into
      `export_blender.py`'s R5 step, which calls `setup_space_env()`
      (`tools/oeb_blender/space_env.py`, extracted this session from
      `tools/JB100-pirate-escape.py`'s proven implementation — see
      section 8's environment bullet, now closed). Two real bugs found
      only by actually rendering, not by reading the code:
      - `tools/render_blend.py`'s review-lighting step unconditionally
        overwrote `scene.world` and added interior-scale room lights —
        exactly wrong for a space backdrop. Fixed with an `env_star_
        sphere`-presence guard that skips it entirely for environment
        scenes.
      - That guard alone left every non-emissive object (ships,
        actors, asteroids) pure black and invisible: the environment's
        visual "sun" is an emissive *mesh*, not a Blender light, so
        skipping room lighting left nothing actually illuminating
        anything. Fixed by adding one SUN lamp aimed from the visual
        sun's direction, plus a second soft SUN lamp aimed from the
        camera (a single hard light with a fully black world/no
        ambient only lights whichever face happens to align with it,
        which left camera-facing surfaces dark purely because of a
        prop's arbitrary rotation). Needed a real ordering fix too:
        `render_blend.py` was calling this lighting setup *before*
        binding the scene's camera from its timeline marker, so the
        camera-aimed fill light silently had no camera to aim from.
      - `docs/world-building/SPACESCAPE.md` (a `wiki: true` doc) was
        found still documenting the disproven `0.775`/`0.88` star
        density cutoff (renders zero stars, confirmed) and an off-black
        space color (renders a visible blue/purple cast against real
        approved 1999 reference stills, per direct user feedback) —
        corrected in place to the live-verified `0.70` cutoff and pure
        black, with the empirical reasoning kept in the doc, not just
        in code comments. Flagged by the user directly asking whether
        heavy refactoring had actually touched any wiki-included docs;
        it hadn't, for this one.

      **Asteroid placeholders** (`tools/build_asteroid_placeholders.py`,
      five deterministic variants — round/oblong/jagged/peanut/cratered,
      user-authored, not built by producer's own fallback path) went
      through the same live-fire loop: first pass rendered as pure
      black/invisible geometry under any normal (non-emissive) lighting
      in both EEVEE and Cycles, root-caused to the crater-carving math
      having no floor on displacement depth (`radial - depression` could
      overshoot past the origin, producing self-intersecting/volume-
      inverting topology that corrupted rendering) — independently
      fixed by the user with a `max(0.72, radial - depression)` clamp,
      smooth shading + vertex colors, and a hard build-time check
      (non-manifold edges / inverted volume / inward-facing normals all
      raise). Also found and fixed: `build_field()` (the asteroid-field
      set-dressing builder) overwrote `asteroid_field`'s location GLB —
      the same file `data/resolver_map.json`'s `_entry`/`_center`/
      `_exit` marks depend on — without including them, breaking
      `validate_spec.py` for every asteroid_field scene. Fixed by
      generating those three marks inside `build_field()` itself, with
      a matching self-check in `validate_exports()`.

      **NASA Blue Marble Earth texture** pulled to `assets/textures/
      planets/earth/earth_land_shallow_topo_2048.jpg` (233KB, real
      public-domain imagery, not a placeholder) as a future planet-asset
      source (section 8's environment bullet references a planet spec
      not yet built). Two other guessed NASA URLs 404'd; not guessed
      further, garbage output deleted rather than left in place.

      **Hyperspace Effect registration (in progress, not yet wired):**
      the approved hero VFX asset (`assets/effects/hyperspace_effect_
      v1.1.0/`, ship-agnostic since v1.1.0's `attach_ship.py` bounds-fits
      any GLB ship or a default squashed-sphere placeholder to the rig)
      has no path into the deterministic pipeline yet. Two blockers
      identified 2026-08-09:
      1. **No GLB export existed** — only `.blend`. Fixed: added a
         `--glb-output` flag to `attach_ship.py`
         (`bpy.ops.export_scene.gltf` on `HYPERSPACE_EVENT_ROOT` and its
         descendants). Verified live by real re-import, not just a
         clean exporter exit code — all of the rig's per-object scale/
         rotation/location animation survives (it lands in a *muted*
         NLA track by default, standard glTF-import behavior this
         project's own `find_action()`/`apply_nla_clip()` already work
         around for character clips, not a new problem). Found and
         fixed one real, narrower gap along the way: the payload's
         disappear-at-frame-17 keyframes were on `hide_render`, which
         has no glTF animation channel at all and was silently dropped
         on export. Fixed by also keyframing the payload carrier's
         `scale` to zero at the same frame (an exportable TRS channel,
         kept alongside the original `hide_render` keyframes rather
         than replacing them, since those still save real render cost
         for Blender-native/non-exported use).
      2. **No cue-type vocabulary for multi-object effect rigs — built
         and live-verified 2026-08-09.** Every existing cue
         (`animation`/`dialogue`/`move` in SceneSpec; `play_move_cue`/
         `play_animation_cue`/`play_dialogue_cue` in Blueprint) targets
         one object with one action. This effect is several objects
         (`HYPERSPACE_EVENT_ROOT` plus each animated stage — ignition,
         engulfment, traveling cloud, terminal residue, the payload
         carrier) that all need to start together at one cue-triggered
         moment. Design, as settled (parent-to-actor placement; no
         hardcoded per-asset object→action table, a naming convention
         instead — Blender's own default `{ObjectName}Action`, left
         unrenamed) built as:
         - **`FXCue`** (`schemas/scenespec.schema.json`) — this `$def`
           already existed, unused (`type: "fx"`, `fx_id`), stubbed
           ahead of an actual implementation; added the required
           `actor_id` field it was missing for parent-to-actor
           placement rather than inventing a parallel cue type.
         - **`play_fx_cue`** — new Blueprint operation, target-scoped
           (parented actor, not scene-level), added alongside the other
           `play_*_cue` operations.
         - **`apply_fx_cue(root_obj, target_obj, frame_num, fps)`**
           (`tools/oeb_blender/cue_execution.py`) — parents *root_obj*
           to *target_obj* at its local origin, then walks `[root_obj]
           + root_obj.children_recursive`, calling the existing
           `apply_nla_clip()` with `clip_id = f"{obj.name}Action"` for
           each; a `ValueError` (no matching action) is caught and
           skipped, not an error. No hardcoded table anywhere — genuinely
           generic, works for any future multi-object rig that keeps
           Blender's default action names.
         - Wired into both consumers: `export_blender.py` (R13 — new
           `fx` cue type allowed past R2's scope gate, effect assets
           collected into the GLB import set alongside sets/actors/
           props, a dedicated dispatch loop resolving `actor_id` →
           target object and `fx_id` → root object via `oeb.config.
           json`'s existing `"node"` field) and `blueprint_interpreter.
           py` (`_apply_play_fx_cue`, resolving `fx_root_id` against an
           already-imported `type: import` primitive in the same
           Blueprint — a Blueprint scene only ever gets geometry through
           its own `primitives` list, so no oeb.config.json lookup
           happens inside the operation itself).
         - **Registered**: `fx_hyperspace_effect_A` in `oeb.config.json`
           (`node: "HYPERSPACE_EVENT_ROOT"`, pointing at a real built
           `.glb` — `assets/effects/hyperspace_effect_v1.1.0/
           hyperspace_effect_v1.1.0.glb`, the default squashed-sphere
           payload variant via `attach_ship.py --primitive --glb-
           output`).
         - **Live-verified end-to-end**, not just unit-tested: injected
           a real `fx` cue (actor `hero`, the real bar-scene fixture)
           into `fixtures/bar_scene.scenespec.json`, ran it through the
           real `validate_spec.py` (passed clean) and `export_blender.
           py` (EXPORT-OK), then introspected the resulting `.blend`
           directly — `HYPERSPACE_EVENT_ROOT` parented to `char_hero_v1`
           exactly as designed; cue `start_time: 2.0` at `fps: 24`
           produced NLA strips starting at frame 49 on `HYPERSPACE_
           EVENT_ROOT`, `CONCEALED_IGNITION`, `TRAVELING_HYPERSPACE_
           CLOUD`, and `TERMINAL_HYPERSPACE_RESIDUE` simultaneously, all
           `HOLD_FORWARD`, all discovered purely by the naming
           convention. Full test suite (382, +2 new) passes.

      **JB100 identified as JourneyBlaster 5000's tier-1 real-asset
      stand-in, plus the mining probe registered, plus one real scene
      with both — 2026-08-09.** `data/resolver_map.json`'s
      `journeyblaster` role pointed at `placeholder_vehicle_
      journeyblaster_A` (a crude cube) even though `prop_jb100_A`
      (real ship, `assets/ships/jb100.glb`) was already a registered
      asset — the tier-1 stand-in mechanism (section 6) just wasn't
      applied to it. Fixed by swapping the role's `character_id`
      directly (`placeholder: false`, `spawn_marks`/`entrances` left
      as-is — those describe the placeholder *locations*, unrelated to
      which mesh plays the ship).

      `assets/props/mining_probe_1999_v1.0.0/` (real asset, real
      manifest, 2,250 verts, a `beacon_blink_loop` animation) had the
      same missing-GLB gap the Hyperspace Effect had — only a `.blend`
      existed. Added a GLB export step to `build_mining_probe.py`
      (mirrors `attach_ship.py`'s fix: export only the
      `ASSET__MiningProbe1999` collection, not the review-only camera/
      lights). One new finding beyond the earlier hide_render gap: the
      beacon blink drives a **material node input** (`Principled
      BSDF`'s Emission Strength), not an object transform — standard
      glTF animation channels can't carry that at all. Tried Blender's
      experimental `export_pointer_animation` (KHR_animation_pointer)
      flag; confirmed by direct re-import that it produced zero
      animation data despite exporting without error — left the flag
      enabled (harmless, may start working in a future Blender), but
      the beacon does not currently blink through the deterministic
      pipeline. Registered `prop_mining_probe_1999_A` in `oeb.config.
      json` and added it as a `default_prop` on the `asteroid_field`
      location (`at_mark: ..._exit`, clear of the asteroid cluster),
      the same mechanism the bar scene already uses for its own props —
      no per-shot authoring needed.

      **Live-verified end-to-end**, real pipeline not a synthetic
      fixture: re-ran the real `pilot_sc03` intent (already on disk
      from the teaser run) through `resolve_intent.py` →
      `validate_spec.py` (passed clean) → `export_blender.py`
      (EXPORT-OK, `prop_jb100_A_mesh` in the import log) → introspected
      the `.blend` directly (`prop_jb100_A`, `prop_mining_probe_
      1999_A` at `(5,0,0)`, `env_star_sphere`, and an asteroid instance
      all present and correctly positioned) → real render, real frame:
      the actual JB100 (red saucer hull, gold intake pods, black
      canopy) correctly lit against a true-black starfield, not a
      primitive. One real scene now has spaceship + asteroids + mining
      probe together. Full test suite (382) unaffected.

      **Beacon blink fixed — 2026-08-09/10.** The material-node-
      animation gap above wasn't accepted as a permanent limitation:
      added a synchronized object-scale animation on `MP_BeaconBulb`/
      `MP_BeaconReflector`, using the exact same on/off frame timing as
      the existing `blink_keys` dict (kept, not replaced -- native
      Blender playback still gets the real light/emission blink; the
      scale channel is the portable stand-in for everything else).
      Also found and fixed a second, real gap this exposed: props place
      correctly (R6) but nothing ever triggered a prop's *own* baked
      animation -- unlike actors, no cue ever names a prop_id, and R4
      already strips every imported object's animation_data on import.
      Fixed generically in `export_blender.py`'s R6 prop loop: after
      placement, walk `[prop_obj] + prop_obj.children_recursive` and
      auto-trigger any matching `{ObjectName}Action` via the existing
      `apply_nla_clip()`, looped for the scene's full length -- the same
      naming-convention discovery `apply_fx_cue()` uses, so every prop
      with baked ambient animation benefits, not just this one.

      Verification took several wrong turns worth recording so they
      aren't repeated: a naive per-frame `world_to_camera_view()` pixel
      sample used the file's top-down PNG row order against Blender's
      *bottom-up* `image.pixels` array, landing on empty background:
      two renders that were actually correct got misread as "no visual
      difference." Once corrected, `render.animation=True` frames still
      looked identical -- because the scene's own `fallback_camera`
      timeline-marker binding (from `export_blender.py`'s R9 step)
      silently overrides a manually-assigned `scene.camera` during
      animation rendering; clearing the scene's markers fixed that.
      With both diagnostic bugs gone, a tight close-up on the beacon
      dome across two frames shows the reflector assembly large at
      frame 1, shrunk to a sliver at frame 5 -- confirmed both visually
      and numerically (109,123 of 480,000 pixel values changed, up to
      24%). Full test suite (382) still passes.

      **Full teaser re-run with all of the above, 2026-08-10: 7 of 7
      delivered.** First attempt (`producer.py --primitive-fallback`,
      no `--scenes` filter) got through 6 of 7 scenes with fresh real
      renders (confirmed by raycast, not just eyeballing -- `pilot_
      sc01`'s render genuinely raycasts to `prop_jb100_A`; `pilot_sc03`/
      `pilot_sc05` genuinely raycast to the mining probe's own parts --
      JB100 and the mining probe turned out to read as visually similar
      red-hulled silhouettes with black articulated parts from this
      teaser's generic fallback-camera angle, which is why they were
      briefly second-guessed against each other, not because either
      identification was wrong) before the run was killed externally
      (not by producer.py, not by anything in this session) with an
      empty log and no final `production_report.json` written. Rather
      than a full re-render, re-ran only the missing scene (`producer.
      py --primitive-fallback --scenes 7`) and then called `producer.
      py`'s own `episode_cut()` directly against all seven already-real
      per-scene renders to reassemble the full stitched cut -- `--
      scenes 7`'s own run only ever knew about that one scene, so it
      had silently overwritten `pilot_episode.mp4` with a 35KB
      single-scene cut; the reassembled version is 451KB / 1:43,
      matching seven scenes plus slates. No re-render needed for the
      cut itself.

## 8. Vocabulary expansion needed

For scenes (not just single assets) to be composable and roughly
animated, the operation vocabulary needs to grow past what section 18
verified:

- **Generalize camera-only keyframing to any object.** `_apply_
  set_camera_keyframe`/`orbit_around`/`dolly_to`
  (`tools/blueprint_interpreter.py`) today only ever target the
  reserved `"camera"` id. A scene with a JB100 flying past chased by two
  other ships needs the *same* keyframe/interpolation machinery applied
  to arbitrary imported-asset ids. Concretely: a general
  `set_keyframe`/`animate_transform` operation, with the existing
  camera-specific operations becoming convenience wrappers over it
  rather than a separate code path.
- **`set_material`/`set_shape_detail`** — proposed in `REVIEW-AUDIT.md`
  section 11, never implemented. Still open, and now matters at scene
  scale too (dressing/variation across composed assets, not just one
  object).
- **Scene-level lighting/environment — done 2026-08-09, both call
  sites.** `setup_space_env()` (`tools/oeb_blender/space_env.py`) is
  wired into `export_blender.py` via `SetSpec.set.environment`; see
  section 7 item 7's write-up for the two real lighting bugs found
  rendering it for real (review-lighting overwrite, no actual light
  source for non-emissive objects) and the `SPACESCAPE.md` correction.
  `blueprint_interpreter.py`'s parallel `set_environment` operation
  (Blueprint-level, used by placeholder/asset builders rather than
  whole-scene composition) carried its own inline copy of the same
  recipe with the old, disproven `0.75` star threshold and off-black
  space color — rather than just patching those two numbers a second
  time, `_apply_set_environment()` now delegates to `setup_space_env()`
  directly (translating its own `params` dict to that function's
  kwargs), so there's only one place left that can drift. Live-verified
  in real Blender: cutoff `0.70`, pure black, matching the
  `export_blender.py` path exactly. Full test suite (380) still passes.
- **Multi-object effect-cue vocabulary — designed and built 2026-08-09.**
  See section 7 item 7's Hyperspace Effect write-up: the `fx` SceneSpec
  cue type (extended an existing unused `FXCue` stub), `play_fx_cue`
  Blueprint operation, and `apply_fx_cue()` in `tools/oeb_blender/
  cue_execution.py` (parent-to-actor placement, naming-convention-based
  animation discovery instead of a hardcoded table), live-verified
  end-to-end against the Hyperspace Effect asset.
- **One consolidated motion-grammar library.** `resolve_intent.py`'s
  existing deterministic motion work (walk-in entrances, NLA
  crossfades) is real, proven, industry-standard-grade work — it gets
  salvaged and pulled forward as a single shared reference library, not
  reimplemented, and applied across all assets where appropriate on
  both the attended and unattended ends of section 4's autonomy dial,
  rather than remaining specific to the old `resolve_intent.py` path
  alone.

No new geometry operations (boolean/bisect/extrude/loft/sweep) are
implied by this plan specifically — those stay deferred per
`blueprint_interpreter.py`'s own documented scope, added one at a time
when an actual need surfaces.

## 9. Scene registry

**Decision: scenes get a registry entry with an explicit "current"
pointer, independent of directory-name versioning.**

`scene_versions/` today is an ad hoc, inconsistently-versioned flat
directory (`oeb_scene_title_v0.0.1` through `v0.0.12`,
`jb100_hyberspace_swarm_v1.0.1` through `v1.0.21` with gaps) — not
reliable to parse for "latest." **Decision: extend `oeb.config.json`
directly** — no parallel scenes registry. Scenes get the same kind of
entry assets already get (canonical name, kind, file reference, tags/
keywords per section 6), plus a field pointing at whichever revision is
currently "current" for conversational/automatic work, set explicitly
rather than inferred from a version number in a directory name.

## 10. `oeb_scene_title_v0.0.11`: relabel, not rebuild

Confirmed directly: the existing hand-built scene
(`scene_versions/oeb_scene_title_v0.0.11/build_scene_title.py`,
`oeb_scene_title_draft.blend`) gets **relabeled** into the new
Blueprint schema by a frontier-model session — introspecting what's
already built and transcribing it into `primitives`/`operations`/scene
composition — rather than rebuilt from the original 1999 reference
stills/video. This preserves the specific hand-tuned choices already
made and approved, including the known, still-unfixed logo rotation-axis
bug (`REVIEW-AUDIT.md` section 17) as an explicit carryover to fix later
in the new representation, not a blocker to relabeling.

## 11. Open implementation-detail questions

Most of what this section originally tracked (motion-grammar mapping,
semantic match-scoring, scene registry schema, tier-2 placeholder
consistency, audit-trail wiring) is now resolved — see sections 5-9.
What's left, deliberately, for scoping when each piece is actually
built:

1. **Translator interface shape** (section 3) — the minimal contract a
   second engine implementation would need to satisfy. Confirmed **not
   a blocker**: no phase in section 12 depends on this being pinned
   down now, since only one translator (Blender) exists and none of
   this plan's work requires a second one. When it's actually reached,
   resolve it against two inputs specifically: what's already worked in
   this project, and real industry-standard interchange/translator
   patterns — not designed speculatively ahead of a real second target.
2. **Prop builder profile authoring** — deliberately deferred, not
   scoped (section 5). No build order, no profile file, no
   qualification drill exist yet, unlike set designer's.
3. **Blueprint's actor-clip-driven marks/moves/dialogue-timing
   vocabulary gap is closed (2026-08-09); the `resolve_intent.py`
   retargeting itself is not yet done.** Per section 3's fixed-schema
   decision, four new operations now exist and are live-verified:
   `play_move_cue`/`play_animation_cue` (clip-driven actor motion --
   `from_mark`/`to_mark`, `clip_id`, `blend_in`, `loop`, `facing`),
   `play_dialogue_cue` (scene-level dialogue timing marker), and
   `set_active_camera` (scene-level, binds a named pre-existing camera
   object as active from a frame — for scenes with several cameras to
   switch between, distinct from `set_camera_keyframe`'s single
   reserved-camera model). All four share
   `tools/oeb_blender/cue_execution.py` with `export_blender.py`'s
   equivalent SceneSpec move/animation-cue execution — extracted from
   it, not reimplemented, and verified byte-identical
   (introspection-manifest diff) before/after. Live-verified further: a
   hand-built walk-in-entrance Blueprint using the real
   `char_hero_v1`/`char_bartender_v1`/bar-set assets and
   `data/resolver_map.json`'s actual timing produced NLA
   tracks/keyframes/blend-ins matching `export_blender.py`'s real
   production output for the identical entrance, frame-for-frame. That
   pass also caught and fixed a real bug: `blueprint_interpreter.py`
   was missing `export_blender.py`'s post-import `animation_data_clear()`
   step, so a later move cue's keyframes were bleeding into an earlier
   NLA clip's action and corrupting its frame range.

   **Still not done: `resolve_intent.py` actually emitting Blueprint
   instead of validating/emitting SceneSpec.** That retargeting also
   requires touching `validate_spec.py` (validates against
   `scenespec.schema.json` today), `run_pipeline.py`'s `qa_render()`/
   `spec_dialogue()` (read SceneSpec's `shots`/dialogue shape
   directly), and a decision on USD/Godot export for this path (no
   Blueprint execution path exists for those translators yet — likely
   out of scope, Blender-only, until picked up separately). All real,
   already-shipped, zero-test-coverage production code
   (`REVIEW-AUDIT.md` Phase 1-6) — deliberately deferred to its own
   pass rather than done alongside the vocabulary work above.
4. **`--studio-chat-fallback` (section 4/7) only covers one of
   `tools/producer.py`'s two blocking points, found by real end-to-end
   testing 2026-08-09.** `producer.py` can block a scene two different
   ways: (a) its own early vocabulary sweep (`tools/producer.py:422-430`)
   — a script mentions a location or role with no resolver-map/stand-in
   entry at all, checked before `run_pipeline.py` is ever invoked; (b)
   `run_pipeline.py --intent` itself returning `EXIT_BLOCKED`, a later
   stage. `studio_chat_rough_draft()` is only called from branch (b).
   Confirmed live against a real 7-shot script introducing new
   locations/characters (`scripts/pilot/Orlando-El-Bastardo-Episode-01-
   The-Pilot-teaser-scene.md`, the JourneyBlaster teaser): every scene
   hit the early vocabulary-sweep block (a), so `--studio-chat-fallback`
   never fired at all — 0 rough drafts despite the flag being set, env
   vars present, and the harness reachable. Branch (a) is arguably the more
   common blocking path for genuinely new script content (new
   locations/characters), not the less common one — this isn't a
   minor gap. **Addressed 2026-08-09, but by a different, deliberately
   separate mechanism, not by extending this one**: `--primitive-fallback`
   (section 7 item 7) targets branch (a) directly with a fast,
   deterministic, offline placeholder instead of routing every
   vocabulary-sweep block through a multi-minute Studio Chat build-job
   call. `studio_chat_rough_draft()` itself is unchanged and still only
   reachable from branch (b) — left as-is deliberately, not because
   wiring it into branch (a) was ruled out, but because the primitive
   path already covers branch (a)'s actual need ("speed up production
   with rough nonsense", not a conversational LLM build). Whether
   branch (b)'s Studio-Chat-conversational route is ever also worth
   reaching from branch (a) is now a much lower-priority open question.

## 12. Phasing

Sequencing follows the same discipline as `REVIEW-AUDIT.md` section 9:
foundational/shared pieces before the capabilities that depend on them,
verification before the next phase builds on top.

1. **Translator boundary** (section 3) — separate core spec from Blender
   execution inside the current single-engine reality. No behavior
   change; makes every later phase additive instead of entangled with
   `blueprint_interpreter.py`'s Blender specifics.
2. **Scene-scoped Blueprint** (section 2) — extend the schema and
   interpreter to compose multiple imported assets + scene-only
   elements under one root; generalized keyframing (section 8, first
   bullet) lands here since scene composition needs it immediately.
3. **`resolve_intent.py` retargeting + SceneSpec derivation for the
   existing translator family** (section 2) — `SceneIntent → Blueprint`
   universally, plus the Blender/USD/Godot exporters' own SceneSpec
   generation step derived from it. Consolidating the motion-grammar
   library (section 8, last bullet) is the detail work inside this
   phase — **done 2026-08-09** (`tools/motion_library.py`, extracted
   from `resolve_intent.py` with verified byte-identical output). The
   vocabulary gap that blocked the retargeting is also **closed
   2026-08-09** (section 11 item 3: `play_move_cue`/`play_animation_cue`/
   `play_dialogue_cue`/`set_active_camera`, live-verified against real
   production assets and data). **Still open**: `resolve_intent.py`
   itself actually emitting Blueprint, plus updating `validate_spec.py`/
   `run_pipeline.py`'s QA gate/the USD-Godot export decision to match —
   deliberately deferred to its own pass given the real production
   blast radius (see section 11 item 3's closing paragraph).
4. **Scene registry + "load X" chooser** (sections 6, 9) — needs (2) to
   have something registrable, needs Milestone 17's `needs_clarification`
   reuse wired to asset/scene resolution specifically.
5. **`oeb_scene_title_v0.0.11` relabel** (section 10) — first real proof
   of (2)-(4) against an actual existing scene, not a synthetic test.
6. **Two-tier missing-asset fallback** (section 7) — depends on (2)
   (scene composition) and the propose/validate/repair loop, already
   proven; mostly wiring plus the ticket-always guarantee. Extended
   2026-08-09 with `producer.py --primitive-fallback` (section 7 item
   7) — the deterministic, offline placeholder path for producer's own
   vocabulary-sweep blocking specifically, live-verified against a real
   multi-scene script, two known-honest limitations documented there.
7. **Producer as a literal Studio Chat client** (section 4) — Producer
   driving real threads/messages, answering its own clarifications,
   under the explicit story/hero-asset guardrails, once (2)-(6) are
   proven attended first.
8. **Agent Bus / Production Designer plan updates** (section 5) — update
   `AGENT-BUS-PLAN.md` and `PRODUCTION-DESIGNER-PLAN.md` in place to
   lift the generative-geometry non-goal and wire the confirmed
   audit-trail citation into the completion-comment discipline, then
   author the prop builder profile (section 11, item 2) once it's
   actually picked up. Depends on (7) proving Studio Chat access works
   safely for an agentic client before opening it to more agent
   profiles.
9. **Lighting/environment + material/shape-detail operations** (section
   8, remaining bullets) — quality-of-output work, not a blocker to
   (1)-(8) landing; sequenced last because nothing above depends on it.

Each phase should get the same verification standard already
established this session: real headless-Blender runs, not just mocked
tests, before being recorded as done.
