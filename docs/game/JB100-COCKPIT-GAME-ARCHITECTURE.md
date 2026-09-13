---
title: JB100 Cockpit Game Architecture
created: 2026-09-12T00:00:00-04:00
updated: 2026-09-12T00:00:00-04:00
doc_type: discovery
production_area: interactive
department: production
status: accepted
canonical: true
canonical_for: journeyblaster_cockpit_game_architecture
wiki: false
---
# JB100 Cockpit Game Architecture

Decision status: **all recommendations accepted on 2026-09-12**.

Implementation status: **core architecture implemented on 2026-09-12**.
Missions 001–003 now launch through the shared game shell and cockpit, and a
cross-mission runtime guardrail verifies that each has exactly one JB100, one
cockpit, all three instrument screens, and active permanent ship systems.
The project launcher selects any current mission with `--mission=001`,
`--mission=002`, or `--mission=003`; Mission 003 remains the default.

## Goal

JourneyBlaster is a JB100 cockpit simulator to which missions can be added
without copying, rebuilding, or backporting the ship experience. Flight,
weapons, power, shields, sensors, cameras, controls, cockpit instruments, and
result presentation must improve once and appear in every mission.

A new mission supplies a world, objectives, contacts, special interactions,
and outcome rules. It does not build or copy the JB100 cockpit.

## Discovery

The three prototypes currently behave like separate mini-games:

- Mission 001 carries its older cockpit HUD in its generated mission scene.
- Mission 002 constructs another HUD inside its mission boot script.
- Mission 003 constructs the current three-screen cockpit inside its mission
  boot script.
- Weapon aiming and HUD updates are repeated across mission scripts.
- The shared JB100 controller contains flight, weapons, power, shields, mouse
  capture, and display behavior, but missions selectively enable and present
  those systems.
- Input responsibility is divided between the ship controller and individual
  mission scripts.
- Senso-Globe presentation is only partially shared. Each mission supplies and
  displays sensor information differently.
- Environment construction, weapon presentation, prompts, and mission result
  treatment have accumulated at different rates in each prototype.

This is why improvements made while developing Mission 003 now need to be
backported to Missions 001 and 002. Continued backporting would multiply with
every new mission and eventually make behavior inconsistent or unsafe to
change.

The shared mission-announcement overlay already demonstrates the correct
direction: one reusable component now supplies the same `GO`, `SUCCESS`, and
`FAILED` language to all missions.

## Accepted architecture

JourneyBlaster will use composition, not mission inheritance. Mission 001 and
Mission 002 will not inherit from Mission 003. All missions will run inside a
single persistent JB100 game shell.

```text
JourneyBlaster Game Shell
├── JB100 spacecraft
│   ├── flight controls
│   ├── power, shields, and weapons
│   ├── pilot-chair cameras
│   └── tow-beam system
├── JB100 cockpit interface
│   ├── left systems screen
│   ├── middle Senso-Globe
│   ├── right mission screen
│   ├── weapon and tool reticles
│   └── GO / SUCCESS / FAILED announcements
└── Mission Host
    └── Loaded mission
        ├── environment and assets
        ├── enemies and objectives
        ├── mission-specific interactions
        └── success and failure rules
```

## Permanent game-shell responsibilities

The game shell owns the parts of the experience that remain true because the
player is flying the JB100:

- the single JB100 player instance and its canonical model
- local-axis flight controls and smoothing
- mouse steering, capture, release, recentering, and focus behavior
- throttle presets, reverse thrust, all stop, and course lock
- rotating pilot-chair views and debug view
- FrapRay and proton-torpedo firing, charge, lock, ammunition, and effects
- the ship-effect exclusion bubble and shared weapon origins
- power generation, thrust availability, shield state, and weapon recharge
- collision consequences and shared ship damage behavior
- fullscreen preference and other persistent player settings
- the complete three-screen cockpit interface
- common weapon and contextual-tool reticles
- mission announcements and restart presentation
- common sensor rendering and contact classification
- centralized input routing

These systems must not be recreated by a mission.

## Cockpit interface responsibilities

Mission 003 is the accepted visual baseline for the reusable cockpit.

The left screen always reads shared JB100 state and presents:

- `PWR`
- `THR`
- `SHD`
- `WPN`
- `TPD`

The middle screen always hosts the Senso-Globe. The globe uses the JB100's
ship-relative coordinate transform, the correct forward indication, shared
range rules, faction colors, and contact lifecycle filtering.

The right screen is the generic mission screen. It presents:

- mission number and state
- current objective
- a bounded, clipped history of mission alerts

Station reports belong to Mission 003, but the screen itself belongs to the
cockpit. Mission 001 can publish probe and recovery messages; Mission 002 can
publish charge, deadline, and debris warnings; future missions publish their
own events through the same interface.

Weapon and tool reticles belong to the cockpit presentation layer. A mission
may request a specialized mode, such as Mission 002's blue charge-placement
circle, but it does not construct or position that reticle itself.

## Mission Host

The game shell contains a `MissionHost` that loads one selected mission scene.
The loaded mission provides:

