extends Node3D

const WeaponProjectile = preload("res://scripts/weapon_projectile.gd")
const StarbaseTarget = preload("res://scripts/starbase_target.gd")
const STARBASE_SCENE = preload("res://generated/scenes/starbase_86_v1.tscn")
const PIRATE_SCENE = preload("res://generated/scenes/pirate_flyer_mk1.tscn")

const STARBASE_CENTER := Vector3(0.0, 75.0, 0.0)
const PLANET_POSITION := Vector3(680.0, 260.0, 3000.0)
const OPEN_HANGAR_CENTER := Vector3(113.86, 10.5, -34.811)
const OPEN_HANGAR_EXIT := Vector3(123.316, 10.5, -3.88)
const PLAYER_HANGAR_START := Vector3(119.724, 10.5, -15.634)
const HANGAR_SAFE_RADIUS_M := 32.0
const PIRATE_RETREAT_HITS := 3.0
const PIRATE_DESTROY_HITS := 7.0
const DEFENSE_PERIMETER_M := 5000.0
const HYPERSPACE_RANGE_M := 6000.0

const OBJECTIVES := {
    "BRIEFING": "Launch from Starbase 86 and repel three attacking pirate flyers.",
    "DEFEND": "Destroy the attackers or drive them beyond the defense perimeter.",
    "COMPLETE": "Starbase 86 is secure. All pirate flyers are gone.",
    "FAILED": "Defense failed. Free flight remains available.",
}

@onready var player := $player_jb100 as CharacterBody3D

var mission_state := "BRIEFING"
var starbase: StaticBody3D
var station_targets: Array[StaticBody3D] = []
var targets_by_category: Dictionary = {}
var pirates: Array[AnimatableBody3D] = []
var player_attacker: AnimatableBody3D
var station_weapon_timers: Dictionary = {}
var random := RandomNumberGenerator.new()
var weapon_aim_enabled := true

var hud: CanvasLayer
var title_label: Label
var status_label: Label
var objective_label: Label
var sensor_label: Label
var weapons_label: Label
var flight_label: Label
var view_label: Label
var prompt_label: Label
var weapon_aim: Control
var frap_aim_left: Label
var frap_aim_right: Label
var torpedo_aim: Label
var frap_origin_left: Node3D
var frap_origin_right: Node3D
var torpedo_origin: Node3D


func _ready() -> void:
    random.randomize()
    frap_origin_left = player.find_child("frap_hardpoint_left", true, false) as Node3D
    frap_origin_right = player.find_child("frap_hardpoint_right", true, false) as Node3D
    torpedo_origin = player.find_child("torpedo_launcher", true, false) as Node3D
    _build_environment()
    _spawn_starbase()
    _build_station_targets()
    _position_player_in_open_hangar()
    _spawn_pirates()
    _build_hud()
    player.ship_disabled.connect(_on_player_disabled)
    _set_state("BRIEFING")
    print("MISSION-003-RUNTIME-OK: Starbase Defense")


func _process(delta: float) -> void:
    if mission_state != "BRIEFING":
        _update_station_defense(delta)
        _maintain_player_attacker()
        _evaluate_outcome()
    _update_hud()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_ENTER, KEY_KP_ENTER:
                begin_mission()
            KEY_TAB:
                weapon_aim_enabled = not weapon_aim_enabled
            KEY_R:
                if mission_state in ["COMPLETE", "FAILED"]:
                    get_tree().reload_current_scene()


func begin_mission() -> void:
    if mission_state != "BRIEFING":
        return
    _set_state("DEFEND")
    for pirate in pirates:
        pirate.ai_enabled = true


func current_state() -> String:
    return mission_state


func _set_state(next_state: String) -> void:
    mission_state = next_state
    if next_state == "FAILED" and _all_station_targets_disabled():
        for pirate in _active_pirates(false):
            pirate.assign_player_attack()
        player_attacker = null


