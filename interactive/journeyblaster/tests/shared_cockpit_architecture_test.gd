extends SceneTree

const MISSIONS := [
    "res://generated/scenes/missions/mission_001_retrieve_mining_probe.tscn",
    "res://scenes/mission_002_planetfall.tscn",
    "res://scenes/mission_003_starbase_defense.tscn",
]


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("SHARED-COCKPIT-ARCHITECTURE-ERROR: %s" % message)
    quit(1)


func _run() -> void:
    for scene_path in MISSIONS:
        var packed := load(scene_path) as PackedScene
        if packed == null:
            fail("mission scene did not load: %s" % scene_path)
            return
        var shell := packed.instantiate() as Node3D
        root.add_child(shell)
        await process_frame
        await process_frame
        if shell.active_mission == null or shell.player == null or shell.cockpit == null:
            fail("shell did not inject player, cockpit, and mission: %s" % scene_path)
            return
        if shell.find_children("player_jb100", "CharacterBody3D", true, false).size() != 1:
            fail("mission does not contain exactly one shell-owned JB100: %s" % scene_path)
            return
        if shell.find_children("HUD", "CanvasLayer", true, false).size() != 1:
            fail("mission does not contain exactly one shared cockpit: %s" % scene_path)
            return
        for screen_name in [
            "LeftSystemsScreen", "MiddleSensorScreen", "RightMissionScreen"
        ]:
            if shell.cockpit.find_child(screen_name, true, false) == null:
                fail("shared cockpit is missing %s in %s" % [screen_name, scene_path])
                return
        if not shell.player.power_system_enabled or not shell.player.shield_tracking_enabled:
            fail("permanent JB100 systems are not active in %s" % scene_path)
            return
        if shell.cockpit.mission_screen_label.text.is_empty():
            fail("mission did not publish its objective to the shared screen: %s" % scene_path)
            return
        if scene_path.contains("mission_001"):
            var probe := shell.active_mission.find_child(
                "mining_probe", true, false
            ) as Node3D
            if probe == null or not probe.is_in_group("sensor_objective_contact"):
                fail("Mission 001 probe is not registered as a yellow objective contact")
                return
            if shell.cockpit.sensor_globe._contact_color(probe).g < 0.8:
                fail("Mission 001 probe objective contact is not yellow")
                return
        shell.queue_free()
        await process_frame
    print("SHARED-COCKPIT-ARCHITECTURE-OK: Missions 001-003 use one JB100 shell")
    quit(0)
