# JourneyBlaster Godot Runtime

Current milestone: **Demo Prototype V4** (`demo-prototype-v4`), declared
complete on 2026-09-08.

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
godot --path interactive/journeyblaster
```

Open `interactive/journeyblaster/project.godot` in Godot after synchronization
to inspect the Mission 001 cockpit boot scene.

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
