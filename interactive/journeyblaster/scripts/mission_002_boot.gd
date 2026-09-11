extends Node3D

const CombatEffects = preload("res://scripts/combat_effects.gd")
const TorpedoChargeIndicator = preload("res://scripts/torpedo_charge_indicator.gd")
const ASTEROID_SCENES := [
    preload("res://generated/scenes/asteroid_round_v1.tscn"),
    preload("res://generated/scenes/asteroid_cratered_v1.tscn"),
    preload("res://generated/scenes/asteroid_jagged_v1.tscn"),
    preload("res://generated/scenes/asteroid_oblong_v1.tscn"),
]

const PRIMARY_START := Vector3(0.0, 0.0, -250.0)
const PLANET_CENTER := Vector3(0.0, -90.0, -1450.0)
const ATMOSPHERE_FAILURE_Z := -915.0
const CHARGE_PLACEMENT_WINDOW_S := 180.0
const PRIMARY_PLACEMENT_DEADLINE_Z := -555.0
const DEBRIS_CHASE_WINDOW_S := 60.0
const PRIMARY_FALL_SPEED_MPS := (
    (PRIMARY_START.z - PRIMARY_PLACEMENT_DEADLINE_Z)
    / CHARGE_PLACEMENT_WINDOW_S
)
const PLACEMENT_RANGE_M := 125.0
const SAFE_DETONATION_RANGE_M := 155.0
const REQUIRED_CHARGES := 3

const OBJECTIVES := {
    "BRIEFING": "Intercept the planet-bound asteroid before atmospheric entry.",
    "INTERCEPT": "Close on the primary asteroid and match its falling course.",
    "PLACEMENT_READY": "Select the reverse tow beam and place three fracture charges.",
    "CHARGE_PLACEMENT": "Fly around the asteroid and place charges at all blue targets.",
    "CLEAR_BLAST": "All charges set. Clear the asteroid before detonation.",
    "DETONATION_READY": "Safe distance reached. Detonate the fracture charges.",
    "BREAKUP": "Controlled breakup in progress. Prepare to pursue the debris.",
    "DEBRIS_CHASE": "Destroy every dangerous fragment before atmospheric penetration.",
    "COMPLETE": "Impact corridor clear. Planetfall threat atomized.",
    "FAILED": "A dangerous fragment penetrated the atmospheric safety boundary.",
}

@onready var player := $player_jb100 as CharacterBody3D

var mission_state := "BRIEFING"
var state_elapsed := 0.0
var charge_phase_elapsed := 0.0
var chase_elapsed := 0.0
var primary_asteroid: StaticBody3D
var charge_sites: Array[Node3D] = []
var charges_placed := 0
var placement_cursor := Vector2.ZERO
var placement_in_progress := false
var placement_elapsed := 0.0
var placement_duration := 0.9
var placement_target: Node3D
var acquired_site: Node3D
var placement_surface_point := Vector3.ZERO
var breakup_spawned := false
var natural_breakup_triggered := false
var debris_was_present := false
var major_velocities: Dictionary = {}
var registered_fragments: Dictionary = {}
var weapon_aim_enabled := true
var towbeam_mode := false

var effect_origin: Node3D
var frap_origin_left: Node3D
var frap_origin_right: Node3D
var torpedo_origin: Node3D
var placement_beam: MeshInstance3D
var placement_beam_mesh: CylinderMesh
var hud: CanvasLayer
var title_label: Label
var status_label: Label
var objective_label: Label
var sensor_label: Label
var weapons_label: Label
var prompt_label: Label
var placement_reticle: Label
var frap_aim_left: Label
var frap_aim_right: Label
var torpedo_aim: Label
var torpedo_charge_indicator: Control
var weapon_aim: Control


func _ready() -> void:
    effect_origin = player.find_child(
        "effect_exclusion_center", true, false
    ) as Node3D
    frap_origin_left = player.find_child(
        "frap_hardpoint_left", true, false
    ) as Node3D
    frap_origin_right = player.find_child(
        "frap_hardpoint_right", true, false
    ) as Node3D
    torpedo_origin = player.find_child(
        "torpedo_launcher", true, false
    ) as Node3D
    _build_space_environment()
    _build_planet()
    _spawn_primary_asteroid()
    _build_placement_beam()
    _build_hud()
    _set_state("BRIEFING")
    begin_mission()
    print("MISSION-002-RUNTIME-OK: Planetfall")


