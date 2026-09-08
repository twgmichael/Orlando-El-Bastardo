extends CharacterBody3D

signal impact(speed_mps: float)
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
@export var frapray_cooldown_s := 0.18
@export var torpedo_cooldown_s := 0.9
@export var proton_torpedo_capacity := 8

var throttle := 0.0
var controls_enabled := true
var course_lock := false
var collision_count := 0
var last_impact_speed_mps := 0.0
var mouse_flight_active := false
var mouse_flight_delta := Vector2.ZERO
var frapray_cooldown_remaining := 0.0
var torpedo_cooldown_remaining := 0.0
var proton_torpedoes_remaining := 8
var frapray_shots_fired := 0
var proton_torpedoes_fired := 0

@onready var frapray_left := get_node_or_null("frap_hardpoint_left") as Node3D
@onready var frapray_right := get_node_or_null("frap_hardpoint_right") as Node3D
@onready var torpedo_launcher := get_node_or_null("torpedo_launcher") as Node3D


func _ready() -> void:
    add_to_group("player_ship")
    proton_torpedoes_remaining = proton_torpedo_capacity


func _physics_process(delta: float) -> void:
    frapray_cooldown_remaining = maxf(0.0, frapray_cooldown_remaining - delta)
    torpedo_cooldown_remaining = maxf(0.0, torpedo_cooldown_remaining - delta)
    if not controls_enabled:
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
        var pitch_input := clampf(
            _key_axis(KEY_DOWN, KEY_UP)
            - _joy_axis(JOY_AXIS_RIGHT_Y)
            - mouse_flight_delta.y * 0.012,
            -1.0,
            1.0
        )
        var yaw_input := clampf(
            _key_axis(KEY_D, KEY_A)
            + _key_axis(KEY_RIGHT, KEY_LEFT)
            - _joy_axis(JOY_AXIS_LEFT_X)
            - mouse_flight_delta.x * 0.012,
            -1.0,
            1.0
        )
        var roll_input := clampf(
            _key_axis(KEY_E, KEY_Q) + _joy_axis(JOY_AXIS_RIGHT_X),
            -1.0,
            1.0
        )
        rotate_object_local(
            Vector3.RIGHT,
            deg_to_rad(pitch_rate_degrees) * pitch_input * delta
        )
        rotate_y(deg_to_rad(yaw_rate_degrees) * yaw_input * delta)
        rotate_object_local(
            Vector3.BACK,
            deg_to_rad(roll_rate_degrees) * roll_input * delta
        )

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
        collision_count += 1
        last_impact_speed_mps = speed_before_move
        velocity *= 0.32
        throttle *= 0.55
        impact.emit(speed_before_move)
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
    elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
        mouse_flight_active = event.pressed
        Input.mouse_mode = (
            Input.MOUSE_MODE_CAPTURED
            if mouse_flight_active
            else Input.MOUSE_MODE_VISIBLE
        )
    elif event is InputEventMouseMotion and mouse_flight_active:
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


func fire_frapray() -> bool:
    if not controls_enabled or frapray_cooldown_remaining > 0.0:
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
    var local_direction := (
        projectile_parent.global_basis.inverse() * -global_basis.z
    ).normalized()
    projectile.configure(
        kind,
        projectile_parent.to_local(hardpoint.global_position),
        local_direction,
        speed_mps,
        hit_damage,
        get_rid()
    )
    projectile_parent.add_child(projectile)


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
