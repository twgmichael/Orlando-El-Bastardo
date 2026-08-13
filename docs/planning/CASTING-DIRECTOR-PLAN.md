---
title: Casting Director Plan
created: 2026-08-10T21:00:00-04:00
updated: 2026-08-12T00:00:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: active
canonical: true
canonical_for: casting_director_role
wiki: true
wiki_group: Planning
wiki_order: 28
---
# Casting Director Plan

Recorded 2026-08-10, from the full 81-scene pilot episode triage run:
81 scenes, 21 delivered, 59 blocked, 1 failed. **159 of 216 blocking
findings (74%) were unmapped speaking roles** — casting is the single
largest blocker to finishing the episode, by a wide margin over
locations (57). This document originally scoped the role only
(explicit user instruction: scope only that pass); a build pass has
since happened — **status: BUILT, uncommitted, live-tested but not yet
reviewed/merged.** See "Build status" at the end of this document.

## Where this sits in the real production pipeline

Per the user's own framing of the industry order of operations: casting
happens after creative development/visualization, before department
prep and principal photography — the Casting Director "finds and
auditions performers with the director and producers." In our terms:
casting has to resolve before Director can even ask "who's present in
this shot," since blocking/framing decisions are keyed on which actors
exist at all.

## Discovery: casting was never actually assigned anywhere

Two real, distinct problems, not one:

1. **Ownership**: exactly the same shape of finding as Set Designer and
   Director before it — casting's actual logic already exists, but
   living inside `tools/producer.py`'s `primitive_fallback()`, put
   there under time pressure, contradicting `PRODUCER-PLAN.md`'s own
   charter. Nobody ever gave it its own role. `PRODUCTION-DESIGNER-PLAN.md`'s
   2026-08-10 discovery section flagged this explicitly as **open, not
   decided** at the time — this document is that decision.