func _build_environment() -> void:
    var world_environment := WorldEnvironment.new()
    world_environment.name = "WorldEnvironment"
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.001, 0.0025, 0.009)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.16, 0.22, 0.34)
    environment.ambient_light_energy = 0.48
    environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
    world_environment.environment = environment
    add_child(world_environment)

    var sun := DirectionalLight3D.new()
    sun.name = "SystemSun"
    sun.rotation_degrees = Vector3(-38.0, -24.0, 12.0)
    sun.light_color = Color(0.82, 0.9, 1.0)
    sun.light_energy = 1.65
    sun.shadow_enabled = true
    add_child(sun)
    _build_starfield()
    _build_planet_and_moon()


func _build_starfield() -> void:
    var stars := MultiMeshInstance3D.new()
    stars.name = "Starfield"
    var star_mesh := SphereMesh.new()
    star_mesh.radius = 0.72
    star_mesh.height = 1.44
    star_mesh.radial_segments = 4
    star_mesh.rings = 2
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.78, 0.88, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.64, 0.77, 1.0)
    material.emission_energy_multiplier = 2.2
    star_mesh.material = material
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = star_mesh
    multimesh.instance_count = 360
    var star_random := RandomNumberGenerator.new()
    star_random.seed = 860003
    for index in multimesh.instance_count:
        var direction := Vector3(
            star_random.randf_range(-1.0, 1.0),
            star_random.randf_range(-1.0, 1.0),
            star_random.randf_range(-1.0, 1.0)
        ).normalized()
        var distance := star_random.randf_range(5200.0, 6800.0)
        var scale_value := star_random.randf_range(0.4, 1.25)
        multimesh.set_instance_transform(
            index,
            Transform3D(
                Basis.IDENTITY.scaled(Vector3.ONE * scale_value),
                direction * distance
            )
        )
    stars.multimesh = multimesh
    add_child(stars)


func _build_planet_and_moon() -> void:
    var planet := MeshInstance3D.new()
    planet.name = "DistantPlanet"
    planet.add_to_group("mission_003_planet")
    var planet_mesh := SphereMesh.new()
    planet_mesh.radius = 520.0
    planet_mesh.height = 1040.0
    planet_mesh.radial_segments = 48
    planet_mesh.rings = 24
    var planet_material := StandardMaterial3D.new()
    planet_material.albedo_color = Color(0.055, 0.16, 0.31)
    planet_material.roughness = 0.92
    planet_material.emission_enabled = true
    planet_material.emission = Color(0.008, 0.035, 0.11)
    planet_material.emission_energy_multiplier = 0.7
    planet_mesh.material = planet_material
    planet.mesh = planet_mesh
    planet.position = PLANET_POSITION
    add_child(planet)

    var atmosphere := MeshInstance3D.new()
    atmosphere.name = "DistantAtmosphere"
    var atmosphere_mesh := SphereMesh.new()
    atmosphere_mesh.radius = 546.0
    atmosphere_mesh.height = 1092.0
    atmosphere_mesh.radial_segments = 48
    atmosphere_mesh.rings = 24
    var atmosphere_material := StandardMaterial3D.new()
    atmosphere_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    atmosphere_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    atmosphere_material.albedo_color = Color(0.05, 0.32, 1.0, 0.12)
    atmosphere_material.emission_enabled = true
    atmosphere_material.emission = Color(0.02, 0.16, 0.7)
    atmosphere_material.emission_energy_multiplier = 1.0
    atmosphere_mesh.material = atmosphere_material
    atmosphere.mesh = atmosphere_mesh
    atmosphere.position = PLANET_POSITION
    add_child(atmosphere)

    var moon := MeshInstance3D.new()
    moon.name = "DistantMoon"
    moon.add_to_group("mission_003_moon")
    var moon_mesh := SphereMesh.new()
    moon_mesh.radius = 118.0
    moon_mesh.height = 236.0
    moon_mesh.radial_segments = 32
    moon_mesh.rings = 16
    var moon_material := StandardMaterial3D.new()
    moon_material.albedo_color = Color(0.42, 0.39, 0.36)
    moon_material.roughness = 1.0
    moon_mesh.material = moon_material
    moon.mesh = moon_mesh
    moon.position = Vector3(1180.0, 470.0, 2790.0)
    add_child(moon)


func _spawn_starbase() -> void:
    starbase = STARBASE_SCENE.instantiate() as StaticBody3D
    starbase.name = "starbase_86"
    starbase.add_to_group("mission_003_starbase")
    add_child(starbase)
    starbase.global_position = Vector3.ZERO