func _process(delta: float) -> void:
    state_elapsed += delta
    _update_phase_clocks(delta)
    _advance_planetfall_targets(delta)
    if mission_state == "FAILED":
        _update_hud()
        return
    if mission_state == "INTERCEPT" and _distance_to_primary() <= PLACEMENT_RANGE_M:
        _set_state("CHARGE_PLACEMENT" if towbeam_mode else "PLACEMENT_READY")
    elif mission_state == "CHARGE_PLACEMENT":
        _update_placement(delta)
    elif mission_state == "CLEAR_BLAST":
        if _distance_to_primary() >= SAFE_DETONATION_RANGE_M:
            _set_state("DETONATION_READY")
    elif mission_state == "BREAKUP" and state_elapsed >= 1.0:
        _spawn_major_fragments()
        _set_state("DEBRIS_CHASE")
    elif mission_state == "DEBRIS_CHASE":
        _register_new_fragments()
        _trigger_natural_breakup_if_due()
        _update_atmospheric_heating()
        _evaluate_debris_outcome()
    _update_hud()


func _update_phase_clocks(delta: float) -> void:
    if mission_state in ["INTERCEPT", "PLACEMENT_READY", "CHARGE_PLACEMENT"]:
        charge_phase_elapsed += delta
        if charge_phase_elapsed >= CHARGE_PLACEMENT_WINDOW_S:
            _set_state("FAILED")
    elif mission_state in ["BREAKUP", "DEBRIS_CHASE"]:
        chase_elapsed += delta
        if (
            chase_elapsed >= DEBRIS_CHASE_WINDOW_S
            and (mission_state == "BREAKUP" or _active_threat_count() > 0)
        ):
            _set_state("FAILED")


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_G:
                request_interaction()
            KEY_SLASH:
                toggle_towbeam_mode()
            KEY_SPACE:
                if towbeam_mode and mission_state == "CHARGE_PLACEMENT":
                    fire_towbeam_charge()
                    get_viewport().set_input_as_handled()
            KEY_TAB:
                weapon_aim_enabled = not weapon_aim_enabled
            KEY_R:
                if mission_state in ["COMPLETE", "FAILED"]:
                    get_tree().reload_current_scene()


func begin_mission() -> void:
    if mission_state == "BRIEFING":
        _set_state("INTERCEPT")


func request_interaction() -> void:
    if mission_state == "DETONATION_READY":
        _begin_controlled_breakup()


func toggle_towbeam_mode() -> void:
    if mission_state not in ["INTERCEPT", "PLACEMENT_READY", "CHARGE_PLACEMENT"]:
        return
    towbeam_mode = not towbeam_mode
    player.set_frapray_fire_suppressed(towbeam_mode)
    placement_beam.visible = false
    if mission_state != "INTERCEPT":
        _set_state("CHARGE_PLACEMENT" if towbeam_mode else "PLACEMENT_READY")


func fire_towbeam_charge() -> bool:
    if (
        not towbeam_mode
        or mission_state != "CHARGE_PLACEMENT"
        or placement_in_progress
        or acquired_site == null
    ):
        return false
    _attempt_charge_placement()
    return true


func current_state() -> String:
    return mission_state


func _set_state(next_state: String) -> void:
    if mission_state == next_state and state_elapsed > 0.0:
        return
    mission_state = next_state
    state_elapsed = 0.0
    if next_state not in ["INTERCEPT", "PLACEMENT_READY", "CHARGE_PLACEMENT"]:
        towbeam_mode = false
        player.set_frapray_fire_suppressed(false)
        placement_in_progress = false
        placement_beam.visible = false


func _advance_planetfall_targets(delta: float) -> void:
    if (
        is_instance_valid(primary_asteroid)
        and mission_state in [
            "INTERCEPT",
            "PLACEMENT_READY",
            "CHARGE_PLACEMENT",
            "CLEAR_BLAST",
            "DETONATION_READY",
        ]
    ):
        primary_asteroid.position.z -= PRIMARY_FALL_SPEED_MPS * delta
        primary_asteroid.rotate_object_local(Vector3.RIGHT, deg_to_rad(2.2) * delta)
        primary_asteroid.rotate_object_local(Vector3.BACK, deg_to_rad(3.4) * delta)

    for major in get_tree().get_nodes_in_group("planetfall_major"):
        if not is_instance_valid(major) or major.destroyed:
            continue
        var velocity: Vector3 = major_velocities.get(
            major.get_instance_id(), Vector3(0.0, 0.0, -20.0)
        )
        major.global_position += velocity * delta
        major.rotate_object_local(Vector3.RIGHT, deg_to_rad(8.0) * delta)
        major.rotate_object_local(Vector3.UP, deg_to_rad(5.0) * delta)


