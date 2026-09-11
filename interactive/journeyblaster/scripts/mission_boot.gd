extends Node3D

const TorpedoChargeIndicator = preload("res://scripts/torpedo_charge_indicator.gd")

const STATE_OBJECTIVES := {
    "BRIEFING": "Bring the JB100 online and enter the asteroid field.",
    "LOCATE": "Use the hull-mounted Senso-Globes to locate the unknown signal.",
    "APPROACH": "Approach the identified mining probe at a safe speed.",
    "DOWNLOAD_READY": "Hold inside 12 m and press G to download probe data.",
    "DOWNLOADING": "Maintain range and relative speed during data transfer.",
    "DATA_SECURED": "Data secured. Prepare the probe for tow.",
    "TOW_READY": "Hold inside 12 m at low speed and press G to take the probe in tow.",
    "IN_TOW": "Tow beam acquiring and latching onto the probe.",
    "RETURN_TO_ENTRY": "Tow the physical probe back to the original entry boundary.",
    "EXIT_READY": "Ship and probe are clear. Press H to engage hyperspace.",
    "HYPERSPACE": "Yoyodyne hyperdrive engaging.",
    "COMPLETE": "Mining probe and data recovered. Mission complete.",
    "FAILED": "Mining probe destroyed. Mission failed.",
}

@export_file("*.json") var mission_data_path: String

var mission_data: Dictionary = {}
var mission_state := "BRIEFING"
var player: CharacterBody3D
var probe: RigidBody3D
var sensor_origin: Node3D
var probe_signature: Node3D
var tow_origin: Node3D
var tow_anchor: Node3D
var entry_boundary: Node3D
var pilot_view: Node3D
var identification_progress := 0.0
var download_progress := 0.0
var state_elapsed := 0.0
var tow_attached := false
var identified := false
var probe_damaged := false
var probe_destroyed := false
var probe_data_secured := false
var tow_beam: MeshInstance3D
var tow_beam_mesh: CylinderMesh
var beacon_light: OmniLight3D
var status_label: Label
var objective_label: Label
var sensor_label: Label
var flight_label: Label
var view_label: Label
var weapons_label: Label
var prompt_label: Label
var weapon_aim: Control
var frap_aim_left: Label
var frap_aim_right: Label
var torpedo_aim: Label
var torpedo_charge_indicator: Control
var frap_origin_left: Node3D
var frap_origin_right: Node3D
var torpedo_origin: Node3D
var weapon_aim_enabled := true
var tow_latch_elapsed := 0.0
var tow_latch_duration := 1.8
var tow_constraint_length := 0.0


func _ready() -> void:
    if not _load_mission_data():
        return
    if not _resolve_runtime_nodes():
        return
    _build_starfield()
    _build_probe_beacon()
    _build_tow_beam()
    _set_state("BRIEFING")
    begin_mission()
    print("MISSION-001-RUNTIME-OK: %s" % mission_data.get("title", "untitled"))


func _process(delta: float) -> void:
    if player == null or probe == null:
        return
    state_elapsed += delta
    _update_probe_beacon()
    if tow_attached:
        _update_tow(delta)
    _update_mission(delta)
    _update_hud()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_G:
                request_interaction()
            KEY_H:
                request_hyperspace()
            KEY_TAB:
                toggle_weapon_aim()
            KEY_R:
                if mission_state in ["COMPLETE", "FAILED"]:
                    get_tree().reload_current_scene()
    elif event is InputEventJoypadButton and event.pressed:
        match event.button_index:
            JOY_BUTTON_A:
                request_interaction()
            JOY_BUTTON_Y:
                request_hyperspace()


func _load_mission_data() -> bool:
    var file := FileAccess.open(mission_data_path, FileAccess.READ)
    if file == null:
        push_error("Mission 001 data is missing: %s" % mission_data_path)
        return false
    var parsed: Variant = JSON.parse_string(file.get_as_text())
    if not parsed is Dictionary:
        push_error("Mission 001 data is not a JSON object: %s" % mission_data_path)
        return false
    mission_data = parsed
    return true