func _build_station_targets() -> void:
    targets_by_category = {"shield": [], "weapon": [], "hangar": []}
    var placements := {
        "shield": [
            Vector3(0.0, 148.0, 8.0),
            Vector3(68.0, 82.0, 24.0),
            Vector3(-42.0, 24.0, 48.0),
        ],
        "weapon": [
            Vector3(-18.0, 150.0, -24.0),
            Vector3(-78.0, 82.0, -18.0),
            Vector3(38.0, 28.0, -72.0),
        ],
        "hangar": [
            Vector3(113.86, 26.0, -34.811),
            Vector3(-87.077, 26.0, -81.2),
            Vector3(-26.783, 26.0, 116.011),
        ],
    }
    var colors := {
        "shield": Color(0.08, 0.68, 1.0),
        "weapon": Color(1.0, 0.52, 0.08),
        "hangar": Color(0.64, 0.32, 1.0),
    }
    var tiers := ["top", "middle", "bottom"]
    for category in ["shield", "weapon", "hangar"]:
        for index in 3:
            var target := StaticBody3D.new()
            target.set_script(StarbaseTarget)
            add_child(target)
            target.configure(category, tiers[index], colors[category])
            target.global_position = placements[category][index]
            target.target_disabled.connect(_on_station_target_disabled)
            station_targets.append(target)
            targets_by_category[category].append(target)
            if category == "weapon":
                station_weapon_timers[target.get_instance_id()] = random.randf_range(2.0, 5.0)


func _position_player_in_open_hangar() -> void:
    player.global_position = PLAYER_HANGAR_START
    player.look_at(OPEN_HANGAR_EXIT, Vector3.UP)
    player.velocity = Vector3.ZERO
    player.throttle = 0.0


func _spawn_pirates() -> void:
    var categories := ["shield", "weapon", "hangar"]
    for category_index in range(categories.size() - 1, 0, -1):
        var swap_index := random.randi_range(0, category_index)
        var temporary: String = categories[category_index]
        categories[category_index] = categories[swap_index]
        categories[swap_index] = temporary
    var positions := [
        Vector3(-245.0, 115.0, -105.0),
        Vector3(235.0, 178.0, -155.0),
        Vector3(-45.0, 64.0, 265.0),
    ]
    for index in 3:
        var pirate := PIRATE_SCENE.instantiate() as AnimatableBody3D
        pirate.name = "pirate_flyer_%d" % (index + 1)
        add_child(pirate)
        pirate.global_position = positions[index]
        var typed_targets: Array[StaticBody3D] = []
        typed_targets.assign(targets_by_category[categories[index]])
        pirate.configure(
            self,
            player,
            STARBASE_CENTER,
            PLANET_POSITION,
            categories[index],
            typed_targets,
            random.randi()
        )
        pirate.objective_completed.connect(_on_pirate_objective_completed)
        pirate.retreat_started.connect(_on_pirate_retreat_started)
        pirate.flyer_destroyed.connect(_on_pirate_destroyed)
        pirate.defense_perimeter_crossed.connect(_on_defense_perimeter_crossed)
        pirates.append(pirate)


func _on_pirate_objective_completed(pirate: AnimatableBody3D) -> void:
    if mission_state == "FAILED" and _all_station_targets_disabled():
        pirate.assign_player_attack()
        return
    if not _player_attacker_is_active():
        player_attacker = pirate
        pirate.assign_player_attack()
    else:
        pirate.assign_pile_on(_remaining_station_targets())


func _on_pirate_retreat_started(pirate: AnimatableBody3D) -> void:
    if player_attacker == pirate:
        player_attacker = null
        _maintain_player_attacker()


func _on_pirate_destroyed(pirate: AnimatableBody3D) -> void:
    if player_attacker == pirate:
        player_attacker = null
        _maintain_player_attacker()
    _evaluate_outcome()


func _on_defense_perimeter_crossed(_pirate: AnimatableBody3D) -> void:
    _evaluate_outcome()


func _on_station_target_disabled(_target: StaticBody3D) -> void:
    _evaluate_outcome()


