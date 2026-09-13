extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("MISSION-003-RUNTIME-ERROR: %s" % message)
    quit(1)


func _spawn_runtime() -> Node3D:
    var packed := load("res://scenes/mission_003_starbase_defense.tscn") as PackedScene
    if packed == null:
        return null
    var shell := packed.instantiate() as Node3D
    root.add_child(shell)
    await process_frame
    await process_frame
    return shell.active_mission as Node3D


func _run() -> void:
    var runtime := await _spawn_runtime()
    if runtime == null:
        fail("Mission 003 scene did not load")
        return
    var player := runtime.player as CharacterBody3D
    if player == null or runtime.starbase == null:
        fail("JB100 or Starbase 86 hero asset is missing")
        return
    if runtime.starbase.get_meta("asset_id", "") != "prop_starbase_86_A":
        fail("Mission 003 did not use the registered Starbase 86 hero model")
        return
    if (
        runtime.docked_starfighter == null
        or runtime.docked_starfighter.get_meta("asset_id", "")
        != "ship_earth_starfighter_hero_A"
    ):
        fail("Earth Starfighter hero craft is not docked in the open bay")
        return
    if not runtime.is_player_in_safe_hangar():
        fail("JB100 did not begin inside the safe open hangar")
        return
    if (
        runtime.hangar_steady_lights.size() != 2
        or runtime.hangar_emergency_lights.size() != 2
    ):
        fail("open hangar did not receive two steady lights and two emergency strobes")
        return
    for light in runtime.hangar_steady_lights:
        if (
            light.light_energy <= 0.0
            or light.global_position.distance_to(runtime.open_hangar_center) > 35.0
        ):
            fail("steady hangar lighting was not active inside the open bay")
            return
    runtime.hangar_strobe_clock = 0.0
    runtime.call("_update_hangar_emergency_lights", 0.01)
    var strobe_energy_on: float = runtime.hangar_emergency_lights[0].light_energy
    runtime.hangar_strobe_clock = 0.5
    runtime.call("_update_hangar_emergency_lights", 0.01)
    var strobe_energy_off: float = runtime.hangar_emergency_lights[0].light_energy
    if strobe_energy_on <= strobe_energy_off:
        fail("red emergency hangar light did not strobe")
        return
    var strobe_a: Vector3 = runtime.hangar_emergency_lights[0].global_position
    var strobe_b: Vector3 = runtime.hangar_emergency_lights[1].global_position
    if not is_equal_approx(strobe_a.distance_to(strobe_b), 6.0):
        fail("open-hangar ceiling strobes are not offset by six meters")
        return
    var strobe_midpoint := strobe_a.lerp(strobe_b, 0.5)
    if not strobe_midpoint.is_equal_approx(
        runtime.open_hangar_center + Vector3.UP * 4.65
    ):
        fail("emergency strobes are not centered on the open-hangar ceiling")
        return
    var hangar_center := runtime.starbase.find_child(
        "hangar_1_volume_center", true, false
    ) as Node3D
    var hangar_exit := runtime.starbase.find_child("hangar_1_exit", true, false) as Node3D
    if hangar_center == null or hangar_exit == null:
        fail("open hangar navigation markers are missing")
        return
    if (
        not runtime.open_hangar_center.is_equal_approx(hangar_center.global_position)
        or not runtime.open_hangar_exit.is_equal_approx(hangar_exit.global_position)
    ):
        fail("Mission 003 did not derive its launch lane from the hero asset markers")
        return
    var launch_direction: Vector3 = (
        runtime.open_hangar_exit - runtime.open_hangar_center
    ).normalized()
    if (-player.global_basis.z).dot(launch_direction) < 0.98:
        fail("JB100 was not facing the open hangar exit")
        return
    if (
        (runtime.docked_starfighter.global_position - player.global_position).dot(
            launch_direction
        ) >= 0.0
        or runtime.docked_starfighter.collision_layer != 0
    ):
        fail("docked Earth Starfighter is not safely parked behind the JB100")
        return
    if get_nodes_in_group("mission_003_station_target").size() != 9:
        fail("starbase does not have nine hidden damage targets")
        return
    for category in ["shield", "weapon", "hangar"]:
        if get_nodes_in_group("mission_003_%s_target" % category).size() != 3:
            fail("%s system does not have three damage locations" % category)
            return
    for target in runtime.station_targets:
        var housing := target.get_node_or_null("SystemHousing") as MeshInstance3D
        var collision := target.get_node_or_null("DamageCollision") as CollisionShape3D
        if housing == null or housing.visible:
            fail("station damage housing remained visibly suspended in space")
            return
        var collision_sphere := collision.shape as SphereShape3D if collision else null
        if collision_sphere == null or collision_sphere.radius > 4.0:
            fail("station damage collision was not tightened to its surface target")
            return
    if runtime.pirates.size() != 3:
        fail("three pirate flyers were not spawned")
        return
    if (
        runtime.station_polar_weapon_emitters.size() != 2
        or runtime.station_polar_weapon_emitters[0].global_position.y
        <= runtime.STARBASE_CENTER.y
        or runtime.station_polar_weapon_emitters[1].global_position.y
        >= runtime.STARBASE_CENTER.y
    ):
        fail("top and bottom Starbase defense arcs are missing")
        return
    if get_nodes_in_group("mission_003_planet").size() != 1:
        fail("distant planet backdrop is missing")
        return
    if get_nodes_in_group("mission_003_moon").size() != 1:
        fail("distant moon backdrop is missing")
        return
    var cockpit_camera := player.find_child(
        "cockpit_camera", true, false
    ) as Camera3D
    if (
        get_nodes_in_group("mission_003_sun").size() != 1
        or runtime.starfield == null
        or cockpit_camera == null
        or cockpit_camera.far < 10000.0
    ):
        fail("visible sun or camera-relative starfield is missing")
        return
    if (
        runtime.starfield.cast_shadow
        != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    ):
        fail("starfield geometry still casts shadows inside the backdrop")
        return
    if (
        runtime.game_shell.get_node_or_null("HUD/LeftSystemsScreen") == null
        or runtime.game_shell.get_node_or_null("HUD/MiddleSensorScreen/SensorGlobe") == null
        or runtime.game_shell.get_node_or_null("HUD/RightMissionScreen") == null
        or runtime.game_shell.get_node_or_null("HUD/MissionAnnouncement") == null
    ):
        fail("cockpit instrumentation or mission-failure overlay is incomplete")
        return
    if (
        not runtime.failure_overlay.visible
        or runtime.failure_overlay.text != "GO"
        or runtime.failure_overlay.get_theme_color("font_color").b < 0.9
    ):
        fail("Mission 003 did not begin with the blue GO announcement")
        return
    runtime.failure_overlay.call("_process", 3.0)
    if runtime.failure_overlay.visible:
        fail("Mission 003 GO announcement did not clear after three seconds")
        return
    if (
        runtime.sensor_globe.call("_contact_color", runtime.pirates[0])
        != runtime.sensor_globe.HOSTILE_RED
        or runtime.sensor_globe.call("_contact_color", runtime.docked_starfighter)
        != runtime.sensor_globe.FRIENDLY_BLUE
    ):
        fail("Senso-Globe did not color enemies red and friendlies blue")
        return
    if runtime.sensor_globe.FORWARD_AMBER.a < 1.0:
        fail("Senso-Globe JB100 forward arrow is missing")
        return
    var sensor_forward: Vector3 = runtime.sensor_globe.call(
        "ship_local_to_sensor_axes", Vector3.FORWARD
    )
    var projected_forward: Vector2 = runtime.sensor_globe.call(
        "project_ship_local_vector", Vector3.FORWARD
    )
    var display_y_axis: Vector2 = runtime.sensor_globe.DISPLAY_Y_AXIS_2D
    if (
        not sensor_forward.is_equal_approx(Vector3(0.0, 1.0, 0.0))
        or absf(projected_forward.normalized().cross(
            display_y_axis.normalized()
        )) > 0.0001
        or projected_forward.dot(display_y_axis) <= 0.0
    ):
        fail("Senso-Globe did not map JB100 local forward toward display +Y")
        return
    var sensor_test_pirate := runtime.pirates[0] as AnimatableBody3D
    sensor_test_pirate.destroyed = true
    if runtime.sensor_globe.call("contact_is_active", sensor_test_pirate):
        fail("Senso-Globe retained a destroyed pirate sensor ghost")
        return
    sensor_test_pirate.destroyed = false
    runtime.call("_update_hud")
    if (
        runtime.systems_value_labels["THR"].text != "THR: 000%"
        or runtime.systems_value_labels["PWR"].text != "PWR: 100%"
        or runtime.systems_value_labels["SHD"].text != "SHD: 100%"
        or runtime.systems_value_labels["WPN"].text != "WPN: 100%"
        or runtime.systems_torpedo_label.text != "TPD: 5"
    ):
        fail("cockpit systems did not show initial power, shields, weapons, or torpedoes")
        return
    player.frapray_power_percent = 70.0
    player.power_percent = 47.0
    player.proton_torpedoes_remaining = 3
    runtime.call("_update_hud")
    if (
        runtime.systems_value_labels["WPN"].text != "WPN: 070%"
        or runtime.systems_value_labels["PWR"].text != "PWR: 047%"
        or runtime.systems_torpedo_label.text != "TPD: 3"
    ):
        fail("cockpit power, weapon, and torpedo readouts did not track live values")
        return
    player.frapray_power_percent = 100.0
    player.power_percent = 100.0
    player.proton_torpedoes_remaining = 5
    player.begin_torpedo_charge()
    player.torpedo_acquired_target = runtime.pirates[0]
    player.torpedo_lock_candidate = runtime.pirates[0]
    player.torpedo_charge_elapsed = 1.5
    runtime.torpedo_aim.visible = true
    runtime.call("_update_torpedo_charge_indicator")
    if (
        not runtime.torpedo_charge_indicator.visible
        or not is_equal_approx(runtime.torpedo_charge_indicator.charge_progress, 0.5)
        or runtime.torpedo_aim.get_theme_color("font_color")
        != Color(0.12, 0.66, 1.0)
    ):
        fail("torpedo lock display mismatch: visible=%s progress=%.2f hot=%s color=%s" % [
            runtime.torpedo_charge_indicator.visible,
            runtime.torpedo_charge_indicator.charge_progress,
            player.torpedo_has_live_lock(),
            runtime.torpedo_aim.get_theme_color("font_color"),
        ])
        return
    player.cancel_torpedo_charge()
    runtime.call("_update_torpedo_charge_indicator")
    if runtime.torpedo_charge_indicator.visible:
        fail("torpedo charge ring remained visible after charge cancellation")
        return
    player.set_throttle_preset(0.8)
    runtime.call("_update_hud")
    if runtime.systems_value_labels["THR"].text != "THR: 080%":
        fail("THR cockpit bar did not display commanded thrust")
        return
    player.set_throttle_preset(0.0)
    if not runtime.mission_screen_label.text.contains("OBJECTIVE"):
        fail("right cockpit screen did not present the current objective")
        return
    for pirate in runtime.pirates:
        if pirate.get_meta("asset_id", "") != "prop_pirate_flyer_A":
            fail("Mission 003 did not use the registered Ellipso flyer model")
            return
        if pirate.torpedoes_remaining != 3:
            fail("each pirate did not begin with three personal torpedoes")
            return
        if not pirate.ai_enabled:
            fail("pirate AI did not activate immediately on load")
            return

    if runtime.current_state() != "DEFEND":
        fail("Mission 003 did not begin immediately on load")
        return
    var station_shots_before: int = runtime.station_shots_fired
    runtime.call("_update_station_defense", 2.0)
    if runtime.station_shots_fired <= station_shots_before:
        fail("station defense did not fire after the mission began")
        return
    if (
        runtime.call("_station_defense_spread_m", 120.0, 1.0)
        >= runtime.call("_station_defense_spread_m", 700.0, 1.0)
    ):
        fail("station defense did not become more accurate at close range")
        return
    if (
        runtime.call("_station_defense_spread_m", 30.0, 1.0) >= 0.5
        or runtime.STATION_FRIENDLY_FIRE_ODDS != 20
    ):
        fail("station defense lacks close-range precision or 1-in-20 friendly fire")
        return
    var categories: Dictionary = {}
    var initial_pirate_positions: Array[Vector3] = []
    for pirate in runtime.pirates:
        categories[pirate.objective_category] = true
        initial_pirate_positions.append(pirate.global_position)
    for frame in 24:
        await physics_frame
    var moving_pirates := 0
    for index in runtime.pirates.size():
        if runtime.pirates[index].global_position.distance_to(
            initial_pirate_positions[index]
        ) > 0.5:
            moving_pirates += 1
    if moving_pirates != 3:
        fail("all three pirate flyers did not move under live AI control")
        return
    var station_run_geometry_checks := 0
    for pirate in runtime.pirates:
        pirate.ai_enabled = false
        if pirate.behavior == "ATTACK_PLAYER":
            continue
        station_run_geometry_checks += 1
        if pirate.attack_run_phase != "INGRESS":
            fail("pirate did not begin by flying to a strafing-run ingress point")
            return
        var assigned_target := pirate.current_target as Node3D
        var ingress_direction: Vector3 = (
            assigned_target.global_position - pirate.run_ingress_point
        ).normalized()
        var target_direction: Vector3 = (
            assigned_target.global_position - pirate.run_ingress_point
        ).normalized()
        if ingress_direction.dot(target_direction) < 0.99:
            fail("pirate attack ingress was not nose-on to its station target")
            return
        if (
            pirate.run_egress_point.distance_to(runtime.STARBASE_CENTER)
            < pirate.STARBASE_KEEP_OUT_RADIUS_M
        ):
            fail("pirate egress waypoint crossed the Starbase keep-out volume")
            return
        var clamped_core_point: Vector3 = pirate.call(
            "_enforce_starbase_keep_out", runtime.STARBASE_CENTER
        )
        if (
            clamped_core_point.distance_to(runtime.STARBASE_CENTER)
            < pirate.STARBASE_KEEP_OUT_RADIUS_M - 0.01
        ):
            fail("pirate movement could enter the Starbase core")
            return
    if station_run_geometry_checks < 1:
        fail("JB100 attacker assignment left no pirate station runs to verify")
        return
    if categories.size() != 3:
        fail("pirates did not begin with one hidden objective category each")
        return

    runtime.call("_maintain_player_attacker")
    var initial_attacker := runtime.player_attacker as AnimatableBody3D
    if initial_attacker == null or initial_attacker.behavior != "ATTACK_PLAYER":
        fail("one pirate was not assigned to attack JB100 at mission start")
        return
    var station_attackers: Array[AnimatableBody3D] = []
    for pirate in runtime.pirates:
        if (
            pirate != initial_attacker
            and pirate.behavior in ["ATTACK_STATION", "PILE_ON"]
        ):
            station_attackers.append(pirate)
    if station_attackers.size() != 2:
        fail("JB100 attacker assignment did not leave two pirates attacking the station")
        return
    var removed_pirate := station_attackers[0] as AnimatableBody3D
    var second_removed_pirate := station_attackers[1] as AnimatableBody3D
    removed_pirate.destroyed = true
    runtime.call("_maintain_player_attacker")
    if initial_attacker.behavior != "ATTACK_PLAYER" or runtime.player_attacker != initial_attacker:
        fail("sole JB100 attacker was not maintained while another station attacker remained")
        return
    second_removed_pirate.destroyed = true
    runtime.call("_maintain_player_attacker")
    if (
        initial_attacker.behavior != "PILE_ON"
        or not is_equal_approx(
            initial_attacker.station_attack_aggression,
            runtime.LAST_PIRATE_STATION_AGGRESSION
        )
    ):
        fail("the final pirate did not intensify its station strafing runs")
        return
    removed_pirate.destroyed = false
    second_removed_pirate.destroyed = false
    initial_attacker.assign_pile_on(runtime.call("_remaining_station_targets"), 1.0)
    runtime.player_attacker = null

    var strafing_pirate := removed_pirate
    strafing_pirate.ai_enabled = true
    strafing_pirate.attack_run_phase = "STRAFE"
    strafing_pirate.run_shot_fired = false
    strafing_pirate.fire_timer = 0.0
    strafing_pirate.global_position = strafing_pirate.run_fire_point
    var pirate_target := strafing_pirate.call("_attack_target_node") as Node3D
    var target_direction: Vector3 = (
        pirate_target.global_position - strafing_pirate.global_position
    ).normalized()
    var sideways_direction := target_direction.cross(Vector3.UP).normalized()
    if sideways_direction.length_squared() < 0.01:
        sideways_direction = Vector3.RIGHT
    strafing_pirate.flight_velocity = sideways_direction * strafing_pirate.preferred_speed
    strafing_pirate.look_at(
        strafing_pirate.global_position + sideways_direction, Vector3.UP
    )
    var projectile_count_before := get_nodes_in_group("weapon_projectile").size()
    strafing_pirate.call("_physics_process", 0.001)
    if (
        get_nodes_in_group("weapon_projectile").size() != projectile_count_before
        or strafing_pirate.run_shot_fired
    ):
        fail("sideways pirate fired without pointing its nose at the station target")
        return
    strafing_pirate.global_position = strafing_pirate.run_fire_point
    target_direction = (
        pirate_target.global_position - strafing_pirate.global_position
    ).normalized()
    strafing_pirate.flight_velocity = target_direction * strafing_pirate.preferred_speed
    strafing_pirate.look_at(pirate_target.global_position, Vector3.UP)
    strafing_pirate.call("_physics_process", 0.001)
    var projectile_count_after_shot := get_nodes_in_group("weapon_projectile").size()
    strafing_pirate.call("_physics_process", 0.001)
    if (
        projectile_count_after_shot != projectile_count_before + 1
        or get_nodes_in_group("weapon_projectile").size() != projectile_count_after_shot
    ):
        fail("pirate did not fire exactly once during a strafing pass")
        return
    var pirate_bolt := get_nodes_in_group("weapon_projectile")[-1] as Node3D
    if (
        pirate_bolt.weapon_kind != "pirate_plasma"
        or pirate_bolt.travel_velocity.normalized().dot(
            -strafing_pirate.global_basis.z.normalized()
        ) < 0.999
    ):
        fail("pirate plasma did not leave along the flyer's forward axis")
        return
    var pursuit_pirate := initial_attacker
    var player_position_before_rear_test: Vector3 = player.global_position
    var pirate_rear_direction := pursuit_pirate.global_basis.z.normalized()
    pursuit_pirate.torpedoes_remaining = 3
    player.global_position = pursuit_pirate.global_position + pirate_rear_direction * 301.0
    pursuit_pirate.rear_torpedo_lock_time = (
        pursuit_pirate.REAR_TORPEDO_LOCK_TIME_S - 0.01
    )
    var pirate_torpedoes_before: int = runtime.pirate_torpedoes_fired
    pursuit_pirate.call("_update_rear_torpedo", 0.02)
    if runtime.pirate_torpedoes_fired != pirate_torpedoes_before:
        fail("pirate torpedo fired beyond its 300-meter launch limit")
        return
    player.global_position = pursuit_pirate.global_position + pirate_rear_direction * 120.0
    pursuit_pirate.rear_torpedo_lock_time = (
        pursuit_pirate.REAR_TORPEDO_LOCK_TIME_S - 0.01
    )
    pursuit_pirate.call("_update_rear_torpedo", 0.02)
    var rear_projectiles := get_nodes_in_group("weapon_projectile").filter(
        func(projectile: Node) -> bool:
            return projectile.weapon_kind == "pirate_torpedo"
    )
    if (
        runtime.pirate_torpedoes_fired != pirate_torpedoes_before + 1
        or pursuit_pirate.torpedoes_remaining != 2
        or rear_projectiles.is_empty()
        or rear_projectiles[-1].acquired_target != null
        or rear_projectiles[-1].terminal_target != player
        or rear_projectiles[-1].travel_velocity.normalized().dot(
            pirate_rear_direction
        ) < 0.999
    ):
        fail("pirate torpedo did not launch straight aft inside 300 meters")
        return
    var rear_torpedo := rear_projectiles[-1] as Node3D
    rear_torpedo.global_position = (
        player.global_position - pirate_rear_direction * 99.0
    )
    rear_torpedo.call("_physics_process", 0.001)
    if (
        not rear_torpedo.terminal_lock_acquired
        or rear_torpedo.acquired_target != player
    ):
        fail("pirate torpedo did not acquire terminal guidance within 100 meters")
        return
    var pirate_forward_direction := -pursuit_pirate.global_basis.z.normalized()
    player.global_position = (
        pursuit_pirate.global_position + pirate_forward_direction * 120.0
    )
    pursuit_pirate.forward_torpedo_lock_time = (
        pursuit_pirate.REAR_TORPEDO_LOCK_TIME_S - 0.01
    )
    pursuit_pirate.call("_update_pursuit_torpedoes", 0.02)
    var pirate_torpedoes := get_nodes_in_group("weapon_projectile").filter(
        func(projectile: Node) -> bool:
            return projectile.weapon_kind == "pirate_torpedo"
    )
    if (
        runtime.pirate_torpedoes_fired != pirate_torpedoes_before + 2
        or pursuit_pirate.torpedoes_remaining != 1
        or pirate_torpedoes[-1].travel_velocity.normalized().dot(
            pirate_forward_direction
        ) < 0.999
    ):
        fail("pirate could not fire its terminal-lock torpedo straight forward at JB100")
        return
    if (
        not runtime.fire_pirate_torpedo(pursuit_pirate, pirate_rear_direction)
        or pursuit_pirate.torpedoes_remaining != 0
        or runtime.fire_pirate_torpedo(pursuit_pirate, pirate_rear_direction)
        or removed_pirate.torpedoes_remaining != 3
    ):
        fail("pirate did not own exactly three fore/aft torpedoes")
        return
    player.global_position = player_position_before_rear_test
    var no_exclusions: Array[RID] = []
    runtime.call(
        "_spawn_combat_projectile",
        "starbase_plasma",
        strafing_pirate.global_position - Vector3(0.0, 0.0, 30.0),
        Vector3.BACK,
        155.0,
        0.8,
        RID(),
        no_exclusions
    )
    if strafing_pirate.call("_defense_fire_avoidance").length_squared() <= 0.0001:
        fail("pirate did not treat intercepting station fire as an evasive threat")
        return
    strafing_pirate.ai_enabled = false

    var shield := runtime.targets_by_category["shield"][0] as StaticBody3D
    var weapon := runtime.targets_by_category["weapon"][0] as StaticBody3D
    shield.apply_weapon_hit(1.0, "pirate_plasma", shield.global_position, Vector3.ZERO)
    if (
        runtime.station_report != "STATION REPORTS DAMAGE TO SHIELDS."
        or not runtime.mission_screen_label.text.contains(
            "DAMAGE TO SHIELDS."
        )
    ):
        fail("right cockpit report did not announce live shield damage")
        return
    runtime.call("_on_station_target_damaged", weapon, 2.0)
    if (
        runtime.station_report != "STATION REPORTS DAMAGE TO WEAPONS."
        or not runtime.mission_screen_label.text.contains(
            "DAMAGE TO WEAPONS."
        )
    ):
        fail("right cockpit report did not announce live weapons damage")
        return
    runtime.call(
        "_on_station_target_damaged", runtime.targets_by_category["hangar"][0], 2.0
    )
    if (
        runtime.station_report != "STATION REPORTS DAMAGE TO HANGARS."
        or runtime.station_alerts.size() != 3
        or not runtime.mission_screen_label.text.contains(
            "DAMAGE TO SHIELDS."
        )
    ):
        fail("right cockpit report did not announce live hangar damage")
        return
    if not is_equal_approx(shield.effectiveness(), 2.0 / 3.0):
        fail("station health did not proportionally reduce system effectiveness")
        return
    shield.apply_weapon_hit(2.0, "pirate_plasma", shield.global_position, Vector3.ZERO)
    if not shield.disabled or not is_equal_approx(runtime._pirate_station_damage(weapon), 2.0):
        fail("a disabled shield did not increase weapon/hangar hit damage")
        return

    var retreating := runtime.pirates[0] as AnimatableBody3D
    for hit in 5:
        retreating.apply_weapon_hit(
            0.8, "frapray", retreating.global_position, Vector3.FORWARD
        )
    if retreating.destroyed or retreating.behavior == "RETREAT":
        fail("five individual FrapRay bolts incorrectly drove off a flyer")
        return
    retreating.apply_weapon_hit(
        0.8, "frapray", retreating.global_position, Vector3.FORWARD
    )
    if retreating.destroyed or retreating.behavior != "RETREAT":
        fail("six individual FrapRay bolt hits did not start a retreat")
        return
    retreating.sync_to_physics = false
    retreating.global_position = runtime.STARBASE_CENTER + Vector3(0.0, 0.0, -5100.0)
    retreating.call("_advance_retreat", 0.001)
    if not retreating.perimeter_crossed:
        fail("a retreating flyer did not count as driven off at 5,000 m")
        return
    if runtime.station_report != "STATION REPORTS 1 PIRATE FLYER HAS RETREATED.":
        fail("right cockpit report did not announce a pirate retreat")
        return
    for hit in 6:
        retreating.apply_weapon_hit(
            0.8, "frapray", retreating.global_position, Vector3.FORWARD
        )
    if not retreating.destroyed:
        fail("twelve individual FrapRay bolt hits did not destroy a flyer")
        return

    var mixed_kill := runtime.pirates[1] as AnimatableBody3D
    mixed_kill.apply_weapon_hit(
        3.2, "proton_torpedo", mixed_kill.global_position, Vector3.FORWARD
    )
    for hit in 6:
        mixed_kill.apply_weapon_hit(
            0.8, "frapray", mixed_kill.global_position, Vector3.FORWARD
        )
    if not mixed_kill.destroyed:
        fail("one torpedo plus six individual FrapRay hits did not destroy a flyer")
        return

    var torpedo_kill := runtime.pirates[2] as AnimatableBody3D
    for hit in 2:
        torpedo_kill.apply_weapon_hit(
            3.2, "proton_torpedo", torpedo_kill.global_position, Vector3.FORWARD
        )
    if not torpedo_kill.destroyed or runtime.current_state() != "COMPLETE":
        fail("two torpedoes and three neutralized flyers did not complete")
        return
    if (
        not runtime.failure_overlay.visible
        or runtime.failure_overlay.text != "SUCCESS"
        or runtime.failure_overlay.get_theme_color("font_color").g < 0.9
    ):
        fail("Mission 003 completion did not show the green SUCCESS announcement")
        return
    if runtime.starfighter_secret_state != "DOCKED":
        fail("post-success Starfighter secret launched before a hangar re-entry")
        return
    player.global_position = runtime.open_hangar_center + Vector3(80.0, 0.0, 0.0)
    runtime.call("_update_post_success_secret", 0.0)
    if not runtime.starfighter_secret_armed:
        fail("leaving the post-success hangar did not arm its Starfighter secret")
        return
    player.global_position = runtime.open_hangar_center
    runtime.call("_update_post_success_secret", 0.0)
    if runtime.starfighter_secret_state != "LAUNCHING":
        fail("post-success hangar re-entry did not launch the Earth Starfighter")
        return
    var starfighter_launch_start: Vector3 = runtime.docked_starfighter.global_position
    runtime.call("_update_post_success_secret", 1.0)
    if runtime.docked_starfighter.global_position.is_equal_approx(
        starfighter_launch_start
    ):
        fail("Earth Starfighter did not fly out of its berth")
        return
    runtime.call("_update_post_success_secret", 3.0)
    if runtime.starfighter_secret_state != "ORBITING":
        fail("Earth Starfighter did not transition from launch to station orbit")
        return
    var starfighter_orbit_start: Vector3 = runtime.docked_starfighter.global_position
    runtime.call("_update_post_success_secret", 0.5)
    if runtime.docked_starfighter.global_position.is_equal_approx(
        starfighter_orbit_start
    ):
        fail("Earth Starfighter did not continue circling Starbase 86")
        return

    runtime.game_shell.queue_free()
    await process_frame
    var shield_runtime := await _spawn_runtime()
    shield_runtime.begin_mission()
    for pirate in shield_runtime.pirates:
        pirate.ai_enabled = false
    var shield_player := shield_runtime.player as CharacterBody3D
    shield_player.apply_weapon_hit(
        1.0, "starbase_plasma", shield_player.global_position, Vector3.FORWARD
    )
    shield_player.apply_weapon_hit(
        1.0, "pirate_torpedo", shield_player.global_position, Vector3.FORWARD
    )
    if (
        not is_equal_approx(shield_player.shield_percent, 65.0)
        or not is_equal_approx(shield_player.hull_integrity, 100.0)
    ):
        fail("JB100 shields did not absorb ten-point plasma and 25-point torpedo hits")
        return
    shield_player.controls_enabled = false
    shield_player._physics_process(1.0)
    shield_player.controls_enabled = true
    if not is_equal_approx(shield_player.shield_percent, 67.0):
        fail("JB100 shields did not recharge at two percent per second")
        return
    shield_player.shield_percent = 100.0
    shield_runtime.call("_on_player_impact", 20.0, shield_runtime.pirates[0])
    shield_runtime.call("_on_player_impact", 20.0, shield_runtime.pirates[0])
    if not is_equal_approx(shield_player.shield_percent, 50.0):
        fail("pirate collision did not remove 50 shields with impact debounce")
        return
    shield_runtime.player_collision_damage_cooldown_s = 0.0
    shield_runtime.call("_on_player_impact", 20.0, shield_runtime.starbase)
    shield_runtime.call("_update_hud")
    if (
        shield_runtime.current_state() != "FAILED"
        or not is_zero_approx(shield_player.shield_percent)
        or shield_runtime.systems_value_labels["SHD"].text != "SHD: 000%"
        or not shield_runtime.failure_overlay.visible
        or shield_runtime.failure_overlay.text != "FAILED"
        or shield_runtime.failure_overlay.get_theme_font_size("font_size") < 72
    ):
        fail("total shield loss did not show the large Mission 003 failure notice")
        return
    shield_runtime.game_shell.queue_free()
    await process_frame
    var failed_runtime := await _spawn_runtime()
    failed_runtime.begin_mission()
    for pirate in failed_runtime.pirates:
        pirate.ai_enabled = false
    for target in failed_runtime.station_targets:
        target.apply_weapon_hit(
            3.0, "pirate_plasma", target.global_position, Vector3.ZERO
        )
    if failed_runtime.current_state() != "FAILED":
        fail("losing all nine station targets did not fail the mission")
        return
    for pirate in failed_runtime.pirates:
        if pirate.behavior != "CIRCLE_STATION":
            fail("mission failure did not redirect every active pirate to circle the station")
            return
    var circling_pirate := failed_runtime.pirates[0] as AnimatableBody3D
    var circle_start: Vector3 = circling_pirate.global_position
    circling_pirate.ai_enabled = true
    circling_pirate.call("_physics_process", 0.25)
    if (
        circling_pirate.global_position.is_equal_approx(circle_start)
        or circling_pirate.run_shot_fired == false
    ):
        fail("post-failure station circle did not move peacefully around Starbase 86")
        return
    print(
        "MISSION-003-RUNTIME-OK: hangar launch + hidden objectives + fuzzy pirates + "
        + "friendly fire + retreat/destruction + station defense"
    )
    failed_runtime.game_shell.queue_free()
    quit(0)