func _resolve_runtime_nodes() -> bool:
    var player_id: String = mission_data.get("player", {}).get("instance_id", "")
    player = find_child(player_id, true, false) as CharacterBody3D
    probe = find_child(
        mission_data.get("sensors", {}).get("target_instance_id", ""),
        true,
        false
    ) as RigidBody3D
    if player == null or probe == null:
        push_error("Mission 001 player or probe instance is missing")
        return false
    sensor_origin = player.find_child("sensor_origin", true, false) as Node3D
    probe_signature = probe.find_child("sensor_signature", true, false) as Node3D
    tow_origin = player.find_child("effect_exclusion_center", true, false) as Node3D
    tow_anchor = probe.find_child("tow_anchor", true, false) as Node3D
    pilot_view = player.find_child("SeatPivot", true, false) as Node3D
    entry_boundary = find_child(
        mission_data.get("environment", {}).get("entry_boundary", {}).get(
            "boundary_id", ""
        ),
        true,
        false
    ) as Node3D
    if (
        sensor_origin == null
        or probe_signature == null
        or tow_origin == null
        or tow_anchor == null
        or pilot_view == null
        or entry_boundary == null
    ):
        push_error("Mission 001 interactive markers are incomplete")
        return false
    probe.freeze = true
    status_label = get_node_or_null("HUD/TopBar/Status") as Label
    objective_label = get_node_or_null("HUD/TopBar/Objective") as Label
    sensor_label = get_node_or_null("HUD/SensorPanel/Sensor") as Label
    flight_label = get_node_or_null("HUD/TelemetryPanel/Flight") as Label
    view_label = get_node_or_null("HUD/TelemetryPanel/View") as Label
    weapons_label = get_node_or_null("HUD/WeaponsPanel/Weapons") as Label
    prompt_label = get_node_or_null("HUD/Prompt") as Label
    weapon_aim = get_node_or_null("HUD/WeaponAim") as Control
    frap_aim_left = get_node_or_null("HUD/WeaponAim/FrapRayLeft") as Label
    frap_aim_right = get_node_or_null("HUD/WeaponAim/FrapRayRight") as Label
    torpedo_aim = get_node_or_null("HUD/WeaponAim/Torpedo") as Label
    torpedo_charge_indicator = TorpedoChargeIndicator.new()
    torpedo_charge_indicator.name = "TorpedoChargeIndicator"
    torpedo_charge_indicator.size = Vector2(31.0, 31.0)
    weapon_aim.add_child(torpedo_charge_indicator)
    frap_origin_left = player.find_child("frap_hardpoint_left", true, false) as Node3D
    frap_origin_right = player.find_child("frap_hardpoint_right", true, false) as Node3D
    torpedo_origin = player.find_child("torpedo_launcher", true, false) as Node3D
    player.connect("impact", _on_player_impact)
    probe.connect("collision_damaged", _on_probe_collision_damaged)
    probe.connect("destroyed_by_weapon", _on_probe_destroyed_by_weapon)
    return true


func begin_mission() -> void:
    if mission_state == "BRIEFING":
        _set_state("LOCATE")


func request_interaction() -> void:
    if (
        mission_state == "DOWNLOAD_READY"
        and not probe_damaged
        and _download_conditions_safe()
    ):
        download_progress = 0.0
        _set_state("DOWNLOADING")
    elif mission_state == "TOW_READY" and _tow_conditions_safe():
        _begin_tow()
        _set_state("IN_TOW")


func request_hyperspace() -> void:
    if mission_state == "EXIT_READY":
        _set_state("HYPERSPACE")


func current_state() -> String:
    return mission_state


func toggle_weapon_aim() -> void:
    weapon_aim_enabled = not weapon_aim_enabled
    _update_weapon_aim()