2. **A real ordering bug, not just a missing role**: `primitive_fallback()`'s
   role loop needs `location_set_id` (the scene's *resolved* location)
   to anchor a new character's spawn marks against. If the location is
   *also* unresolved in the same scene — common, since a scene
   introducing a new character often also introduces a new place — the
   role can't be placeholder-cast at all this pass: "no location to
   anchor role marks against; still blocked." Confirmed live in the
   triage run's own log output. This is why role-blocking (159)
   outnumbers location-blocking (57) so heavily: many role blockers are
   downstream of a location blocker in the *same* scene, not
   independent problems.

## Casting is not shaped like Set Designer's two tiers

Set Designer's tier-1 ("stand-in") works because many different scripted
locations can legitimately share one real physical set — a bar is a
bar. `data/standins.json` confirms the asymmetry structurally — it has
`location_standins` (many raw location tags mapping to few real sets)
but nothing analogous for cast; `cast` is a flat one name -> one
role_tag table, no shared-identity concept anywhere in it. **Visual
identity turns out not to matter here either way** (user, 2026-08-10:
"we had success using oblongs in place of characters" — the existing
crude placeholder already carries the whole project fine, no need for
principals to look distinct from each other or from background). The
principal/background split below is about **registration, not looks**:
whether a name gets its own tracked role/asset entry an eventual real
character build can replace individually, or shares one placeholder
entry with every other background voice.

**The real distinguishing tier, informed by the industry breakdown
above, is principal vs. background** — the same distinction a real
Casting Director makes between principal cast and day players/extras,
mapped onto asset registration rather than appearance:

- **Principal**: a named character worth its own tracked role/asset
  entry — appears across multiple scenes, or is addressed by a proper
  name rather than a functional label. Gets its own placeholder build
  and registration (as `primitive_fallback()` already does today,
  unchanged), so a real character build can later replace this one
  role without touching any other.
- **Background**: a single-scene functional voice (`second voice`,
  `station announcer`, `colonist voice`, a guard, a technician) that
  the story never distinguishes and never needs replacing individually.
  Doesn't need its own registration at all — shares one reusable
  placeholder entry, the same way `notes`/background props already
  don't get individual tickets.

**Classification is deterministic, not an LLM call.** This section
originally sketched a whole-episode scene-appearance tally (>=2 scenes,
or a proper name -> principal); Open Question #5 below superseded that
before the build pass: since recurrence never auto-promotes background
to principal anyway (needs human approval, not designed yet), no tally
is actually needed for classification itself. What's built in
`tools/casting_director.py`'s `classify_cast()` is a pure per-name
keyword check against `FUNCTIONAL_LABEL_KEYWORDS` (Open Question #4) —
no episode-wide pass, no scene counting. Same "reuse existing rails, no
new judgment-call vocabulary" discipline as every other deterministic
classifier in this pipeline (`classify_shot_scale()`, `present_actors()`).

## Role definition

**Mission (one sentence)**: given a scene's speaking characters with no
existing cast mapping, resolve each to a role — principal placeholder
or shared background placeholder — anchored to that scene's resolved
location, then let the scene continue.

Responsibilities:
- Classify each newly-seen speaker as principal or background (a
  per-name keyword check, not an episode-wide pass — see the
  classification section above).
- Register principal roles with their own placeholder character build
  (relocated from `primitive_fallback()`'s role loop, unchanged in
  substance).
- Register background roles against one shared reusable placeholder
  instead of building a new asset per name.
- Extend an already-cast role to a new location's spawn_mark
  (`role_location` handling, relocated unchanged from the same
  function).
- Never invent dialogue, never decide who a character *is* beyond
  principal/background triage, never touch a real (non-placeholder)
  character asset.

Boundaries (same standing constraints as every other role this
session): git read-only, no downloads, repo-relative paths only,
escalate rather than improvise past what's described here.

## What relocates out of `tools/producer.py`

- The main-loop "unknown speakers block" check (lines ~643-650) stays
  in Producer — noticing and ticketing the gap is exactly Producer's
  job, unchanged, same as it correctly stayed for locations.
- `primitive_fallback()`'s `role` and `role_location` loops (currently
  lines ~371-424) relocate to a new `tools/casting_director.py`,
  mirroring `tools/set_designer.py`'s relocation of the location loop.
- The location-dependency ordering bug gets fixed as part of the move,
  not left as a "still blocked, try again later" — see Open Questions.

## Dispatch (built, mirrors Set Designer)

Given the ordering bug, Casting Director's dispatch can't simply mirror
Set Designer's "enqueue immediately on the blocking ticket" pattern
without solving the "location not resolved yet" case first. Built as:

- Same worker-queue extension as Set Designer
  (`docs/planning/WORKER-AGENT-PLAN.md`) — a `tools/casting_director.py`
  job dispatched via the existing `BlenderCLIAdapter` (stdlib-only, no
  bpy required, same as `set_designer.py`), no new adapter.
- Producer enqueues a casting job at the same point it enqueues a
  location job. When the scene's location is *also* blocked in the same
  pass, the casting job is created with `depends_on_job_id` set to the
  location job's id (see Open Questions #1) so a worker never claims it
  before the location actually exists.

## Open questions (deliberately not decided here)

1. ~~Job sequencing~~ **Decided 2026-08-10 (user): wait on the location
   job explicitly.** Real new infrastructure, not just new casting
   logic — confirmed against the actual job model
   (`oeb-studio-harness/server/app/models/job.py`) and the real
   eligibility query (`list_eligible_jobs()`,
   `app/routers/jobs.py:386`). `Job.sibling_job_id` already exists but
   is the wrong shape for this — it's a bidirectional, purely
   informational pairing (preview/final render jobs point at each
   other), never checked by the eligibility query at all. What's
   actually needed:
   - A new nullable `depends_on_job_id` field on `Job` (a real
     migration, `oeb-studio-harness/server/migrations/`).
   - One new condition in `list_eligible_jobs()`'s `is_eligible(j)`
     check: if `j.depends_on_job_id` is set, the referenced job's
     `status` must be `"completed"` (a worker never even sees a
     dependent job until then — same "never offer an unsafe/premature
     option" discipline as the collision-avoidance mark filter).
   - `enqueue_set_designer_job()`-equivalent for casting sets
     `depends_on_job_id` to the location job's id whenever Producer
     enqueues both from the same blocked scene; omits it (no
     dependency) when the scene's location already resolved and only
     casting is blocked.
   - **Decided 2026-08-10 (user): cascades.** If the location job a
     casting job depends on fails, the dependent casting job fails too
     rather than hanging forever or waiting for manual release. Same
     `is_eligible(j)` neighborhood: on the location job transitioning
     to `"failed"`, any job with `depends_on_job_id` pointing at it
     should also transition to `"failed"` (with a reason referencing
     the upstream failure, for the NEEDED-ticket trail) rather than
     sitting `"pending"` forever, unclaimable, with no signal why.
2. ~~Background pool size and identity~~ **Decided 2026-08-10 (user):**
   one shared placeholder body for every background voice,
   episode-wide. The existing crude cylinder placeholder has already
   worked fine as a generic character stand-in throughout this project
   — no pool, no per-instance variation needed for background roles.
3. ~~Principal visual variation~~ **Decided 2026-08-10 (user):** none
   needed. Two different principals sharing the same placeholder shape
   is fine — "it's 3D animation, not rocket surgery." Principals still
   get their own *registered* role/asset (so a real character build can
   replace one later without touching the others), just not a visually
   distinct crude shape in the meantime.
4. ~~Where "proper name vs. functional label" classification actually
   lives~~ **Decided 2026-08-10: a keyword lookup list**, same pattern
   as `VAST_SCALE_KEYWORDS`/`tools/index_assets.py`'s `TAG_VOCABULARY`
   — a raw speaker name matching any keyword as a substring (case-
   insensitive) is background regardless of whether it also contains
   what looks like a proper name (`"deranti secretary"` -> background,
   not principal, because `secretary` matches — same "keyword presence
   wins" simplicity already used elsewhere). Verified against every
   real blocked-role name from the 81-scene triage — all 15 real
   functional labels match, none of the 8 real proper names
   (`marqui`/`farring`/`quill`/`horous`/`penn`/`rogers`/`hudson`/`collins`)
   false-positive. `FUNCTIONAL_LABEL_KEYWORDS`, ready to lift into
   `tools/casting_director.py` when built:

   ```python
   FUNCTIONAL_LABEL_KEYWORDS = (
       # generic job/occupational titles
       "guard", "officer", "technician", "official", "secretary",
       "pilot", "waiter", "waitress", "clerk", "attendant", "operator",
       "dispatcher", "receptionist", "steward", "medic", "engineer",
       "mechanic", "crewman", "soldier", "trooper", "marine", "worker",
       "staff",
       # system/comms voices
       "announcer", "controller", "control", "voice", "computer",
       # ordinal/numbered generic labels -- almost always background/extras
       "first", "second", "third", "fourth", "fifth",
   )
   ```

   One episode's worth of evidence, not proof of a general rule —
   still small and conservative enough (matching this project's
   established vocabulary-extension discipline) to extend later if a
   future script's real data shows a gap, same as `TAG_VOCABULARY`/
   `VAST_SCALE_KEYWORDS` before it.
5. ~~Does a recurring background label across scenes get promoted to
   principal?~~ **Decided 2026-08-10 (user): no, not automatically —
   requires approval.** Recurrence alone never auto-promotes; a
   background role that turns out to recur (e.g. "second guard"
   speaking in five different scenes) stays background unless a human
   explicitly approves promoting it to its own registered principal
   role. Mechanism not designed yet, but the shape is now consistent
   with every other human-gate this pipeline already has (kitbash
   approval, `/review/kitbash`) rather than a silent, automatic
   reclassification mid-episode.

## Build status (2026-08-12)

All five open questions above are decided, and all three next-step
items are built. Uncommitted on disk, not yet reviewed/merged:

1. **Done** — `oeb-studio-harness/server`: `depends_on_job_id` migration
   (`migrations/versions/0012_job_depends_on.py`), the `Job` model
   column, the `is_eligible(j)` gating check and the on-`"failed"`
   dependent-cascade in `fail_job()`, and the schema/request fields —
   all in `app/models/job.py`, `app/routers/jobs.py`,
   `app/schemas/job.py` (Open Question #1).
2. **Done** — `tools/casting_director.py` exists: `primitive_fallback()`'s
   `role`/`role_location` loops relocated and are gone from
   `tools/producer.py`; `classify_cast()` implements the
   `FUNCTIONAL_LABEL_KEYWORDS` per-name check (Open Question #4); one
   shared `BACKGROUND_CHARACTER_ID` placeholder is built once and reused
   episode-wide (Open Question #2); principal roles still get their own
   registered placeholder build/asset (Open Question #3).
3. **Done** — `tools/producer.py`: `enqueue_casting_director_job()`
   added alongside `enqueue_set_designer_job()`; `main()` dispatches
   location jobs first, then role/role_location jobs with
   `depends_on_job_id` set to the same-scene location job's id when one
   was just enqueued.

**Evidence of live testing**, visible in the uncommitted diffs (not
just written, actually exercised): `oeb.config.json` /
`data/resolver_map.json` / `data/standins.json` carry real
casting-director-sourced registrations — `zandra` (a real triage name)
plus synthetic `testperson`/`testpersonbeta` and
`dep_test_location_alpha`/`beta`/`testforge_nebula_outpost` entries,
consistent with exercising both the principal path and the
location-dependency/cascade path end-to-end.

**Not yet done**: nothing has been committed to git; no indication yet
of a full-episode re-run to confirm the 159 role blockers actually
clear. (`PROJECT-TODO.md`'s Casting Director line was itself stale
against this build pass — corrected 2026-08-12.)