func _spawn_primary_asteroid() -> void:
    primary_asteroid = ASTEROID_SCENES[0].instantiate() as StaticBody3D
    primary_asteroid.name = "planetfall_primary_asteroid"
    primary_asteroid.scale = Vector3.ONE * 9.0
    primary_asteroid.integrity = 9999.0
    primary_asteroid.fragment_count = 0
    add_child(primary_asteroid)
    primary_asteroid.global_position = PRIMARY_START
    primary_asteroid.rotation_degrees = Vector3(18.0, 27.0, 9.0)
    primary_asteroid.add_to_group("planetfall_primary")
    _apply_rock_material(primary_asteroid, Color(0.24, 0.205, 0.17))
    var site_positions := [
        Vector3(0.0, 1.4, 5.15),
        Vector3(-4.75, 1.65, 1.35),
        Vector3(4.15, -3.05, -0.75),
    ]
    for index in REQUIRED_CHARGES:
        _build_charge_site(index, site_positions[index])


func _build_charge_site(index: int, local_position: Vector3) -> void:
    var site := Node3D.new()
    site.name = "fracture_site_%d" % (index + 1)
    site.position = local_position
    site.set_meta("placed", false)
    site.set_meta("site_index", index)
    primary_asteroid.add_child(site)

    var marker := MeshInstance3D.new()
    marker.name = "FractureTarget"
    var mesh := TorusMesh.new()
    mesh.inner_radius = 0.18
    mesh.outer_radius = 0.34
    mesh.rings = 12
    mesh.ring_segments = 6
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.08, 0.52, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.02, 0.24, 1.0)
    material.emission_energy_multiplier = 5.0
    mesh.material = material
    marker.mesh = mesh
    marker.look_at_from_position(Vector3.ZERO, local_position.normalized(), Vector3.UP)
    site.add_child(marker)
    charge_sites.append(site)


func _update_placement(delta: float) -> void:
    if placement_in_progress:
        placement_elapsed += delta
        var ratio := clampf(placement_elapsed / placement_duration, 0.0, 1.0)
        var start := _beam_visible_start(placement_target.global_position)
        var tip := start.lerp(
            placement_target.global_position,
            smoothstep(0.0, 1.0, ratio)
        )
        _update_beam_geometry(start, tip)
        if ratio >= 1.0:
            _finish_charge_placement()
        return
    _update_placement_acquisition()


func _update_placement_acquisition() -> void:
    acquired_site = null
    var camera := get_viewport().get_camera_3d()
    if camera == null:
        placement_beam.visible = false
        return
    var fire_direction := -player.global_basis.z.normalized()
    var ray_origin := effect_origin.global_position
    var ray_finish := ray_origin + fire_direction * PLACEMENT_RANGE_M
    var query := PhysicsRayQueryParameters3D.create(ray_origin, ray_finish)
    query.exclude = [player.get_rid()]
    var result := get_world_3d().direct_space_state.intersect_ray(query)
    placement_surface_point = ray_finish
    if result.get("collider") == primary_asteroid:
        placement_surface_point = result.get("position", Vector3.ZERO)

    var nearest_surface_distance := 12.0
    for site in charge_sites:
        if site.get_meta("placed", false) or camera.is_position_behind(site.global_position):
            continue
        if effect_origin.global_position.distance_to(site.global_position) > PLACEMENT_RANGE_M:
            continue
        var surface_distance := site.global_position.distance_to(placement_surface_point)
        if (
            result.get("collider") != primary_asteroid
            or surface_distance >= nearest_surface_distance
        ):
            continue
        if not _site_has_line_of_sight(site, camera):
            continue
        nearest_surface_distance = surface_distance
        acquired_site = site

    var reticle_point := (
        acquired_site.global_position if acquired_site else placement_surface_point
    )
    if not camera.is_position_behind(reticle_point):
        placement_cursor = camera.unproject_position(reticle_point)
    placement_beam.visible = false


func _site_has_line_of_sight(site: Node3D, camera: Camera3D) -> bool:
    # The primary uses a spherical gameplay collision proxy. A surface point
    # is visible only on the camera-facing hemisphere; points around the limb
    # or far side therefore require the pilot to fly around the asteroid.
    var surface_normal := (
        site.global_position - primary_asteroid.global_position
    ).normalized()
    var toward_camera := (
        camera.global_position - site.global_position
    ).normalized()
    return surface_normal.dot(toward_camera) > 0.04


func _attempt_charge_placement() -> void:
    if placement_in_progress or acquired_site == null:
        return
    placement_target = acquired_site
    placement_in_progress = true
    placement_elapsed = 0.0


