---
title: JourneyBlaster Multiplayer Sandbox Demo Discovery
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: discovery
production_area: interactive
department: production
status: proposed
canonical: true
canonical_for: journeyblaster_multiplayer_sandbox_demo_discovery
wiki: false
---
# JourneyBlaster Multiplayer Sandbox Demo Discovery

## Purpose

This note records the initial discussion about turning the existing
JourneyBlaster prototype foundation into a small multiplayer sandbox demo. It
is a side-quest concept, not an approved implementation phase, and no code or
project configuration was changed as part of this discovery.

## Recommended first playable scope

The most practical first version is a host-authoritative sandbox for two to
four players on a local network or through a direct Internet connection.

Players would:

- spawn in separate JB100 ships around Starbase 86;
- fly independently while seeing the other ships in the world;
- retain local cockpit camera, rotating-chair, control, and instrumentation
  behavior;
- see other players as contacts on the Senso-Globe;
- exchange synchronized FrapRay fire;
- eventually tow shared objects, damage asteroids, and fight host-controlled
  pirate flyers; and
- respawn or reset within a lightweight shared arena.

The initial demo would deliberately exclude accounts, public matchmaking,
persistent-universe state, progression, competitive anti-cheat, and large
player counts.

## Existing work that can be reused

The current prototype already provides much of the player-facing experience:

- the JB100 hero model and cockpit presentation;
- ship-local six-axis flight and smoothed controls;
- independent pilot-chair camera views;
- FrapRay and proton-torpedo weapons;
- projectile impacts, damage, asteroid breakup, and destruction effects;
- tractor-beam attachment and towing behavior;
- Starbase 86, pirate flyers, mining probe, and asteroid assets;
- fuzzy pirate flight and combat behavior;
- Senso-Globe contact presentation; and
- mission-state, failure, restart, and automated runtime-test patterns.

The principal challenge is therefore simulation architecture and network
quality rather than asset production.

## Required architectural changes

### Separate input, simulation, and presentation

The current JB100 controller assumes one local pilot. Multiplayer requires it
to be separated into:

1. local input collection;
2. authoritative shared ship simulation; and
3. local or remote visual presentation.

Cockpit camera movement and screen rendering should remain local. Ship
position, orientation, velocity, throttle, damage, weapon state, and towing
state must become shared simulation data.

### Host-authoritative simulation

For the first demo, one player should host the session and remain authoritative
for:

- ship physics outcomes;
- weapon firing validation and hits;
- damage and destruction;
- projectiles or authoritative hit results;
- tractor-beam acquisition and release;
- shared asteroid and probe motion;
- pirate AI; and
- respawning and arena resets.

Clients send control intentions to the host and receive authoritative world
updates. This is simpler and more consistent than allowing every client to
decide combat or physics outcomes independently.

### Network identity and ownership

Every replicated ship and interactive object needs a stable network identity.
The session must explicitly track which peer owns each pilot input stream while
the host owns final simulation state.

### Smooth remote flight

Raw transform replication would look jittery. Remote ships need interpolation,
and the locally piloted JB100 would benefit from modest client prediction and
authoritative correction so steering remains responsive under normal latency.

### Shared interactions

The following state must be synchronized consistently:

- transforms and velocities;
- throttle and thrust effectiveness;
- weapon firing and ammunition;
- projectile creation or validated hit events;
- hull and subsystem damage;
- asteroid breakup and fragment removal;
- tractor-beam target, tether distance, and release;
- pirate behavior and targets; and
- player destruction, disablement, respawn, and disconnect.

## Suggested development sequence

### Milestone 1 — Two-ship flight

- Create a separate multiplayer sandbox scene so Missions 001–003 remain
  intact.
- Add a minimal Host/Join interface with player name and connection status.
- Spawn two JB100 ships around Starbase 86.
- Replicate authoritative ship motion and interpolate the remote ship.
- Keep cockpit cameras and instrumentation local.

### Milestone 2 — Sensors and FrapRay combat

- Show remote players on the 1,000-meter Senso-Globe.
- Synchronize FrapRay firing and impacts.
- Make damage and disablement host-authoritative.
- Add safe spawn positions, friendly-fire rules, respawn, and arena reset.

This is the recommended first demonstrable multiplayer milestone: two JB100s
flying around Starbase 86, detecting each other, and exchanging synchronized
FrapRay fire.

### Milestone 3 — Shared sandbox systems

- Add proton torpedoes.
- Add synchronized asteroid damage, breakup, and vaporization.
- Add shared tractor-beam acquisition and towing.
- Add host-controlled pirate flyers and cooperative defense play.
- Add graceful disconnect and reconnect behavior.

### Later scalability work

If players are allowed to travel thousands of kilometers apart, the sandbox
will eventually need floating-origin or sector-shifting support. This is not
required for the first Starbase 86 arena.

## Effort assessment

A rough same-network proof of two ships moving together could be produced in
several focused days. A credible four-player demo with smooth flight,
synchronized combat and towing, shared AI, reconnect handling, visual polish,
and proportionate automated testing is more realistically three to five weeks
of focused development.

## Recommendation

If this side quest is approved, begin with a separate two-player Starbase 86
sandbox and prove responsive replicated JB100 flight before networking the
more complicated weapon, damage, towing, asteroid, or pirate systems. The
quality of that first shared flight experience should be the gate for further
multiplayer investment.
