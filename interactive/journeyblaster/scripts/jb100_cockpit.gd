extends CanvasLayer

const SensorGlobeDisplay = preload("res://scripts/sensor_globe_display.gd")
const TorpedoChargeIndicator = preload("res://scripts/torpedo_charge_indicator.gd")
const MissionAnnouncementOverlay = preload(
    "res://scripts/mission_announcement_overlay.gd"
)

var player: CharacterBody3D
var mission_number := "---"
var systems_bars: Dictionary = {}
var systems_value_labels: Dictionary = {}
var systems_torpedo_label: Label
var sensor_globe: Control
var mission_screen_label: Label
var weapon_aim: Control
var frap_aim_left: Label
var frap_aim_right: Label
var torpedo_aim: Label
var torpedo_charge_indicator: Control
var context_reticle: Label
var announcement: Label


func _ready() -> void:
    name = "HUD"
    _build_systems_screen()
    _build_sensor_screen()
    _build_mission_screen()
    _build_weapon_aim()
    announcement = MissionAnnouncementOverlay.new()
    announcement.name = "MissionAnnouncement"
    add_child(announcement)


func configure(
    ship: CharacterBody3D,
    number: String,
    contacts: Array[Node3D] = []
) -> void:
    player = ship
    mission_number = number
    sensor_globe.configure(player, contacts)
    update_systems()


func set_contacts(contacts: Array[Node3D]) -> void:
    if player:
        sensor_globe.configure(player, contacts)


func register_contact(contact: Node3D) -> void:
    if contact and contact not in sensor_globe.tracked_contacts:
        sensor_globe.tracked_contacts.append(contact)


func unregister_contact(contact: Node3D) -> void:
    sensor_globe.tracked_contacts.erase(contact)


func update_systems() -> void:
    if player == null:
        return
    var thrust_percent: int = player.available_thrust_percent()
    var power_percent: int = player.power_level_percent()
    var shield_percent: int = player.shield_level_percent()
    var frapray_percent: int = floori(player.frapray_power_percent)
    _set_system_value("PWR", power_percent)
    _set_system_value("THR", thrust_percent)
    _set_system_value("SHD", shield_percent)
    _set_system_value("WPN", frapray_percent)
    systems_torpedo_label.text = "TPD: %d" % player.proton_torpedoes_remaining


func set_mission_display(
    state: String,
    objective: String,
    alerts: Array[String] = []
) -> void:
    var alert_feed := "NO NEW REPORTS"
    if not alerts.is_empty():
        alert_feed = "\n".join(alerts)
    mission_screen_label.text = (
        "MISSION %s · %s\nOBJECTIVE\n%s\n\nALERTS\n%s"
        % [mission_number, state, objective, alert_feed]
    ).to_upper()


func show_go() -> void:
    announcement.call("show_go")


func show_success() -> void:
    announcement.call("show_success")


func show_failed() -> void:
    announcement.call("show_failed")


func _set_system_value(key: String, value: int) -> void:
    systems_bars[key].value = value
    systems_value_labels[key].text = "%s: %03d%%" % [key, value]


func _build_instrument_screen(
    screen_name: String, position_2d: Vector2, size_2d: Vector2
) -> Control:
    var screen := Panel.new()
    screen.name = screen_name
    screen.position = position_2d
    screen.size = size_2d
    screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.0, 0.012, 0.006, 0.98)
    style.border_color = Color(0.08, 0.72, 0.32, 0.92)
    style.set_border_width_all(1)
    style.corner_radius_top_left = 3
    style.corner_radius_top_right = 3
    style.corner_radius_bottom_left = 3
    style.corner_radius_bottom_right = 3
    screen.add_theme_stylebox_override("panel", style)
    add_child(screen)
    return screen