func _finish_charge_placement() -> void:
    placement_in_progress = false
    if placement_target == null or placement_target.get_meta("placed", false):
        return
    placement_target.set_meta("placed", true)
    charges_placed += 1
    _attach_charge_visual(placement_target)
    placement_target = null
    placement_beam.visible = false
    if charges_placed >= REQUIRED_CHARGES:
        _set_state("CLEAR_BLAST")


func force_place_charge_for_test(index: int) -> void:
    if index < 0 or index >= charge_sites.size():
        return
    placement_target = charge_sites[index]
    _finish_charge_placement()


func _attach_charge_visual(site: Node3D) -> void:
    var target_visual := site.get_node_or_null("FractureTarget") as MeshInstance3D
    if target_visual:
        target_visual.visible = false
    var charge := MeshInstance3D.new()
    charge.name = "PlacedDemolitionCharge"
    var mesh := BoxMesh.new()
    mesh.size = Vector3(0.42, 0.16, 0.62)
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.12, 0.46, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.03, 0.26, 1.0)
    material.emission_energy_multiplier = 6.0
    mesh.material = material
    charge.mesh = mesh
    site.add_child(charge)
    var light := OmniLight3D.new()
    light.name = "ChargeArmedLight"
    light.light_color = Color(0.08, 0.42, 1.0)
    light.light_energy = 3.5
    light.omni_range = 3.0
    site.add_child(light)


func _build_placement_beam() -> void:
    placement_beam = MeshInstance3D.new()
    placement_beam.name = "ReverseTowPlacementBeam"
    placement_beam.add_to_group("mission_002_placement_beam")
    placement_beam_mesh = CylinderMesh.new()
    placement_beam_mesh.top_radius = 0.08
    placement_beam_mesh.bottom_radius = 0.035
    placement_beam_mesh.height = 1.0
    placement_beam_mesh.radial_segments = 8
    var material := StandardMaterial3D.new()
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.08, 0.48, 1.0, 0.82)
    material.emission_enabled = true
    material.emission = Color(0.015, 0.2, 1.0)
    material.emission_energy_multiplier = 4.5
    placement_beam_mesh.material = material
    placement_beam.mesh = placement_beam_mesh
    placement_beam.visible = false
    add_child(placement_beam)


func _beam_visible_start(target: Vector3) -> Vector3:
    var center := effect_origin.global_position
    var direction := target - center
    if direction.length() <= 0.001:
        return center
    var radius: float = effect_origin.get_meta("effect_exclusion_radius_m", 3.25)
    var clearance: float = effect_origin.get_meta("effect_exclusion_clearance_m", 0.1)
    return center + direction.normalized() * minf(direction.length(), radius + clearance)


func _update_beam_geometry(start: Vector3, finish: Vector3) -> void:
    var direction := finish - start
    if direction.length() <= 0.01:
        placement_beam.visible = false
        return
    placement_beam.visible = true
    placement_beam_mesh.height = direction.length()
    var alignment := Basis(Quaternion(Vector3.UP, direction.normalized()))
    placement_beam.global_transform = Transform3D(alignment, (start + finish) * 0.5)


func _begin_controlled_breakup() -> void:
    if not is_instance_valid(primary_asteroid):
        return
    _set_state("BREAKUP")
    for site in charge_sites:
        CombatEffects.spawn_dust_cloud(self, site.global_position, 2.8, 7)
    CombatEffects.spawn_dust_cloud(
        self, primary_asteroid.global_position, 18.0, 34
    )


func _spawn_major_fragments() -> void:
    if breakup_spawned:
        return
    breakup_spawned = true
    var center := (
        primary_asteroid.global_position
        if is_instance_valid(primary_asteroid)
        else PRIMARY_START
    )
    if is_instance_valid(primary_asteroid):
        primary_asteroid.queue_free()
    var offsets := [
        Vector3(-16.0, 8.0, 0.0),
        Vector3(15.0, -6.0, -3.0),
        Vector3(2.0, 15.0, 5.0),
    ]
    var lateral_velocities := [
        Vector2(-2.8, 1.2),
        Vector2(3.2, -1.0),
        Vector2(0.8, 2.6),
    ]
    var fall_factors := [1.0, 0.93, 0.88]
    var scales := [2.35, 2.1, 1.9]
    for index in 3:
        var major := ASTEROID_SCENES[index + 1].instantiate() as StaticBody3D
        major.name = "planetfall_major_%d" % (index + 1)
        major.scale = Vector3.ONE * scales[index]
        major.integrity = 3.0
        major.fragment_count = 3
        add_child(major)
        major.global_position = center + offsets[index]
        major.rotation_degrees = Vector3(17.0 * index, 29.0, 13.0 * index)
        major.add_to_group("planetfall_major")
        _apply_rock_material(
            major,
            Color(0.2 + index * 0.025, 0.18, 0.16 - index * 0.015)
        )
        var remaining_time := maxf(1.0, DEBRIS_CHASE_WINDOW_S - chase_elapsed)
        var boundary_speed := (
            (major.global_position.z - ATMOSPHERE_FAILURE_Z) / remaining_time
        )
        major_velocities[major.get_instance_id()] = Vector3(
            lateral_velocities[index].x,
            lateral_velocities[index].y,
            -boundary_speed * fall_factors[index]
        )
    debris_was_present = true


