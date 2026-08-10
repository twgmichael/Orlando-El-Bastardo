---
title: Screenplay Slugline Actor-Presence Gap
created: 2026-08-10T04:19:20-04:00
updated: 2026-08-10T04:28:11-04:00
doc_type: reference
production_area: pipeline
department: pipeline
status: active
canonical: false
wiki: true
wiki_group: Planning
---
# Screenplay Slugline Actor-Presence Gap

## Discovery

While reviewing the 2026-08-10 full-teaser re-run
(`scripts/pilot/Orlando-El-Bastardo-Episode-01-The-Pilot-teaser-scene.md`),
scene 6 (`## 6. INT. JOURNEYBLASTER - COCKPIT`) rendered without JB100
present, while scene 4 (`## 4. INT. JOURNEYBLASTER - COCKPIT` — the same
location) did.

Scene 4's action text:

> The JourneyBlaster dives, probe still attached.

Scene 6's full body text:

> Orlando checks the probe telemetry.
>
> **ORLANDO** Survey package intact. Mining company gets its data. I get
> paid. Everybody wins.
>
> **SHIP AI** External sensor array three does not win.
>
> **ORLANDO** Nobody likes a sore loser.

Scene 6 never says "JourneyBlaster" anywhere in its body — only
"Orlando," "Ship AI," and "the probe." Dramatically that's normal: two
characters already inside the ship have no reason to name it again.

## Root cause

`tools/producer.py`'s actor-presence check:

```python
def scene_action_text(scene):
    return " ".join(p for sec in scene["sections"] for p in sec["action"])


def present_actors(scene, cast):
    scene_text = scene_action_text(scene)
    speakers = {n.lower() for sec in scene["sections"]
                for n, _t in sec["dialogue"]}
    return [n for n in cast if n in speakers or names_in(scene_text, [n])]
```

`scene_action_text()` joins only each section's `action` paragraphs. It
never includes `scene["slugline"]`. The slugline is parsed elsewhere
purely to resolve `location_tag` (`INT. JOURNEYBLASTER - COCKPIT` →
`journeyblaster_cockpit`) — the fact that the slugline's own text
contains a cast-mapped name ("JOURNEYBLASTER") is discarded at that
point and never reaches `present_actors()`.

So: a cast member whose name appears only in the slugline, never
restated in dialogue or action text, is silently treated as absent from
the scene — and if that member is the vehicle/set itself, its mesh
never gets imported or placed for that shot.

## Why this generalizes

