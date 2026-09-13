extends Node

const MISSION_SCENES := {
    "001": "res://generated/scenes/missions/mission_001_retrieve_mining_probe.tscn",
    "002": "res://scenes/mission_002_planetfall.tscn",
    "003": "res://scenes/mission_003_starbase_defense.tscn",
}

@export_enum("001", "002", "003") var default_mission := "003"


func _ready() -> void:
    var mission_number := _requested_mission()
    var packed := load(MISSION_SCENES[mission_number]) as PackedScene
    if packed == null:
        push_error("JourneyBlaster could not load Mission %s" % mission_number)
        return
    var mission_shell := packed.instantiate()
    mission_shell.name = "Mission%s" % mission_number
    add_child(mission_shell)


func _requested_mission() -> String:
    for argument in OS.get_cmdline_user_args():
        if argument.begins_with("--mission="):
            var requested := argument.trim_prefix("--mission=").pad_zeros(3)
            if MISSION_SCENES.has(requested):
                return requested
            push_warning("Unknown JourneyBlaster mission '%s'; using %s" % [
                requested, default_mission
            ])
    return default_mission
