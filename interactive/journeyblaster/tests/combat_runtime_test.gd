extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("COMBAT-RUNTIME-ERROR: %s" % message)
    quit(1)


func _run() -> void:
    var scene_path := "res://generated/scenes/missions/mission_001_retrieve_mining_probe.tscn"
    var packed := load(scene_path) as PackedScene
    if packed == null:
        fail("Mission 001 scene did not load")
        return
    var runtime := packed.instantiate()
    root.add_child(runtime)
    await process_frame

    var player := runtime.find_child("player_jb100", true, false) as CharacterBody3D
    var asteroid := runtime.find_child("asteroid_round_01", true, false) as StaticBody3D
    if player == null or asteroid == null:
        fail("player or test asteroid is missing")
        return
    if not player.has_method("fire_frapray") or not player.has_method("fire_proton_torpedo"):
        fail("JB100 weapon controls are missing")
        return
    if not asteroid.has_method("apply_weapon_hit"):
        fail("asteroid destruction controller is missing")
        return

    if not player.fire_frapray():
        fail("FrapRay did not fire")
        return
    var frap_bolts := get_nodes_in_group("weapon_projectile").filter(
        func(projectile: Node) -> bool: return projectile.weapon_kind == "frapray"
    )
    if frap_bolts.size() != 2:
        fail("FrapRay did not emit paired plasma bolts")
        return
    var frap_left := player.find_child("frap_hardpoint_left", true, false) as Node3D
    var frap_right := player.find_child("frap_hardpoint_right", true, false) as Node3D
    var muzzle_matches := 0
    for bolt: Node3D in frap_bolts:
        if (
            bolt.global_position.distance_to(frap_left.global_position) < 0.01
            or bolt.global_position.distance_to(frap_right.global_position) < 0.01
        ):
            muzzle_matches += 1
    if muzzle_matches != 2:
        fail("FrapRay bolts did not originate at both physical cannon muzzles")
        return
    await process_frame
    if frap_bolts[0].find_child("OrangePlasmaBolt", true, false) == null:
        fail("FrapRay orange plasma visual is missing")
        return

    var torpedoes_before: int = player.proton_torpedoes_remaining
    if not player.fire_proton_torpedo():
        fail("proton torpedo did not launch")
        return
    await process_frame
    if player.proton_torpedoes_remaining != torpedoes_before - 1:
        fail("proton torpedo ammunition did not decrement")
        return
    var torpedoes := get_nodes_in_group("weapon_projectile").filter(
        func(projectile: Node) -> bool: return projectile.weapon_kind == "proton_torpedo"
    )
    if torpedoes.size() != 1:
        fail("proton torpedo projectile is missing")
        return
    if torpedoes[0].find_child("BlueCore", true, false) == null:
        fail("proton torpedo blue core is missing")
        return
    if runtime.find_child("WhiteVaporTrail", true, false) == null:
        fail("proton torpedo white vapor trail is missing")
        return

    player.throttle = 0.8
    player.velocity = Vector3(18.0, -4.0, -26.0)
    player.dead_stop()
    if not is_zero_approx(player.throttle) or not player.velocity.is_zero_approx():
        fail("X dead-stop behavior did not zero throttle and velocity")
        return

    for projectile in get_nodes_in_group("weapon_projectile"):
        projectile.queue_free()
    await process_frame
    asteroid.global_position = player.global_position - player.global_basis.z * 34.0
    player.torpedo_cooldown_remaining = 0.0
    if not player.fire_proton_torpedo():
        fail("proton torpedo could not fire at the destructible asteroid")
        return
    for frame in 40:
        await physics_frame
        if get_nodes_in_group("asteroid_fragment").size() == 3:
            break
    var fragments := get_nodes_in_group("asteroid_fragment")
    if fragments.size() != 3:
        fail("proton torpedo impact did not split the large asteroid into three fragments")
        return
    if get_nodes_in_group("combat_dust_cloud").is_empty():
        fail("asteroid breakup dust cloud is missing")
        return

    var fragment: Node = fragments[0]
    fragment.apply_weapon_hit(0.8, "frapray", fragment.global_position, Vector3.FORWARD)
    await process_frame
    if get_nodes_in_group("asteroid_fragment").size() != 2:
        fail("small asteroid fragment did not vaporize")
        return

    var frap_target := runtime.find_child("asteroid_oblong_01", true, false) as StaticBody3D
    var fragments_before_frap := get_nodes_in_group("asteroid_fragment").size()
    frap_target.global_position = player.global_position - player.global_basis.z * 34.0
    player.frapray_cooldown_remaining = 0.0
    if not player.fire_frapray():
        fail("FrapRay could not fire at the destructible asteroid")
        return
    for frame in 24:
        await physics_frame
    if frap_target.hits_received < 2 or frap_target.destroyed:
        fail("first paired FrapRay burst did not damage without prematurely breaking the asteroid")
        return
    player.frapray_cooldown_remaining = 0.0
    if not player.fire_frapray():
        fail("second FrapRay burst did not fire")
        return
    for frame in 30:
        await physics_frame
        if get_nodes_in_group("asteroid_fragment").size() >= fragments_before_frap + 3:
            break
    if get_nodes_in_group("asteroid_fragment").size() < fragments_before_frap + 3:
        fail("paired FrapRay bursts did not break the asteroid")
        return

    print("COMBAT-RUNTIME-OK: FrapRay + proton torpedo + breakup + fragment vaporization + dust")
    runtime.queue_free()
    quit(0)
