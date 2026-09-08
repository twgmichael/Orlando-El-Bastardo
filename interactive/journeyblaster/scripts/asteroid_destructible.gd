extends StaticBody3D

const AsteroidFragment = preload("res://scripts/asteroid_fragment.gd")
const CombatEffects = preload("res://scripts/combat_effects.gd")

@export var integrity := 3.0
@export var fragment_count := 3

var destroyed := false
var hits_received := 0


func _ready() -> void:
    add_to_group("destructible_asteroid")
    set_meta("size_tier", "large")


func apply_weapon_hit(
    damage: float,
    weapon_kind: String,
    hit_position: Vector3,
    impact_direction: Vector3
) -> void:
    if destroyed:
        return
    hits_received += 1
    integrity -= damage
    CombatEffects.spawn_dust_cloud(get_parent(), hit_position, 0.55, 7)
    if integrity <= 0.0:
        _break_apart(weapon_kind, impact_direction)


func _break_apart(weapon_kind: String, impact_direction: Vector3) -> void:
    destroyed = true
    var parent := get_parent()
    var center := global_position
    var source_scale := maxf(global_basis.get_scale().length() / sqrt(3.0), 0.7)
    var random := RandomNumberGenerator.new()
    random.seed = hash(name)
    CombatEffects.spawn_dust_cloud(parent, center, 1.7 * source_scale, 22)
    for index in fragment_count:
        var fragment := RigidBody3D.new()
        fragment.name = "%s_fragment_%d" % [name, index + 1]
        fragment.set_script(AsteroidFragment)
        parent.add_child(fragment)
        var direction := Vector3(
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0)
        ).normalized()
        if direction.dot(impact_direction) < -0.45:
            direction = -direction
        var radius := random.randf_range(1.2, 1.8) * source_scale
        fragment.global_position = center + direction * radius * 0.65
        var launch_speed := random.randf_range(4.0, 9.0)
        if weapon_kind == "proton_torpedo":
            launch_speed *= 1.45
        fragment.call(
            "configure_fragment",
            radius,
            direction * launch_speed + impact_direction * 2.0,
            Color(
                random.randf_range(0.22, 0.34),
                random.randf_range(0.19, 0.28),
                random.randf_range(0.17, 0.24)
            ),
            Vector3(
                random.randf_range(-2.4, 2.4),
                random.randf_range(-2.4, 2.4),
                random.randf_range(-2.4, 2.4)
            )
        )
    queue_free()
