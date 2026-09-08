extends RigidBody3D

const CombatEffects = preload("res://scripts/combat_effects.gd")

var fragment_radius := 1.6
var destroyed := false


func configure_fragment(
    radius: float,
    launch_velocity: Vector3,
    tint: Color,
    spin: Vector3
) -> void:
    fragment_radius = radius
    mass = maxf(0.8, radius * 1.6)
    gravity_scale = 0.0
    linear_damp = 0.08
    angular_damp = 0.12
    linear_velocity = launch_velocity
    angular_velocity = spin
    set_meta("size_tier", "fragment")

    var collision := CollisionShape3D.new()
    collision.name = "FragmentCollision"
    var shape := SphereShape3D.new()
    shape.radius = radius * 0.72
    collision.shape = shape
    add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "FragmentVisual"
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    mesh.radial_segments = 7
    mesh.rings = 4
    var material := StandardMaterial3D.new()
    material.albedo_color = tint
    material.roughness = 0.94
    mesh.material = material
    visual.mesh = mesh
    visual.scale = Vector3(1.0, 0.72, 0.86)
    visual.rotation_degrees = Vector3(17.0, 31.0, 9.0)
    add_child(visual)
    add_to_group("destructible_asteroid")
    add_to_group("asteroid_fragment")


func apply_weapon_hit(
    _damage: float,
    _weapon_kind: String,
    hit_position: Vector3,
    _impact_direction: Vector3
) -> void:
    if destroyed:
        return
    destroyed = true
    CombatEffects.spawn_dust_cloud(get_parent(), hit_position, fragment_radius, 28)
    queue_free()