func _on_player_disabled() -> void:
    if mission_state != "COMPLETE":
        _set_state("FAILED")


func _maintain_player_attacker() -> void:
    if mission_state == "BRIEFING" or _all_station_targets_disabled():
        return
    if _player_attacker_is_active():
        return
    player_attacker = null
    for pirate in pirates:
        if (
            pirate.completed_primary_objective
            and not pirate.destroyed
            and not pirate.perimeter_crossed
            and pirate.behavior not in ["RETREAT", "DRIVEN_OFF"]
        ):
            player_attacker = pirate
            pirate.assign_player_attack()
            return


func _player_attacker_is_active() -> bool:
    return (
        is_instance_valid(player_attacker)
        and not player_attacker.destroyed
        and not player_attacker.perimeter_crossed
        and player_attacker.behavior == "ATTACK_PLAYER"
    )


func _remaining_station_targets() -> Array[StaticBody3D]:
    var remaining: Array[StaticBody3D] = []
    for target in station_targets:
        if not target.disabled:
            remaining.append(target)
    return remaining


func _all_station_targets_disabled() -> bool:
    return not station_targets.is_empty() and _remaining_station_targets().is_empty()


func _active_pirates(include_retreating := true) -> Array[AnimatableBody3D]:
    var active: Array[AnimatableBody3D] = []
    for pirate in pirates:
        if pirate.destroyed or pirate.hyperspace_departed:
            continue
        if not include_retreating and pirate.behavior in ["RETREAT", "DRIVEN_OFF"]:
            continue
        active.append(pirate)
    return active


func _evaluate_outcome() -> void:
    if mission_state == "COMPLETE":
        return
    var neutralized := 0
    for pirate in pirates:
        if pirate.destroyed or pirate.perimeter_crossed:
            neutralized += 1
    if neutralized == pirates.size() and not pirates.is_empty():
        _set_state("COMPLETE")
        return
    if player.disabled_in_space:
        _set_state("FAILED")
        return
    if _all_station_targets_disabled():
        _set_state("FAILED")


func is_player_in_safe_hangar() -> bool:
    return player.global_position.distance_to(OPEN_HANGAR_CENTER) <= HANGAR_SAFE_RADIUS_M


func fire_pirate_weapon(pirate: AnimatableBody3D, target: Node3D) -> void:
    if mission_state == "BRIEFING" or pirate.destroyed:
        return
    var direction := target.global_position - pirate.global_position
    if direction.length() <= 0.01:
        return
    var damage := 10.0 if target == player else _pirate_station_damage(target)
    var exclusions: Array[RID] = []
    for other in pirates:
        exclusions.append(other.get_rid())
    _spawn_combat_projectile(
        "pirate_plasma",
        pirate.global_position + direction.normalized() * 6.0,
        direction.normalized(),
        132.0,
        damage,
        pirate.get_rid(),
        exclusions
    )


func _pirate_station_damage(target: Node3D) -> float:
    if target.system_category == "shield":
        return 1.0
    return 1.0 + float(_disabled_shield_count())


func _disabled_shield_count() -> int:
    var count := 0
    for target in targets_by_category.get("shield", []):
        if target.disabled:
            count += 1
    return count


func _update_station_defense(delta: float) -> void:
    if mission_state == "COMPLETE":
        return
    var possible_targets := _active_pirates()
    if possible_targets.is_empty():
        return
    for weapon in targets_by_category.get("weapon", []):
        if weapon.disabled:
            continue
        var identifier: int = weapon.get_instance_id()
        var timer: float = station_weapon_timers.get(identifier, 0.0) - delta
        if timer > 0.0:
            station_weapon_timers[identifier] = timer
            continue
        var target: AnimatableBody3D = possible_targets[random.randi_range(0, possible_targets.size() - 1)]
        var aim_error := Vector3(
            random.randf_range(-15.0, 15.0),
            random.randf_range(-10.0, 10.0),
            random.randf_range(-15.0, 15.0)
        )
        var direction: Vector3 = target.global_position + aim_error - weapon.global_position
        var exclusions: Array[RID] = [starbase.get_rid()]
        for station_target in station_targets:
            exclusions.append(station_target.get_rid())
        _spawn_combat_projectile(
            "starbase_plasma",
            weapon.global_position + direction.normalized() * 7.0,
            direction.normalized(),
            155.0,
            0.8,
            weapon.get_rid(),
            exclusions
        )
        station_weapon_timers[identifier] = lerpf(
            12.0, 5.2, weapon.effectiveness()
        ) + random.randf_range(0.0, 2.0)


