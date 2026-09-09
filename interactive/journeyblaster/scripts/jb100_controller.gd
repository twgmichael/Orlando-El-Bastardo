extends CharacterBody3D

signal impact(speed_mps: float, collider: Object)
signal weapon_fired(weapon_kind: String)

const WeaponProjectile = preload("res://scripts/weapon_projectile.gd")

@export var maximum_forward_speed_mps := 92.0
@export var maximum_reverse_speed_mps := 18.0
@export var throttle_response_per_second := 0.72
@export var velocity_response_per_second := 1.8
@export var lateral_speed_mps := 24.0
@export var pitch_rate_degrees := 54.0
@export var yaw_rate_degrees := 48.0
@export var roll_rate_degrees := 72.0
@export var steering_response_per_second := 7.5
@export var mouse_aim_sensitivity_degrees_per_pixel := 0.13
@export var mouse_aim_smoothing_per_second := 20.0
@export var frapray_cooldown_s := 0.18
@export var torpedo_cooldown_s := 0.9
@export var proton_torpedo_capacity := 8

var throttle := 0.0
var controls_enabled := true
var course_lock := false
var collision_count := 0
var last_impact_speed_mps := 0.0
var mouse_flight_active := false
var mouse_flight_suppressed := false
var frapray_fire_suppressed := false
var mouse_flight_delta := Vector2.ZERO
var mouse_rotation_step := Vector2.ZERO
var pitch_input_smoothed := 0.0
var yaw_input_smoothed := 0.0
var roll_input_smoothed := 0.0
var frapray_cooldown_remaining := 0.0
var torpedo_cooldown_remaining := 0.0
var proton_torpedoes_remaining := 8
var frapray_shots_fired := 0
var proton_torpedoes_fired := 0

@onready var frapray_left := get_node_or_null("frap_hardpoint_left") as Node3D
@onready var frapray_right := get_node_or_null("frap_hardpoint_right") as Node3D
@onready var torpedo_launcher := get_node_or_null("torpedo_launcher") as Node3D
@onready var effect_exclusion_center := (
    get_node_or_null("effect_exclusion_center") as Node3D
)


func _ready() -> void:
    add_to_group("player_ship")
    proton_torpedoes_remaining = proton_torpedo_capacity


