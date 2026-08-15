---
title: E_DUPLICATE_CHARACTER — Correction Record (Archived)
created: 2026-08-13T22:00:00-04:00
updated: 2026-08-15T00:00:00-04:00
archived: 2026-08-15
doc_type: decision_log
production_area: pipeline
department: production
status: archived
canonical: false
canonical_for: e_duplicate_character_bug
wiki: false
wiki_group: Journal
---
# E_DUPLICATE_CHARACTER — Correction Record

Found live during the 2026-08-13 full 81-scene pilot re-triage. This
document records an attempted fix that turned out to be insufficient,
why, and the corrected direction — so whoever implements the real fix
doesn't re-walk the same dead end.

## The bug

Any scene with **two or more background-tier speaking roles** failed
at the resolve stage:

```
RESOLVE-ERROR E_DUPLICATE_CHARACTER: character_id 'placeholder_character_background_A'
resolved for both 'first_guard' and 'second_guard'
```

Confirmed in `pilot_sc37` (`voice` + `computer`) and `pilot_sc69`
(`first_guard` + `second_guard`); suspected in `pilot_sc78`
(`voice` + `ship ai`).

`tools/resolve_intent.py`'s R3 rule (`seen_char_ids`) rejects two
actors in one scene resolving to the identical `character_id` — a
real, correct constraint in general (two different named actors
should never accidentally share one asset identity). The violation
came from `tools/casting_director.py`: **every** background role was
registered under the exact same literal `character_id`
(`BACKGROUND_CHARACTER_ID = "placeholder_character_background_A"`),
not just the same underlying built asset. The plan doc
(`docs/planning/CASTING-DIRECTOR-PLAN.md`) always intended these to be
independently placeable — *"sharing the asset is not the same as
sharing a position, and two background characters can appear in the
same scene at once"* — the implementation just never delivered on
that.

## Attempted fix (insufficient — do not repeat)

Gave every background role its own registry-distinct `character_id`
(`placeholder_character_background_A__<role_tag>`), all pointing at
the one already-built shared `.glb`:

- `tools/placeholder_blueprint.py`: `register_placeholder_asset()`
  gained an optional `node` param (default `None` → falls back to
  `canonical_id`, so every other caller is unaffected).
- `tools/casting_director.py`: new `ensure_background_role_asset()`
  builds the shared mesh once (unchanged), then registers a per-role
  `canonical_id` in `oeb.config.json` with `node=BACKGROUND_CHARACTER_ID`
  pointing at the one real built object.
- Real data patched: 14 background roles that had been cast under the
  old bare shared ID (`dock_official`, `station_announcer`, `waitress`,
  `voice`, `security_officer`, `deranti_secretary`, `computer`,
  `male_technician`, `technician`, `orion_pilot`,
  `communications_officer`, `first_guard`, `second_guard`,
  `controller`) were removed from `data/resolver_map.json`/
  `data/standins.json` so they'd re-cast fresh.

This resolved the `E_DUPLICATE_CHARACTER` check itself — verified live
(two roles in one scene now get distinct `character_id`s). **But it
does not fix the scene.** Re-running `pilot_sc37` moved the failure
one stage later, to `validate`:

```
"binding_unresolved": actor 'computer' blender_object
'placeholder_character_background_A__computer' not found in GLB library nodes
```

Root cause of *that*: `tools/resolve_intent.py` sets
`target_bindings.blender_object = role_entry["character_id"]`
directly (line ~563) — it never consults `oeb.config.json`'s `node`
field. And `tools/validate_spec.py`'s `_build_library()` builds its
known-node set by **actually parsing the referenced .glb files**, not
by reading the registry. The shared `.glb` only ever contains one real
object, literally named `placeholder_character_background_A` — the
synthetic per-role `character_id` strings were never real objects
inside it. So the registry-level fix just relocated the failure; it
never made the scene assemble correctly.

**Worse: even fixing the binding lookup (making `blender_object`
resolve through the registry's `node` field) would not be correct
either.** `tools/export_blender.py`'s actor-placement loop
(~line 242-262) does a single `bpy.data.objects.get(bo_name)` lookup
and moves that one object. Two actors sharing one `blender_object`
name would silently fetch the *same* object twice and move it twice —
no error, no crash, just a wrong scene (the second actor's placement
silently clobbers the first's). A validator-satisfying fix without an
export-time fix would trade a loud failure for a silent wrong render.

## The corrected direction (not yet implemented)

`tools/jb100_hyberspace_swarm_draft.py` already has the right pattern
for this, proven in production for the hyperspace fleet effect:
**Collection Instancing**, not object duplication.

```python
bi_collection = bpy.data.collections.new("BI_ASSET")   # source geometry, moved in once
for obj in bi_objects:
    ...
    bi_collection.objects.link(obj)

def interceptor(name, keys, scale=1.0):
    inst = bpy.data.objects.new(name, None)             # lightweight Empty, no geometry of its own
    scene.collection.objects.link(inst)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = bi_collection             # shares the source geometry
```

Each instance is a lightweight Empty with its own transform, sharing
one collection's actual geometry — Blender's native instancing
mechanism, render-correct in both Cycles and EEVEE, and the same
technique needed regardless for the stated future requirement (scenes
with hundreds of ships / thousands of actors — instancing cost scales
with unique-asset count, not instance count).

**Plan for `tools/export_blender.py`'s placement loop:**
1. Import each unique asset's geometry into a dedicated collection
   once (matching `bi_collection`/`bi_source.hide_render`/
   `hide_viewport` above), not once per actor.
2. For every actor — whether 1 or 1,000 share that asset — create a
   per-actor Empty instance (`instance_type = "COLLECTION"`), placed
   at its own `spawn_mark`, instead of moving one shared object.

Once export always creates a fresh per-actor instance, it stops
mattering whether many actors share one `character_id` — which means
the registry-level per-role `character_id` fix above becomes
unnecessary for *this* reason (harmless to keep for other bookkeeping
purposes, but not required). `resolve_intent.py`'s R3 duplicate check
would also need to allow duplicate `character_id`s within a scene once
export genuinely supports multi-instance placement of one asset.

## Status as of 2026-08-13

- Registry-level per-role `character_id` fix: **implemented, verified,
  live in `data/resolver_map.json`/`data/standins.json`.** Not
  reverted — harmless to leave in place under the corrected plan.
- `resolve_intent.py` binding resolution / `export_blender.py`
  collection-instancing change: **not implemented.** This is the real
  fix; scenes 37/69/78 remain blocked until it lands.
