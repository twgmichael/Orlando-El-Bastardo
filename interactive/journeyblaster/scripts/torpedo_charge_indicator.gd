extends Control

const CHARGE_BLUE := Color(0.12, 0.66, 1.0, 1.0)
const TRACK_BLUE := Color(0.05, 0.25, 0.42, 0.85)

var charge_progress := 0.0


func _ready() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    visible = false


func set_charge_progress(progress: float) -> void:
    charge_progress = clampf(progress, 0.0, 1.0)
    visible = charge_progress > 0.0
    queue_redraw()


func _draw() -> void:
    if charge_progress <= 0.0:
        return
    var center := size * 0.5
    var radius := minf(size.x, size.y) * 0.42
    draw_arc(center, radius, 0.0, TAU, 40, TRACK_BLUE, 1.5, true)
    draw_arc(
        center,
        radius,
        -PI * 0.5,
        -PI * 0.5 + TAU * charge_progress,
        maxi(3, ceili(40.0 * charge_progress)),
        CHARGE_BLUE,
        2.5,
        true
    )