func _register_new_fragments() -> void:
    for fragment in get_tree().get_nodes_in_group("asteroid_fragment"):
        var identifier := fragment.get_instance_id()
        if registered_fragments.has(identifier):
            continue
        registered_fragments[identifier] = true
        fragment.add_to_group("planetfall_debris")
        var remaining_time := maxf(1.0, DEBRIS_CHASE_WINDOW_S - chase_elapsed)
        fragment.linear_velocity.z = (
            (ATMOSPHERE_FAILURE_Z - fragment.global_position.z) / remaining_time
        ) * 0.94


func _trigger_natural_breakup_if_due() -> void:
    if natural_breakup_triggered or chase_elapsed < 26.0:
        return
    for major in get_tree().get_nodes_in_group("planetfall_major"):
        if is_instance_valid(major) and not major.destroyed:
            natural_breakup_triggered = true
            major.call("_break_apart", "natural_breakup", Vector3(0.0, 0.0, -1.0))
            return


func _update_atmospheric_heating() -> void:
    for fragment in get_tree().get_nodes_in_group("planetfall_debris"):
        if not is_instance_valid(fragment):
            continue
        if fragment.global_position.z <= -650.0 and not fragment.has_node("EntryGlow"):
            var glow := OmniLight3D.new()
            glow.name = "EntryGlow"
            glow.light_color = Color(1.0, 0.24, 0.035)
            glow.light_energy = 2.8
            glow.omni_range = 8.0
            fragment.add_child(glow)


func _evaluate_debris_outcome() -> void:
    if mission_state == "FAILED":
        return
    var majors := get_tree().get_nodes_in_group("planetfall_major").filter(
        func(node: Node) -> bool: return is_instance_valid(node) and not node.destroyed
    )
    var fragments := get_tree().get_nodes_in_group("planetfall_debris").filter(
        func(node: Node) -> bool: return is_instance_valid(node) and not node.destroyed
    )
    if debris_was_present and majors.is_empty() and fragments.is_empty():
        _set_state("COMPLETE")


func _distance_to_primary() -> float:
    if not is_instance_valid(primary_asteroid):
        return INF
    return player.global_position.distance_to(primary_asteroid.global_position)


func _build_space_environment() -> void:
    var world_environment := WorldEnvironment.new()
    world_environment.name = "WorldEnvironment"
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.0015, 0.003, 0.009)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.18, 0.23, 0.34)
    environment.ambient_light_energy = 0.42
    environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
    world_environment.environment = environment
    add_child(world_environment)

    var sunlight := DirectionalLight3D.new()
    sunlight.name = "SystemSun"
    sunlight.rotation_degrees = Vector3(-28.0, -34.0, 9.0)
    sunlight.light_color = Color(0.78, 0.87, 1.0)
    sunlight.light_energy = 1.55
    sunlight.shadow_enabled = true
    add_child(sunlight)
    _build_starfield()


func _build_starfield() -> void:
    var stars := MultiMeshInstance3D.new()
    stars.name = "Starfield"
    var star_mesh := SphereMesh.new()
    star_mesh.radius = 0.5
    star_mesh.height = 1.0
    star_mesh.radial_segments = 4
    star_mesh.rings = 2
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.78, 0.88, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.68, 0.8, 1.0)
    material.emission_energy_multiplier = 2.0
    star_mesh.material = material
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = star_mesh
    multimesh.instance_count = 280
    var random := RandomNumberGenerator.new()
    random.seed = 20000202
    for index in multimesh.instance_count:
        var direction := Vector3(
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0)
        ).normalized()
        var distance := random.randf_range(850.0, 1250.0)
        var star_scale := random.randf_range(0.3, 1.05)
        multimesh.set_instance_transform(
            index,
            Transform3D(
                Basis.IDENTITY.scaled(Vector3.ONE * star_scale),
                direction * distance
            )
        )
    stars.multimesh = multimesh
    add_child(stars)


