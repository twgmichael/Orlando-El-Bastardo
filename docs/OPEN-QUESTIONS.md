# Open questions

Unresolved design questions carried from the research phase. Resolve as they block
work; record the answer here and reflect it in SCHEMA.md / BAR-SCENE.md.

1. ~~Seated vs walking start?~~ **ANSWERED 2026-07-04: seated-only v0.** Hero
   starts seated at `hero_barstool_A`; `walk_to_stool`/`sit_barstool` stay in
   the library for v1. No locomotion/root motion in v0.
2. ~~Dialogue timing auto vs explicit?~~ **ANSWERED 2026-07-04: explicit.**
   `DialogueCue` requires `start_time` + `duration`. A resolver-side estimator
   may later FILL the field pre-validation, but the schema always requires it.
3. ~~Camera grammar storage?~~ **ANSWERED 2026-07-04: JSON data.**
   `data/camera_grammar.json`, validated by `schemas/camera-grammar.schema.json`;
   code interprets, data defines.
4. ~~Animation naming convention and retargeting standard?~~ **ANSWERED
   2026-07-06: `oeb_humanoid_v1`.** UE-mannequin skeleton exactly as shipped
   by the Quaternius UBC/UAL CC0 stack (65 joints, `A_TPose` rest);
   canonical clip IDs stay per BAR-SCENE.md with source-name remaps at
   asset-build time; clips are in-place (root motion = waypoint IR); foreign
   skeletons adapt via `data/bone_maps/*.json`. Full spec: docs/RIGGING.md.
5. ~~LLM output boundary?~~ **ANSWERED 2026-07-04: SceneIntent only.** The LLM
   never emits asset/clip IDs; the deterministic resolver maps intent to
   approved assets.
6. Preferred lipsync strategy for v1: none, coarse mouth states, or
   phoneme/viseme mapping? (Does not block v1 schemas — `DialogueCue` carries
   no viseme fields; adding them later is a minor-version schema bump.)