This is not specific to JourneyBlaster or to scene 6. Any scene whose
subject is *named by its own heading* rather than restated in prose is
affected — cockpit/interior scenes of a named vehicle are the most
likely recurring case (once inside, characters have no narrative reason
to keep naming the vehicle they're already in), but the same gap would
silently drop any cast-mapped name that only ever appears in a
slugline.

## Discussion: why body-text scanning was the wrong primary signal

The slugline is deterministic, authored, and unambiguous — it is
already the sole source of truth for `location_tag` resolution. Scanning
action-text prose for name mentions is a weaker, incomplete proxy: it
happens to work when a writer's prose restates the subject, and fails
silently (no error, no warning, just an actor quietly missing) when they
don't. The slugline should be treated as at least as authoritative as
body text for presence detection, not ignored by it.

## Proposed correction

Fold the slugline into the same text `present_actors()` already scans,
so any cast-mapped name in the heading is picked up by the existing
`names_in()` check — no new mechanism, no new data, minimal blast
radius:

```python
def scene_action_text(scene):
    return " ".join(
        [scene.get("slugline", "")]
        + [p for sec in scene["sections"] for p in sec["action"]]
    )
```

(Exact call site may differ slightly once implemented; the essential
change is including `scene["slugline"]` in the text `present_actors()`
scans, alongside the existing action-text/dialogue-speaker sources.)

### Scope and known limits of this fix

- **Fixes**: any scene whose slugline names a cast-mapped entity that
  isn't otherwise restated in dialogue or action text — the JourneyBlaster
  cockpit case exactly.
- **Does not fix**: a generic heading with no name at all (e.g. `INT.
  COCKPIT` with nothing identifying *whose* cockpit) — there is no text
  anywhere in that scene to detect. That is a real, separate limitation
  (an unnamed/implicit-continuity heading), not something a text scan of
  any kind can resolve without additional context (e.g. carrying forward
  the previous scene's vehicle).
- Low risk: `present_actors()`'s output only ever adds actors already in
  `cast` (`data/standins.json`) that are genuinely named somewhere in the
  scene; including the slugline cannot introduce false positives for
  names that aren't already registered cast members, and any location
  name that happens to share text with a cast entry is already the
  intended signal here, not incidental noise.

## Broader direction: slugline-first scene direction (2026-08-10)

Following the discussion above, the intended fix generalizes into a
larger principle for how the deterministic pipeline should read a
screenplay, not just a one-line patch to `present_actors()`. Recorded
here as direction, not yet designed in implementation detail or
scoped into phases — that is follow-up work.

### 1. Slugline is the primary, authoritative signal for location/set

Read the slugline first to resolve location/set. It is the author's
deliberate direction and will usually match the resolver map outright
(this is already how `location_tag` resolution works today — the
change is only that presence detection should defer to it the same
way). When the slugline does *not* resolve cleanly against known
locations, that is the trigger to fall back to scanning the scene's
body text for clues: a genuinely new location/set to register, or an
author typo/inconsistency to flag — not the default, first-pass
behavior it is today for presence detection.

### 2. Scene text drives composition, not just presence

Beyond "is this cast member present," the scene's action text carries
real spatial/compositional direction that is currently discarded
entirely. Example from this same script: sc3/sc5 place the JourneyBlaster
and the mining probe in the same asteroid-field location, but nothing
in the pipeline today reads "towing the probe" (sc5) or the probe's own
narrative role as *found and retrieved by* the ship (sc2: "Mechanical
clamps extend") as a instruction to place the probe *near* JB100 rather
than at an arbitrary default-prop mark. Today's mining-probe placement
(`data/resolver_map.json`'s `asteroid_field.default_props`, `at_mark`
fixed to the location's own `_exit` mark) is a static, scene-independent
default — it doesn't respond to what the scene text actually says is
happening between the ship and the probe.

### 3. Scene direction breaks down into interactions/motion cues

Further than static composition: action lines describing movement
("The JourneyBlaster dives," "It clears the field and coasts into open
space," "The JourneyBlaster breaks free of the debris cloud") describe
actual blocking — motion a real cue (`move`, `play_move_cue`) could
drive — not just a presence signal. Today this text is only mined for
the presence check and the LLM review's beat descriptions/prop
inventory; it is never broken down into the kind of from_mark/to_mark
or interaction cues `tools/motion_library.py`/`tools/oeb_blender/
cue_execution.py` already know how to execute for actors. Extending
that same breakdown to vehicles/props named in action text (an example
target: "JB100 flies into asteroid field" → a `move` cue with a
sensible from/to mark within `asteroid_field`) is the natural next
step once composition (item 2) exists to place things sensibly in the
first place.

### Relationship to existing systems

This direction touches, and would need to be reconciled with, several
systems already built this session rather than started from scratch:
`tools/screenplay_entity_resolution.py` (entity/candidate extraction
from prose, already used for vehicle-placeholder detection),
`tools/compose_screenplay_scene.py` (scene composition, built earlier
this session per section 6), and the cue vocabulary (`tools/
motion_library.py`, `tools/oeb_blender/cue_execution.py`,
`tools/export_blender.py`'s move-cue handling). None of these currently
read the slugline as a first-class signal or use action text for
inter-object spatial placement; this section records the gap between
what they do today and this direction, not a redesign of them.

## Status

Proposed 2026-08-10. Not implemented — this document records the
discussion and discovery only, per explicit instruction to take no other
action at this time. The broader slugline-first/composition/interaction
direction above is recorded as author intent for future scoping, not
yet broken into an implementation plan.