func _update_mission(delta: float) -> void:
    if mission_state == "BRIEFING" and player.velocity.length() > 0.5:
        begin_mission()
    elif mission_state == "LOCATE":
        var identify_range: float = mission_data["sensors"]["identification_range_m"]
        if _distance_to_probe() <= identify_range and _has_probe_line_of_sight():
            identification_progress += delta
        else:
            identification_progress = maxf(0.0, identification_progress - delta * 0.5)
        if identification_progress >= mission_data["sensors"]["identification_dwell_s"]:
            identified = true
            _set_state("TOW_READY" if probe_damaged else "APPROACH")
    elif mission_state == "APPROACH":
        if probe_damaged:
            _set_state("TOW_READY")
        elif _download_conditions_safe():
            _set_state("DOWNLOAD_READY")
    elif mission_state == "DOWNLOAD_READY":
        if not _download_conditions_safe():
            _set_state("APPROACH")
    elif mission_state == "DOWNLOADING":
        if not _download_conditions_safe():
            download_progress = 0.0
            _set_state("DOWNLOAD_READY")
        else:
            download_progress += delta
            if download_progress >= mission_data["interactions"]["download"]["duration_s"]:
                probe_data_secured = true
                _set_state("DATA_SECURED")
    elif mission_state == "DATA_SECURED" and state_elapsed >= 0.65:
        _set_state("TOW_READY")
    elif mission_state == "IN_TOW" and tow_latch_elapsed >= tow_latch_duration:
        _set_state("RETURN_TO_ENTRY")
    elif mission_state == "RETURN_TO_ENTRY" and _ship_and_probe_inside_entry_boundary():
        _set_state("EXIT_READY")
    elif mission_state == "HYPERSPACE":
        player.velocity = -player.global_transform.basis.z * (160.0 + state_elapsed * 180.0)
        if state_elapsed >= 2.0:
            _set_state("COMPLETE")
            player.set_controls_enabled(false)


func _set_state(next_state: String) -> void:
    if mission_state == next_state and state_elapsed > 0.0:
        return
    mission_state = next_state
    state_elapsed = 0.0
    if status_label:
        status_label.text = "MISSION STATE · %s" % mission_state.replace("_", " ")


func _download_conditions_safe() -> bool:
    var rules: Dictionary = mission_data["interactions"]["download"]
    return (
        probe.call("can_download_data")
        and not probe_damaged
        and _distance_to_probe() <= rules["range_m"]
        and player.velocity.length() <= rules["max_relative_speed_mps"]
        and (not rules["requires_line_of_sight"] or _has_probe_line_of_sight())
    )


func _tow_conditions_safe() -> bool:
    var rules: Dictionary = mission_data["interactions"]["tow"]
    return (
        probe.call("can_be_towed")
        and _distance_to_probe() <= rules["range_m"]
        and player.velocity.length() <= rules["max_relative_speed_mps"]
    )


func _on_player_impact(impact_speed_mps: float, collider: Object) -> void:
    if collider == probe and not probe_destroyed:
        probe.call("apply_collision_damage", impact_speed_mps)


func _on_probe_collision_damaged(_impact_speed_mps: float) -> void:
    probe_damaged = true
    download_progress = 0.0
    if not probe_data_secured and mission_state in [
        "APPROACH", "DOWNLOAD_READY", "DOWNLOADING"
    ]:
        _set_state("TOW_READY")


func _on_probe_destroyed_by_weapon(_weapon_kind: String) -> void:
    probe_destroyed = true
    tow_attached = false
    weapon_aim_enabled = false
    if tow_beam:
        tow_beam.visible = false
    _set_state("FAILED")
    _update_hud()


func _has_probe_line_of_sight() -> bool:
    var query := PhysicsRayQueryParameters3D.create(
        sensor_origin.global_position,
        probe_signature.global_position
    )
    query.exclude = [player.get_rid()]
    var result := get_world_3d().direct_space_state.intersect_ray(query)
    return result.is_empty() or result.get("collider") == probe


