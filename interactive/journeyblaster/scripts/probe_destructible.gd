extends RigidBody3D

const CombatEffects = preload("res://scripts/combat_effects.gd")

signal collision_damaged(impact_speed_mps: float)
signal destroyed_by_weapon(weapon_kind: String)

@export var integrity := 1.0

var damaged := false
var destroyed := false
var collision_hits := 0
var warning_light: OmniLight3D


func _ready() -> void:
    add_to_group("destructible_probe")


func can_download_data() -> bool:
    return not damaged and not destroyed


func can_be_towed() -> bool:
    return not destroyed


func apply_collision_damage(impact_speed_mps: float) -> void:
    if destroyed or impact_speed_mps < 0.5:
        return
    damaged = true
    collision_hits += 1
    integrity = maxf(0.05, integrity - clampf(impact_speed_mps / 45.0, 0.12, 0.65))
    _show_damage_feedback()
    collision_damaged.emit(impact_speed_mps)


func apply_weapon_hit(
    _damage: float,
    weapon_kind: String,
    hit_position: Vector3,
    impact_direction: Vector3
) -> void:
    if destroyed:
        return
    destroyed = true
    integrity = 0.0
    _spawn_explosion(hit_position, impact_direction)
    destroyed_by_weapon.emit(weapon_kind)
    _hide_destroyed_probe()


func _show_damage_feedback() -> void:
    CombatEffects.spawn_dust_cloud(get_parent(), global_position, 0.3, 6)
    if warning_light == null:
        warning_light = OmniLight3D.new()
        warning_light.name = "ProbeDamageWarning"
        warning_light.light_color = Color(1.0, 0.08, 0.02)
        warning_light.light_energy = 3.5
        warning_light.omni_range = 5.0
        add_child(warning_light)
    var tween := warning_light.create_tween()
    tween.tween_property(warning_light, "light_energy", 0.7, 0.3)


func _spawn_explosion(hit_position: Vector3, impact_direction: Vector3) -> void:
    var parent := get_parent() as Node3D
    var burst := Node3D.new()
    burst.name = "ProbeExplosion"
    burst.add_to_group("probe_explosion")
    parent.add_child(burst)
    burst.global_position = global_position

    var flash := MeshInstance3D.new()
    flash.name = "ProbeExplosionFlash"
    var mesh := SphereMesh.new()
    mesh.radius = 0.6
    mesh.height = 1.2
    mesh.radial_segments = 10
    mesh.rings = 6
    var material := StandardMaterial3D.new()
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(1.0, 0.3, 0.03, 0.96)
    material.emission_enabled = true
    material.emission = Color(1.0, 0.08, 0.01)
    material.emission_energy_multiplier = 9.0
    mesh.material = material
    flash.mesh = mesh
    burst.add_child(flash)

    var light := OmniLight3D.new()
    light.name = "ProbeExplosionLight"
    light.light_color = Color(1.0, 0.2, 0.04)
    light.light_energy = 14.0
    light.omni_range = 18.0
    burst.add_child(light)

    CombatEffects.spawn_dust_cloud(
        parent,
        hit_position - impact_direction.normalized() * 0.15,
        1.25,
        20
    )
    flash.scale = Vector3.ONE * 0.2
    var burst_tween := burst.create_tween().set_parallel(true)
    burst_tween.tween_property(flash, "scale", Vector3.ONE * 4.2, 0.72).set_trans(
        Tween.TRANS_EXPO
    ).set_ease(Tween.EASE_OUT)
    burst_tween.tween_property(flash, "transparency", 1.0, 0.72)
    burst_tween.tween_property(light, "light_energy", 0.0, 0.62)
    var cleanup := burst.create_tween()
    cleanup.tween_interval(1.0)
    cleanup.tween_callback(burst.queue_free)


func _hide_destroyed_probe() -> void:
    var visual := get_node_or_null("Visual") as Node3D
    if visual:
        visual.visible = false
    for child in get_children():
        if child is CollisionShape3D:
            child.set_deferred("disabled", true)
    collision_layer = 0
    collision_mask = 0
    if warning_light:
        warning_light.visible = false
