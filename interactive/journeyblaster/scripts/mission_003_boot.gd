extends Node3D

const WeaponProjectile = preload("res://scripts/weapon_projectile.gd")
const StarbaseTarget = preload("res://scripts/starbase_target.gd")
const SharedCockpit = preload("res://scripts/jb100_cockpit.gd")
const STARBASE_SCENE = preload("res://generated/scenes/starbase_86_v1.tscn")
const PIRATE_SCENE = preload("res://generated/scenes/pirate_flyer_mk1.tscn")
const EARTH_STARFIGHTER_SCENE = preload(
    "res://generated/scenes/earth_starfighter_docked_v1.tscn"
)

const STARBASE_CENTER := Vector3(0.0, 75.0, 0.0)
const PLANET_POSITION := Vector3(680.0, 260.0, 3000.0)
const OPEN_HANGAR_CENTER_FALLBACK := Vector3(113.86, 10.5, -34.811)
const OPEN_HANGAR_ENTRANCE_FALLBACK := Vector3(104.404, 10.5, -65.741)
const OPEN_HANGAR_EXIT_FALLBACK := Vector3(123.316, 10.5, -3.88)
const PLAYER_HANGAR_START_RATIO := 0.62
const HANGAR_SAFE_RADIUS_M := 32.0
const PIRATE_RETREAT_HITS := 6.0
const PIRATE_DESTROY_HITS := 12.0
const DEFENSE_PERIMETER_M := 5000.0
const HYPERSPACE_RANGE_M := 6000.0
const PLAYER_ATTACK_MIN_ACTIVE_PIRATES := 2
const LAST_PIRATE_STATION_AGGRESSION := 1.6
const STATION_FRIENDLY_FIRE_ODDS := 20
const STATION_ALERT_HISTORY_SIZE := 3
const STARFIGHTER_LAUNCH_DURATION_S := 3.2
const STARFIGHTER_ORBIT_SPEED_RAD_S := 0.22

const OBJECTIVES := {
    "BRIEFING": "Launch from Starbase 86 and repel three attacking pirate flyers.",
    "DEFEND": "Destroy the attackers or drive them beyond the defense perimeter.",
    "COMPLETE": "Starbase 86 is secure. All pirate flyers are gone.",
    "FAILED": "Defense failed. Free flight remains available.",
}

var player: CharacterBody3D
var cockpit
var game_shell: Node3D
var booted := false

var mission_state := "BRIEFING"
var starbase: StaticBody3D
var docked_starfighter: StaticBody3D
var starfighter_secret_state := "DOCKED"
var starfighter_secret_armed := false
var starfighter_launch_elapsed := 0.0
var starfighter_launch_start := Vector3.ZERO
var starfighter_launch_finish := Vector3.ZERO
var starfighter_orbit_angle := 0.0
var starfighter_orbit_radius := 0.0
var starfighter_orbit_height := 0.0
var station_targets: Array[StaticBody3D] = []
var targets_by_category: Dictionary = {}
var pirates: Array[AnimatableBody3D] = []
var station_polar_weapon_emitters: Array[Node3D] = []
var player_attacker: AnimatableBody3D
var station_weapon_timers: Dictionary = {}
var station_shots_fired := 0
var station_friendly_fire_shots := 0
var pirate_torpedoes_fired := 0
var random := RandomNumberGenerator.new()
var weapon_aim_enabled := true
var open_hangar_center := OPEN_HANGAR_CENTER_FALLBACK
var open_hangar_entrance := OPEN_HANGAR_ENTRANCE_FALLBACK
var open_hangar_exit := OPEN_HANGAR_EXIT_FALLBACK
var player_hangar_start := OPEN_HANGAR_CENTER_FALLBACK.lerp(
    OPEN_HANGAR_EXIT_FALLBACK, PLAYER_HANGAR_START_RATIO
)