func _distance_to_probe() -> float:
    return player.global_position.distance_to(probe.global_position)


func _ship_and_probe_inside_entry_boundary() -> bool:
    var radius: float = entry_boundary.get_meta("radius_m", 0.0)
    return (
        player.global_position.distance_to(entry_boundary.global_position) <= radius
        and probe.global_position.distance_to(entry_boundary.global_position) <= radius
        and tow_attached
    )


func _begin_tow() -> void:
    tow_attached = true
    tow_latch_elapsed = 0.0
    tow_latch_duration = float(
        mission_data["interactions"]["tow"].get("latch_duration_s", 1.8)
    )
    tow_constraint_length = _captured_tow_length()


func _captured_tow_length() -> float:
    var safety_max: float = mission_data["interactions"]["tow"]["tow_length_m"]
    return clampf(
        tow_origin.global_position.distance_to(tow_anchor.global_position),
        0.5,
        safety_max
    )


func _update_tow(delta: float) -> void:
    if tow_constraint_length <= 0.0:
        tow_constraint_length = _captured_tow_length()
    if tow_latch_elapsed < tow_latch_duration:
        tow_latch_elapsed = minf(tow_latch_elapsed + delta, tow_latch_duration)
        var latch_ratio := clampf(tow_latch_elapsed / tow_latch_duration, 0.0, 1.0)
        var latch_eased := smoothstep(0.0, 1.0, latch_ratio)
        var beam_start := _tow_beam_visible_start(tow_anchor.global_position)
        var beam_tip := beam_start.lerp(tow_anchor.global_position, latch_eased)
        _update_tow_beam_geometry(beam_start, beam_tip)
        return

    # The probe is not parented to the ship. It keeps its world-space position
    # through a pivot, then the taut tether projects its anchor back onto the
    # captured radius. Straight flight pulls it along; turns make it trail.
    var anchor_offset := tow_anchor.global_position - tow_origin.global_position
    var tether_direction := anchor_offset.normalized()
    if tether_direction.is_zero_approx():
        tether_direction = player.global_transform.basis.z.normalized()
    var constrained_anchor := (
        tow_origin.global_position + tether_direction * tow_constraint_length
    )
    probe.global_position += constrained_anchor - tow_anchor.global_position
    _update_tow_beam_geometry(
        _tow_beam_visible_start(tow_anchor.global_position),
        tow_anchor.global_position
    )


func _tow_beam_visible_start(target: Vector3) -> Vector3:
    var center := tow_origin.global_position
    var center_to_target := target - center
    var target_distance := center_to_target.length()
    if target_distance <= 0.001:
        return center
    var radius: float = tow_origin.get_meta("effect_exclusion_radius_m", 0.0)
    var clearance: float = tow_origin.get_meta("effect_exclusion_clearance_m", 0.1)
    var visible_distance := minf(target_distance, radius + clearance)
    return center + center_to_target / target_distance * visible_distance


func _build_tow_beam() -> void:
    tow_beam = MeshInstance3D.new()
    tow_beam.name = "TowBeam"
    tow_beam_mesh = CylinderMesh.new()
    tow_beam_mesh.top_radius = 0.055
    tow_beam_mesh.bottom_radius = 0.055
    tow_beam_mesh.height = 1.0
    tow_beam_mesh.radial_segments = 8
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(1.0, 0.55, 0.08, 0.82)
    material.emission_enabled = true
    material.emission = Color(1.0, 0.22, 0.02)
    material.emission_energy_multiplier = 3.0
    tow_beam_mesh.material = material
    tow_beam.mesh = tow_beam_mesh
    tow_beam.visible = false
    add_child(tow_beam)


func _update_tow_beam_geometry(start: Vector3, finish: Vector3) -> void:
    var direction := finish - start
    var length := direction.length()
    if length <= 0.01:
        tow_beam.visible = false
        return
    tow_beam.visible = true
    tow_beam_mesh.height = length
    var alignment := Basis(Quaternion(Vector3.UP, direction.normalized()))
    tow_beam.global_transform = Transform3D(alignment, (start + finish) * 0.5)


