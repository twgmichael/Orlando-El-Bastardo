# Flight Animation — Techniques and Patterns

Patterns discovered while building `tmp_jb100_space_action.py` and
`tmp_jb100_barrel_roll.py`. Not yet wired into the production pipeline.

---

## Hero-in-rolling-ship (no-parenting, world-space tracking)

### Problem

The JB100 barrel roll uses `ship.rotation_mode = 'QUATERNION'` and
`ship.rotation_quaternion` changes every frame. Parenting the hero to the
ship works in the viewport but historically caused `matrix_parent_inverse`
offsets when the ship was not at identity transform at parenting time.
The confirmed safe approach is **no parenting + manual world-space keyframes**.

### Implementation

```python
from mathutils import Vector, Quaternion, Euler

COCKPIT_LOCAL = Vector((0.0, -0.4, 0.23))   # cockpit in ship local space

# Hero's resting quaternion in ship local space.
# Capture base_rot from import, add π around Z so hero faces -Y (nose).
hero.rotation_mode = 'XYZ'
base_rot = tuple(hero.rotation_euler)
hero_local_quat = Euler(
    (base_rot[0], base_rot[1], base_rot[2] + math.pi), 'XYZ'
).to_quaternion()
hero.rotation_mode = 'QUATERNION'

# Inside the per-frame loop (where final_quat is the ship's quaternion):
cockpit_world            = pos + final_quat.to_matrix() @ COCKPIT_LOCAL
hero.location            = cockpit_world
hero.rotation_quaternion = final_quat @ hero_local_quat
hero.keyframe_insert(data_path="location",            frame=frame)
hero.keyframe_insert(data_path="rotation_quaternion", frame=frame)
```

### Notes

- `final_quat.to_matrix() @ COCKPIT_LOCAL` rotates the local cockpit offset
  into world space. During a barrel roll the cockpit traces a small circle
  (radius ≈ 0.23 units) around the flight axis — negligible at normal camera
  distances but physically correct.
- `final_quat @ hero_local_quat` composes the ship's world rotation with the
  hero's resting local orientation. The hero rolls with the ship exactly.
- Bone keyframes (arm controls) are separate pose-mode passes and are
  unaffected by this object-level transform.
- The `base_rot + π` rule assumes the hero asset faces +Y at import. If a
  different character asset has a different default facing, adjust the Z offset.

---

## Two-phase flight choreography (approach + warp boost)

### Pattern

Splits a flight path into a normal quadratic-acceleration phase and a sudden
speed boost phase for the "appears out of nowhere / zooms off" effect.

```python
PHASE1_DUR = 9.0
DIST_1     = (NORMAL_END - START).length
SPEED_AT_9 = 2.0 * DIST_1 / PHASE1_DUR   # instantaneous speed at phase boundary

def ship_pos(t):
    if t <= PHASE1_DUR:
        return START + travel_dir * (DIST_1 * (t / PHASE1_DUR) ** 2)
    else:
        return NORMAL_END + travel_dir * (SPEED_AT_9 * 4.0 * (t - PHASE1_DUR))
```

### Tuning levers

| Parameter | Effect |
|---|---|
| `START` distance from camera | How long ship is invisible at start; further = longer build-up |
| `PHASE1_DUR` | When the boost fires; earlier = more tail, later = less |
| Speed multiplier (4.0×) | Exit drama; 4× at `SPEED_AT_9` ≈ 110 units in 1 s for this path |
| `DIST_1` | Total approach distance; set to 2× the original path for "twice as far" |

The roll angle uses the full `DURATION` independently of the phase split:
`roll_angle = 2π × t / DURATION` — the roll completes at t=10 s regardless.

---

## Animated tracking camera (sweep-hold-track)

### Pattern

Camera moves from a starting position to a resting position over the first
half of the shot, then holds position but continues tracking the subject.

```python
CAM_START = Vector((-10.5, -9.5, 5.5))
CAM_END   = Vector((-29.35, -32.9, 8.75))
CAM_MID   = CAM_START.lerp(CAM_END, 0.5)   # resting point at t=5 s

def cam_ease(t):
    return t * t * (3.0 - 2.0 * t)         # smoothstep

# Inside per-frame loop:
t_cam        = min(t / 5.0, 1.0)           # 0→1 over first 5 s, then frozen
cam.location = CAM_START.lerp(CAM_MID, cam_ease(t_cam))
cam_look     = cockpit_world - cam.location
cam.rotation_euler = cam_look.to_track_quat('-Z', 'Y').to_euler()
cam.keyframe_insert(data_path="location",       frame=frame)
cam.keyframe_insert(data_path="rotation_euler", frame=frame)
```

### Notes

- `to_track_quat('-Z', 'Y')` points the camera's -Z axis (its look direction)
  at the target. Y is the up axis. No roll is applied — add
  `cam.rotation_euler.rotate_axis('Z', angle)` after if a Dutch angle is wanted.
- Setting rotation keyframes at every frame (same cadence as position) is
  required for correct tracking. Sparse rotation keyframes produce Bezier
  interpolation that does not follow the cockpit's circular roll path.
- `CAM_MID = CAM_START.lerp(CAM_END, 0.5)` puts the camera at the "over the
  right shoulder" position. The full `CAM_END` (100%) was never needed —
  50% gave the correct framing for this shot.

---

## Coordinate conventions (flight scripts)

| Symbol | Value | Meaning |
|---|---|---|
| Ship nose | −Y local | `to_track_quat('-Y', 'Z')` aligns nose to travel direction |
| `COCKPIT_LOCAL` | `(0, −0.4, 0.23)` | Hero seat in JB100 local space |
| `SHIP_RIGHT` | `(0.665, −0.746, 0)` | +X local in world (pre-computed for this path) |
| `SHIP_UP` | `≈(0.054, 0.048, 0.997)` | +Z local in world (nearly world Z for this path) |

These values are specific to the `START=(64,57,−3) → END=(−28,−25,6)` travel
direction. Recompute from `travel_dir.to_track_quat('-Y','Z').to_matrix()` for
any new flight path.