func _build_planet() -> void:
    var planet := MeshInstance3D.new()
    planet.name = "Planet"
    planet.add_to_group("mission_002_planet")
    var planet_mesh := SphereMesh.new()
    planet_mesh.radius = 480.0
    planet_mesh.height = 960.0
    planet_mesh.radial_segments = 64
    planet_mesh.rings = 32
    var surface := ShaderMaterial.new()
    var surface_shader := Shader.new()
    surface_shader.code = """
shader_type spatial;
render_mode cull_back, diffuse_burley;
void fragment() {
    float continents = sin(NORMAL.x * 11.0 + sin(NORMAL.z * 7.0));
    continents += sin(NORMAL.y * 17.0 - NORMAL.x * 5.0) * 0.55;
    continents += sin((NORMAL.x + NORMAL.z) * 23.0) * 0.22;
    float land = smoothstep(0.28, 0.46, continents);
    vec3 ocean = vec3(0.018, 0.095, 0.19);
    vec3 terrain = mix(vec3(0.12, 0.18, 0.085), vec3(0.32, 0.27, 0.13), NORMAL.y * 0.5 + 0.5);
    ALBEDO = mix(ocean, terrain, land);
    ROUGHNESS = 0.9;
}
"""
    surface.shader = surface_shader
    planet_mesh.material = surface
    planet.mesh = planet_mesh
    planet.position = PLANET_CENTER
    add_child(planet)

    var atmosphere := MeshInstance3D.new()
    atmosphere.name = "AtmosphereShell"
    atmosphere.add_to_group("mission_002_atmosphere")
    var atmosphere_mesh := SphereMesh.new()
    atmosphere_mesh.radius = 505.0
    atmosphere_mesh.height = 1010.0
    atmosphere_mesh.radial_segments = 64
    atmosphere_mesh.rings = 32
    var air := ShaderMaterial.new()
    var air_shader := Shader.new()
    air_shader.code = """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_back;
void fragment() {
    float rim = pow(1.0 - max(dot(normalize(NORMAL), normalize(VIEW)), 0.0), 3.2);
    ALBEDO = vec3(0.035, 0.28, 0.95);
    EMISSION = vec3(0.015, 0.12, 0.55) * (0.4 + rim * 2.4);
    ALPHA = 0.012 + rim * 0.52;
}
"""
    air.shader = air_shader
    atmosphere_mesh.material = air
    atmosphere.mesh = atmosphere_mesh
    atmosphere.position = PLANET_CENTER
    add_child(atmosphere)


func _apply_rock_material(body: Node, tint: Color) -> void:
    var rock := StandardMaterial3D.new()
    rock.albedo_color = tint
    rock.roughness = 0.96
    for candidate in body.find_children("*", "MeshInstance3D", true, false):
        var mesh_instance := candidate as MeshInstance3D
        if mesh_instance:
            mesh_instance.material_override = rock


func _build_hud() -> void:
    hud = CanvasLayer.new()
    hud.name = "HUD"
    add_child(hud)
    _build_panel(Vector2(20.0, 20.0), Vector2(760.0, 126.0), Color(0.02, 0.035, 0.04, 0.9))
    title_label = _build_label(Vector2(38.0, 32.0), Vector2(710.0, 25.0), 14, Color(0.38, 0.92, 0.67))
    status_label = _build_label(Vector2(38.0, 59.0), Vector2(710.0, 24.0), 12, Color(0.92, 0.89, 0.79))
    objective_label = _build_label(Vector2(38.0, 87.0), Vector2(710.0, 26.0), 13, Color(0.76, 0.84, 0.88))

    var viewport_width := get_viewport().get_visible_rect().size.x
    _build_panel(Vector2(viewport_width - 400.0, 20.0), Vector2(380.0, 154.0), Color(0.055, 0.032, 0.012, 0.9))
    sensor_label = _build_label(Vector2(viewport_width - 382.0, 35.0), Vector2(350.0, 130.0), 13, Color(1.0, 0.63, 0.18))
    _build_panel(Vector2(viewport_width - 400.0, 186.0), Vector2(380.0, 120.0), Color(0.018, 0.032, 0.07, 0.9))
    weapons_label = _build_label(Vector2(viewport_width - 382.0, 198.0), Vector2(350.0, 105.0), 13, Color(0.42, 0.68, 1.0))

    prompt_label = _build_label(Vector2(viewport_width * 0.5 - 330.0, 638.0), Vector2(660.0, 42.0), 18, Color(1.0, 0.68, 0.22))
    prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    var help := _build_label(Vector2(viewport_width - 850.0, 684.0), Vector2(830.0, 25.0), 11, Color(0.68, 0.72, 0.72, 0.86))
    help.text = "W/S throttle · arrows/A/D steer · Q/E roll · X recenter · ESC stop · mouse steer · LMB FRAPRAY · hold/release RMB TORPEDO · /? FRAPRAY/TOW · SPACE place · G detonate"
    help.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

    weapon_aim = Control.new()
    weapon_aim.name = "WeaponAim"
    weapon_aim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    weapon_aim.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(weapon_aim)
    frap_aim_left = _build_aim_label("FrapRayLeft", "•", Color(1.0, 0.12, 0.08), 14)
    frap_aim_right = _build_aim_label("FrapRayRight", "•", Color(1.0, 0.12, 0.08), 14)
    torpedo_aim = _build_aim_label("Torpedo", "×", Color(1.0, 0.12, 0.08), 14)
    torpedo_charge_indicator = TorpedoChargeIndicator.new()
    torpedo_charge_indicator.name = "TorpedoChargeIndicator"
    torpedo_charge_indicator.size = Vector2(31.0, 31.0)
    weapon_aim.add_child(torpedo_charge_indicator)

    placement_reticle = Label.new()
    placement_reticle.name = "BluePlacementReticle"
    placement_reticle.text = "○"
    placement_reticle.size = Vector2(48.0, 48.0)
    placement_reticle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    placement_reticle.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    placement_reticle.add_theme_font_size_override("font_size", 38)
    placement_reticle.add_theme_color_override("font_color", Color(0.08, 0.52, 1.0))
    placement_reticle.mouse_filter = Control.MOUSE_FILTER_IGNORE
    placement_reticle.add_to_group("mission_002_blue_reticle")
    hud.add_child(placement_reticle)