func _build_probe_beacon() -> void:
    var animation_player := probe.find_child("AnimationPlayer", true, false) as AnimationPlayer
    if animation_player and animation_player.has_animation("beacon_blink_loop"):
        animation_player.play("beacon_blink_loop")
    beacon_light = OmniLight3D.new()
    beacon_light.name = "ProbeBeaconRuntime"
    beacon_light.light_color = Color(1.0, 0.48, 0.08)
    beacon_light.omni_range = 16.0
    beacon_light.light_energy = 2.0
    probe.add_child(beacon_light)


func _update_probe_beacon() -> void:
    if beacon_light and probe_destroyed:
        beacon_light.light_energy = 0.0
    elif beacon_light:
        beacon_light.light_energy = 1.0 + maxf(0.0, sin(Time.get_ticks_msec() * 0.008)) * 5.0


func _build_starfield() -> void:
    var stars := MultiMeshInstance3D.new()
    stars.name = "ProceduralStarfield"
    var star_mesh := SphereMesh.new()
    star_mesh.radius = 0.42
    star_mesh.height = 0.84
    star_mesh.radial_segments = 4
    star_mesh.rings = 2
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.78, 0.88, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.72, 0.84, 1.0)
    material.emission_energy_multiplier = 2.2
    star_mesh.material = material
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = star_mesh
    multimesh.instance_count = 320
    var random := RandomNumberGenerator.new()
    random.seed = 19991031
    for index in multimesh.instance_count:
        var direction := Vector3(
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0)
        ).normalized()
        var distance := random.randf_range(900.0, 1600.0)
        var scale := random.randf_range(0.35, 1.25)
        multimesh.set_instance_transform(
            index,
            Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * scale), direction * distance)
        )
    stars.multimesh = multimesh
    add_child(stars)


func _update_hud() -> void:
    if objective_label:
        if mission_state == "TOW_READY" and probe_damaged and not probe_data_secured:
            objective_label.text = "DATA PORT DAMAGED. Recover the probe in tow."
        elif mission_state == "COMPLETE" and probe_damaged and not probe_data_secured:
            objective_label.text = "Damaged mining probe recovered. Data unavailable."
        else:
            objective_label.text = STATE_OBJECTIVES.get(mission_state, "")
    if sensor_label:
        sensor_label.text = _sensor_readout()
    if flight_label:
        flight_label.text = (
            "SHIP VECTOR\nSPEED  %03d m/s\nTHROTTLE  %s%%\nCOURSE LOCK  %s"
            % [
                roundi(player.velocity.length()),
                player.throttle_percent(),
                "ON" if player.course_lock else "OFF",
            ]
        )
    if view_label:
        view_label.text = "PILOT CHAIR\nVIEW  %s\nSHIP HEADING INDEPENDENT" % pilot_view.current_view_label()
    if weapons_label and player.has_method("weapon_status_text"):
        weapons_label.text = "%s\nAIM HUD  %s · TAB" % [
            player.weapon_status_text(),
            "ON" if weapon_aim_enabled else "OFF",
        ]
    _update_weapon_aim()
    if prompt_label:
        prompt_label.text = _context_prompt()


func _update_weapon_aim() -> void:
    if weapon_aim == null:
        return
    weapon_aim.visible = weapon_aim_enabled
    if not weapon_aim_enabled:
        return
    var camera := get_viewport().get_camera_3d()
    if camera == null or frap_origin_left == null or frap_origin_right == null or torpedo_origin == null:
        weapon_aim.visible = false
        return
    var fire_direction := -player.global_basis.z.normalized()
    var left_point := _weapon_impact_point(frap_origin_left.global_position, fire_direction, 610.0)
    var right_point := _weapon_impact_point(frap_origin_right.global_position, fire_direction, 610.0)
    var torpedo_point := _weapon_impact_point(torpedo_origin.global_position, fire_direction, 690.0)
    if (
        player.torpedo_charging
        and player.torpedo_acquired_target != null
        and is_instance_valid(player.torpedo_acquired_target)
    ):
        torpedo_point = player.torpedo_acquired_target.global_position
    _position_weapon_marker(frap_aim_left, left_point, camera)
    _position_weapon_marker(frap_aim_right, right_point, camera)
    _position_weapon_marker(torpedo_aim, torpedo_point, camera)
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