func _spawn_combat_projectile(
    kind: String,
    start: Vector3,
    direction: Vector3,
    speed: float,
    damage: float,
    shooter: RID,
    exclusions: Array[RID]
) -> void:
    var projectile := WeaponProjectile.new()
    projectile.configure(
        kind, start, direction, speed, damage, shooter, exclusions
    )
    add_child(projectile)


func _build_hud() -> void:
    hud = CanvasLayer.new()
    hud.name = "HUD"
    add_child(hud)
    _build_panel(Vector2(20.0, 20.0), Vector2(760.0, 126.0), Color(0.02, 0.035, 0.04, 0.9))
    title_label = _build_label(Vector2(38.0, 32.0), Vector2(710.0, 25.0), 14, Color(0.38, 0.92, 0.67))
    status_label = _build_label(Vector2(38.0, 59.0), Vector2(710.0, 24.0), 12, Color(0.92, 0.89, 0.79))
    objective_label = _build_label(Vector2(38.0, 87.0), Vector2(710.0, 28.0), 13, Color(0.76, 0.84, 0.88))
    var width := get_viewport().get_visible_rect().size.x
    _build_panel(Vector2(width - 400.0, 20.0), Vector2(380.0, 146.0), Color(0.055, 0.032, 0.012, 0.9))
    sensor_label = _build_label(Vector2(width - 382.0, 35.0), Vector2(350.0, 122.0), 13, Color(1.0, 0.63, 0.18))
    _build_panel(Vector2(width - 400.0, 178.0), Vector2(380.0, 120.0), Color(0.018, 0.032, 0.07, 0.9))
    weapons_label = _build_label(Vector2(width - 382.0, 190.0), Vector2(350.0, 102.0), 13, Color(0.42, 0.68, 1.0))
    _build_panel(Vector2(20.0, 542.0), Vector2(430.0, 158.0), Color(0.02, 0.035, 0.04, 0.9))
    flight_label = _build_label(Vector2(38.0, 557.0), Vector2(185.0, 132.0), 12, Color(0.38, 0.92, 0.67))
    view_label = _build_label(Vector2(230.0, 557.0), Vector2(205.0, 132.0), 12, Color(0.92, 0.89, 0.79))
    prompt_label = _build_label(Vector2(width * 0.5 - 325.0, 632.0), Vector2(650.0, 42.0), 18, Color(1.0, 0.68, 0.22))
    prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    var help := _build_label(Vector2(width - 820.0, 680.0), Vector2(800.0, 30.0), 11, Color(0.68, 0.72, 0.72, 0.86))
    help.text = "W/S throttle · arrows/A/D steer · Q/E roll · X stop · LMB drag steer · SPACE FRAPRAY · T TORPEDO · TAB aim · R restart"
    help.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    weapon_aim = Control.new()
    weapon_aim.name = "WeaponAim"
    weapon_aim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    weapon_aim.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(weapon_aim)
    frap_aim_left = _build_aim_label("FrapRayLeft", "•")
    frap_aim_right = _build_aim_label("FrapRayRight", "•")
    torpedo_aim = _build_aim_label("Torpedo", "×")


func _build_panel(position_2d: Vector2, size_2d: Vector2, color: Color) -> void:
    var panel := ColorRect.new()
    panel.position = position_2d
    panel.size = size_2d
    panel.color = color
    panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(panel)


func _build_label(
    position_2d: Vector2, size_2d: Vector2, font_size: int, color: Color
) -> Label:
    var label := Label.new()
    label.position = position_2d
    label.size = size_2d
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(label)
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