func _physics_process(delta: float) -> void:
    frapray_cooldown_remaining = maxf(0.0, frapray_cooldown_remaining - delta)
    torpedo_cooldown_remaining = maxf(0.0, torpedo_cooldown_remaining - delta)
    if not controls_enabled:
        mouse_flight_delta = Vector2.ZERO
        return

    var throttle_input := clampf(
        _key_axis(KEY_S, KEY_W) - _joy_axis(JOY_AXIS_LEFT_Y),
        -1.0,
        1.0
    )
    throttle = clampf(
        throttle + throttle_input * throttle_response_per_second * delta,
        -0.25,
        1.0
    )
    if not course_lock:
        var pitch_target := clampf(
            _key_axis(KEY_DOWN, KEY_UP)
            - _joy_axis(JOY_AXIS_RIGHT_Y),
            -1.0,
            1.0
        )
        var yaw_target := clampf(
            _key_axis(KEY_D, KEY_A)
            + _key_axis(KEY_RIGHT, KEY_LEFT)
            - _joy_axis(JOY_AXIS_LEFT_X),
            -1.0,
            1.0
        )
        var roll_target := clampf(
            _key_axis(KEY_E, KEY_Q) + _joy_axis(JOY_AXIS_RIGHT_X),
            -1.0,
            1.0
        )
        pitch_input_smoothed = _smooth_axis(
            pitch_input_smoothed, pitch_target, delta
        )
        yaw_input_smoothed = _smooth_axis(yaw_input_smoothed, yaw_target, delta)
        roll_input_smoothed = _smooth_axis(roll_input_smoothed, roll_target, delta)
        _apply_ship_rotation(
            deg_to_rad(pitch_rate_degrees) * pitch_input_smoothed * delta,
            deg_to_rad(yaw_rate_degrees) * yaw_input_smoothed * delta,
            deg_to_rad(roll_rate_degrees) * roll_input_smoothed * delta
        )
        var mouse_rotation := _consume_mouse_rotation(delta)
        _apply_ship_rotation(mouse_rotation.y, mouse_rotation.x, 0.0)
    else:
        pitch_input_smoothed = _smooth_axis(pitch_input_smoothed, 0.0, delta)
        yaw_input_smoothed = _smooth_axis(yaw_input_smoothed, 0.0, delta)
        roll_input_smoothed = _smooth_axis(roll_input_smoothed, 0.0, delta)
        mouse_rotation_step = Vector2.ZERO
        mouse_flight_delta = Vector2.ZERO

    var strafe_input := _key_axis(KEY_C, KEY_Z)
    var lift_input := clampf(
        _key_axis(KEY_F, KEY_R)
        + _joy_axis(JOY_AXIS_TRIGGER_RIGHT)
        - _joy_axis(JOY_AXIS_TRIGGER_LEFT),
        -1.0,
        1.0
    )
    var forward_speed := (
        throttle * maximum_forward_speed_mps
        if throttle >= 0.0
        else throttle * maximum_reverse_speed_mps * 4.0
    )
    var desired_velocity := (
        -global_transform.basis.z * forward_speed
        + global_transform.basis.x * strafe_input * lateral_speed_mps
        + global_transform.basis.y * lift_input * lateral_speed_mps
    )
    velocity = velocity.lerp(
        desired_velocity,
        clampf(velocity_response_per_second * delta, 0.0, 1.0)
    )

    var speed_before_move := velocity.length()
    move_and_slide()
    if get_slide_collision_count() > 0:
        var collision := get_slide_collision(0)
        collision_count += 1
        last_impact_speed_mps = speed_before_move
        velocity *= 0.32
        throttle *= 0.55
        impact.emit(speed_before_move, collision.get_collider())
    mouse_flight_delta = Vector2.ZERO


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_L:
                course_lock = not course_lock
            KEY_BACKSPACE:
                dead_stop()
            KEY_X:
                dead_stop()
            KEY_SPACE:
                fire_frapray()
            KEY_T:
                fire_proton_torpedo()
    elif (
        event is InputEventMouseButton
        and event.button_index == MOUSE_BUTTON_LEFT
        and not mouse_flight_suppressed
    ):
        _set_mouse_flight_active(event.pressed)
    elif (
        event is InputEventMouseMotion
        and mouse_flight_active
        and not mouse_flight_suppressed
    ):
        mouse_flight_delta += event.relative
    elif event is InputEventJoypadButton and event.pressed:
        if event.button_index == JOY_BUTTON_B:
            course_lock = not course_lock
        elif event.button_index == JOY_BUTTON_BACK:
            throttle = 0.0
        elif event.button_index == JOY_BUTTON_X:
            fire_frapray()
        elif event.button_index == JOY_BUTTON_RIGHT_STICK:
            fire_proton_torpedo()


func _smooth_axis(current: float, target: float, delta: float) -> float:
    return move_toward(
        current,
        target,
        steering_response_per_second * delta
    )


func _consume_mouse_rotation(delta: float) -> Vector2:
    var target_rotation := Vector2.ZERO
    if mouse_flight_active:
        var pixels := mouse_flight_delta.limit_length(96.0)
        target_rotation = -pixels * deg_to_rad(
            mouse_aim_sensitivity_degrees_per_pixel
        )
    var smoothing_weight := 1.0 - exp(
        -mouse_aim_smoothing_per_second * delta
    )
    mouse_rotation_step = mouse_rotation_step.lerp(
        target_rotation,
        smoothing_weight
    )
    mouse_flight_delta = Vector2.ZERO
    return mouse_rotation_step


func _apply_ship_rotation(
    pitch_radians: float,
    yaw_radians: float,
    roll_radians: float
) -> void:
    # Every flight axis is ship-local. Rolling inverted therefore changes the
    # world-space direction of "up" and "left" without changing their meaning
    # to the pilot.
    rotate_object_local(Vector3.RIGHT, pitch_radians)
    rotate_object_local(Vector3.UP, yaw_radians)
    rotate_object_local(Vector3.BACK, roll_radians)
    transform.basis = transform.basis.orthonormalized()


func _set_mouse_flight_active(active: bool, update_pointer_mode := true) -> void:
    mouse_flight_active = active
    mouse_flight_delta = Vector2.ZERO
    mouse_rotation_step = Vector2.ZERO
    if update_pointer_mode:
        Input.mouse_mode = (
            Input.MOUSE_MODE_CAPTURED
            if active
            else Input.MOUSE_MODE_VISIBLE
        )


