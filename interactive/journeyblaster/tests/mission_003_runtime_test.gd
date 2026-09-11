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
    var runtime := packed.instantiate() as Node3D
    root.add_child(runtime)
    await process_frame
    return runtime


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
        runtime.get_node_or_null("HUD/LeftSystemsScreen") == null
        or runtime.get_node_or_null("HUD/MiddleSensorScreen/SensorGlobe") == null
        or runtime.get_node_or_null("HUD/RightMissionScreen") == null
    ):
        fail("three-screen cockpit instrumentation mockup is incomplete")
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
    player.proton_torpedoes_remaining = 3
    runtime.call("_update_hud")
    if (
        runtime.systems_value_labels["WPN"].text != "WPN: 070%"
        or runtime.systems_torpedo_label.text != "TPD: 3"
    ):
        fail("cockpit weapon and torpedo readouts did not track live ammunition")
        return
    player.frapray_power_percent = 100.0
    player.proton_torpedoes_remaining = 5
    player.begin_torpedo_charge()
    player.torpedo_charge_elapsed = 1.5
    runtime.call("_update_weapon_aim")
    if (
        not runtime.torpedo_charge_indicator.visible
        or not is_equal_approx(runtime.torpedo_charge_indicator.charge_progress, 0.5)
        or runtime.torpedo_aim.get_theme_color("font_color")
        != Color(0.12, 0.66, 1.0)
    ):
        fail("torpedo reticle did not turn blue and half-fill during charge")
        return
    player.cancel_torpedo_charge()
    runtime.call("_update_weapon_aim")
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
    for pirate in runtime.pirates:
        pirate.ai_enabled = false
        if pirate.attack_run_phase != "INGRESS":
            fail("pirate did not begin by flying to a strafing-run ingress point")
            return
        var ingress_direction: Vector3 = (
            pirate.run_fire_point - pirate.run_ingress_point
        ).normalized()
        var egress_direction: Vector3 = (
            pirate.run_egress_point - pirate.run_fire_point
        ).normalized()
        if ingress_direction.dot(egress_direction) < 0.8:
            fail("pirate strafing lane did not continue past its target")
            return
    if categories.size() != 3:
        fail("pirates did not begin with one hidden objective category each")
        return

    var strafing_pirate := runtime.pirates[0] as AnimatableBody3D
    strafing_pirate.ai_enabled = true
    strafing_pirate.attack_run_phase = "STRAFE"
    strafing_pirate.run_shot_fired = false
    strafing_pirate.fire_timer = 0.0
    strafing_pirate.global_position = strafing_pirate.run_fire_point
    var projectile_count_before := get_nodes_in_group("weapon_projectile").size()
    strafing_pirate.call("_physics_process", 0.001)
    var projectile_count_after_shot := get_nodes_in_group("weapon_projectile").size()
    strafing_pirate.call("_physics_process", 0.001)
    if (
        projectile_count_after_shot != projectile_count_before + 1
        or get_nodes_in_group("weapon_projectile").size() != projectile_count_after_shot
    ):
        fail("pirate did not fire exactly once during a strafing pass")
        return
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
    if runtime.station_report != "STARBASE 86 REPORTS DAMAGE TO SHIELDS.":
        fail("right cockpit report did not announce live shield damage")
        return
    runtime.call("_on_station_target_damaged", weapon, 2.0)
    if runtime.station_report != "STARBASE 86 REPORTS DAMAGE TO WEAPONS.":
        fail("right cockpit report did not announce live weapons damage")
        return
    runtime.call(
        "_on_station_target_damaged", runtime.targets_by_category["hangar"][0], 2.0
    )
    if runtime.station_report != "STARBASE 86 REPORTS DAMAGE TO HANGARS.":
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
    for hit in 6:
        retreating.apply_weapon_hit(
            0.8, "frapray", retreating.global_position, Vector3.FORWARD
        )
    if retreating.destroyed or retreating.behavior != "RETREAT":
        fail("three paired FrapRay shots did not start a retreat")
        return
    retreating.sync_to_physics = false
    retreating.global_position = runtime.STARBASE_CENTER + Vector3(0.0, 0.0, -5100.0)
    retreating.call("_advance_retreat", 0.001)
    if not retreating.perimeter_crossed:
        fail("a retreating flyer did not count as driven off at 5,000 m")
        return
    if runtime.station_report != "STARBASE 86 REPORTS 1 PIRATE FLYER HAS RETREATED.":
        fail("right cockpit report did not announce a pirate retreat")
        return

    var mixed_kill := runtime.pirates[1] as AnimatableBody3D
    for hit in 2:
        mixed_kill.apply_weapon_hit(
            3.2, "proton_torpedo", mixed_kill.global_position, Vector3.FORWARD
        )
    if not mixed_kill.destroyed:
        fail("two proton torpedoes did not destroy a flyer")
        return

    var frapray_kill := runtime.pirates[2] as AnimatableBody3D
    for hit in 12:
        frapray_kill.apply_weapon_hit(
            0.8, "frapray", frapray_kill.global_position, Vector3.FORWARD
        )
    if not frapray_kill.destroyed or runtime.current_state() != "COMPLETE":
        fail("six FrapRay shots and three neutralized flyers did not complete")
        return

    player.apply_weapon_hit(
        10.0, "starbase_plasma", player.global_position, Vector3.FORWARD
    )
    if (
        not is_equal_approx(player.hull_integrity, 90.0)
        or not is_equal_approx(player.thrust_efficiency(), 0.9)
    ):
        fail("friendly fire did not remove ten hull and thrust points")
        return

    runtime.queue_free()
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
    var failed_player := failed_runtime.player as CharacterBody3D
    for hit in 10:
        failed_player.apply_weapon_hit(
            10.0, "pirate_plasma", failed_player.global_position, Vector3.FORWARD
        )
    if not failed_player.disabled_in_space or not is_zero_approx(failed_player.thrust_efficiency()):
        fail("ten combat hits did not leave the JB100 dead in space")
        return

    print(
        "MISSION-003-RUNTIME-OK: hangar launch + hidden objectives + fuzzy pirates + "
        + "friendly fire + retreat/destruction + station defense"
    )
    failed_runtime.queue_free()
    quit(0)
