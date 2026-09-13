extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("PROBE-DAMAGE-RUNTIME-ERROR: %s" % message)
    quit(1)


func _instantiate_mission() -> Node3D:
    var scene_path := (
        "res://generated/scenes/missions/"
        + "mission_001_retrieve_mining_probe.tscn"
    )
    var packed := load(scene_path) as PackedScene
    if packed == null:
        return null
    var shell := packed.instantiate() as Node3D
    root.add_child(shell)
    return shell.active_mission as Node3D


func _run() -> void:
    var collision_runtime := _instantiate_mission()
    if collision_runtime == null:
        fail("Mission 001 scene did not load")
        return
    await process_frame

    var collision_player := collision_runtime.player as CharacterBody3D
    var collision_probe := collision_runtime.find_child(
        "mining_probe", true, false
    ) as RigidBody3D
    if collision_player == null or collision_probe == null:
        fail("player or mining probe is missing")
        return
    collision_runtime.call("_set_state", "DOWNLOAD_READY")
    collision_runtime.call("_on_player_impact", 9.0, collision_probe)
    await process_frame
    if not collision_probe.damaged or not collision_runtime.probe_damaged:
        fail("ship impact did not damage the mining probe")
        return
    if collision_probe.can_download_data():
        fail("damaged mining probe still permits data download")
        return
    if not collision_probe.can_be_towed():
        fail("collision-damaged mining probe is no longer towable")
        return
    if collision_runtime.current_state() != "TOW_READY":
        fail("probe collision did not bypass download and offer towing")
        return
    collision_player.global_position = (
        collision_probe.global_position + Vector3(0.0, 0.0, 5.0)
    )
    collision_player.velocity = Vector3.ZERO
    collision_runtime.request_interaction()
    if (
        not collision_runtime.tow_attached
        or collision_runtime.current_state() != "IN_TOW"
    ):
        fail("damaged mining probe could not be taken in tow")
        return
    collision_runtime.game_shell.queue_free()
    await process_frame

    var weapon_runtime := _instantiate_mission()
    if weapon_runtime == null:
        fail("Mission 001 scene could not reload for weapon test")
        return
    await process_frame
    var weapon_player := weapon_runtime.player as CharacterBody3D
    var weapon_probe := weapon_runtime.find_child(
        "mining_probe", true, false
    ) as RigidBody3D
    if weapon_player == null or weapon_probe == null:
        fail("weapon-test player or mining probe is missing")
        return
    for obstacle in weapon_runtime.get_children():
        if obstacle.get_meta("mission_role", "") == "obstacle":
            obstacle.position += Vector3(500.0, 500.0, 500.0)
    weapon_player.global_position = Vector3.ZERO
    weapon_player.global_rotation = Vector3.ZERO
    weapon_player.velocity = Vector3.ZERO
    weapon_probe.global_position = Vector3(0.0, 0.02, -24.0)
    if not weapon_player.fire_proton_torpedo(weapon_probe):
        fail("proton torpedo could not fire at mining probe")
        return
    for frame in 40:
        await physics_frame
        if weapon_runtime.current_state() == "FAILED":
            break
    if not weapon_probe.destroyed:
        fail("weapon hit did not destroy the mining probe")
        return
    if weapon_runtime.current_state() != "FAILED":
        fail("destroyed mining probe did not fail the mission")
        return
    if (
        not weapon_runtime.mission_announcement.visible
        or weapon_runtime.mission_announcement.text != "FAILED"
        or weapon_runtime.mission_announcement.get_theme_color("font_color").r < 0.9
    ):
        fail("Mission 001 failure did not show the red FAILED announcement")
        return
    if not weapon_player.controls_enabled:
        fail("flight controls were disabled after mission failure")
        return
    weapon_player.throttle = 0.5
    weapon_player.call("_physics_process", 1.0 / 60.0)
    if weapon_player.velocity.is_zero_approx():
        fail("JB100 could not continue flying after mission failure")
        return
    if weapon_runtime.tow_attached:
        fail("tow remained attached after mining probe destruction")
        return
    var visual := weapon_probe.find_child("Visual", true, false) as Node3D
    if visual == null or visual.visible:
        fail("destroyed mining probe visual did not disappear")
        return
    if get_nodes_in_group("probe_explosion").is_empty():
        fail("mining probe explosion effect is missing")
        return

    print(
        "PROBE-DAMAGE-RUNTIME-OK: collision disables download + tow survives + "
        + "weapon destruction fails mission + post-failure free flight"
    )
    weapon_runtime.game_shell.queue_free()
    quit(0)
