---
title: JourneyBlaster Mission 003 Starbase Defense Prototype V1
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: milestone
production_area: interactive
department: production
status: complete
canonical: true
canonical_for: journeyblaster_mission_003_prototype_v1
wiki: false
---
# Mission 003 — Starbase Defense Prototype V1

Declared complete on 2026-09-09. This milestone proves the playable Starbase
86 defense loop from an interior JB100 hangar launch through pirate retreat,
destruction, station loss, and player disablement.

## Implemented experience

- The JB100 v38 starts inside Starbase 86 v1.1's real open hangar, facing its
  exit and the distant planet-and-moon vista.
- `Enter` starts the attack while all established cockpit, chair, mouse-drag,
  keyboard, FrapRay, proton-torpedo, and aiming-HUD controls remain intact.
- Three accepted Ellipso pirate flyers receive unique randomized subsystem
  objectives and randomized target order every run.
- Nine unmarked starbase targets cover shields, weapons, and hangars without
  revealing their health to the player.
- Fuzzy movement blends objective pursuit, attack orbiting, JB100 evasion,
  starbase clearance, flyer separation, and individual variation.
- The first flyer to finish its assigned category attacks the JB100. Other
  completed flyers pile onto remaining station targets; a replacement takes
  over if the JB100 attacker is neutralized.
- Starbase defensive weapons fire slowly and imperfectly at pirate flyers.
  Their projectiles can also strike the JB100 but cannot damage the station.
- Each paired FrapRay volley counts as one shot. Three shots start a committed
  retreat, seven destroy a flyer, and one torpedo plus three FrapRay shots also
  destroys it.
- Retreat remains pursuable below JB100 maximum thrust. A flyer counts as
  driven off at 5,000 m and jumps at 6,000 m.
- Each station target has three points. Disabled shields amplify subsequent
  weapon/hangar damage, and damaged station weapons fire less effectively.
- Friendly and hostile hits remove 10 of the JB100's 100 points and reduce
  thrust proportionally until the ship is dead in space.
- Losing all nine station targets or all JB100 thrust fails the mission while
  preserving the current scene. The safe hangar causes flyers to ignore the
  player, and `R` restarts after success or failure.
- Destroying or driving off all three flyers completes the mission, with
  success winning any simultaneous demo-state tie.

## Asset decision

The connected production drive contains designated Starbase 86, Ventradi
pirate-flyer, and generic pirate-vehicle placeholders. Prototype V1 uses the
higher-quality local hero Starbase 86, JB100, and Ellipso flyer assets; the
drive assets remain validated fallbacks.