func _position_weapon_marker(marker: Label, world_point: Vector3, camera: Camera3D) -> void:
    if marker == null:
        return
    if camera.is_position_behind(world_point):
        marker.visible = false
        return
    var screen_point := camera.unproject_position(world_point)
    var viewport_size := Vector2(get_viewport().get_visible_rect().size)
    marker.visible = (
        screen_point.x >= 0.0
        and screen_point.y >= 0.0
        and screen_point.x <= viewport_size.x
        and screen_point.y <= viewport_size.y
    )
    if marker.visible:
        marker.position = screen_point - marker.size * 0.5


func _sensor_readout() -> String:
    if probe_destroyed:
        return "SENSO-GLOBES · ACTIVE/PASSIVE\nTARGET DESTROYED"
    var distance := _distance_to_probe()
    var rules: Dictionary = mission_data["sensors"]
    var prefix := "SENSO-GLOBES · ACTIVE/PASSIVE\n"
    if distance > rules["detection_range_m"]:
        return prefix + "NO CONTACT"
    if distance > rules["bearing_range_m"]:
        return prefix + "UNKNOWN RETURN · RANGE UNRESOLVED"
    var local_target := player.to_local(probe.global_position)
    var bearing := rad_to_deg(atan2(local_target.x, -local_target.z))
    var side := "AHEAD"
    if bearing < -4.0:
        side = "LEFT"
    elif bearing > 4.0:
        side = "RIGHT"
    var readout := prefix + "BEARING  %s %03d°" % [side, roundi(absf(bearing))]
    if distance <= rules["strength_range_m"]:
        var strength := clampi(roundi((1.0 - distance / rules["strength_range_m"]) * 8.0), 1, 8)
        readout += "\nSIGNAL   [%s%s]" % ["#".repeat(strength), ".".repeat(8 - strength)]
    if distance <= rules["identification_range_m"]:
        if identified:
            readout += "\nID  MINING PROBE · %03d m" % roundi(distance)
        else:
            var dwell: float = rules["identification_dwell_s"]
            readout += "\nANALYZING  %02d%%" % roundi(identification_progress / dwell * 100.0)
    if identified and distance <= rules["visual_range_m"]:
        readout += "\nVISUAL ACQUISITION"
    if probe_damaged and not probe_data_secured:
        readout += "\nDATA PORT DAMAGED · TOW ONLY"
    return readout


func _context_prompt() -> String:
    match mission_state:
        "BRIEFING":
            return "ENTER · BEGIN MISSION"
        "DOWNLOAD_READY":
            return "G · DOWNLOAD DATA"
        "DOWNLOADING":
            var duration: float = mission_data["interactions"]["download"]["duration_s"]
            return "DOWNLOADING · %02d%%" % roundi(download_progress / duration * 100.0)
        "TOW_READY":
            return "G · TAKE PROBE IN TOW" if _tow_conditions_safe() else "REDUCE SPEED AND CLOSE TO 12 m"
        "IN_TOW":
            return "TOW BEAM LATCHING · %02d%%" % roundi(
                tow_latch_elapsed / tow_latch_duration * 100.0
            )
        "EXIT_READY":
            return "H · ENGAGE HYPERSPACE"
        "COMPLETE":
            return "MISSION COMPLETE · R TO RESTART"
        "FAILED":
            return "MISSION FAILED · R TO RESTART"
        _:
            return ""
