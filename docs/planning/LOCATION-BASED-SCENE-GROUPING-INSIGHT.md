---
title: Location-Based Scene Grouping Insight
created: 2026-08-15T00:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
doc_type: plan
production_area: layout
department: layout
status: draft
canonical: true
canonical_for: location_based_scene_grouping
wiki: true
wiki_group: Planning
wiki_page: Location-Based-Scene-Grouping-Insight
wiki_order: 201
---
# Location-based scene grouping insight

Recorded 2026-08-15. Status: **insight to ponder — not decided, nothing
scoped or built from this document.**

## The insight (as given)

Usually we wouldn't build individual scenes, each with its own location,
characters, assets, vehicles, and props. We build sets and locations to
create a series of scene *sets*, where each "scene" is really just camera
placement within the location or set.

Example: in the teaser trailer, every scene is set in space or an asteroid
field — also space — including the JourneyBlaster 5000 ship, a mining probe,
and asteroids. It's one *location* with vehicles, characters, and props,
multiple cameras for each scene, and the vehicles move through that one
location while each camera (observer) records.

Right now every scene is treated as a separate problem to solve, when it's
really one solution serving several problems, with the occasional actual
one-location/one-scene case genuinely being just one scene.

Producer will need to read context for scenes sharing a location, determine
sort order and connection between them, and inform Director which scenes are
connected.

## What this does not change

Per-scene validation and construction work stays valuable and applicable
even once this is broadened — that discipline (resolving a scene's cast,
location, assets; validating against the schema; deterministic
resolve→validate→export→render) doesn't go away. What changes is the *unit*
those steps operate on: today it's always exactly one screenplay scene;
under this insight it becomes a shared location/set build plus N camera
passes across a connected group of scenes, with the underlying per-item
validation and construction discipline still applying at the camera-pass
level, and at the occasional genuine single-scene case.

## What already partially exists

Location resolution already has some reuse: the Set Designer tier of
`resolve_location()` persists matches into `location_standins`
(`docs/planning/LLM-ASSET-MATCHING-PLAN.md`), so two scenes sharing the
*exact same* `location_tag` string already resolve to the same built
stand-in instead of rebuilding it. What's missing is everything above that:
recognizing that differently-named location tags ("space," "asteroid field")
are the *same physical set*; and, more importantly, that vehicles,
characters, and props need continuous position/motion across the whole
connected run of scenes, not just a shared backdrop. Today each scene is
still an independent build+placement+render unit even when it happens to
reuse a stand-in.

## Expanded architecture discussion (2026-08-15, continued)

Follow-on discussion, going role by role through what changes. Still
**insight to ponder — not decided, nothing scoped or built.**

### Producer

The Producer should understand the screenplay globally rather than scene by
scene. Its first responsibility becomes identifying production
relationships — for example:

- Scene 1: Space, JourneyBlaster approaches probe.
- Scene 3: Space, JourneyBlaster passes asteroids.
- Scene 7: Asteroid field, JourneyBlaster pursued.
- Scene 11: Space, exterior establishing shot.

The Producer recognizes that these belong to the same production family and
tells downstream roles something shaped like:

```text
Production Group: Outer Space / Asteroid Environment
Scenes: 1, 3, 7, 11
Shared assets: JB5K, asteroids, stars, mining probe
Continuity relationships: 1 → 3 → 7
Independent establishing shot: 11
```

The Producer therefore owns production grouping, dependency identification,
continuity relationships, and production order. Real-world equivalents
overlap with the producer, line producer, 1st AD, and script breakdown
functions. Note this example groups scenes 1, 3, 7, and 11 — **not**
contiguous screenplay scenes; other, unrelated scenes may fall between them.

### Production Designer

The Production Designer builds the reusable world, not an isolated scene.
Its assignment becomes something shaped like "create the Outer Space /
Asteroid production environment required by Scenes 1, 3, 7, and 11," and it
determines:

- environment dimensions and coordinate system
- asteroid distribution
- starfield/background
- lighting framework
- reusable spacecraft
- probe placement
- reusable props
- environment variants
- areas that cameras must see
- areas that never need construction

The Production Designer should see all associated scenes before designing
the environment — otherwise it may build something adequate for Scene 1
that fails Scene 7. This matches physical production: a production designer
builds the bridge set, not "the bridge set for Scene 27"; Scene 31
subsequently uses the same bridge.

### Casting Director

The Casting Director should identify characters across the entire
screenplay and establish reusable canonical cast assignments — for example,
Orlando maps to the Orlando canonical character, the Bugblatter pilot to a
character/cast requirement, a background pilot to a reusable background
performer, a voice-only computer to a voice role — and should also identify
which production groups require which characters. The Casting Director
therefore answers who must exist and where they are required, rather than
creating a character independently for every scene.

### Director

