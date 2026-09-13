# JourneyBlaster Godot Runtime

Current milestone: **Mission 003 Starbase Defense Prototype V4**
(`mission-003-prototype-v4`), declared complete on
2026-09-09.

Every playable mission opens with a large blue `GO` announcement for three
seconds. Meeting the mission criteria displays persistent green `SUCCESS`;
failing displays persistent red `FAILED`. Announcements do not disable the
mission's established post-result controls.

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
godot --headless --path interactive/journeyblaster \
  --script res://tests/shared_cockpit_architecture_test.gd
godot --path interactive/journeyblaster
```

The project launcher starts Mission 003 by default. Select another mission from
the command line with `godot --path interactive/journeyblaster -- --mission=001`
or `--mission=002`. Every selection loads the same shell-owned JB100 and cockpit
around that mission's world and rules.

Run the explicit import after every clean sync. Sync replaces the generated
tree deterministically, including Godot's adjacent `.import` sidecars.

The current playable prototype includes flight, independent 360-degree pilot
chair views, hull-mounted Senso-Globe sensing, probe identification and data
download, physical towing, return validation, and hyperspace completion.

Controls are shown in the HUD. The primary keyboard bindings are `W/S`
variable throttle, backtick (`` ` ``) fixed 25-percent reverse thrust, `1`–`5`
fixed 10/30/50/80/100-percent forward thrust, `A/D` or
left/right arrows to turn, up/down arrows to pitch, `Q/E` roll, `Z/C` strafe,
`R/F` lift, `G` interact, `X` recenter mouse flight, `Tab` all stop, `Esc`
release mouse, `Control-Command-F` fullscreen, `-`/`+` chair-view cycling, middle-mouse free
chair rotation, `L` course lock, `\` aiming HUD, `H` hyperspace, and `F3`
external debug view. The JB100 continuously steers toward
an internal virtual stick from relative mouse movement with no button held.
The system cursor remains captured inside the game window. Left click fires a
paired FrapRay volley. Hold right mouse for three seconds to build and acquire a
target, then release to launch the proton torpedo. Gamepad flight paths are
also available.

Keyboard and arrow steering eases into and out of full deflection. Pitch, yaw,
and roll are always relative to the JB100 itself, including after the ship
rolls upside down. Mouse steering uses a bounded 180-pixel virtual stick, a 6%
dead zone, a 2.2 response exponent, and automatic spring return for precise
aiming without losing turn authority.
Pressing `X` warps the pointer to the exact screen center and immediately
clears residual mouse steering, leaving the JB100 pointed straight along its
current heading. Startup, window exit, and focus loss also force the virtual
stick to neutral so stale steering can never remain latched. When released,
the overlay reads `CLICK TO RESUME FLIGHT`; the next click recaptures the mouse
without firing. The macOS-standard `Control-Command-F` shortcut toggles display
mode with no visible HUD button, and the preference persists between sessions.

FrapRay power starts at 100 percent, each paired volley costs 10 percent, and
the reserve recharges at two percent per second. Proton torpedoes start at
five and count down as they launch. While a torpedo builds and acquires, the
center red X turns blue and its circular charge indicator fills for three
seconds; a full charge remains held until right mouse is released. Acquired
torpedoes steer themselves toward their target at 260 m/s and pursue long
enough that pirate flyers cannot escape by speed alone. FrapRay
bolts are orange plasma energy. Proton torpedoes have a blue
core and a fading white vapor trail. Large asteroids break into moving
fragments; weapon hits vaporize the fragments into disappearing dust clouds.
The aiming HUD projects the actual two cannon paths and center torpedo path;
the FrapRay paths use red dots and the center target uses a small red X. `\`
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

Mission 002 begins immediately. Intercept the falling primary asteroid and
close to placement range, then press `/` or `?` to switch from FrapRay to the
reverse tow beam. Mouse position always steers the JB100; the restored blue
circle shows where the ship-forward tow beam will strike. Aim it over a blue
torus and press `Space` to shoot the beam and attach a charge. Press `/` or `?`
again to switch back to FrapRay; `T` continues to launch proton torpedoes.
Each placed charge is the canonical one-meter explosive-pack Blender asset;
its alternating warning beacons animate once the pack attaches to the surface.

The three-minute charge-placement window begins as soon as the mission loads.

After placing all three charges, retreat to the displayed safe distance and
press `G` to detonate. Chase the resulting major fragments with `Space`
FrapRay and `T` proton torpedoes. Major fragments break into small debris;
small debris vaporizes into dust on the next hit. One major fragment breaks up
naturally during the chase. Destroy every dangerous return before it crosses
the atmospheric boundary. A separate one-minute planetfall clock begins when
the charges detonate; the breakup animation is included in that minute.
Failure preserves free flight and `R` restarts.

## Mission 003 controls and loop

Mission 003 begins immediately, with the JB100 inside Starbase 86's open
hangar and facing the launch exit. Use the established mouse-follow or keyboard
flight controls to launch, click left for paired FrapRay fire, hold right mouse
to launch a proton torpedo, and use `\` for the actual weapon-path HUD.

Three Ellipso pirate flyers attack nine hidden station damage locations. Their
objectives, target order, and health are not exposed. Six individual FrapRay
bolt hits drive a flyer into a committed retreat; twelve bolt hits, one torpedo
plus six bolt hits, or two torpedoes destroy it. Starbase defensive bolts can hit
the pirates or the JB100.

Exactly one pirate attacks the JB100 while at least one other remains on
station attack. Each pirate carries three fore/aft torpedoes, launches only
within 300 m after alignment, and gains terminal guidance inside 100 m. The
JB100's torpedoes require a three-second continuous load/lock cycle. The same
target must remain in range and in the aiming view throughout; either loss
resets immediately. Releasing
without a completed live lock neither fires nor spends a torpedo.

The JB100 begins with 100-percent shields. Station and pirate plasma hits remove
10 percent, pirate torpedoes remove 25 percent, and collisions with a flyer or
Starbase 86 remove 50 percent. Shields recharge at two percent per second, the
same rate as FrapRay power. Reaching zero shields fails the mission while
preserving free flight; the left cockpit screen reports the live SHD value.

PWR is a shared 0–100 generator reserve. It changes each second by `4`, minus
`3 × absolute throttle`, minus `2` each while shields or weapons are recovering.
Its power factor ranges from 50% at empty to 100% at full and scales available
thrust plus SHD and WPN recharge rates. The Senso-Globe uses X for left/right,
Z for up/down, and +Y for forward; its amber arrow and contacts share that
ship-relative transform. Destroyed pirates disappear from its returns
immediately even while their effect nodes finish cleaning up.

The right cockpit screen reports live shield, weapon, and hangar damage plus
pirate retreats and destruction. The Senso-Globe shows pirate flyers in red
and Starbase 86 and other friendly contacts in blue.

Destroy all three flyers or drive each beyond 5,000 m to complete the mission.
The open hangar is safe from deliberate pirate pursuit. Losing all nine
station targets or all JB100 shields fails the mission without ending the
current scene; surviving pirates disengage and circle Starbase 86 while the
pilot remains free to fly or observe. A large red `FAILED` notice appears in
the center of the viewing area, and `R` restarts.
