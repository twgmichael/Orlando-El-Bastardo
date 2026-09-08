extends Node3D

const VIEW_PRESETS := [
    {"label": "FORWARD", "yaw": 0.0, "pitch": 0.0},
    {"label": "FORWARD-UP", "yaw": 0.0, "pitch": 52.0},
    {"label": "LEFT SIDE", "yaw": -90.0, "pitch": 0.0},
    {"label": "RIGHT SIDE", "yaw": 90.0, "pitch": 0.0},
    {"label": "STRAIGHT BACK", "yaw": 180.0, "pitch": 0.0},
]

@export var rotation_speed := 7.0
@export var mouse_sensitivity := 0.16

var target_yaw_degrees := 0.0
var target_pitch_degrees := 0.0
var current_preset := 0
var free_look_active := false
var view_label := "FORWARD"

@onready var cockpit_camera := get_node("cockpit_camera") as Camera3D
@onready var debug_camera := get_parent().get_node_or_null("DebugCamera") as Camera3D


func _ready() -> void:
    add_to_group("pilot_view")
    snap_to_preset(0)


func _process(delta: float) -> void:
    rotation.y = lerp_angle(
        rotation.y,
        deg_to_rad(target_yaw_degrees),
        clampf(rotation_speed * delta, 0.0, 1.0)
    )
    rotation.x = lerp_angle(
        rotation.x,
        deg_to_rad(target_pitch_degrees),
        clampf(rotation_speed * delta, 0.0, 1.0)
    )


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_1:
                snap_to_preset(0)
            KEY_2:
                snap_to_preset(1)
            KEY_3:
                snap_to_preset(2)
            KEY_4:
                snap_to_preset(3)
            KEY_5:
                snap_to_preset(4)
            KEY_V:
                snap_to_preset((current_preset + 1) % VIEW_PRESETS.size())
            KEY_HOME:
                snap_to_preset(0)
            KEY_F3:
                toggle_debug_camera()
    elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
        free_look_active = event.pressed
        Input.mouse_mode = (
            Input.MOUSE_MODE_CAPTURED
            if free_look_active
            else Input.MOUSE_MODE_VISIBLE
        )
    elif event is InputEventMouseMotion and free_look_active:
        target_yaw_degrees -= event.relative.x * mouse_sensitivity
        target_pitch_degrees = clampf(
            target_pitch_degrees - event.relative.y * mouse_sensitivity,
            -85.0,
            85.0
        )
        current_preset = -1
        view_label = "FREE 360"
    elif event is InputEventJoypadButton and event.pressed:
        match event.button_index:
            JOY_BUTTON_DPAD_UP:
                snap_to_preset(1)
            JOY_BUTTON_DPAD_LEFT:
                snap_to_preset(2)
            JOY_BUTTON_DPAD_RIGHT:
                snap_to_preset(3)
            JOY_BUTTON_DPAD_DOWN:
                snap_to_preset(4)
            JOY_BUTTON_LEFT_SHOULDER:
                snap_to_preset(0)
            JOY_BUTTON_RIGHT_SHOULDER:
                snap_to_preset((maxi(current_preset, -1) + 1) % VIEW_PRESETS.size())


func snap_to_preset(index: int) -> void:
    current_preset = clampi(index, 0, VIEW_PRESETS.size() - 1)
    var preset: Dictionary = VIEW_PRESETS[current_preset]
    target_yaw_degrees = preset["yaw"]
    target_pitch_degrees = preset["pitch"]
    view_label = preset["label"]
    if cockpit_camera:
        cockpit_camera.current = true


func toggle_debug_camera() -> void:
    if debug_camera == null:
        return
    if debug_camera.current:
        cockpit_camera.current = true
        view_label = (
            VIEW_PRESETS[current_preset]["label"]
            if current_preset >= 0
            else "FREE 360"
        )
    else:
        debug_camera.current = true
        view_label = "EXTERNAL DEBUG"


func current_view_label() -> String:
    return view_label
