# Progress — 2026-07-05 — Animated preview (end-to-end motion render test)

Session goal (set by the human): prove the process end-to-end by rendering an
animated preview — the hero walks into the bar and sits at the stool — using
the Phase 2A placeholders. Explicitly scoped as a process test, not
entertainment: no rigging, no action-verb scripts, straight object motion in
the horizontal plane allowed.

## Delivered

- **`tools/render_anim_preview.py`** — headless Blender animated-preview
  renderer. Imports the placeholder GLB, strips all imported animation data
  (determinism), keys the `char_hero_v1` armature *object* through a waypoint
  list of `(frame, location, heading)`, renders an EEVEE PNG sequence through
  one grammar camera, encodes to H.264 MP4, and deletes the frames. Same CLI
  conventions as `render_preview.py` (args after `--`; `--glb`, `--camera`,
  `--output`, `--width/--height`).
- **`renders/previews/anim_hero_walk_sit.mp4`** — first pass: entry mark →
  stool approach → settle onto seat. 96 frames, 4 s, 960×540 @ 24 fps.
- **`renders/previews/anim_hero_walk_turn_sit.mp4`** — extended path per
  follow-up request: walk halfway → turn to face the bar → ¾-second pause →
  continue to the stool → sit. 144 frames, 6 s. Waypoints gained a heading
  component (Z-rotation, 0° = facing the bar) to make the turn read.
- Both clips visually verified by extracting frames at the key beats with
  ffmpeg and inspecting them (start / mid-walk / pause-at-bar / seated).

## Discoveries (environment + technique)

1. **This Blender 5.1.2 build has no FFMPEG output format at all.** The
   `file_format` enum offers image formats only — direct video render is
   impossible. No system ffmpeg either. Resolution: `pip install
   imageio-ffmpeg` into `.venv` (bundles a static arm64 ffmpeg binary) and
   encode the PNG sequence in a subprocess. This affects **every** future
   video render in the pipeline; recorded in project memory and here.
2. **Imported GLB animation must be cleared before authoring motion.** The
   placeholder GLB carries 12 NLA-exported actions; leaving them in place
   makes renders non-deterministic relative to authored keys. The script
   clears `animation_data` on all objects and removes all actions on import.
3. **Seat height is derivable from placeholder geometry.** Stool top =
   centre 0.38 + (unit-cylinder depth 1.0 × scale_z 0.75)/2 = 0.755; hero
   body bottom sits 0.01 above its armature origin → armature z = 0.745 when
   seated. Hard-coded for now; a resolver should compute this from the asset.
4. **The turn reads even on an unrigged capsule** because the placeholder
   body is elliptical in cross-section (0.28 m × 0.21 m). Heading keys are
   applied on top of whatever static rotation the glTF import leaves on the
   armature object (`rotation_mode` forced to `'XYZ'`, base euler preserved).
5. **The entry mark naturally enters frame.** `hero_entry_A` (−3.5, −3.0)
   sits just outside `cam_establishing_wide`'s 35 mm frustum, so the walk-in
   genuinely enters the shot — a happy property of the Phase 2A layout worth
   preserving when real assets replace placeholders.

## Discussion + recommendations

- **Waypoint list as an intermediate representation.** The
  `(frame, location, heading)` waypoint schedule that emerged here looks like
  a natural IR between SceneIntent verbs ("walk to", "sit") and Blender
  keyframes. Recommend considering it explicitly when designing the Phase 3
  resolver output / Phase 4 Blender-exporter input, rather than inventing a
  different motion representation from scratch.
- **"Horizontal-only" has one necessary exception:** the sit itself needs a
  small vertical translate to land the body on the seat. Any future motion
  grammar needs verbs that change elevation (sit, stand, lean).
- **Next work: Phase 3 (resolver + validator).** Nothing blocks it. Phase 2
  (real assets) remains gated on human asset selection and can run in
  parallel.
- **Tracker reconciliation** (applied 2026-07-05 alongside this doc): the
  optional animated-preview item is done in its object-motion form (the
  NLA-driven variant — placeholder keyed actions playing back — remains a
  separate optional item); four of the six open questions were decided
  2026-07-04 and are now checked off in PROJECT-TODO.md.

## Decisions this session

- Animated previews render as PNG sequence → bundled-ffmpeg encode (forced by
  discovery #1; not a preference).
- `imageio-ffmpeg` 0.6.0 added to `.venv` as the project's encode dependency.
- Object-level motion (no rig, no actions) is acceptable for process tests;
  clip filenames under `renders/previews/` describe the motion
  (`anim_hero_walk_sit`, `anim_hero_walk_turn_sit`).

## Environment notes

- Internal disk keeps shrinking; figures tracked in
  `docs/local/MACHINE-NOTES.md` (local only). Storage-plan reclaim steps
  still not executed.
- Renders are cheap at this fidelity: 96–144 frames at 960×540 EEVEE render
  and encode in roughly a minute; clips are 65–92 KB.