The Director receives something much more useful than an isolated
screenplay scene — something shaped like: "Scene 7 occurs inside Production
Group `outer_space_01`, shares continuity with Scenes 1 and 3, uses JB5K and
mining probe assets, and begins with the JB5K at the state produced by Scene
3." The Director then owns the actual observation of the action: camera
placement, camera movement, lenses/framing, blocking, vehicle trajectories,
character animation, timing, performance, shot sequence, and coverage. The
Director does not rebuild the asteroid field — it stages Scene 7 inside the
existing asteroid field.

### The core architectural distinction

```text
Screenplay Scene → Production Group → Environment/Set → Scene State → Shots/Cameras
```

A screenplay scene is therefore mostly a narrative and continuity boundary.
It is not inherently a separate 3D scene file or separate world. The current
architecture appears to collapse screenplay scene, production environment,
and render scene into one concept — those should separate.

For Orlando El Bastardo, the Producer should probably perform a
screenplay-wide pass before any Director work begins: identify shared
locations, chronological relationships, asset dependencies, continuity
chains, and efficient production groups. The Production Designer and
Casting Director can then prepare each shared production package once. The
Director subsequently stages every associated screenplay scene inside that
package. That turns:

```text
Scene → solve everything → render
```

into:

```text
Screenplay → organize production → build reusable world → stage scenes → shoot cameras
```

This distinction is substantial enough to be treated as a candidate **core
Studio architecture principle**, not a narrow optimization.

### How this discussion informs (but does not resolve) the open questions below

- **Non-contiguous grouping is the intended shape**, not consecutive-scene
  batching — the worked example (scenes 1, 3, 7, 11) explicitly spans
  unrelated interstitial scenes. Built sets/environments would need to
  persist and be re-enterable across the whole episode, confirming the
  larger of the two shapes raised in open question 2 below.
- **A concrete continuity mechanism is proposed**: the Producer identifies
  the ordered dependency chain (`1 → 3 → 7`) at the grouping/breakdown
  stage; the Director then authors the actual per-scene trajectory/staging,
  starting from the "state produced by" the prior scene in the chain. This
  gives open question 3 a candidate answer — a "Scene State" handoff
  between connected scenes — though the exact data shape of "Scene State"
  is not defined here.
- **A new first-class production unit is implied**: "Production Group" /
  "Environment/Set," built once and reused, sitting between the screenplay
  scene and the individual camera/shot. The screenplay scene itself seems to
  remain the narrative/continuity/shot-tracking boundary. This informs open
  question 4 (today's report/ticket/`episode_cut()` unit is the screenplay
  scene) without settling how Production Group would be tracked alongside
  it.
- Open questions 1 (how location tags get judged "the same set") and 5
  (incremental vs. big-bang rollout) are not addressed by this discussion.

## Open questions (not decided)

Raised in discussion 2026-08-15, unresolved:

1. **How does the system decide two location tags are "the same set"?** The
   teaser example groups "space" and "asteroid field" as one — that's a
   judgment call, not a string match. Human-curated location-family mapping
   (consistent with this project's pattern of constrained LLM matching
   against a real candidate list, never free-form invention), or should the
   local LLM infer the grouping from scene context?
2. **Contiguous vs. non-contiguous grouping?** Runs of *consecutive*
   screenplay scenes sharing a location (simpler — batch N adjacent scenes
   into one build pass), or *any* scenes anywhere in the episode that share
   a location family, even with unrelated scenes interspersed (bigger — built
   sets would need to persist and be re-enterable across the whole episode,
   not just within one contiguous run)?
3. **What carries continuity across the group, and who authors it?** If the
   JourneyBlaster moves through the asteroid field across scenes 5→7→9, does
   something need an authored trajectory spanning the whole group so scene 7
   picks up where scene 5 left the ship, or is "connected" mainly about
   camera/observer placement within a more static tableau, with less
   pressure on exact motion continuity? This is the difference between a
   camera-placement problem and a full shot-continuity/animation problem.
4. **What's the new unit of production tracking?** Today one screenplay
   scene number maps 1:1 to one ticket, one report entry, one rendered
   output. If N scenes become one location build plus N camera passes, does
   per-scene tracking (`report.json`, tickets, `DELIVERED` status,
   `episode_cut()`) stay keyed to the original scene numbers sourcing from a
   shared build, or does "location build" become its own first-class tracked
   unit separate from "camera pass"? Touches `tools/producer.py`,
   `tools/tickets.py`, and episode assembly directly.
5. **Incremental or big-bang?** This changes Producer's core loop from
   "walk scenes one at a time" to "read the whole script first, group, then
   dispatch groups to Director/Set Designer." One redesign, or staged —
   e.g. first just location-family grouping to stop redundant builds, then
   layer in cross-scene camera/motion continuity as a second pass?

## Not built

Nothing in this document has been implemented or scoped into an
implementation plan. `tools/producer.py`'s scene-by-scene loop is unchanged
as of this writing.
