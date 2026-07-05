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
4. What is the first exact animation naming convention and retargeting standard?
   (Clip *names* are de-facto set by BAR-SCENE.md; the retargeting standard is
   still open — bites at Phase 2 real assets.)
5. ~~LLM output boundary?~~ **ANSWERED 2026-07-04: SceneIntent only.** The LLM
   never emits asset/clip IDs; the deterministic resolver maps intent to
   approved assets.
6. Preferred lipsync strategy for v1: none, coarse mouth states, or
   phoneme/viseme mapping? (Does not block v1 schemas — `DialogueCue` carries
   no viseme fields; adding them later is a minor-version schema bump.)
