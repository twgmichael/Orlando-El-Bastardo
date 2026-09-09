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
    if not runtime.is_player_in_safe_hangar():
        fail("JB100 did not begin inside the safe open hangar")
        return
    var launch_direction: Vector3 = (
        runtime.OPEN_HANGAR_EXIT - runtime.OPEN_HANGAR_CENTER
    ).normalized()
    if (-player.global_basis.z).dot(launch_direction) < 0.98:
        fail("JB100 was not facing the open hangar exit")
        return
    if get_nodes_in_group("mission_003_station_target").size() != 9:
        fail("starbase does not have nine hidden damage targets")
        return
    for category in ["shield", "weapon", "hangar"]:
        if get_nodes_in_group("mission_003_%s_target" % category).size() != 3:
            fail("%s system does not have three damage locations" % category)
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
    for pirate in runtime.pirates:
        if pirate.get_meta("asset_id", "") != "prop_pirate_flyer_A":
            fail("Mission 003 did not use the registered Ellipso flyer model")
            return
        if pirate.ai_enabled:
            fail("pirate AI advanced during the briefing")
            return

    runtime.begin_mission()
    if runtime.current_state() != "DEFEND":
        fail("Enter did not begin the defense mission")
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

    var mixed_kill := runtime.pirates[1] as AnimatableBody3D
    mixed_kill.apply_weapon_hit(
        3.2, "proton_torpedo", mixed_kill.global_position, Vector3.FORWARD
    )
    for hit in 6:
        mixed_kill.apply_weapon_hit(
            0.8, "frapray", mixed_kill.global_position, Vector3.FORWARD
        )
    if not mixed_kill.destroyed:
        fail("one torpedo plus three FrapRay shots did not destroy a flyer")
        return

    var frapray_kill := runtime.pirates[2] as AnimatableBody3D
    for hit in 14:
        frapray_kill.apply_weapon_hit(
            0.8, "frapray", frapray_kill.global_position, Vector3.FORWARD
        )
    if not frapray_kill.destroyed or runtime.current_state() != "COMPLETE":
        fail("seven FrapRay shots and three neutralized flyers did not complete")
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
        if pirate.behavior != "ATTACK_PLAYER":
            fail("station loss did not redirect every active pirate to the JB100")
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