- mission identity and title
- environment, lighting, backdrop, and world geometry
- mission-specific asset instances
- the JB100 starting transform
- sensor contacts and their classifications
- objectives and alert events
- enemies and mission AI
- special interaction rules
- success and failure criteria
- mission cleanup and restart state

The host supplies the loaded mission with references to shared services rather
than requiring the mission to search for or recreate them.

## Mission interface

Each mission will follow one small common lifecycle:

1. Load into the Mission Host.
2. Receive a mission context containing the JB100 and shared services.
3. Register its starting transform, contacts, objective, alerts, and optional
   contextual action.
4. Start immediately and request the shared blue `GO` announcement.
5. Publish state and alert changes as gameplay proceeds.
6. Signal success or failure to the game shell.
7. Preserve the mission's intended post-result play until restart or exit.
8. Cleanly unregister contacts and unload on restart or mission change.

The mission context should expose narrow services for:

- ship state
- weapons and tow-beam tools
- sensor contact registration
- objective and alert publication
- mission announcements
- contextual input actions
- success, failure, and restart

Signals and explicit service references are preferred over a global event bus.
This keeps dependencies visible and makes each mission testable in isolation.

## Input decision

Flight and cockpit controls are universal and will be mapped once through
named input actions. Missions cannot redefine them.

A mission may register a contextual action and its prompt. Examples include:

- download probe data
- take the probe in tow
- place an explosive pack
- detonate charges
- engage hyperspace

The centralized input router invokes the currently registered contextual
action. This preserves consistent controls while allowing missions to define
what an interaction means at a particular state.

## Sensor decision

The reusable Senso-Globe will consume a shared sensor-contact registry. A
mission registers contacts with identity, faction, active state, and optional
priority. Destruction, departure, or unloading removes a contact through the
same registry so sensor ghosts cannot survive mission state changes.

Mission scripts may determine whether an object is detectable, but they do not
draw the globe or transform coordinates for display.

## System configuration decision

Power, shields, thrust, weapons, and ammunition are permanent JB100 systems,
not Mission 003 features. They should exist in every mission even if a mission
does not actively threaten every system.

A mission profile may configure initial values, available equipment, damage
rules, or ammunition for a specific scenario. Configuration changes values;
it does not replace the underlying ship system or its cockpit presentation.

## Environment decision

Mission environments remain mission-specific. Planetfall, an asteroid field,
and Starbase 86 need different world assets and lighting.

Reusable environment helpers may provide common space features such as a
camera-relative starfield, visible system sun, or lightweight distant planet,
but each mission decides which helpers and assets it uses. Environment content
must not own cockpit UI or ship controls.

## Migration sequence

The accepted migration order minimizes visual and gameplay regressions:

1. Freeze the current Mission 003 cockpit as the reference presentation.
2. Extract that cockpit into a reusable scene without changing its appearance.
3. Connect the cockpit to shared JB100 and mission-state sources.
4. Move weapon reticles, contextual reticles, announcements, and Senso-Globe
   registration into the shared cockpit layer.
5. Introduce the JourneyBlaster game shell, Mission Host, mission context, and
   centralized input router.
6. Run Mission 003 inside the new shell first and verify behavior remains
   identical.
7. Convert Mission 002 by retaining its asteroid, placement, breakup, deadline,
   and debris logic while removing its JB100, HUD, and duplicated presentation.
8. Convert Mission 001 by retaining its probe, download, damage, towing, return,
   and hyperspace logic while removing its generated legacy cockpit structure.
9. Make the game shell the project's main scene and select missions through a
   mission catalog or launch parameter.
10. Delete obsolete duplicated HUD and weapon-presentation code only after all
    mission regression and visual checks pass.

This is an incremental refactor. Existing mission behavior remains the
reference during each conversion; the prototypes do not need to be rewritten
simultaneously.

## Guardrails and regression requirements

Architecture checks should enforce that:

- a mission scene cannot own another JB100 instance
- a mission scene cannot construct the permanent cockpit screens
- a mission cannot redefine universal flight or weapon controls
- every mission supplies a valid starting transform and objective
- every registered sensor contact is removed when destroyed, departed, or
  unloaded
- restarting resets the JB100, cockpit, contacts, contextual tools, and mission
  state without stale data
- changing a shared cockpit component is covered across every playable mission

Existing mission-specific regression suites remain. A new shared cockpit suite
will test the same JB100 presentation and controls against each mission loaded
through the Mission Host.

## Definition of success

The architecture is complete when:

- Missions 001, 002, and 003 run through the same game shell.
- All three display the Mission 003 cockpit baseline without copied HUD code.
- All three use the same flight, camera, weapon, power, shield, sensor, mouse,
  fullscreen, announcement, and restart systems.
- Mission scripts contain only mission world and mission-rule behavior.
- A new mission can be added by creating its scene, controller, profile, and
  tests without editing or cloning the JB100 cockpit.
- A future cockpit improvement appears in every mission from one change.

This structure restores the original product goal: one evolving JB100 cockpit
simulator with an expandable library of missions.
