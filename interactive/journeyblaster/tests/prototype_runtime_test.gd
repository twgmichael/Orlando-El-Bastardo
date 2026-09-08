extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("PROTOTYPE-RUNTIME-ERROR: %s" % message)
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
    var probe := runtime.find_child("mining_probe", true, false) as RigidBody3D
    var chair := player.find_child("SeatPivot", true, false)
    if player == null or probe == null or chair == null:
        fail("player, probe, or rotating chair is missing")
        return
    if not player.has_method("speed_mps") or not chair.has_method("snap_to_preset"):
        fail("flight or independent-chair controller is missing")
        return

    var ship_basis := player.global_transform.basis
    chair.snap_to_preset(4)
    if chair.current_view_label() != "STRAIGHT BACK":
        fail("straight-back chair view is unavailable")
        return
    if not player.global_transform.basis.is_equal_approx(ship_basis):
        fail("chair rotation changed ship heading")
        return
    chair.snap_to_preset(0)

    runtime.begin_mission()
    if runtime.current_state() != "LOCATE":
        fail("mission did not enter LOCATE")
        return

    player.global_position = probe.global_position + Vector3(0.0, 0.0, 100.0)
    player.velocity = Vector3.ZERO
    await physics_frame
    runtime.identification_progress = runtime.mission_data["sensors"]["identification_dwell_s"]
    runtime._update_mission(0.0)
    if runtime.current_state() != "APPROACH":
        fail("Senso-Globe identification did not unlock APPROACH")
        return

    player.global_position = probe.global_position + Vector3(0.0, 0.0, 10.0)
    player.velocity = Vector3.ZERO
    await physics_frame
    runtime._update_mission(0.0)
    if runtime.current_state() != "DOWNLOAD_READY":
        fail("safe probe approach did not unlock download")
        return
    runtime.request_interaction()
    if runtime.current_state() != "DOWNLOADING":
        fail("download interaction did not start")
        return
    runtime.download_progress = runtime.mission_data["interactions"]["download"]["duration_s"]
    runtime._update_mission(0.0)
    runtime.state_elapsed = 0.65
    runtime._update_mission(0.0)
    if runtime.current_state() != "TOW_READY":
        fail("completed download did not unlock towing")
        return

    runtime.request_interaction()
    runtime.state_elapsed = 0.35
    runtime._update_mission(0.0)
    if runtime.current_state() != "RETURN_TO_ENTRY" or not runtime.tow_attached:
        fail("physical tow did not begin the return leg")
        return
    runtime._update_tow(0.1)
    if not runtime.tow_beam.visible:
        fail("tow beam is not visible while the probe is attached")
        return

    var entry := runtime.find_child("asteroid_field_entry", true, false) as Node3D
    player.global_position = entry.global_position
    probe.global_position = entry.global_position + Vector3(0.0, 0.0, 14.0)
    runtime._update_mission(0.0)
    if runtime.current_state() != "EXIT_READY":
        fail("returning ship and probe did not unlock hyperspace")
        return
    runtime.request_hyperspace()
    runtime.state_elapsed = 2.0
    runtime._update_mission(0.0)
    if runtime.current_state() != "COMPLETE":
        fail("hyperspace did not complete the mission")
        return

    print("PROTOTYPE-RUNTIME-OK: flight + chair + sensors + download + tow + return + hyperspace")
    runtime.queue_free()
    quit(0)
