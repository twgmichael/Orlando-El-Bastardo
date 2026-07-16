---
title: Bar Scene
created: 2026-07-03T21:44:09-04:00
updated: 2026-07-16T10:13:39-04:00
doc_type: design_record
production_area: sets
department: art
status: active
canonical: true
canonical_for: bar_scene_integration_target
wiki: true
wiki_group: Design
wiki_page: Bar-Scene
wiki_order: 30
---
# First integration target — "Hero in a bar chatting with a bartender"

Chosen because it exercises two-character dialogue, set loading, camera grammar,
basic animation clip switching, dialogue timing + audio binding, and prop
placement — while avoiding crowds, complex pathfinding, and advanced physics.

## v0 constraints

- 1 bar interior set
- 2 characters
- 1 counter zone
- 2–4 cameras
- 6–10 reusable animations
- 6–12 lines of dialogue
- No crowds
- No advanced procedural behavior

## Suggested asset groups

**Set:** `set_bar_small_A`, `variant_night`

**Characters:** `char_hero_v1`, `char_bartender_v1`

**Props:** `prop_bar_counter_A`, `prop_stool_A`, `prop_glass_tumbler_A`, `prop_bottle_generic_A`

**Marks:** `hero_entry_A`, `hero_barstool_A`, `bartender_idle_A`, `bartender_backbar_A`

**Hero animations:** `walk_to_stool`, `sit_barstool`, `idle_seated_relaxed`, `talk_neutral_seated`, `nod_small`, `look_down_then_up`

**Bartender animations:** `idle_standing_relaxed`, `wipe_glass_loop`, `talk_friendly_standing`, `pour_drink_short`, `lean_forward_counter`, `shrug_small`

**Camera grammar:** `cam_establishing_wide`, `cam_two_shot_bar`, `cam_close_hero`, `cam_close_bartender`

The bar-scene `SceneSpec` will serve as the reference fixture for exporter testing.
