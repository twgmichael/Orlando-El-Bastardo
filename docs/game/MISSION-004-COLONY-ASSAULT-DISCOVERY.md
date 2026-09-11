---
title: JourneyBlaster Mission 004 Colony Assault Discovery
created: 2026-09-09T00:00:00-04:00
updated: 2026-09-09T00:00:00-04:00
doc_type: discovery
production_area: interactive
department: production
status: proposed
canonical: true
canonical_for: journeyblaster_mission_004_colony_assault_discovery
wiki: false
---
# Mission 004 — Colony Assault Discovery

## Mission concept

Mission 004 begins with the JB100 in orbit around a planet. The player flies
the hero craft directly into the atmosphere, descends toward a small colony,
and engages pirate flyers over its buildings, roads, landmarks, city spaces,
and surrounding countryside.

The experience must remain continuous. There is no cutscene, loading screen,
or interruption of player control between orbital flight, atmospheric entry,
surface approach, and combat.

## Core experience promise

> Approach from orbit, enter the atmosphere manually, locate the colony
> through the Senso-Globe, emerge beneath the clouds during an active pirate
> assault, and fight continuously over the colony and countryside.

The seamless orbit-to-surface transition is the central technical and
experiential challenge. Existing JB100 flight, cockpit views, instrumentation,
sensors, weapons, damage, pirate AI, and mission-state work provide the
foundation for the encounter.

## Recommended seamless-transition strategy

The demo should use a hybrid continuous transition instead of attempting a
literal full-scale, fully detailed planet.

1. Begin beside a conventional planet sphere in orbital space.
2. Establish a designated atmospheric-entry corridor leading toward the
   colony region.
3. Gradually introduce atmosphere scattering, heating, vibration, drag,
   gravity, cloud layers, and reduced visibility during descent.
4. Use the cloud and haze layers to conceal surface-region streaming and the
   transition from planetary coordinates to a floating local reference frame.
5. Preserve the JB100's apparent position, heading, velocity, and control state
   throughout the transition.
6. Emerge beneath the clouds over the authored colony and surface-combat area.

This is a continuous controlled flight sequence, not a disguised cutscene.
The player retains control throughout.

## Flight regimes

The runtime should blend continuously through three flight regimes.

### Orbital flight

- No gravity-relative control assumptions.
- Existing six-axis spaceflight behavior.
- Large-scale planet and orbital presentation.

### Atmospheric entry

- Progressive gravity and aerodynamic drag.
- Reentry heating, vibration, turbulence, and atmospheric audio/visual cues.
- Increasing control resistance without reversing established ship-relative
  control orientation.
- Layered atmosphere, haze, and clouds that communicate altitude and conceal
  level-of-detail transitions.

### Surface flight

- Ship-relative controls remain consistent.
- Gravity, altitude, terrain collision, and atmospheric handling become active.
- Low-altitude flight communicates speed through terrain, roads, buildings,
  landmarks, and nearby combatants.

## Surface-region scope

The first demo should author a focused combat region approximately 10–15
kilometers across rather than a fully detailed planet.

The region can include:

- a compact colony center assembled from modular buildings;
- landing pads, power structures, communications equipment, and defensive
  positions;
- roads connecting recognizable landmarks and outlying facilities;
- farms, hills, valleys, rocks, and sparse vegetation;
- city blocks and open countryside supporting different combat patterns;
- low-detail terrain rings and atmospheric haze hiding the detailed area's
  outer boundary; and
- recycled or streamed countryside tiles if the player continues beyond the
  authored region.

## Planet and terrain presentation

The orbital planet, atmosphere, and surface terrain should be treated as
layers of one visual system:

- a lower-detail curved planet at orbital distance;
- an atmosphere shell or scattering treatment;
- intermediate cloud and haze layers;
- a streamed high-detail terrain patch around the colony;
- progressively simpler distant terrain rings; and
- impostors or procedural repetition beyond the primary play area.

Level of detail, atmospheric concealment, and careful scale compression should
provide the impression of a planetary descent without requiring a planet-sized
rendering or physics workload.

## Pirate surface-combat behavior

Pirate flyers require an atmospheric and terrain-aware extension of the
existing fuzzy combat AI. Surface flyers should:

- bank through turns;
- maintain a safe minimum altitude;
- avoid terrain, buildings, and landmarks;
- use roads and landmarks as navigation references;
- make committed attack passes rather than circle targets while firing;
- break formation and evade when threatened;
- divide attention between the JB100 and colony objectives; and
- transition visibly between attack, egress, reposition, and pursuit states.

Some flyers can pursue the JB100 while others attack changing colony targets,
building on the role-assignment groundwork established for Mission 003.

## Technical foundation required

### Hierarchical reference frames

Orbital and surface play operate at very different scales. The mission needs a
planetary frame for orbit and a floating local frame near the colony. The
transition must preserve apparent motion while shifting the simulation origin
to avoid precision problems.

### Streaming and level of detail

Terrain, colony structures, landmarks, vegetation, and surface effects should
stream or change detail by distance. Expensive collision and AI navigation
should remain active only near the player and combat area.

### Continuous state transfer

The following state must remain continuous across atmospheric entry:

- player heading and orientation;
- velocity and throttle;
- cockpit camera and pilot-chair view;
- weapon and ship-system state;
- mission and sensor state; and
- the apparent position of the planet, horizon, colony, and other contacts.

### Instrumentation additions

The cockpit screens will eventually need atmospheric information such as
altitude, descent rate, heat, atmospheric density, terrain proximity, and
surface contacts. True weapon-targeting information should remain in the
forward targeting display.

## Principal risks

- Coordinate precision across orbital and surface scales.
- A visually convincing planet-to-terrain scale transition.
- Terrain and colony streaming without visible pauses.
- Convincing atmosphere, cloud, horizon, and reentry presentation.
- Ground collision and terrain-aware flight behavior.
- Pirate navigation around buildings and uneven terrain.
- Maintaining performance while presenting a readable colony battle.
- Preventing the authored surface region's boundary from becoming obvious.

## Recommended first vertical slice

The first implementation should prove one complete, controlled route:

1. Start in orbit with the colony bearing available through sensors.
2. Manually align with and enter the atmospheric corridor.
3. Fly through a progressive reentry and cloud sequence without losing control.
4. Transition invisibly to the floating surface reference frame.
5. Emerge over a compact colony with roads and surrounding terrain.
6. Acquire pirate flyers and enter low-altitude combat.

The first slice does not need a full planet, unrestricted global navigation,
or a return-to-orbit sequence. Quality of the continuous descent and first
surface engagement should determine whether the system expands further.

## Discovery recommendation

Mission 004 is achievable by stretching the existing prototype foundation,
provided the team treats seamless scale transition, atmosphere, streaming,
and floating-origin support as the mission's primary engineering work. The
recommended approach is one carefully authored surface region connected to
orbit through a continuous atmospheric corridor, with clouds and level of
detail carrying the illusion of planetary scale.
