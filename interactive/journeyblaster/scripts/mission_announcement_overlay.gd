extends Label

const GO_DURATION_S := 3.0
const GO_COLOR := Color(0.08, 0.48, 1.0)
const SUCCESS_COLOR := Color(0.08, 1.0, 0.28)
const FAILED_COLOR := Color(1.0, 0.035, 0.02)

var go_time_remaining := 0.0


func _ready() -> void:
    anchor_left = 0.5
    anchor_top = 0.39
    anchor_right = 0.5
    anchor_bottom = 0.39
    offset_left = -300.0
    offset_top = -58.0
    offset_right = 300.0
    offset_bottom = 58.0
    horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    var announcement_font := SystemFont.new()
    announcement_font.font_names = PackedStringArray(
        ["Arial Black", "Arial", "Helvetica"]
    )
    announcement_font.font_weight = 900
    add_theme_font_override("font", announcement_font)
    add_theme_font_size_override("font_size", 92)
    add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.96))
    add_theme_constant_override("outline_size", 14)
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    visible = false


func _process(delta: float) -> void:
    if go_time_remaining <= 0.0:
        return
    go_time_remaining = maxf(0.0, go_time_remaining - delta)
    if is_zero_approx(go_time_remaining) and text == "GO":
        visible = false


func show_go() -> void:
    text = "GO"
    add_theme_color_override("font_color", GO_COLOR)
    go_time_remaining = GO_DURATION_S
    visible = true


func show_failed() -> void:
    text = "FAILED"
    add_theme_color_override("font_color", FAILED_COLOR)
    go_time_remaining = 0.0
    visible = true


func show_success() -> void:
    text = "SUCCESS"
    add_theme_color_override("font_color", SUCCESS_COLOR)
    go_time_remaining = 0.0
    visible = true
