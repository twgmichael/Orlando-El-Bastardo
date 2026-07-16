---
title: Rigging
created: 2026-07-06T19:37:01-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: standard
production_area: rigging
department: rigging
status: approved
canonical: true
canonical_for: rigging_standard
wiki: true
wiki_group: Standards
wiki_page: Rigging
wiki_order: 10
---
# Rigging & retargeting standard — `oeb_humanoid_v1`

DECIDED 2026-07-06 (human sign-off; closes OPEN-QUESTIONS #4). The canonical
character skeleton and clip conventions for all rigged OEB characters from
Phase 2 onward.

## 1. Canonical skeleton: `oeb_humanoid_v1`

The Unreal-mannequin-style skeleton as shipped by the Quaternius Universal
Base Characters / Universal Animation Library (CC0 — see docs/PROVENANCE.md).
Ground truth for the joint list and rest pose is the `A_TPose` clip inside
`assets/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb`.

65 joints (names verbatim — note `Head` is capitalized, everything else
lowercase; sides are `_l`/`_r` suffixes):

- Core: `root`, `pelvis`, `spine_01`, `spine_02`, `spine_03`, `neck_01`, `Head`
- Arms: `clavicle_l/r`, `upperarm_l/r`, `lowerarm_l/r`, `hand_l/r`
- Fingers (per hand): `thumb_01..03`, `index_01..03`, `middle_01..03`,
  `ring_01..03`, `pinky_01..03`, each chain ending in a `*_04_leaf` bone
  (thumb ends at `thumb_04_leaf`)
- Legs: `thigh_l/r`, `calf_l/r`, `foot_l/r`, `ball_l/r`, `ball_leaf_l/r`

Rules: never rename, never re-parent, never delete joints on a conforming
character. Extra NON-deforming attachment bones (props, hair — cf. the UBC
hairstyles rigged to `Head`) are allowed as leaf additions and must not
receive clip keyframes.

Why this skeleton: the UBC characters and the 43-clip UAL library already
share it (zero retargeting for our primary stack); Godot 4's retargeting
profile maps it cleanly; Mixamo/Rigify sources have well-known mappings onto
it.

## 2. Orientation, units, rest pose

- Meters; 1.0 scene unit = 1 m. Characters authored at real-world scale
  (~1.7 m unless a design doc says otherwise).
- Blender authoring space: character faces **+Y**, up is **+Z**, feet at
  z = 0, `root` bone at world origin at floor level. (glTF export/import
  handles the Y-up conversion; the rule is about authoring space.)
- Rest pose = the `A_TPose` clip's pose. Every conforming character must
  bind in this pose.

## 3. Side naming and bone maps

Canonical side convention is the `_l` / `_r` suffix exactly as in §1 — never
`Left*`, `.L`, or `mixamorig:` forms in pipeline assets. Foreign skeletons
are adapted via **bone-map data files** in `data/bone_maps/<source>.json`
(same philosophy as the camera grammar: code interprets, data defines):

```json
{ "schema_version": "1.0.0", "source": "mixamo",
  "map": { "mixamorig:Hips": "pelvis", "mixamorig:Spine": "spine_01" } }
```

A map covers every deforming bone of its source or names the omissions in an
`"unmapped"` list (unmapped source bones must carry no weights after
conversion). First maps to author when needed: `mixamo`, `rigify`,
`oeb_5bone` (the placeholder/legacy starter rig).

## 4. Clip conventions

- Canonical clip IDs stay as defined in `docs/BAR-SCENE.md` (logical-ID
  pattern `^[a-z][a-zA-Z0-9_]*$`); library-source names are remapped to
  canonical IDs at asset-build time and recorded in the character/clip
  asset's build script (e.g. UAL `Sitting_Idle_Loop` → `idle_seated_relaxed`).
- Clips are authored/imported **in-place**: no root translation in the clip;
  locomotion comes from object-level waypoint motion
  (`(frame, location, heading)` IR) applied by the exporters. Root-motion
  variants (UAL `_RM`) are reference-only, never pipeline assets.
- 24 fps timebase; loopable clips must be loop-clean (first pose == last
  pose); loop intent is declared by the AnimationCue `loop` flag, not baked
  repetition.
- A clip may key only `oeb_humanoid_v1` joints (attachment bones excluded).

## 5. Retargeting procedure (foreign clip → pipeline clip)

1. Import source clip; apply the source's bone map (`data/bone_maps/`).
2. Bake onto the `oeb_humanoid_v1` rest pose at 24 fps.
3. Strip root translation (in-place rule) unless the clip is a
   reference-only `_RM` keep-aside.
4. Rename to the canonical clip ID; export into the owning character/clip
   GLB (+ `.usdc` sibling).
5. **Acceptance gates (all machine-checkable):**
   (a) keyed-bone set ⊆ the §1 joint list;
   (b) first-frame pose within tolerance of `A_TPose` for locomotion/idle
       clips (loop-clean check for `*_Loop` sources);
   (c) feet-on-floor sanity render (one still at frame 1, reviewed);
   (d) `tools/validate_spec.py` passes on a spec referencing the clip
       (unknown_clip is the existing backstop).

## 6. Versioning

- Character assets declare their skeleton in `oeb.config.json` via a
  `"skeleton": "oeb_humanoid_v1"` field on the asset entry (additive config
  change; absent field = legacy/non-conforming, e.g. the salvaged
  `oeb_guy_characters.glb` on the 5-bone starter rig).
- Skeleton changes (added joints, changed hierarchy) bump to
  `oeb_humanoid_v2` — never mutate v1 in place. Clips and characters must
  declare the same skeleton version to be paired by the resolver (a future
  validator check once mixed skeletons actually coexist).

## Current state (2026-07-06)

- Conforming stack on disk, all CC0: UBC characters + UAL 43-clip library
  (shared skeleton, zero retargeting needed).
- Legacy `oeb_guy_characters.glb` remains on the 5-bone starter rig and in
  service for seated v0; it migrates to `oeb_humanoid_v1` when walking/v1
  staging is unlocked (a separate locked-decision change).
- The clip-ID remap for the bar scene (UAL → canonical) and the UBC-based
  hero/bartender v2 build are the next asset-track tasks.
