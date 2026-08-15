---
title: Vehicle Discovery Plan
created: 2026-08-13T22:30:00-04:00
updated: 2026-08-13T23:15:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: draft
canonical: true
canonical_for: vehicle_discovery_role
wiki: true
wiki_group: Planning
wiki_order: 180
---
# Vehicle Discovery Plan

Recorded 2026-08-13, from a real-asset registration + discussion: the
first hand-built (non-placeholder) vehicle asset, Earth Starfighter
Hero v0.0.8, was registered into `oeb.config.json`, which surfaced
four related, unscoped gaps in how the pipeline discovers and places
vehicles versus characters. **Status: scoping only — nothing built
from this document.** The one concrete fix that came out of the same
conversation (scene 5's no-actor edge case) landed separately in
`tools/producer.py`'s `register_vehicle_placeholder()`/
`_generic_vehicle_subject()` and is not gated on this plan.

## Where this sits

Same shape of question as Casting Director's own origin
(`docs/planning/CASTING-DIRECTOR-PLAN.md`): a role's logic living
uncredited inside `tools/producer.py`, discovered by asking "how does
X actually work" rather than by a ticket. Casting Director resolved
that question for *speaking characters*. This document is the same
question for *vehicles* — deliberately not folded into
`CASTING-DIRECTOR-PLAN.md` itself, since vehicles are cast through a
completely different, much narrower path today (see below), not
through Casting Director at all.

## Discovery 1: no content-based asset lookup anywhere in the pipeline

Asked three times in the same conversation, same answer each time:

- **"How does the casting director know a registered ship is available
  for a new scene?"** It doesn't. `casting_director.py` only checks
  whether *its own* synthetic placeholder ID already exists
  (idempotency against itself), never whether a real, already-built
  asset matches the subject by name.
- **"How does the production designer know what locations/sets
  exist?"** Only via `data/standins.json["location_standins"]` — an
  exact-match, human-curated `raw scripted tag -> real set canonical_id`
  table. If a human hasn't already entered that specific mapping,
  `set_designer.py`'s `resolve_location()` falls straight to building a
  fresh placeholder, blind to whatever real sets already exist.
- **"How does the producer know what characters, props, vehicles,
  locations and sets exist?"** Same pattern across every category:
  flat pre-curated name tables (`cast`, `known_items`,
  `location_standins`) or direct `resolver_map.json` key checks —
  never a scan of `oeb.config.json`'s actual asset library. Vehicles
  have no table at all outside one narrow fallback (Discovery 2,
  below); props are the only category where an unknown item is
  non-blocking (a note, not a ticket).

**Net effect**: registering Earth Starfighter Hero made it
*referenceable* (something can point a role's `character_id` at its
canonical_id directly), but nothing *discovers* it by name. A future
script naming "the Earth Starfighter" would just get a fresh crude box
placeholder, same as before this asset existed, unless a human wires
the binding explicitly.

## Discovery 2: vehicle discovery only fires when zero actors are present

`tools/producer.py`'s `register_vehicle_placeholder()` is vehicles'
*only* discovery path, and it only runs when
`not present_actors(scene, cast)` — i.e., a scene with **zero** present
characters. The moment a scene has both a speaking character and a
named vehicle (the common case: "Orlando in the JourneyBlaster
cockpit"), vehicle registration never fires at all. The ship becomes,
at best, a non-blocking "unknown item" note — never placed, never
positioned, never framable as a shot subject.

Compare to characters: Casting Director fires for *every* dialogue
speaker not yet cast, regardless of who else is present in the scene.
Vehicles have no equivalent broad trigger.

## Discovery 3: no parenting/hierarchy for characters inside vehicles

`tools/export_blender.py`'s actor placement (R6) is flat world-space
for every actor: `obj.location = mark_obj.location.copy()` (or, since
today's collection-instancing fix, an Empty instance placed the same
way). Nothing parents an actor's object to a vehicle's object.

This doesn't currently bite because every existing cockpit-interior
scene (JourneyBlaster cockpit, etc.) models the cockpit as a static
*location* (its own set, own marks) — the ship itself is never an
animated, moving on-screen object in those shots, so nothing needs to
move together. It would bite the moment a scene needs a character to
stay seated *inside* a vehicle that's actually being animated (flying,
maneuvering): the character would stay at a fixed world position while
the vehicle moved out from under them, with no error raised anywhere.

## Discovery 4: name-to-asset is pure string determinism, never matching

Traced live against the real code with two worked examples, action
text `"The JourneyBlaster 5000 drops out of hyperspace..."` and `"A
small red ship drifts past..."`:

- **Proper noun ("JourneyBlaster 5000")**:
  `screenplay_entity_resolution.extract_entity_candidates()` only
  captures a run of consecutive Title-Case *words* — it pulled
  `"JourneyBlaster"` and silently dropped the trailing `"5000"` (digits
  don't extend the capitalized-word run). That string goes straight
  through `placeholder_blueprint.slugify_placeholder_id("JourneyBlaster",
  "vehicle")` -> `placeholder_vehicle_journeyblaster_A` — a pure
  string-to-ID function, confirmed against the real registry
  (`oeb.config.json`'s existing `placeholder_vehicle_journeyblaster_A`,
  `source: "producer --primitive-fallback"`, built this same way, not
  by anything matching a real asset).
- **Generic phrase ("small red ship")**: no proper noun exists, so
  `extract_entity_candidates()` finds nothing and
  `_generic_vehicle_subject()` (today's fix) falls back to a literal
  `VEHICLE_NOUN_KEYWORDS` match -- finds `"ship"` -- and discards
  `"small red"` entirely. A script saying "massive rusted ship" would
  produce the exact same generic `placeholder_vehicle_ship_A`,
  indistinguishable from this one.

Confirms Discovery 1 with a concrete trace: there is no matching step
anywhere in either path, proper-noun or generic -- just deterministic
name -> slug conversion, blind to both the real asset library and any
descriptive detail beyond the bare noun.

**A second bug surfaced by the same trace**: `register_vehicle_placeholder()`
filters out any candidate already in `cast` --
`candidates = [c for c in candidates if c.lower() not in cast]` -- so
a proper-noun vehicle named again in a *later* scene gets silently
dropped from consideration. Unlike Casting Director's
`resolve_role()`, which has an explicit "already cast, extend to this
new location" branch for exactly this situation, this function has no
equivalent branch at all: once its only candidate is filtered out, it
just falls through to `_generic_vehicle_subject()` as if no proper
noun had ever been in the text, silently ignoring the name it just
excluded rather than reusing/extending the already-registered vehicle.

## Should vehicles and characters be treated the same?

**Registry shape: already unified, no change needed.** Both use the
identical `resolver_map.json["roles"]` shape (`character_id` ->
`spawn_marks` -> `entrances`), the same `register_placeholder_role()`,
and the same placeholder-build pipeline — differing only in primitive
shape (`tools/placeholder_blueprint.py`'s `_DEFAULT_PRIMITIVE_BY_KIND`:
character = tall thin cylinder, vehicle = wide box).

**Discovery mechanism: not unified, and arguably shouldn't be
identical** — a vehicle named in action text and a character speaking
dialogue are found through genuinely different textual signals
(`screenplay_entity_resolution.py`'s proper-noun extraction vs.
dialogue-cue speaker names). But vehicle discovery's *trigger
condition* (only when actor-less) is too narrow regardless of that
difference, and is the concrete bug in Discovery 2.

## Open questions (not decided here)

1. Does vehicle discovery move to its own role (mirroring Casting
   Director's own split from Producer), or stay inside
   `register_vehicle_placeholder()`/`producer.py`, just with a broader
   trigger (run it whenever action text contains a vehicle-shaped
   subject, independent of `present_actors()`)?
2. What does content-based asset discovery actually look like for any
   category (characters, vehicles, locations)? Exact-name match against
   `oeb.config.json`'s non-placeholder assets is the obvious floor;
   fuzzy/semantic matching is a much bigger, judgment-laden feature not
   scoped here.
3. Parenting design for characters inside moving vehicles: object
   parenting at export time (`obj.parent = vehicle_obj`) is the obvious
   mechanism, but nothing about spawn_mark/entrance semantics currently
   expresses "relative to a vehicle" versus "relative to a location" --
   that distinction doesn't exist in the schema yet.
4. Should a vehicle ever be cast as a *speaking* role (a ship AI voice,
   e.g. scene 78's "ship ai")? That case already goes through Casting
   Director today (as a background-tier character), not through
   `register_vehicle_placeholder()` at all -- worth reconciling which
   path "vehicle" really means in each case.
5. ~~Should `register_vehicle_placeholder()` gain an "already cast,
   extend to this location" branch?~~ **Resolved 2026-08-13, landed in
   `tools/producer.py`.** Turned out not to need a new branch at all --
   that branch already existed (added alongside the scene 5 fix); the
   bug was the dead `candidates = [c for c in candidates if c.lower()
   not in cast]` pre-filter one step earlier, silently dropping an
   already-cast vehicle's name before it ever reached that branch.
   Traced live: this function only ever runs when
   `not present_actors(scene, cast)`, and `present_actors()` already
   checks every cast member's name against the identical
   `scene_action_text(scene)` -- so the filter could never protect
   against its apparent intent (a known character's name in the text
   would already have made the caller skip this function entirely). Its
   only live effect was this bug. Removed the filter; verified live
   against scratch data that a vehicle named in two separate scenes now
   correctly extends the same role on the second mention instead of
   falling through to `_generic_vehicle_subject()`. If vehicle discovery
   later moves to its own role (Question 1), this fix moves with it.

## Not built

Two narrow fixes have landed out of this document -- the scene 5
no-actor fallback (`_generic_vehicle_subject()`) and Question 5's
already-cast fall-through fix (both in
`register_vehicle_placeholder()`, `tools/producer.py`) -- neither
changes the scope of Discoveries 1-4 or Open Questions 1-4. Everything
else, including any actual architecture change (moving vehicle
discovery to its own role, content-based asset lookup, vehicle/character
parenting), remains scoping only. No other code changes made from this
discussion.
