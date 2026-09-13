extends Node3D

const Cockpit = preload("res://scripts/jb100_cockpit.gd")

@export var mission_number := "003"

@onready var player := $player_jb100 as CharacterBody3D
@onready var mission_host := $MissionHost as Node3D

var cockpit
var active_mission: Node3D


func _ready() -> void:
    cockpit = Cockpit.new()
    cockpit.name = "HUD"
    add_child(cockpit)
    if mission_host.get_child_count() != 1:
        push_error("JourneyBlaster MissionHost requires exactly one mission runtime")
        return
    active_mission = mission_host.get_child(0) as Node3D
    if active_mission.has_method("configure_mission"):
        active_mission.configure_mission(player, cockpit, self)


func restart_mission() -> void:
    get_tree().reload_current_scene()
