# Asset And Location Orientation Standard

Date: 2026-07-16

## Context

During prompt-to-render testing, standalone asset builds such as spaceships, stools, chairs, beds, airplanes, and rockets exposed a recurring weakness: the system can build recognizable primitive forms, but the meaning of directional language is not yet disciplined.

The pipeline now preserves more structured local LLM output through `scene_plan` / `repaired_scene_plan` objects, but the builder still needs a consistent orientation contract so words such as front, rear, left, right, top, bottom, mounted, attached, and on surface map to predictable 3D positions.

We also identified scene-tech-debt in asset builds. Standalone assets do not need a floor, wall, room, or environment shell. Locations and sets may need spatial shells, but assets should be rendered as isolated objects in an asset-local coordinate frame.

## Discovery

The local LLM can produce useful object structure:

- object labels, such as body, wing, engine, window, stool leg, backrest
- categories, such as structure, machine, seating, screen, surface
- counts, such as two wings or four legs
- placement hints, such as front, center, around
- mounting and relationship hints, such as mounted_on or aligned_with

However, those hints only become reliable if the renderer and review tools share one standard interpretation of orientation.

We observed that one camera angle is not enough for asset review. A single action/preview camera can make a shape look plausible while hiding problems in top, side, rear, bottom, or left/right structure. Multi-view renders are only meaningful after we define a canonical local axis standard.

## Research Summary

Industry practice is not one universal axis convention. Instead, the common methodology is:

- define an asset-local coordinate frame
- define origin and pivot rules
- define forward, right, left, up, and down axes
- use bounding-box conventions for width, depth/length, and height
- store named attachment points or sockets when needed
- render canonical front, rear, side, top, bottom, and action views
- store the orientation contract as metadata with the asset

Different tools use different world-up or forward conventions. Blender commonly uses Z-up. Game engines and interchange formats vary. The important thing for OEB is to pick one convention and enforce it consistently through LLM prompts, builder placement logic, manifests, tests, and review renders.

## Decision

OEB asset-local orientation standard:

```text
+X = front
-X = rear/back
-Y = left
+Y = right
+Z = up
-Z = down
```

This applies to standalone assets unless a specific format export requires transform adaptation.

## Asset Origin Rules

Initial standard:

- Props: origin at center-bottom of the object unless impractical.
- Furniture: origin at center-bottom footprint.
- Vehicles and ships: origin on centerline at body midpoint, with Z positioned at neutral/resting height.
- Characters: origin at center-bottom between feet.
- Locations and sets: origin at location center, not necessarily tied to a single asset footprint.

These rules are allowed to become more specific by asset family, but the axis convention should not drift.

## Location And Set Orientation

Locations and sets use the same global semantic directions:

```text
+X = front / entrance-facing direction when applicable
-X = rear / back
-Y = left
+Y = right
+Z = up
-Z = down
```

Unlike standalone assets, locations and sets may include floor, wall, ceiling, terrain, room shells, environmental props, and spatial boundaries when requested or implied by the location type.

## Camera Views

Canonical asset review cameras should be derived from the local axes:

- action: current three-quarter orthographic preview
- front: camera looks along `-X` toward the origin
- rear: camera looks along `+X` toward the origin
- left: camera looks along `+Y` toward the origin
- right: camera looks along `-Y` toward the origin
- top: camera looks along `-Z` toward the origin
- bottom: camera looks along `+Z` toward the origin

The action view remains useful for quick recognition. The canonical axis views are needed for validation.

## Prompting Recommendation

The LLM intake prompt should explicitly state:

```text
All standalone assets use this local coordinate frame:
+X front, -X rear/back, -Y left, +Y right, +Z up, -Z down.
Use placement and orientation language relative to this frame.
For standalone assets, describe only the asset and its parts.
Do not add floors, walls, rooms, base planes, environment props, or scene shells unless the user explicitly asks for a location or set.
```

For locations and sets, the prompt may allow floors, walls, ceilings, roads, terrain, rooms, and environment shells.

## Builder Recommendation

The primitive builder should stop relying on fuzzy string placement and instead centralize direction mapping:

```text
front -> +X
rear/back -> -X
left -> -Y
right -> +Y
top/up -> +Z
bottom/down -> -Z
center -> origin / local center
around -> distributed around relevant target or origin
```

Relationship interpretation should be layered on top of this:

- `mounted_on`
- `attached_to`
- `inside`
- `around`
- `aligned_with`
- `left_of`
- `right_of`
- `in_front_of`
- `behind`

The builder should prefer structured graph objects and relationships over flattened component strings.

## Manifest Recommendation

Every asset build manifest should include orientation metadata:

```json
{
  "orientation_standard": {
    "front_axis": "+X",
    "rear_axis": "-X",
    "left_axis": "-Y",
    "right_axis": "+Y",
    "up_axis": "+Z",
    "down_axis": "-Z",
    "origin_policy": "asset_family_default"
  }
}
```

Locations and sets should include the same axis metadata, with an origin policy appropriate to a location center.

## Testing Recommendation

Add focused tests for:

- LLM prompts include the OEB orientation standard.
- Standalone asset prompts prohibit scene shells.
- Location prompts allow environment shells.
- Builder maps front/rear/left/right/top/bottom to the correct axes.
- Manifests include orientation metadata.
- Multi-view camera names and camera vectors match the standard.

## Final Recommendation

Proceed in this order:

1. Document and adopt the axis standard.
2. Add the standard to LLM prompts.
3. Add builder placement helpers that enforce axis mapping.
4. Add manifest orientation metadata.
5. Add front/rear/left/right/top/bottom/action render outputs.
6. Use multi-view renders to evaluate whether object parts are spatially coherent.

The key decision is that OEB assets are not built in a generic scene. They are built in an asset-local coordinate sandbox with a clear orientation contract. Locations and sets can have environmental shells; standalone assets should not.