func _build_panel(position_2d: Vector2, size_2d: Vector2, color: Color) -> ColorRect:
    var panel := ColorRect.new()
    panel.position = position_2d
    panel.size = size_2d
    panel.color = color
    panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(panel)
    return panel


func _build_label(
    position_2d: Vector2,
    size_2d: Vector2,
    font_size: int,
    color: Color
) -> Label:
    var label := Label.new()
    label.position = position_2d
    label.size = size_2d
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hud.add_child(label)
    return label


func _build_aim_label(
    label_name: String,
    text_value: String,
    color: Color,
    font_size: int
) -> Label:
    var label := Label.new()
    label.name = label_name
    label.text = text_value
    label.size = Vector2(17.0, 17.0)
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    weapon_aim.add_child(label)
    return label


func _update_hud() -> void:
    if title_label == null:
        return
    title_label.text = "JOURNEYBLASTER · MISSION 002 · PLANETFALL PROTOTYPE V1"
    status_label.text = "MISSION STATE · %s" % mission_state.replace("_", " ")
    objective_label.text = OBJECTIVES.get(mission_state, "")
    sensor_label.text = _sensor_readout()
    var selected_weapon_status: String = player.weapon_status_text()
    if towbeam_mode:
        selected_weapon_status = (
            "WEAPONS\nTOW BEAM  %s · SPACE\nPROTON TORPEDO  %02d · T"
            % [
                "PLACING" if placement_in_progress else "READY",
                player.proton_torpedoes_remaining,
            ]
        )
    weapons_label.text = "%s\nCHARGES  %d/%d" % [
        selected_weapon_status,
        charges_placed,
        REQUIRED_CHARGES,
    ]
    weapons_label.text += "\nMODE  %s · /?" % (
        "TOW BEAM" if towbeam_mode else "FRAPRAY"
    )
    prompt_label.text = _context_prompt()
    placement_reticle.visible = (
        towbeam_mode
        and mission_state in ["INTERCEPT", "PLACEMENT_READY", "CHARGE_PLACEMENT"]
    )
    placement_reticle.position = placement_cursor - placement_reticle.size * 0.5
    placement_reticle.text = "◉" if acquired_site else "○"
    placement_reticle.add_theme_color_override(
        "font_color",
        Color(0.22, 0.76, 1.0) if acquired_site else Color(0.08, 0.52, 1.0)
    )
    _update_weapon_aim()