func _update_hud() -> void:
    if title_label == null:
        return
    title_label.text = "JOURNEYBLASTER · MISSION 003 · STARBASE DEFENSE PROTOTYPE V3"
    status_label.text = "MISSION STATE · %s" % mission_state
    objective_label.text = OBJECTIVES.get(mission_state, "")
    sensor_label.text = _sensor_readout()
    weapons_label.text = "%s\nAIM HUD  %s · TAB" % [
        player.weapon_status_text(), "ON" if weapon_aim_enabled else "OFF"
    ]
    flight_label.text = "SHIP VECTOR\nSPEED  %03d m/s\nTHROTTLE  %s%%\nHULL  %03d\nTHRUST  %03d%%" % [
        roundi(player.velocity.length()),
        player.throttle_percent(),
        roundi(player.hull_integrity),
        roundi(player.thrust_efficiency() * 100.0),
    ]
    var pilot_view := player.find_child("SeatPivot", true, false)
    view_label.text = "PILOT CHAIR\nVIEW  %s\nSHIP HEADING\nINDEPENDENT" % pilot_view.current_view_label()
    prompt_label.text = _context_prompt()
    _update_weapon_aim()


func _sensor_readout() -> String:
    var active := _active_pirates()
    var prefix := "SENSO-GLOBES · STARBASE DEFENSE\n"
    if active.is_empty():
        return prefix + "NO HOSTILE RETURNS"
    var nearest: AnimatableBody3D = active[0]
    var nearest_distance := player.global_position.distance_to(nearest.global_position)
    for pirate in active.slice(1):
        var distance := player.global_position.distance_to(pirate.global_position)
        if distance < nearest_distance:
            nearest = pirate
            nearest_distance = distance
    var local_target := player.to_local(nearest.global_position)
    var bearing := rad_to_deg(atan2(local_target.x, -local_target.z))
    var side := "AHEAD"
    if bearing < -4.0:
        side = "LEFT"
    elif bearing > 4.0:
        side = "RIGHT"
    return prefix + "HOSTILE RETURNS  %d\nNEAREST  %s %03d° · %04d m\nATTACK INTENT · UNRESOLVED" % [
        active.size(), side, roundi(absf(bearing)), roundi(nearest_distance)
    ]


func _context_prompt() -> String:
    if mission_state == "BRIEFING":
        return "ENTER · BEGIN STARBASE DEFENSE"
    if mission_state == "COMPLETE":
        return "MISSION COMPLETE · R TO RESTART"
    if mission_state == "FAILED":
        return "MISSION FAILED · FREE FLIGHT · R TO RESTART"
    if is_player_in_safe_hangar():
        return "LAUNCH CLEAR · W THROTTLE · HANGAR SAFE"
    return "REPEL ALL THREE PIRATE FLYERS"


func _update_weapon_aim() -> void:
    weapon_aim.visible = weapon_aim_enabled
    if not weapon_aim_enabled:
        return
    var camera := get_viewport().get_camera_3d()
    if camera == null:
        weapon_aim.visible = false
        return
    var direction := -player.global_basis.z.normalized()
    _position_aim_marker(frap_aim_left, _weapon_impact_point(frap_origin_left.global_position, direction, 650.0), camera)
    _position_aim_marker(frap_aim_right, _weapon_impact_point(frap_origin_right.global_position, direction, 650.0), camera)
    _position_aim_marker(torpedo_aim, _weapon_impact_point(torpedo_origin.global_position, direction, 700.0), camera)


func _weapon_impact_point(origin: Vector3, direction: Vector3, range_m: float) -> Vector3:
    var finish := origin + direction * range_m
    var query := PhysicsRayQueryParameters3D.create(origin, finish)
    query.exclude = [player.get_rid()]
    var result := get_world_3d().direct_space_state.intersect_ray(query)
    return result.get("position", finish)


func _position_aim_marker(marker: Label, point: Vector3, camera: Camera3D) -> void:
    if marker == null or camera.is_position_behind(point):
        if marker:
            marker.visible = false
        return
    var screen := camera.unproject_position(point)
    var viewport_size := get_viewport().get_visible_rect().size
    marker.visible = (
        screen.x >= 0.0 and screen.y >= 0.0
        and screen.x <= viewport_size.x and screen.y <= viewport_size.y
    )
    if marker.visible:
        marker.position = screen - marker.size * 0.5
