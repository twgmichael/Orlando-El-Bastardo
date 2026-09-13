extends Control

const SENSOR_RANGE_M := 1000.0
const GREEN := Color(0.18, 1.0, 0.48, 0.95)
const DIM_GREEN := Color(0.08, 0.48, 0.24, 0.82)
const HOSTILE_RED := Color(1.0, 0.11, 0.06, 1.0)
const FRIENDLY_BLUE := Color(0.12, 0.62, 1.0, 1.0)
const OBJECTIVE_YELLOW := Color(1.0, 0.86, 0.08, 1.0)
const FORWARD_AMBER := Color(1.0, 0.68, 0.12, 1.0)
const DISPLAY_Y_AXIS_2D := Vector2(0.62, -0.44)

var player: Node3D
var tracked_contacts: Array = []


func configure(sensor_origin: Node3D, contacts: Array[Node3D]) -> void:
    player = sensor_origin
    tracked_contacts = contacts
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    queue_redraw()


func _process(_delta: float) -> void:
    for index in range(tracked_contacts.size() - 1, -1, -1):
        var contact = tracked_contacts[index]
        if not is_instance_valid(contact) or (
            contact.is_in_group("mission_003_pirate")
            and bool(contact.get("destroyed"))
        ):
            tracked_contacts.remove_at(index)
    queue_redraw()


func _draw() -> void:
    var center := size * 0.5 + Vector2(0.0, 5.0)
    var radius := minf(size.x, size.y) * 0.34
    draw_arc(center, radius, 0.0, TAU, 48, GREEN, 1.2, true)
    _draw_ellipse(center, radius, radius * 0.34, DIM_GREEN)
    _draw_vertical_ellipse(center, radius * 0.36, radius, DIM_GREEN)

    draw_line(center - Vector2(radius, 0.0), center + Vector2(radius, 0.0), DIM_GREEN, 1.0)
    draw_line(center - Vector2(0.0, radius), center + Vector2(0.0, radius), DIM_GREEN, 1.0)
    draw_line(
        center - DISPLAY_Y_AXIS_2D * radius,
        center + DISPLAY_Y_AXIS_2D * radius,
        DIM_GREEN,
        1.0
    )
    var font := ThemeDB.fallback_font
    draw_string(font, center + Vector2(radius + 2.0, 4.0), "X", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 9, GREEN)
    draw_string(font, center + Vector2(3.0, -radius + 8.0), "Z", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 9, GREEN)
    draw_string(font, center + DISPLAY_Y_AXIS_2D * radius, "Y", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 9, GREEN)
    draw_circle(center, 2.3, FRIENDLY_BLUE)
    _draw_forward_arrow(center, radius)

    if player == null or not is_instance_valid(player):
        return
    for contact in tracked_contacts:
        if not contact_is_active(contact):
            continue
        var local_position := player.to_local(contact.global_position)
        var distance := local_position.length()
        if distance > SENSOR_RANGE_M:
            continue
        var normalized := local_position / SENSOR_RANGE_M
        var projected := project_ship_local_vector(normalized)
        var contact_position := center + projected * radius * 0.82
        var contact_radius := 2.5 if contact.is_in_group("mission_003_pirate") else 2.0
        draw_circle(contact_position, contact_radius, _contact_color(contact))


func _contact_color(contact) -> Color:
    if contact.is_in_group("mission_003_pirate"):
        return HOSTILE_RED
    if contact.is_in_group("sensor_objective_contact"):
        return OBJECTIVE_YELLOW
    return FRIENDLY_BLUE


func contact_is_active(contact) -> bool:
    if contact == null or not is_instance_valid(contact) or not contact.visible:
        return false
    if contact.is_in_group("mission_003_pirate"):
        return not bool(contact.get("destroyed"))
    return true


func _draw_forward_arrow(center: Vector2, radius: float) -> void:
    # Godot ship-forward is local -Z. On the cockpit convention that maps to
    # display +Y toward the Y label, with X lateral and Z vertical.
    var forward_direction := project_ship_local_vector(Vector3.FORWARD).normalized()
    var start := center - forward_direction * radius * 0.48
    var tip := center + forward_direction * radius * 0.48
    var side := Vector2(-forward_direction.y, forward_direction.x)
    var arrow_length := 7.0
    var arrow_width := 4.0
    draw_line(start, tip, FORWARD_AMBER, 2.0, true)
    draw_colored_polygon(
        PackedVector2Array([
            tip,
            tip - forward_direction * arrow_length + side * arrow_width,
            tip - forward_direction * arrow_length - side * arrow_width,
        ]),
        FORWARD_AMBER
    )


func ship_local_to_sensor_axes(local_vector: Vector3) -> Vector3:
    # Return display-space X/Y/Z: lateral, front-to-back, and vertical.
    return Vector3(local_vector.x, -local_vector.z, local_vector.y)


func project_ship_local_vector(local_vector: Vector3) -> Vector2:
    var sensor_axes := ship_local_to_sensor_axes(local_vector)
    return (
        Vector2(sensor_axes.x, -sensor_axes.z)
        + DISPLAY_Y_AXIS_2D * sensor_axes.y
    )


func _draw_ellipse(
    center: Vector2, horizontal_radius: float, vertical_radius: float, color: Color
) -> void:
    var points := PackedVector2Array()
    for index in 33:
        var angle := TAU * float(index) / 32.0
        points.append(
            center + Vector2(cos(angle) * horizontal_radius, sin(angle) * vertical_radius)
        )
    draw_polyline(points, color, 1.0, true)


func _draw_vertical_ellipse(
    center: Vector2, horizontal_radius: float, vertical_radius: float, color: Color
) -> void:
    var points := PackedVector2Array()
    for index in 33:
        var angle := TAU * float(index) / 32.0
        points.append(
            center + Vector2(cos(angle) * horizontal_radius, sin(angle) * vertical_radius)
        )
    draw_polyline(points, color, 1.0, true)
