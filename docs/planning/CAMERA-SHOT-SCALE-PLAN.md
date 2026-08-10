---
title: Camera Shot-Scale and Collision Plan
created: 2026-08-10T19:00:00-04:00
updated: 2026-08-10T19:30:00-04:00
doc_type: plan
production_area: pipeline
department: production
status: active
canonical: true
canonical_for: camera_shot_scale
wiki: true
wiki_group: Planning
wiki_order: 26
---
# Camera Shot-Scale and Collision Plan

Recorded 2026-08-10, from a real bug found by watching the JourneyBlaster
teaser's real renders: scenes 3 and 5 (`EXT. ASTEROID FIELD`) showed the
camera essentially inside JB100's own hull. Root-caused, fixed, and
extended into a second real problem (asteroids far too small, JB100
able to fly straight through them) the same session. **Status: BUILT
and live-verified**, both parts.

## Part 1: camera shot-scale

### Discovery

`tools/export_blender.py`'s camera resolution looks up a named
`scene_object` (from `data/camera_grammar.json`) inside whatever
location GLB is loaded for the shot. `placeholder_location_asteroid_field_A`
had never had a camera object baked into it at all (`tools/placeholder_
blueprint.py`'s generic location builder only ever produced body+marks) --
so the lookup failed, and the code fell back to a fixed generic camera
position (`(0, -8, 3)`, tuned for the sci-fi bar's small interior). A
full-size spacecraft dropped into that same fixed-distance shot, in a
vast exterior, produced extreme clipping.

**Direct user framing of the fix, not "one camera per location":** "we
don't need a camera per scene, we need to follow the script... EXT.
DEEP SPACE... would indicate a wide establishing shot... INT.
JOURNEYBLASTER - COCKPIT is a close up and is fine. We need a selection
of camera shot lengths that make sense for the script."

### Design

A small, closed **shot_scale** vocabulary -- `"intimate"` | `"vast"` --
classified deterministically from the script's own `INT`/`EXT` slugline
prefix plus a small keyword check on the location text, never an LLM
judgment call (same "deliberate author direction first" principle as
slugline/location resolution,
`SCREENPLAY-SLUGLINE-ACTOR-PRESENCE-GAP.md`):

- `INT` is always `"intimate"` -- an interior is confined regardless of
  what's inside it (the cockpit is correctly intimate as-is).
- `EXT` defaults to `"intimate"` too (an ordinary exterior -- a rooftop
  garden -- doesn't need a vast establishing shot) unless the location/
  action text names a cosmic/large-scale setting (`space`, `asteroid`,
  `orbit`, `nebula`, `galaxy`, ... -- a lookup vocabulary, not free
  classification).

Two reusable camera *templates*, not per-location authoring:
`tools/placeholder_blueprint.py`'s `SHOT_SCALE_CAMERAS` dict.
`"intimate"` reuses the bar's own `cam_establishing_wide` scene_object
name -- every intimate-scale location bakes its own object under that
same name into its own `.glb`, exactly like the bar already does, no
new `camera_grammar.json` entry needed. `"vast"` is the one genuinely
new entry (`cam_establishing_vast`, far back, wide 24mm lens).

### Built

- `tools/screenplay.py`: `int_ext` captured on every parsed scene
  (`SLUG_RE`/`MD_SCENE_RE` already matched the group, just discarded
  it before).
- `tools/blueprint_interpreter.py`: new `"camera"` primitive type
  (position + optional `aim_at` + `lens_mm`) -- a real, named,
  *exported* camera object, distinct from the interpreter's existing
  reserved choreography camera (`_ensure_camera()`, deliberately
  excluded from geometry export). Also fixed a real, separate bug
  found while wiring this: the interpreter's own `export_scene.gltf`
  call never passed `export_cameras=True`, so a camera primitive
  wouldn't have exported even once added.
- `tools/placeholder_blueprint.py`: `classify_shot_scale()`,
  `SHOT_SCALE_CAMERAS`, and `default_placeholder_blueprint()` now bakes
  the right camera in when building a location.
  `register_placeholder_location()` stores `shot_scale` on the
  resolver_map.json entry (defaults to `"intimate"` -- backward
  compatible with every location registered before this field existed).
- `schemas/camera-grammar.schema.json`: added the `shot_scale` field;
  also fixed a real pre-existing bug found validating real data for the
  first time -- `medium_on` wasn't in the schema's `framing` enum despite
  being live-used camera data.
- `tools/resolve_intent.py` (R5): establishing/two_shot camera
  resolution now filters by `(framing, shot_scale)`, not framing alone
  -- `shot_scale` read from the resolved location's resolver_map.json
  entry, defaulting to `"intimate"`.
- `tools/set_designer.py`/`tools/producer.py`: `int_ext` threaded from
  the scene parse through `enqueue_set_designer_job()` into
  `resolve_location()`, so every *new* placeholder location gets
  classified automatically going forward, not just the two retrofitted
  below.

### A real mistake, caught and fixed the same session

Retrofitting `asteroid_field` initially used the *generic* placeholder
builder (`placeholder_blueprint.default_placeholder_blueprint()`) to
add the camera -- which silently destroyed that location's real,
bespoke content: `tools/build_asteroid_placeholders.py`'s `build_field()`
is a wholly separate script that procedurally builds 5 real asteroid
meshes directly into the location's `.glb` (never registered as
`default_props`, so nothing else even hinted they existed there). The
generic rebuild replaced all of it with an empty room. Caught when the
user asked "what happened to our asteroids" after the camera fix
render came back correct but empty. Recovered via a Blender `.blend1`
backup confirming what was lost, then fixing `build_field()` itself
(not the generic builder) to bake the camera in -- see
`register_field_collision_data()` below, which is also how Part 2 got
built in the same pass. **Lesson, not yet written into a profile
anywhere formal**: before rebuilding *any* placeholder location's
`.glb`, check whether it has a dedicated build script before assuming
the generic builder is what produced it.

## Part 2: real-world scale and collision avoidance

### Discovery

Once the camera was fixed, the user gave the actual reference scale:
JB100 is ~2m tall x ~3m wide; asteroids should be ~10m wide. Measuring
the real assets (reusing `tools/index_assets.py`'s bounding-box
computation, built earlier the same session for the kitbash library
survey) showed: JB100's real model is ~2.3m tall (close) but ~6.2-6.6m
wide (~2x the stated target -- a real, hand-modeled hero asset, left
as-is rather than resized, see Decisions); the field's asteroids were
only ~1.4-2.5m each after `build_field()`'s own layout-scale
multipliers -- 4-8x too small, and clustered close enough together
(and to the marks) that a true-to-life-sized JB100 moving between them
would routinely have overlapped one.

### Decision: deterministic geometry, not LLM reasoning

Same conclusion as the blocking/move-mark reliability findings earlier
the same session (`DIRECTOR-ROLE-PLAN.md`): a small local model cannot
be trusted to reason about numeric spatial relationships in text.
Collision avoidance is built as a **pre-filter**, not a judgment
Director has to make -- the system computes which of a location's
marks are physically safe for a given actor's real size *before*
Director ever sees the mark list, so Director is never offered an
unsafe destination and never has to reason about geometry at all.

### Built

- **`oeb.config.json`**: `radius_m` on `prop_jb100_A` (3.3, half its
  real measured width) -- the first asset with a registered physical
  size. Reusable by any future scene JB100 appears in, not
  asteroid_field-specific.
- **`data/resolver_map.json`** location entries gain two new optional
  fields: `obstacles` (`[{"position": [x,y,z], "radius_m": r}, ...]`)
  and `mark_positions` (`{mark_name: [x,y,z]}`) -- plain registered
  data, not geometry introspection, so the collision check needs no
  bpy. A location with neither field is unaffected (every location
  registered before this existed).
- **`tools/motion_library.py`**: `clear_marks_for_mover(location_entry,
  mover_radius_m)` -- the actual geometric check (sphere-distance vs.
  sum of radii, plus a 1m margin). Pure function, no bpy, reusable by
  both the rough-tier pre-Director filter and any future validator-side
  check.
  - **This is the general mechanism, not a scene-specific patch**:
    `clear_marks_for_mover()` and the `radius_m`/`obstacles`/
    `mark_positions` fields are generic; any location with registered
    obstacles and any actor with a registered `radius_m` gets filtered
    the same way. `asteroid_field` is just the first location with real
    obstacle data -- the code path isn't hardcoded to it.
- **`tools/producer.py`**: before calling `director.direct_scene()`,
  computes the largest registered radius among the scene's present
  actors and calls `clear_marks_for_mover()` to filter `location_marks`
  down to the collision-safe subset before Director ever sees them.
  Falls back to the unfiltered list when no actor/location has
  registered size data.
- **`tools/build_asteroid_placeholders.py`**: `build_field()` now
  computes each asteroid's own scale factor from
  `ASTEROID_TARGET_DIAMETER_M / raw_max_dimension` (targeting exactly
  10m per asteroid, whatever its raw procedural size), repositions all
  5 well clear of the entry-center-exit travel line (verified by the
  same distance math `clear_marks_for_mover()` uses, not eyeballed),
  and returns the built obstacle list so `register_field_collision_data()`
  can write it straight into `data/resolver_map.json` -- single source
  of truth: what got built is exactly what gets registered. `FIELD_MARKS`
  widened from +-2/+-5m to +-25m to match the new true-to-life scale.
- **Verified live**: `clear_marks_for_mover()` against the real
  registered asteroid_field data returns all 3 marks clear for JB100's
  real radius (3.3) and *zero* marks clear for a hypothetical
  radius-10 mover -- confirms the check actually discriminates by
  size, not just passing everything. Re-rendered scenes 3 and 5:
  correctly massive asteroids, JB100 clearly smaller, no clipping, no
  overlap. Full `oeb-studio-harness/server` pytest suite (382 tests)
  unaffected; `tools/security_sweep.py` clean.

### Decisions

- **JB100's own geometry is not resized.** Its real measured width
  (~6.2-6.6m) is used for collision math as-is; the user's stated ~3m
  reference is treated as an approximate target for placeholder content
  (the asteroids), not a mandate to edit a real hero asset's modeled
  proportions. Explicit user decision, 2026-08-10.
- **Collision avoidance is a pre-filter on Director's mark choices**,
  not a validated/rejected proposal and not a resolver-level hard
  error. If a location's own spawn marks (not just Director's move
  destinations) turn out unsafe at true scale, that's a Set
  Designer/location-layout concern, not something this mechanism
  retroactively audits or fixes.

## Not built / still open

- No general per-asset radius registry sweep -- only `prop_jb100_A` and
  the 5 asteroids have real size data. Extending this to every asset
  (reusing `tools/index_assets.py`'s bbox computation to auto-derive
  `radius_m` at registration time, rather than hand-specifying) would
  make the collision check meaningful project-wide instead of only
  where someone happened to add the numbers by hand.
  `tools/index_assets.py`'s own bbox output is already accurate enough
  to drive this -- not wired in yet.
  - **This session did not need it to trigger correctly** on
    asteroid_field, since the JB100/asteroid radii were hand-added as
    part of this exact fix -- but nothing today auto-populates
    `radius_m` for a newly-built or newly-registered asset the way
    `shot_scale` auto-classifies from `int_ext`.
  - The camera fix's own `classify_shot_scale()`, for comparison, *is*
    fully automatic for every future placeholder location (any `int_ext`
    Producer already threads through). The scale/collision fix is not
    yet at that same level of automatic coverage for other props.
- Collision avoidance only *filters marks* -- it doesn't reposition,
  nudge, or resize anything, and doesn't check moving-actor-vs-moving-
  actor collision (only mover-vs-static-obstacle).
- No formal write-up yet of the "check for a dedicated build script
  before rebuilding a placeholder location generically" lesson into an
  agent profile or standing constraint -- currently only documented
  here, in prose.
