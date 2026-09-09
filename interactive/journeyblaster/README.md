# JourneyBlaster Godot Runtime

Current milestone: **Mission 003 Starbase Defense Prototype V1**
(`mission-003-starbase-defense-prototype-v1`), declared complete on
2026-09-09.

This nested Godot 4 project is the first OEB interactive runtime. Canonical
assets remain under the Studio's `assets/` tree. Runtime copies and wrapper
scenes are generated and intentionally ignored.

From the repository root:

```bash
blender --background --python tools/build_asteroid_placeholders.py -- \
  --output-dir interactive/journeyblaster/source_assets/asteroids \
  --skip-resolver-update
.venv/bin/python tools/validate_interactive.py
.venv/bin/python tools/sync_interactive_assets.py
godot --headless --path interactive/journeyblaster --import
godot --headless --path interactive/journeyblaster \
  --script res://tests/phase1_boot_test.gd
godot --headless --path interactive/journeyblaster \
  --script res://tests/prototype_runtime_test.gd
godot --headless --path interactive/journeyblaster \
  --script res://tests/probe_damage_runtime_test.gd
godot --headless --path interactive/journeyblaster \
  --script res://tests/flight_controls_runtime_test.gd
godot --headless --path interactive/journeyblaster \
  --script res://tests/mission_002_runtime_test.gd
godot --headless --path interactive/journeyblaster \
  --script res://tests/mission_003_runtime_test.gd
godot --path interactive/journeyblaster
```

Open `interactive/journeyblaster/project.godot` in Godot after synchronization
to play Mission 003. Mission 001 remains available at
`res://generated/scenes/missions/mission_001_retrieve_mining_probe.tscn`, and
Mission 002 remains available at `res://scenes/mission_002_planetfall.tscn`.

Run the explicit import after every clean sync. Sync replaces the generated
tree deterministically, including Godot's adjacent `.import` sidecars.

The current playable prototype includes flight, independent 360-degree pilot
chair views, hull-mounted Senso-Globe sensing, probe identification and data
download, physical towing, return validation, and hyperspace completion.

Controls are shown in the HUD. The primary keyboard bindings are `W/S`
throttle, `A/D` or left/right arrows to turn, up/down arrows to pitch, `Q/E`
roll, `Z/C` strafe, `R/F` lift, `Space` FrapRay, `T` proton torpedo, `G`
interact, `X` dead stop, `1`–`5` chair views, right-mouse free chair rotation,
`L` course lock, `Tab` aiming HUD, `H`
hyperspace, and `F3` external debug view. Left-mouse drag and gamepad flight
paths are also available.

Keyboard and arrow steering eases into and out of full deflection. Pitch, yaw,
and roll are always relative to the JB100 itself, including after the ship
rolls upside down. Left-mouse drag uses direct pixel sensitivity with a short
smoothing filter; releasing and clicking again starts cleanly without stale
motion or a slower second drag.

Combat controls are `Space` for paired FrapRay blasts and `T` for a proton
torpedo. FrapRay bolts are orange plasma energy. Proton torpedoes have a blue
core and a fading white vapor trail. Large asteroids break into moving
fragments; weapon hits vaporize the fragments into disappearing dust clouds.
The aiming HUD projects the actual two cannon paths and center torpedo path;
the FrapRay paths use red dots and the center target uses a small red X. `Tab`
toggles them together. The tow beam extends and latches over 1.8 seconds, then
holds the captured distance while the probe trails naturally as the JB100
pivots and changes course. A centered 3.25 m ship-effect bubble hides tow and
weapon visuals inside the hull; they become visible 0.10 m beyond its surface.

The mining probe now carries mission consequences. Colliding with it damages
its data port and permanently prevents the download, but the damaged probe can
still be taken in tow and recovered. Hitting it with either weapon destroys it
in an explosion and fails the mission, but the JB100 remains freely flyable in
the current scene. Press `R` when ready to restart.

The asteroid contracts prefer their registered canonical assets. When the
external `assets/placeholders` library is not mounted, the documented builder
command creates equivalent deterministic runtime sources under this project.

## Mission 002 controls and loop

Mission 002 starts with `Enter`. Intercept the falling primary asteroid and
close to placement range, then press `/` or `?` to switch from FrapRay to the
reverse tow beam. Left-mouse drag always steers the JB100; the restored blue
circle shows where the ship-forward tow beam will strike. Aim it over a blue
torus and press `Space` to shoot the beam and attach a charge. Press `/` or `?`
again to switch back to FrapRay; `T` continues to launch proton torpedoes.

The three-minute charge-placement window begins when `Enter` starts the
mission; time spent reading the briefing does not consume it.

After placing all three charges, retreat to the displayed safe distance and
press `G` to detonate. Chase the resulting major fragments with `Space`
FrapRay and `T` proton torpedoes. Major fragments break into small debris;
small debris vaporizes into dust on the next hit. One major fragment breaks up
naturally during the chase. Destroy every dangerous return before it crosses
the atmospheric boundary. A separate one-minute planetfall clock begins when
the charges detonate; the breakup animation is included in that minute.
Failure preserves free flight and `R` restarts.

## Mission 003 controls and loop

Mission 003 starts with `Enter`, with the JB100 inside Starbase 86's open
hangar and facing the launch exit. Use the established mouse-drag or keyboard
flight controls to launch, `Space` for paired FrapRay fire, `T` for proton
torpedoes, and `Tab` for the actual weapon-path HUD.

Three Ellipso pirate flyers attack nine hidden station damage locations. Their
objectives, target order, and health are not exposed. Three FrapRay shots drive
a flyer into a committed retreat, seven destroy it, and one torpedo plus three
FrapRay shots also destroys it. Starbase defensive bolts can hit the pirates
or the JB100; each hit on the JB100 removes 10 of its 100 thrust points.

Destroy all three flyers or drive each beyond 5,000 m to complete the mission.
The open hangar is safe from deliberate pirate pursuit. Losing all nine
station targets or all JB100 thrust fails the mission without ending the
current battle; `R` restarts.
