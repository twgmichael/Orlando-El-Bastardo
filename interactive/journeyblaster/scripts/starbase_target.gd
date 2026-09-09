extends StaticBody3D

signal target_disabled(target: StaticBody3D)

var system_category := "shield"
var vertical_tier := "middle"
var maximum_health := 3.0
var health := 3.0
var disabled := false
var hit_flash: OmniLight3D


func configure(category: String, tier: String, tint: Color) -> void:
    system_category = category
    vertical_tier = tier
    name = "%s_%s_target" % [category, tier]
    add_to_group("mission_003_station_target")
    add_to_group("mission_003_%s_target" % category)

    var collision := CollisionShape3D.new()
    collision.name = "DamageCollision"
    var collision_shape := SphereShape3D.new()
    collision_shape.radius = 5.5
    collision.shape = collision_shape
    add_child(collision)

    var marker := MeshInstance3D.new()
    marker.name = "SystemHousing"
    var mesh := SphereMesh.new()
    mesh.radius = 3.4
    mesh.height = 6.8
    mesh.radial_segments = 12
    mesh.rings = 6
    var material := StandardMaterial3D.new()
    material.albedo_color = tint.darkened(0.5)
    material.metallic = 0.55
    material.roughness = 0.38
    material.emission_enabled = true
    material.emission = tint.darkened(0.2)
    material.emission_energy_multiplier = 1.8
    mesh.material = material
    marker.mesh = mesh
    add_child(marker)

    hit_flash = OmniLight3D.new()
    hit_flash.name = "DamageFlash"
    hit_flash.light_color = tint
    hit_flash.light_energy = 0.0
    hit_flash.omni_range = 14.0
    add_child(hit_flash)


func apply_weapon_hit(
    damage: float,
    weapon_kind: String,
    _hit_position: Vector3,
    _impact_direction: Vector3
) -> void:
    if disabled or weapon_kind != "pirate_plasma":
        return
    health = maxf(0.0, health - damage)
    hit_flash.light_energy = 8.0
    var tween := hit_flash.create_tween()
    tween.tween_property(hit_flash, "light_energy", 0.0, 0.28)
    if health <= 0.0:
        disabled = true
        collision_layer = 0
        collision_mask = 0
        var visual := get_node_or_null("SystemHousing") as MeshInstance3D
        if visual:
            visual.transparency = 0.72
        target_disabled.emit(self)


func effectiveness() -> float:
    return clampf(health / maximum_health, 0.0, 1.0)