func _sensor_readout() -> String:
    var prefix := "SENSO-GLOBES · PLANETFALL TRACKING\n"
    if mission_state in ["BRIEFING", "INTERCEPT", "PLACEMENT_READY", "CHARGE_PLACEMENT", "CLEAR_BLAST", "DETONATION_READY"]:
        if not is_instance_valid(primary_asteroid):
            return prefix + "PRIMARY SIGNAL LOST"
        var remaining := maxf(
            0.0, CHARGE_PLACEMENT_WINDOW_S - charge_phase_elapsed
        )
        return prefix + "PRIMARY MASS · CRITICAL\nRANGE  %03d m\nATMOSPHERE  %03d s" % [
            roundi(_distance_to_primary()),
            roundi(remaining),
        ]
    var threats := _active_threat_count()
    var nearest_depth := _nearest_threat_depth()
    if mission_state == "FAILED":
        return prefix + "ATMOSPHERIC PENETRATION\nMISSION THREAT UNCONTAINED"
    if mission_state == "COMPLETE":
        return prefix + "NO DANGEROUS RETURNS\nIMPACT CORRIDOR CLEAR"
    var chase_remaining := maxf(0.0, DEBRIS_CHASE_WINDOW_S - chase_elapsed)
    return prefix + "DANGEROUS RETURNS  %02d\nNEAREST BOUNDARY  %03d m\nATMOSPHERE  %02d s" % [
        threats,
        roundi(nearest_depth),
        roundi(chase_remaining),
    ]


func _active_threat_count() -> int:
    var count := 0
    for major in get_tree().get_nodes_in_group("planetfall_major"):
        if is_instance_valid(major) and not major.destroyed:
            count += 1
    for fragment in get_tree().get_nodes_in_group("planetfall_debris"):
        if is_instance_valid(fragment) and not fragment.destroyed:
            count += 1
    return count


func _nearest_threat_depth() -> float:
    var nearest := INF
    for group_name in ["planetfall_major", "planetfall_debris"]:
        for target in get_tree().get_nodes_in_group(group_name):
            if is_instance_valid(target) and not target.destroyed:
                nearest = minf(nearest, target.global_position.z - ATMOSPHERE_FAILURE_Z)
    return maxf(0.0, nearest if nearest < INF else 0.0)


func _context_prompt() -> String:
    match mission_state:
        "BRIEFING":
            return "ENTER · BEGIN PLANETFALL INTERCEPT"
        "PLACEMENT_READY":
            return "/? · SELECT TOW BEAM"
        "CHARGE_PLACEMENT":
            if placement_in_progress:
                return "PLACING CHARGE · %02d%%" % roundi(placement_elapsed / placement_duration * 100.0)
            return "MOUSE STEER · SPACE SHOOT BLUE TORUS · %d/%d SET" % [charges_placed, REQUIRED_CHARGES]
        "CLEAR_BLAST":
            return "CLEAR TO %d m · CURRENT %d m" % [SAFE_DETONATION_RANGE_M, roundi(_distance_to_primary())]
        "DETONATION_READY":
            return "G · DETONATE FRACTURE CHARGES"
        "BREAKUP":
            return "CONTROLLED BREAKUP · STAND BY"
        "DEBRIS_CHASE":
            return "DESTROY AND ATOMIZE ALL DANGEROUS DEBRIS"
        "COMPLETE":
            return "MISSION COMPLETE · R TO RESTART"
        "FAILED":
            return "MISSION FAILED · FREE FLIGHT · R TO RESTART"
        _:
            return ""


func _update_weapon_aim() -> void:
    if weapon_aim == null:
        return
    weapon_aim.visible = weapon_aim_enabled and not towbeam_mode
    if not weapon_aim.visible:
        return
    var camera := get_viewport().get_camera_3d()
    if camera == null:
        weapon_aim.visible = false
        return
    var direction := -player.global_basis.z.normalized()
    _position_aim_marker(
        frap_aim_left,
        _weapon_impact_point(frap_origin_left.global_position, direction, 650.0),
        camera
    )
    _position_aim_marker(
        frap_aim_right,
        _weapon_impact_point(frap_origin_right.global_position, direction, 650.0),
        camera
    )
    var torpedo_point := _weapon_impact_point(
        torpedo_origin.global_position, direction, 700.0
    )
    if (
        player.torpedo_charging
        and player.torpedo_acquired_target != null
        and is_instance_valid(player.torpedo_acquired_target)
    ):
        torpedo_point = player.torpedo_acquired_target.global_position
    _position_aim_marker(torpedo_aim, torpedo_point, camera)
    _update_torpedo_charge_indicator()


func _update_torpedo_charge_indicator() -> void:
    var charging: bool = player.torpedo_charging
    torpedo_aim.add_theme_color_override(
        "font_color",
        Color(0.12, 0.66, 1.0) if charging else Color(1.0, 0.12, 0.08)
    )
    torpedo_charge_indicator.position = (
        torpedo_aim.position + torpedo_aim.size * 0.5
        - torpedo_charge_indicator.size * 0.5
    )
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
        screen.x >= 0.0
        and screen.y >= 0.0
        and screen.x <= viewport_size.x
        and screen.y <= viewport_size.y
    )
    if marker.visible:
        marker.position = screen - marker.size * 0.5