var hud: CanvasLayer
var title_label: Label
var status_label: Label
var objective_label: Label
var sensor_label: Label
var weapons_label: Label
var flight_label: Label
var view_label: Label
var prompt_label: Label
var failure_overlay: Label
var weapon_aim: Control
var frap_aim_left: Label
var frap_aim_right: Label
var torpedo_aim: Label
var torpedo_charge_indicator: Control
var frap_origin_left: Node3D
var frap_origin_right: Node3D
var torpedo_origin: Node3D
var systems_bars: Dictionary = {}
var systems_value_labels: Dictionary = {}
var systems_torpedo_label: Label
var sensor_globe: Control
var mission_screen_label: Label
var station_report := "STATION REPORTS ALL SYSTEMS OPERATIONAL."
var station_alerts: Array[String] = ["STATION REPORTS ALL SYSTEMS OPERATIONAL."]
var starfield: MultiMeshInstance3D
var solar_sun_disk: MeshInstance3D
var hangar_steady_lights: Array[OmniLight3D] = []
var hangar_emergency_lights: Array[OmniLight3D] = []
var hangar_emergency_materials: Array[StandardMaterial3D] = []
var hangar_strobe_clock := 0.0
var player_collision_damage_cooldown_s := 0.0


func _ready() -> void:
    call_deferred("_boot_mission")


func configure_mission(
    shared_player: CharacterBody3D,
    shared_cockpit: CanvasLayer,
    shell: Node3D
) -> void:
    player = shared_player
    cockpit = shared_cockpit
    game_shell = shell


func _boot_mission() -> void:
    if booted:
        return
    if player == null:
        player = get_node_or_null("player_jb100") as CharacterBody3D
    if player == null:
        push_error("Mission 003 requires the shared JB100 player")
        return
    booted = true
    random.randomize()
    frap_origin_left = player.find_child("frap_hardpoint_left", true, false) as Node3D
    frap_origin_right = player.find_child("frap_hardpoint_right", true, false) as Node3D
    torpedo_origin = player.find_child("torpedo_launcher", true, false) as Node3D
    _configure_mission_cameras()
    _build_environment()
    _spawn_starbase()
    _spawn_docked_starfighter()
    _build_open_hangar_lighting()
    _build_station_targets()
    _build_station_polar_weapon_arcs()
    _position_player_in_open_hangar()
    _spawn_pirates()
    _build_hud()
    player.enable_power_system()
    player.enable_shield_tracking()
    player.ship_disabled.connect(_on_player_disabled)
    player.shields_depleted.connect(_on_player_shields_depleted)
    player.impact.connect(_on_player_impact)
    _set_state("BRIEFING")
    begin_mission()
    print("MISSION-003-RUNTIME-OK: Starbase Defense")


func _process(delta: float) -> void:
    player_collision_damage_cooldown_s = maxf(
        0.0, player_collision_damage_cooldown_s - delta
    )
    _update_space_backdrop()
    _update_hangar_emergency_lights(delta)
    if mission_state != "BRIEFING":
        _update_station_defense(delta)
        _maintain_player_attacker()
        _evaluate_outcome()
    _update_post_success_secret(delta)
    _update_hud()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_BACKSLASH:
                weapon_aim_enabled = not weapon_aim_enabled
            KEY_R:
                if mission_state in ["COMPLETE", "FAILED"]:
                    if game_shell and game_shell.has_method("restart_mission"):
                        game_shell.restart_mission()
                    else:
                        get_tree().reload_current_scene()


func begin_mission() -> void:
    if mission_state != "BRIEFING":
        return
    _set_state("DEFEND")
    failure_overlay.call("show_go")
    for pirate in pirates:
        pirate.ai_enabled = true
    for weapon in _station_defense_mounts():
        station_weapon_timers[weapon.get_instance_id()] = random.randf_range(0.55, 1.1)


func current_state() -> String:
    return mission_state


func _set_state(next_state: String) -> void:
    mission_state = next_state
    if failure_overlay:
        if next_state == "FAILED":
            failure_overlay.call("show_failed")
        elif next_state == "COMPLETE":
            failure_overlay.call("show_success")
    if next_state == "FAILED":
        for pirate in _active_pirates():
            pirate.assign_station_circle()
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
    _build_visible_sun()
    _build_starfield()
    _build_planet_and_moon()


func _configure_mission_cameras() -> void:
    var cockpit_camera := player.find_child("cockpit_camera", true, false) as Camera3D
    var debug_camera := player.find_child("DebugCamera", true, false) as Camera3D
    if cockpit_camera:
        cockpit_camera.far = 12000.0
    if debug_camera:
        debug_camera.far = 12000.0


