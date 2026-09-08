extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("PHASE1-BOOT-ERROR: %s" % message)
    quit(1)


func _run() -> void:
    var manifest_path := "res://generated/manifest.json"
    if not FileAccess.file_exists(manifest_path):
        fail("generated manifest is missing")
        return
    var manifest_file := FileAccess.open(manifest_path, FileAccess.READ)
    var manifest: Variant = JSON.parse_string(manifest_file.get_as_text())
    if not manifest is Dictionary:
        fail("generated manifest is invalid")
        return
    for asset: Dictionary in manifest.get("assets", []):
        var staged_path := "res://%s" % asset.get("staged", "")
        if not ResourceLoader.exists(staged_path, "PackedScene"):
            fail("staged GLB is not imported: %s" % staged_path)
            return
        var wrapper_path: String = asset.get("wrapper_scene", "")
        if not ResourceLoader.exists(wrapper_path, "PackedScene"):
            fail("generated wrapper is unavailable: %s" % wrapper_path)
            return
    var mission_path := "res://generated/data/missions/mission_001_retrieve_mining_probe.interactive.json"
    var mission_file := FileAccess.open(mission_path, FileAccess.READ)
    if mission_file == null:
        fail("staged Mission 001 data is missing")
        return
    var mission: Variant = JSON.parse_string(mission_file.get_as_text())
    if not mission is Dictionary:
        fail("staged Mission 001 data is invalid")
        return
    var scene_path: String = mission.get("runtime_scene", "")
    if not ResourceLoader.exists(scene_path):
        fail("Mission 001 scene does not exist: %s" % scene_path)
        return
    var packed := load(scene_path) as PackedScene
    if packed == null:
        fail("Mission 001 scene did not load")
        return
    var instance := packed.instantiate()
    root.add_child(instance)
    await process_frame

    var player_id: String = mission.get("player", {}).get("instance_id", "")
    var player := instance.find_child(player_id, true, false)
    if player == null:
        fail("player instance is missing")
        return
    if player.find_child("Visual", true, false) == null:
        fail("JB100 visual instance is missing")
        return
    var cockpit_camera := player.find_child("cockpit_camera", true, false) as Camera3D
    if cockpit_camera == null or not cockpit_camera.current:
        fail("current JB100 cockpit camera is missing")
        return
    if not is_equal_approx(cockpit_camera.fov, 72.0):
        fail("JB100 cockpit camera is not using the exterior-first field of view")
        return
    if player.find_child("sensor_origin", true, false) == null:
        fail("JB100 sensor origin is missing")
        return
    var seat_pivot := player.find_child("SeatPivot", true, false) as Node3D
    if seat_pivot == null:
        fail("JB100 independent pilot-chair pivot is missing")
        return
    seat_pivot.call("snap_to_preset", 1)
    if seat_pivot.get("target_pitch_degrees") <= 0.0:
        fail("JB100 forward-up preset does not look upward")
        return
    for senso_globe in [
        "senso_globe_forward",
        "senso_globe_port",
        "senso_globe_starboard",
        "senso_globe_aft",
        "senso_globe_dorsal",
    ]:
        if player.find_child(senso_globe, true, false) == null:
            fail("JB100 Senso-Globe marker is missing: %s" % senso_globe)
            return
    var effect_center := player.find_child(
        "effect_exclusion_center", true, false
    ) as Node3D
    if effect_center == null:
        fail("JB100 effect-exclusion center is missing")
        return
    if (
        not effect_center.position.is_equal_approx(Vector3(0.0, 1.1, 0.0))
        or not is_equal_approx(
            float(effect_center.get_meta("effect_exclusion_radius_m", 0.0)), 3.25
        )
        or not is_equal_approx(
            float(effect_center.get_meta("effect_exclusion_clearance_m", 0.0)), 0.1
        )
    ):
        fail("JB100 effect-exclusion bubble contract is incorrect")
        return
    if (
        player.find_child("frap_hardpoint_left", true, false) == null
        or player.find_child("frap_hardpoint_right", true, false) == null
        or player.find_child("torpedo_launcher", true, false) == null
    ):
        fail("JB100 weapon hardpoints are missing")
        return
    var frap_left := player.find_child("frap_hardpoint_left", true, false) as Node3D
    var frap_right := player.find_child("frap_hardpoint_right", true, false) as Node3D
    if (
        not frap_left.position.is_equal_approx(Vector3(-1.4919, 0.9571, -2.8263))
        or not frap_right.position.is_equal_approx(Vector3(1.4919, 0.9571, -2.8263))
    ):
        fail("FrapRay hardpoints do not match the physical cannon muzzles")
        return
    if instance.find_child("Reticle", true, false) != null:
        fail("legacy fixed green reticle is still present")
        return
    var weapon_aim := instance.find_child("WeaponAim", true, false) as Control
    if weapon_aim == null or not instance.has_method("toggle_weapon_aim"):
        fail("toggleable projected weapon-aim HUD is missing")
        return
    var frap_aim_left := instance.find_child("FrapRayLeft", true, false) as Label
    var frap_aim_right := instance.find_child("FrapRayRight", true, false) as Label
    var torpedo_aim := instance.find_child("Torpedo", true, false) as Label
    if (
        frap_aim_left == null
        or frap_aim_right == null
        or torpedo_aim == null
        or frap_aim_left.text != "•"
        or frap_aim_right.text != "•"
        or torpedo_aim.text != "×"
    ):
        fail("weapon-aim HUD does not distinguish FrapRay dots from the target X")
        return
    instance.toggle_weapon_aim()
    if weapon_aim.visible:
        fail("weapon-aim HUD did not toggle off")
        return
    instance.toggle_weapon_aim()
    if not weapon_aim.visible:
        fail("weapon-aim HUD did not toggle back on")
        return

    var probe := instance.find_child("mining_probe", true, false)
    if probe == null:
        fail("mining probe instance is missing")
        return
    if probe.find_child("Visual", true, false) == null:
        fail("mining probe visual instance is missing")
        return
    if probe.find_child("data_port", true, false) == null:
        fail("mining probe data port is missing")
        return
    if probe.find_child("tow_anchor", true, false) == null:
        fail("mining probe tow anchor is missing")
        return
    if (
        not probe.has_method("apply_collision_damage")
        or not probe.has_method("apply_weapon_hit")
        or not probe.has_method("can_download_data")
        or not probe.has_method("can_be_towed")
    ):
        fail("mining probe destructibility controller is missing")
        return

    var obstacle_count := 0
    for obstacle in mission.get("environment", {}).get("obstacles", []):
        if instance.find_child(obstacle.get("instance_id", ""), true, false) != null:
            obstacle_count += 1
    var expected_obstacles: int = mission.get("environment", {}).get("obstacles", []).size()
    if obstacle_count != expected_obstacles or obstacle_count < 5:
        fail(
            "expected %d staged asteroid instances, found %d"
            % [expected_obstacles, obstacle_count]
        )
        return

    var steps: Array = mission.get("steps", [])
    if steps.is_empty() or steps[0].get("state") != "BRIEFING" or steps[-1].get("state") != "COMPLETE":
        fail("mission state sequence is incomplete")
        return
    print(
        "PHASE1-BOOT-OK: cockpit + chair pivot + Senso-Globes + probe + tow + %d asteroids"
        % obstacle_count
    )
    instance.queue_free()
    quit(0)