func set_mouse_flight_suppressed(suppressed: bool) -> void:
    mouse_flight_suppressed = suppressed
    if suppressed:
        _set_mouse_flight_active(false)


func set_frapray_fire_suppressed(suppressed: bool) -> void:
    frapray_fire_suppressed = suppressed


func fire_frapray() -> bool:
    if (
        not controls_enabled
        or frapray_fire_suppressed
        or frapray_cooldown_remaining > 0.0
    ):
        return false
    if frapray_left == null or frapray_right == null:
        return false
    frapray_cooldown_remaining = frapray_cooldown_s
    var hardpoints := [frapray_left, frapray_right]
    for hardpoint: Node3D in hardpoints:
        _spawn_projectile("frapray", hardpoint, 245.0, 0.8)
    frapray_shots_fired += 1
    weapon_fired.emit("frapray")
    return true


func fire_proton_torpedo() -> bool:
    if (
        not controls_enabled
        or torpedo_cooldown_remaining > 0.0
        or proton_torpedoes_remaining <= 0
        or torpedo_launcher == null
    ):
        return false
    torpedo_cooldown_remaining = torpedo_cooldown_s
    proton_torpedoes_remaining -= 1
    _spawn_projectile("proton_torpedo", torpedo_launcher, 138.0, 3.2)
    proton_torpedoes_fired += 1
    weapon_fired.emit("proton_torpedo")
    return true


func _spawn_projectile(
    kind: String,
    hardpoint: Node3D,
    speed_mps: float,
    hit_damage: float
) -> void:
    var projectile := WeaponProjectile.new()
    var projectile_parent := get_parent() as Node3D
    var global_direction := -global_basis.z.normalized()
    var local_direction := (
        projectile_parent.global_basis.inverse() * global_direction
    ).normalized()
    var safe_origin := effect_safe_origin(hardpoint.global_position, global_direction)
    projectile.configure(
        kind,
        projectile_parent.to_local(safe_origin),
        local_direction,
        speed_mps,
        hit_damage,
        get_rid()
    )
    projectile_parent.add_child(projectile)


func effect_safe_origin(requested_origin: Vector3, direction: Vector3) -> Vector3:
    if effect_exclusion_center == null:
        return requested_origin
    var normalized_direction := direction.normalized()
    if normalized_direction.is_zero_approx():
        return requested_origin
    var center := effect_exclusion_center.global_position
    var radius: float = effect_exclusion_center.get_meta(
        "effect_exclusion_radius_m", 0.0
    )
    var clearance: float = effect_exclusion_center.get_meta(
        "effect_exclusion_clearance_m", 0.1
    )
    var safe_radius := radius + clearance
    var offset := requested_origin - center
    if offset.length_squared() >= safe_radius * safe_radius:
        return requested_origin
    var along_ray := offset.dot(normalized_direction)
    var discriminant := (
        along_ray * along_ray - (offset.length_squared() - safe_radius * safe_radius)
    )
    if discriminant < 0.0:
        return requested_origin
    var exit_distance := -along_ray + sqrt(discriminant)
    return requested_origin + normalized_direction * maxf(0.0, exit_distance)


func weapon_status_text() -> String:
    var frap_status := "READY" if frapray_cooldown_remaining <= 0.0 else "CHARGING"
    var torpedo_status := "%02d" % proton_torpedoes_remaining
    return "WEAPONS\nFRAPRAY  %s · SPACE\nPROTON TORPEDO  %s · T" % [frap_status, torpedo_status]


func dead_stop() -> void:
    throttle = 0.0
    velocity = Vector3.ZERO


func _key_axis(negative_key: Key, positive_key: Key) -> float:
    return (
        float(Input.is_physical_key_pressed(positive_key))
        - float(Input.is_physical_key_pressed(negative_key))
    )


func _joy_axis(axis: JoyAxis) -> float:
    var value := Input.get_joy_axis(0, axis)
    return 0.0 if absf(value) < 0.12 else value


func speed_mps() -> float:
    return velocity.length()


func throttle_percent() -> int:
    return roundi(throttle * 100.0)


func set_controls_enabled(enabled: bool) -> void:
    controls_enabled = enabled
    if not enabled:
        velocity = Vector3.ZERO