func _build_visible_sun() -> void:
    solar_sun_disk = MeshInstance3D.new()
    solar_sun_disk.name = "SolarSystemSun"
    solar_sun_disk.add_to_group("mission_003_sun")
    var sun_mesh := SphereMesh.new()
    sun_mesh.radius = 74.0
    sun_mesh.height = 148.0
    sun_mesh.radial_segments = 24
    sun_mesh.rings = 12
    var sun_material := StandardMaterial3D.new()
    sun_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    sun_material.albedo_color = Color(1.0, 0.86, 0.48)
    sun_material.emission_enabled = true
    sun_material.emission = Color(1.0, 0.68, 0.2)
    sun_material.emission_energy_multiplier = 5.5
    sun_mesh.material = sun_material
    solar_sun_disk.mesh = sun_mesh
    add_child(solar_sun_disk)


func _build_starfield() -> void:
    starfield = MultiMeshInstance3D.new()
    starfield.name = "Starfield"
    starfield.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    var star_mesh := SphereMesh.new()
    star_mesh.radius = 1.8
    star_mesh.height = 3.6
    star_mesh.radial_segments = 4
    star_mesh.rings = 2
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.78, 0.88, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.64, 0.77, 1.0)
    material.emission_energy_multiplier = 2.2
    material.set_flag(BaseMaterial3D.FLAG_DONT_RECEIVE_SHADOWS, true)
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
        var distance := star_random.randf_range(2600.0, 4400.0)
        var scale_value := star_random.randf_range(0.55, 1.45)
        multimesh.set_instance_transform(
            index,
            Transform3D(
                Basis.IDENTITY.scaled(Vector3.ONE * scale_value),
                direction * distance
            )
        )
    starfield.multimesh = multimesh
    add_child(starfield)


func _update_space_backdrop() -> void:
    if starfield:
        starfield.global_position = player.global_position
    if solar_sun_disk:
        solar_sun_disk.global_position = (
            player.global_position + Vector3(-1450.0, 920.0, 4200.0)
        )


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
    var center_marker := starbase.find_child("hangar_1_volume_center", true, false) as Node3D
    var entrance_marker := starbase.find_child("hangar_1_entrance", true, false) as Node3D
    var exit_marker := starbase.find_child("hangar_1_exit", true, false) as Node3D
    if center_marker != null and entrance_marker != null and exit_marker != null:
        open_hangar_center = center_marker.global_position
        open_hangar_entrance = entrance_marker.global_position
        open_hangar_exit = exit_marker.global_position
        player_hangar_start = open_hangar_center.lerp(
            open_hangar_exit, PLAYER_HANGAR_START_RATIO
        )


func _spawn_docked_starfighter() -> void:
    docked_starfighter = EARTH_STARFIGHTER_SCENE.instantiate() as StaticBody3D
    docked_starfighter.name = "docked_earth_starfighter"
    docked_starfighter.add_to_group("mission_003_docked_craft")
    add_child(docked_starfighter)
    var corridor_direction := (open_hangar_exit - open_hangar_entrance).normalized()
    var lateral_direction := corridor_direction.cross(Vector3.UP).normalized()
    var parking_position := (
        open_hangar_center.lerp(open_hangar_entrance, 0.52)
        + lateral_direction * 6.8
    )
    parking_position.y = 6.75
    docked_starfighter.global_position = parking_position
    docked_starfighter.look_at(parking_position + corridor_direction, Vector3.UP)
    # The docked craft dresses the bay without narrowing the prototype's
    # through-flight lane. Physical parking collision can follow with a
    # purpose-built hangar navigation mesh.
    docked_starfighter.collision_layer = 0
    docked_starfighter.collision_mask = 0