func _build_systems_screen() -> void:
    var screen := _build_instrument_screen(
        "LeftSystemsScreen", Vector2(340.0, 564.0), Vector2(184.0, 144.0)
    )
    var heading := _build_child_label(
        screen, Vector2(8.0, 5.0), Vector2(168.0, 15.0), 10
    )
    heading.text = "SYSTEMS"
    for index in 4:
        var key: String = ["PWR", "THR", "SHD", "WPN"][index]
        var bar := ProgressBar.new()
        bar.position = Vector2(8.0, 23.0 + index * 28.0)
        bar.size = Vector2(168.0, 22.0)
        bar.min_value = 0.0
        bar.max_value = 100.0
        bar.show_percentage = false
        bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
        var background := StyleBoxFlat.new()
        background.bg_color = Color(0.005, 0.045, 0.022, 1.0)
        background.border_color = Color(0.06, 0.38, 0.19, 1.0)
        background.set_border_width_all(1)
        var fill := StyleBoxFlat.new()
        fill.bg_color = Color(0.08, 0.58, 0.27, 0.82)
        bar.add_theme_stylebox_override("background", background)
        bar.add_theme_stylebox_override("fill", fill)
        screen.add_child(bar)
        systems_bars[key] = bar
        var value_label := _build_child_label(
            screen,
            Vector2(14.0, 25.0 + index * 28.0),
            Vector2(156.0, 18.0),
            10
        )
        value_label.text = "%s: --%%" % key
        systems_value_labels[key] = value_label
    systems_value_labels["WPN"].size.x = 94.0
    systems_torpedo_label = _build_child_label(
        screen, Vector2(108.0, 109.0), Vector2(62.0, 18.0), 10
    )
    systems_torpedo_label.text = "TPD: 5"
    systems_torpedo_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT


func _build_sensor_screen() -> void:
    var screen := _build_instrument_screen(
        "MiddleSensorScreen", Vector2(548.0, 548.0), Vector2(190.0, 160.0)
    )
    var heading := _build_child_label(
        screen, Vector2(8.0, 5.0), Vector2(174.0, 15.0), 10
    )
    heading.text = "SENSO-GLOBE · 1000 M"
    sensor_globe = SensorGlobeDisplay.new()
    sensor_globe.name = "SensorGlobe"
    sensor_globe.position = Vector2(9.0, 20.0)
    sensor_globe.size = Vector2(172.0, 132.0)
    screen.add_child(sensor_globe)


func _build_mission_screen() -> void:
    var screen := _build_instrument_screen(
        "RightMissionScreen", Vector2(754.0, 564.0), Vector2(198.0, 144.0)
    )
    screen.clip_contents = true
    mission_screen_label = _build_child_label(
        screen, Vector2(9.0, 7.0), Vector2(180.0, 130.0), 8
    )
    mission_screen_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    mission_screen_label.clip_text = true
    mission_screen_label.add_theme_constant_override("line_spacing", -1)


func _build_weapon_aim() -> void:
    weapon_aim = Control.new()
    weapon_aim.name = "WeaponAim"
    weapon_aim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    weapon_aim.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(weapon_aim)
    frap_aim_left = _build_aim_label("FrapRayLeft", "•")
    frap_aim_right = _build_aim_label("FrapRayRight", "•")
    torpedo_aim = _build_aim_label("Torpedo", "×")
    torpedo_charge_indicator = TorpedoChargeIndicator.new()
    torpedo_charge_indicator.name = "TorpedoChargeIndicator"
    torpedo_charge_indicator.size = Vector2(31.0, 31.0)
    weapon_aim.add_child(torpedo_charge_indicator)
    context_reticle = _build_aim_label("ContextReticle", "○")
    context_reticle.size = Vector2(54.0, 54.0)
    context_reticle.add_theme_font_size_override("font_size", 38)
    context_reticle.add_theme_color_override(
        "font_color", Color(0.18, 0.62, 1.0, 0.95)
    )
    context_reticle.visible = false


func _build_child_label(
    parent: Control, position_2d: Vector2, size_2d: Vector2, font_size: int
) -> Label:
    var label := Label.new()
    label.position = position_2d
    label.size = size_2d
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", Color(0.22, 1.0, 0.5))
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    parent.add_child(label)
    return label


func _build_aim_label(label_name: String, value: String) -> Label:
    var label := Label.new()
    label.name = label_name
    label.text = value
    label.size = Vector2(17.0, 17.0)
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    label.add_theme_font_size_override("font_size", 14)
    label.add_theme_color_override("font_color", Color(1.0, 0.12, 0.08))
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    weapon_aim.add_child(label)
    return label
