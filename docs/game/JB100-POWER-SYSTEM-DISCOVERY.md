---
title: JB100 Shared Power System Discovery
created: 2026-09-11T00:00:00-04:00
updated: 2026-09-11T00:00:00-04:00
doc_type: discovery
production_area: interactive
department: production
status: active
canonical: true
canonical_for: journeyblaster_shared_power_system
wiki: false
---
# JB100 Shared Power System Discovery

Implementation status: **implemented in Mission 003 on 2026-09-11**.

## Purpose

The cockpit already displays PWR, THR, SHD, and WPN. The prototype needs a
simple relationship between those readings so PWR represents a real shared
ship resource instead of a static value. The design should communicate that
the JB100's generator supports propulsion, shields, and weapons without
introducing a power-allocation interface or a detailed engineering simulation.

## Discussion and discovery

The initial idea treated the generator as producing a fixed amount of power
while thrust, shield recovery, and weapon recovery created competing loads.
This established the desired relationship, but its first explanation used
“coasting” as an operating state.

The current flight model does not use coasting as a concept. The revised model
therefore treats the absolute commanded throttle as a continuous generator
load. Lower thrust allows PWR to recover faster; higher thrust slows recovery.
When shields and weapons are also recovering, their combined demand can
temporarily exceed generator output and reduce PWR.

PWR then feeds back into the three consuming systems. Low PWR reduces
available thrust and slows shield and weapon recovery. This creates a visible,
understandable connection among all four cockpit bars without requiring the
pilot to operate additional controls.

## Confirmed formula

PWR is a percentage clamped between 0 and 100.

Each second:

`PWR change = 4 - (3 × absolute throttle) - shield load - weapon load`

Loads are deliberately binary for the demo:

- shield load is `2` while SHD is below 100% and recharging
- weapon load is `2` while WPN is below 100% and recharging
- a fully restored system contributes no recharge load
- forward and reverse thrust use the absolute throttle value

Representative outcomes:

| Ship state | PWR change |
| --- | ---: |
| 100% thrust; SHD and WPN full | +1%/s |
| 50% thrust; SHD and WPN full | +2.5%/s |
| 100% thrust; SHD and WPN recharging | -3%/s |
| 50% thrust; SHD and WPN recharging | -1.5%/s |

## System effectiveness

Calculate one shared power factor:

`power factor = 0.5 + (0.5 × PWR / 100)`

Apply that factor to:

- maximum available forward and reverse thrust
- shield recharge speed
- FrapRay weapon-power recharge speed

At 100% PWR, all affected systems operate at full effectiveness. At 50% PWR,
they operate at 75%. At 0% PWR, they retain 50% emergency capability. The
emergency floor prevents a depleted generator reserve from creating a
self-locking state in which the player cannot move or recover.

## Interaction with existing combat rules

Weapon firing and shield impacts continue to change their existing WPN and SHD
reserves. They do not also subtract an immediate arbitrary amount from PWR.
Their power cost is represented by the sustained generator load required to
restore those reserves. This avoids charging the player twice for the same
event and keeps the cockpit readings easy to interpret.

For the current Mission 003 rules:

- a FrapRay volley reduces WPN and creates weapon-recharge load
- damage reduces SHD and creates shield-recharge load
- using more thrust slows PWR recovery while either system is restoring
- falling PWR progressively slows thrust, shield recovery, and weapon recovery
- the existing zero-SHD mission-failure rule remains separate from PWR

## Prototype presentation

No new HUD element is required. The existing left cockpit display provides all
necessary feedback:

- PWR shows the shared reserve
- THR shows effective available thrust after the PWR factor
- SHD shows current shield strength
- WPN shows current FrapRay reserve

The changing rates of the four bars should demonstrate the system. Numerical
load breakdowns, warning dialogs, and allocation sliders are unnecessary for
the demo.

## Explicit non-goals

- no coasting state or new momentum simulation
- no manual subsystem power allocation
- no reactor temperature, fuel, batteries, or individual power buses
- no shutdown of life support or cockpit instrumentation
- no immediate PWR penalty in addition to SHD or WPN recharge costs
- no permanent loss of generator capacity in the current demo

## Tuning note

The recharge loads were increased from `1` to `2` after playtesting showed that
the original one-percent-per-second combined drain was hidden by the integer
cockpit display and ended as soon as either reserve recovered. The constants
`4`, `3`, `2`, `2`, and the 50% emergency floor remain deliberately simple and
may be tuned further, but the shared formula and its relationships should stay
intact unless the prototype becomes unclear or produces an unrecoverable state.