func _build_open_hangar_lighting() -> void:
    var ceiling_offset := Vector3.UP * 4.25
    var steady_positions := [
        open_hangar_center.lerp(open_hangar_entrance, 0.58) + ceiling_offset,
        open_hangar_center.lerp(open_hangar_exit, 0.68) + ceiling_offset,
    ]
    for index in steady_positions.size():
        var steady := OmniLight3D.new()
        steady.name = "OpenHangarSteadyLight%d" % (index + 1)
        steady.light_color = Color(0.72, 0.86, 1.0)
        steady.light_energy = 5.2
        steady.omni_range = 31.0
        steady.omni_attenuation = 0.72
        steady.shadow_enabled = false
        add_child(steady)
        steady.global_position = steady_positions[index]
        hangar_steady_lights.append(steady)

    var corridor_direction := (open_hangar_exit - open_hangar_entrance).normalized()
    var emergency_center := open_hangar_center + Vector3.UP * 4.65
    var emergency_positions := [
        emergency_center - corridor_direction * 3.0,
        emergency_center + corridor_direction * 3.0,
    ]
    for index in emergency_positions.size():
        var beacon := MeshInstance3D.new()
        beacon.name = "OpenHangarEmergencyBeacon%d" % (index + 1)
        var beacon_mesh := SphereMesh.new()
        beacon_mesh.radius = 0.48
        beacon_mesh.height = 0.96
        beacon_mesh.radial_segments = 12
        beacon_mesh.rings = 6
        var beacon_material := StandardMaterial3D.new()
        beacon_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        beacon_material.albedo_color = Color(0.82, 0.015, 0.01)
        beacon_material.emission_enabled = true
        beacon_material.emission = Color(1.0, 0.01, 0.005)
        beacon_material.emission_energy_multiplier = 2.0
        beacon_mesh.material = beacon_material
        beacon.mesh = beacon_mesh
        add_child(beacon)
        beacon.global_position = emergency_positions[index]
        hangar_emergency_materials.append(beacon_material)

        var emergency := OmniLight3D.new()
        emergency.name = "OpenHangarEmergencyStrobe%d" % (index + 1)
        emergency.light_color = Color(1.0, 0.015, 0.008)
        emergency.light_energy = 0.35
        emergency.omni_range = 24.0
        emergency.omni_attenuation = 0.62
        emergency.shadow_enabled = false
        add_child(emergency)
        emergency.global_position = emergency_positions[index]
        hangar_emergency_lights.append(emergency)


func _update_hangar_emergency_lights(delta: float) -> void:
    hangar_strobe_clock = fmod(hangar_strobe_clock + delta, 1.4)
    for index in hangar_emergency_lights.size():
        var phase := fmod(hangar_strobe_clock + float(index) * 0.7, 1.4)
        var pulse_on := phase < 0.14 or (phase >= 0.26 and phase < 0.40)
        hangar_emergency_lights[index].light_energy = 13.0 if pulse_on else 0.35
        hangar_emergency_materials[index].emission_energy_multiplier = (
            12.0 if pulse_on else 2.0
        )


