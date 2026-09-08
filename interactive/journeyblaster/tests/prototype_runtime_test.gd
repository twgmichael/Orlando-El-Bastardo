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
    if runtime.current_state() != "IN_TOW" or not runtime.tow_attached:
        fail("tow latch sequence did not start")
        return
    var tow_origin := player.find_child("effect_exclusion_center", true, false) as Node3D
    var tow_anchor := probe.find_child("tow_anchor", true, false) as Node3D
    var probe_at_latch := probe.global_position
    var captured_length: float = tow_origin.global_position.distance_to(
        tow_anchor.global_position
    )
    runtime._update_tow(runtime.tow_latch_duration * 0.5)
    if not runtime.tow_beam.visible:
        fail("tow beam is not visible during the latch sequence")
        return
    if not probe.global_position.is_equal_approx(probe_at_latch):
        fail("probe moved before the tow beam finished latching")
        return
    if runtime.tow_beam_mesh.height >= captured_length:
        fail("tow beam did not visibly extend toward the probe")
        return
    runtime._update_tow(runtime.tow_latch_duration * 0.5)
    runtime._update_mission(0.0)
    if runtime.current_state() != "RETURN_TO_ENTRY":
        fail("completed tow latch did not begin the return leg")
        return
    var beam_start: Vector3 = runtime._tow_beam_visible_start(tow_anchor.global_position)
    var bubble_clearance: float = beam_start.distance_to(tow_origin.global_position)
    if not is_equal_approx(bubble_clearance, 3.35):
        fail("tow beam did not begin 10 cm outside the 3.25 m ship bubble")
        return

    var probe_local_before_pivot := player.to_local(probe.global_position)
    player.rotate_y(PI * 0.5)
    var rigidly_rotated_probe := player.to_global(probe_local_before_pivot)
    runtime._update_tow(0.1)
    if not is_equal_approx(
        tow_origin.global_position.distance_to(tow_anchor.global_position),
        captured_length
    ):
        fail("tow constraint did not preserve the captured tether distance")
        return
    if probe.global_position.distance_to(rigidly_rotated_probe) < 0.5:
        fail("probe rotated rigidly with the ship instead of trailing")
        return
    player.global_position += -player.global_transform.basis.z * 5.0
    runtime._update_tow(0.1)
    if not is_equal_approx(
        tow_origin.global_position.distance_to(tow_anchor.global_position),
        captured_length
    ):
        fail("trailing probe did not remain at the latched distance")
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