func _build_station_targets() -> void:
    targets_by_category = {"shield": [], "weapon": [], "hangar": []}
    var placements := {
        "shield": [
            Vector3(0.0, 145.0, 5.0),
            Vector3(64.0, 78.0, 20.0),
            Vector3(-38.0, 22.0, 44.0),
        ],
        "weapon": [
            Vector3(-14.0, 146.0, -20.0),
            Vector3(-72.0, 78.0, -15.0),
            Vector3(34.0, 23.0, -66.0),
        ],
        "hangar": [
            Vector3(113.86, 18.2, -34.811),
            Vector3(-87.077, 18.2, -81.2),
            Vector3(-26.783, 18.2, 116.011),
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
            target.target_damaged.connect(_on_station_target_damaged)
            target.target_disabled.connect(_on_station_target_disabled)
            station_targets.append(target)
            targets_by_category[category].append(target)
            if category == "weapon":
                station_weapon_timers[target.get_instance_id()] = random.randf_range(2.0, 5.0)


func _build_station_polar_weapon_arcs() -> void:
    var polar_mounts := [
        {
            "name": "TopPolarDefenseEmitter",
            "position": STARBASE_CENTER + Vector3(0.0, 118.0, 0.0),
            "arc": "top",
            "system": targets_by_category["weapon"][0],
        },
        {
            "name": "BottomPolarDefenseEmitter",
            "position": STARBASE_CENTER + Vector3(0.0, -118.0, 0.0),
            "arc": "bottom",
            "system": targets_by_category["weapon"][2],
        },
    ]
    for definition in polar_mounts:
        var emitter := Node3D.new()
        emitter.name = definition["name"]
        emitter.set_meta("polar_arc", definition["arc"])
        emitter.set_meta("linked_weapon_system", definition["system"])
        emitter.add_to_group("mission_003_polar_weapon_arc")
        add_child(emitter)
        emitter.global_position = definition["position"]
        station_polar_weapon_emitters.append(emitter)
        station_weapon_timers[emitter.get_instance_id()] = random.randf_range(1.0, 2.2)


func _position_player_in_open_hangar() -> void:
    player.global_position = player_hangar_start
    player.look_at(open_hangar_exit, Vector3.UP)
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
    if mission_state == "FAILED":
        pirate.assign_station_circle()
        return
    var combat_pirates := _combat_capable_pirates()
    if (
        combat_pirates.size() >= PLAYER_ATTACK_MIN_ACTIVE_PIRATES
        and not _player_attacker_is_active()
    ):
        player_attacker = pirate
        pirate.assign_player_attack()
    else:
        var aggression := (
            LAST_PIRATE_STATION_AGGRESSION if combat_pirates.size() == 1 else 1.0
        )
        pirate.assign_pile_on(_remaining_station_targets(), aggression)


func _on_pirate_retreat_started(pirate: AnimatableBody3D) -> void:
    if player_attacker == pirate:
        player_attacker = null
        _maintain_player_attacker()


func _on_pirate_destroyed(pirate: AnimatableBody3D) -> void:
    if player_attacker == pirate:
        player_attacker = null
        _maintain_player_attacker()
    var destroyed_count := pirates.filter(
        func(candidate: AnimatableBody3D) -> bool:
            return candidate.destroyed
    ).size()
    _post_station_alert("STATION REPORTS %d PIRATE %s DESTROYED." % [
        destroyed_count,
        "FLYER" if destroyed_count == 1 else "FLYERS",
    ])
    _evaluate_outcome()


func _on_defense_perimeter_crossed(_pirate: AnimatableBody3D) -> void:
    var retreat_count := pirates.filter(
        func(candidate: AnimatableBody3D) -> bool:
            return candidate.perimeter_crossed
    ).size()
    _post_station_alert("STATION REPORTS %d PIRATE %s %s RETREATED." % [
        retreat_count,
        "FLYER" if retreat_count == 1 else "FLYERS",
        "HAS" if retreat_count == 1 else "HAVE",
    ])
    _evaluate_outcome()


func _on_station_target_damaged(target: StaticBody3D, _remaining_health: float) -> void:
    var system_name: String = str({
        "shield": "SHIELDS",
        "weapon": "WEAPONS",
        "hangar": "HANGARS",
    }.get(target.system_category, target.system_category.to_upper()))
    _post_station_alert("STATION REPORTS DAMAGE TO %s." % system_name)


func _on_station_target_disabled(target: StaticBody3D) -> void:
    var system_name: String = str({
        "shield": "SHIELD",
        "weapon": "WEAPON",
        "hangar": "HANGAR",
    }.get(target.system_category, target.system_category.to_upper()))
    _post_station_alert("STATION REPORTS %s SYSTEM DISABLED." % system_name)
    _evaluate_outcome()


func _post_station_alert(message: String) -> void:
    station_report = message
    station_alerts.push_front(message)
    if station_alerts.size() > STATION_ALERT_HISTORY_SIZE:
        station_alerts.resize(STATION_ALERT_HISTORY_SIZE)
    _refresh_mission_screen()


func _on_player_disabled() -> void:
    if mission_state != "COMPLETE":
        _set_state("FAILED")


func _on_player_shields_depleted(_source_kind: String) -> void:
    if mission_state != "COMPLETE":
        _set_state("FAILED")


func _on_player_impact(_speed_mps: float, collider: Object) -> void:
    if player_collision_damage_cooldown_s > 0.0 or collider == null:
        return
    if not collider is Node:
        return
    var collider_node := collider as Node
    if not (
        collider_node.is_in_group("mission_003_pirate")
        or collider_node.is_in_group("mission_003_starbase")
        or collider_node.is_in_group("mission_003_station_target")
    ):
        return
    player_collision_damage_cooldown_s = 0.8
    player.apply_shield_damage(50.0, "collision")


func _maintain_player_attacker() -> void:
    if mission_state != "DEFEND" or _all_station_targets_disabled():
        return
    var combat_pirates := _combat_capable_pirates()
    if combat_pirates.size() < PLAYER_ATTACK_MIN_ACTIVE_PIRATES:
        if _player_attacker_is_active():
            var aggression := (
                LAST_PIRATE_STATION_AGGRESSION
                if combat_pirates.size() == 1
                else 1.0
            )
            player_attacker.assign_pile_on(_remaining_station_targets(), aggression)
        player_attacker = null
        if combat_pirates.size() == 1:
            var last_pirate := combat_pirates[0]
            if (
                last_pirate.behavior != "PILE_ON"
                or not is_equal_approx(
                    last_pirate.station_attack_aggression,
                    LAST_PIRATE_STATION_AGGRESSION
                )
            ):
                last_pirate.assign_pile_on(
                    _remaining_station_targets(), LAST_PIRATE_STATION_AGGRESSION
                )
        return
    if _player_attacker_is_active():
        return
    player_attacker = null
    for pirate in combat_pirates:
        if (
            pirate.completed_primary_objective
        ):
            player_attacker = pirate
            pirate.assign_player_attack()
            return
    # Keep one flyer pressuring the JB100 from mission start while every other
    # combat-capable flyer continues its station objective.
    player_attacker = combat_pirates[0]
    player_attacker.assign_player_attack()


func _combat_capable_pirates() -> Array[AnimatableBody3D]:
    var combat_pirates: Array[AnimatableBody3D] = []
    for pirate in pirates:
        if (
            pirate.destroyed
            or pirate.perimeter_crossed
            or pirate.hyperspace_departed
            or pirate.behavior in ["RETREAT", "DRIVEN_OFF"]
        ):
            continue
        combat_pirates.append(pirate)
    return combat_pirates


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
    return player.global_position.distance_to(open_hangar_center) <= HANGAR_SAFE_RADIUS_M


func _update_post_success_secret(delta: float) -> void:
    if mission_state != "COMPLETE" or not is_instance_valid(docked_starfighter):
        return
    if starfighter_secret_state == "LAUNCHING":
        _advance_starfighter_launch(delta)
        return
    if starfighter_secret_state == "ORBITING":
        _advance_starfighter_orbit(delta)
        return
    if not is_player_in_safe_hangar():
        starfighter_secret_armed = true
    elif starfighter_secret_armed:
        _launch_docked_starfighter()


func _launch_docked_starfighter() -> void:
    starfighter_secret_state = "LAUNCHING"
    starfighter_launch_elapsed = 0.0
    starfighter_launch_start = docked_starfighter.global_position
    var corridor_direction := (open_hangar_exit - open_hangar_entrance).normalized()
    starfighter_launch_finish = (
        open_hangar_exit + corridor_direction * 115.0 + Vector3.UP * 18.0
    )
    docked_starfighter.look_at(starfighter_launch_finish, Vector3.UP)


func _advance_starfighter_launch(delta: float) -> void:
    starfighter_launch_elapsed += delta
    var progress := clampf(
        starfighter_launch_elapsed / STARFIGHTER_LAUNCH_DURATION_S, 0.0, 1.0
    )
    var eased_progress := smoothstep(0.0, 1.0, progress)
    docked_starfighter.global_position = starfighter_launch_start.lerp(
        starfighter_launch_finish, eased_progress
    )
    var launch_direction := (
        starfighter_launch_finish - starfighter_launch_start
    ).normalized()
    docked_starfighter.look_at(
        docked_starfighter.global_position + launch_direction, Vector3.UP
    )
    if progress < 1.0:
        return
    var radial := docked_starfighter.global_position - STARBASE_CENTER
    starfighter_orbit_radius = maxf(Vector2(radial.x, radial.z).length(), 190.0)
    starfighter_orbit_angle = atan2(radial.z, radial.x)
    starfighter_orbit_height = docked_starfighter.global_position.y
    starfighter_secret_state = "ORBITING"


func _advance_starfighter_orbit(delta: float) -> void:
    starfighter_orbit_angle = fmod(
        starfighter_orbit_angle + STARFIGHTER_ORBIT_SPEED_RAD_S * delta, TAU
    )
    var next_position := Vector3(
        STARBASE_CENTER.x + cos(starfighter_orbit_angle) * starfighter_orbit_radius,
        starfighter_orbit_height,
        STARBASE_CENTER.z + sin(starfighter_orbit_angle) * starfighter_orbit_radius
    )
    var tangent_target := Vector3(
        STARBASE_CENTER.x
        + cos(starfighter_orbit_angle + 0.04) * starfighter_orbit_radius,
        starfighter_orbit_height,
        STARBASE_CENTER.z
        + sin(starfighter_orbit_angle + 0.04) * starfighter_orbit_radius
    )
    docked_starfighter.global_position = next_position
    docked_starfighter.look_at(tangent_target, Vector3.UP)


func fire_pirate_weapon(pirate: AnimatableBody3D, target: Node3D) -> bool:
    if mission_state == "BRIEFING" or pirate.destroyed:
        return false
    if not pirate.can_fire_forward_at(target):
        return false
    var direction := -pirate.global_basis.z.normalized()
    var damage := 10.0 if target == player else _pirate_station_damage(target)
    var exclusions: Array[RID] = []
    for other in pirates:
        exclusions.append(other.get_rid())
    if target != player:
        exclusions.append(starbase.get_rid())
    _spawn_combat_projectile(
        "pirate_plasma",
        pirate.global_position + direction.normalized() * 6.0,
        direction.normalized(),
        132.0,
        damage,
        pirate.get_rid(),
        exclusions
    )
    return true


func fire_pirate_torpedo(
    pirate: AnimatableBody3D, launch_direction: Vector3
) -> bool:
    if (
        mission_state != "DEFEND"
        or pirate.destroyed
        or pirate.torpedoes_remaining <= 0
        or pirate.global_position.distance_to(player.global_position)
        > pirate.REAR_TORPEDO_MAX_RANGE_M
    ):
        return false
    var direction := launch_direction.normalized()
    var exclusions: Array[RID] = [starbase.get_rid()]
    for other in pirates:
        exclusions.append(other.get_rid())
    for station_target in station_targets:
        exclusions.append(station_target.get_rid())
    _spawn_combat_projectile(
        "pirate_torpedo",
        pirate.global_position + direction * 6.0,
        direction,
        190.0,
        10.0,
        pirate.get_rid(),
        exclusions,
        player
    )
    pirate.torpedoes_remaining -= 1
    pirate_torpedoes_fired += 1
    return true


func fire_pirate_rear_torpedo(pirate: AnimatableBody3D) -> bool:
    return fire_pirate_torpedo(pirate, pirate.global_basis.z.normalized())


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
    for weapon_mount in _station_defense_mounts():
        var weapon_system := _weapon_system_for_mount(weapon_mount)
        if weapon_system == null or weapon_system.disabled:
            continue
        var identifier: int = weapon_mount.get_instance_id()
        var timer: float = station_weapon_timers.get(identifier, 0.0) - delta
        if timer > 0.0:
            station_weapon_timers[identifier] = timer
            continue
        var target: Node3D
        var friendly_fire: bool = (
            random.randi_range(1, STATION_FRIENDLY_FIRE_ODDS) == 1
            and not is_player_in_safe_hangar()
            and not player.disabled_in_space
        )
        if friendly_fire:
            target = player
            station_friendly_fire_shots += 1
        else:
            var arc_targets := _targets_for_weapon_arc(
                weapon_mount, possible_targets
            )
            target = arc_targets[
                random.randi_range(0, arc_targets.size() - 1)
            ]
        var target_range: float = weapon_mount.global_position.distance_to(
            target.global_position
        )
        var aim_spread: float = _station_defense_spread_m(
            target_range, weapon_system.effectiveness()
        )
        var aim_error := Vector3(
            random.randf_range(-aim_spread, aim_spread),
            random.randf_range(-aim_spread * 0.68, aim_spread * 0.68),
            random.randf_range(-aim_spread, aim_spread)
        )
        var direction: Vector3 = (
            target.global_position + aim_error - weapon_mount.global_position
        )
        var exclusions: Array[RID] = [starbase.get_rid()]
        for station_target in station_targets:
            exclusions.append(station_target.get_rid())
        _spawn_combat_projectile(
            "starbase_plasma",
            weapon_mount.global_position + direction.normalized() * 7.0,
            direction.normalized(),
            155.0,
            10.0 if friendly_fire else 0.8,
            weapon_system.get_rid(),
            exclusions
        )
        station_shots_fired += 1
        station_weapon_timers[identifier] = lerpf(
            12.0, 5.2, weapon_system.effectiveness()
        ) + random.randf_range(0.0, 2.0)


func _station_defense_mounts() -> Array[Node3D]:
    var mounts: Array[Node3D] = []
    for weapon in targets_by_category.get("weapon", []):
        mounts.append(weapon)
    mounts.append_array(station_polar_weapon_emitters)
    return mounts


func _weapon_system_for_mount(mount: Node3D) -> StaticBody3D:
    if mount.has_meta("linked_weapon_system"):
        var linked_system: Variant = mount.get_meta("linked_weapon_system")
        if linked_system is StaticBody3D:
            return linked_system as StaticBody3D
    return mount as StaticBody3D


func _targets_for_weapon_arc(
    mount: Node3D, possible_targets: Array[AnimatableBody3D]
) -> Array[AnimatableBody3D]:
    var arc_name := str(mount.get_meta("polar_arc", ""))
    if arc_name.is_empty():
        return possible_targets
    var arc_targets: Array[AnimatableBody3D] = []
    for pirate in possible_targets:
        var above_center := pirate.global_position.y >= STARBASE_CENTER.y
        if (arc_name == "top" and above_center) or (
            arc_name == "bottom" and not above_center
        ):
            arc_targets.append(pirate)
    return possible_targets if arc_targets.is_empty() else arc_targets


func _station_defense_spread_m(target_range: float, effectiveness: float) -> float:
    var range_factor := clampf((target_range - 20.0) / 770.0, 0.0, 1.0)
    var healthy_spread := lerpf(0.15, 23.0, pow(range_factor, 1.65))
    return healthy_spread * lerpf(2.2, 1.0, clampf(effectiveness, 0.0, 1.0))


func _spawn_combat_projectile(
    kind: String,
    start: Vector3,
    direction: Vector3,
    speed: float,
    damage: float,
    shooter: RID,
    exclusions: Array[RID],
    target: Node3D = null
) -> void:
    var projectile := WeaponProjectile.new()
    projectile.configure(
        kind, start, direction, speed, damage, shooter, exclusions, target
    )
    add_child(projectile)


func _build_hud() -> void:
    if cockpit == null:
        cockpit = SharedCockpit.new()
        cockpit.name = "HUD"
        add_child(cockpit)
    hud = cockpit
    var contacts: Array[Node3D] = [starbase, docked_starfighter]
    for pirate in pirates:
        contacts.append(pirate)
    cockpit.configure(player, "003", contacts)
    systems_bars = cockpit.systems_bars
    systems_value_labels = cockpit.systems_value_labels
    systems_torpedo_label = cockpit.systems_torpedo_label
    sensor_globe = cockpit.sensor_globe
    mission_screen_label = cockpit.mission_screen_label
    weapon_aim = cockpit.weapon_aim
    frap_aim_left = cockpit.frap_aim_left
    frap_aim_right = cockpit.frap_aim_right
    torpedo_aim = cockpit.torpedo_aim
    torpedo_charge_indicator = cockpit.torpedo_charge_indicator
    failure_overlay = cockpit.announcement


func _update_hud() -> void:
    if mission_screen_label == null:
        return
    cockpit.update_systems()
    _refresh_mission_screen()
    _update_weapon_aim()


func _refresh_mission_screen() -> void:
    if mission_screen_label == null:
        return
    var compact_alerts: Array[String] = []
    for alert in station_alerts:
        compact_alerts.append(alert.trim_prefix("STATION REPORTS "))
    cockpit.set_mission_display(
        mission_state, OBJECTIVES.get(mission_state, ""), compact_alerts
    )


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
    var torpedo_point := _weapon_impact_point(
        torpedo_origin.global_position, direction, 700.0
    )
    if (
        player.torpedo_charging
        and player.torpedo_lock_candidate != null
        and is_instance_valid(player.torpedo_lock_candidate)
    ):
        torpedo_point = player.torpedo_lock_candidate.global_position
    _position_aim_marker(torpedo_aim, torpedo_point, camera)
    _update_torpedo_charge_indicator()


func _update_torpedo_charge_indicator() -> void:
    var charging: bool = player.torpedo_charging
    var hot: bool = charging and player.torpedo_has_live_lock()
    var lock_scale: float = player.torpedo_lock_reticle_scale()
    torpedo_aim.pivot_offset = torpedo_aim.size * 0.5
    torpedo_aim.scale = Vector2.ONE * lock_scale
    torpedo_aim.add_theme_color_override(
        "font_color",
        Color(0.12, 0.66, 1.0) if hot else Color(1.0, 0.12, 0.08)
    )
    torpedo_charge_indicator.position = (
        torpedo_aim.position + torpedo_aim.size * 0.5
        - torpedo_charge_indicator.size * 0.5
    )
    torpedo_charge_indicator.pivot_offset = torpedo_charge_indicator.size * 0.5
    torpedo_charge_indicator.scale = Vector2.ONE * lock_scale
    torpedo_charge_indicator.set_charge_progress(player.torpedo_charge_ratio())
    torpedo_charge_indicator.visible = charging and torpedo_aim.visible


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
