extends Node3D

var weapon_kind := "frapray"
var travel_velocity := Vector3.ZERO
var damage := 1.0
var lifetime_s := 2.5
var shooter_rid: RID
var vapor_clock := 0.0


func configure(
    kind: String,
    start_position: Vector3,
    direction: Vector3,
    speed_mps: float,
    hit_damage: float,
    source_rid: RID
) -> void:
    weapon_kind = kind
    position = start_position
    travel_velocity = direction.normalized() * speed_mps
    damage = hit_damage
    shooter_rid = source_rid
    basis = Basis.looking_at(direction.normalized(), Vector3.UP)


func _ready() -> void:
    add_to_group("weapon_projectile")
    if weapon_kind == "proton_torpedo":
        name = "ProtonTorpedo"
        lifetime_s = 5.0
        _build_torpedo_visual()
        _spawn_vapor_puff()
    else:
        name = "FrapRayBolt"
        _build_frapray_visual()


func _physics_process(delta: float) -> void:
    var start := global_position
    var finish := start + travel_velocity * delta
    var query := PhysicsRayQueryParameters3D.create(start, finish)
    if shooter_rid.is_valid():
        query.exclude = [shooter_rid]
    var result := get_world_3d().direct_space_state.intersect_ray(query)
    if not result.is_empty():
        var collider: Object = result.get("collider")
        if collider and collider.has_method("apply_weapon_hit"):
            collider.apply_weapon_hit(
                damage,
                weapon_kind,
                result.get("position", finish),
                travel_velocity.normalized()
            )
        queue_free()
        return
    global_position = finish
    lifetime_s -= delta
    if weapon_kind == "proton_torpedo":
        vapor_clock -= delta
        if vapor_clock <= 0.0:
            vapor_clock = 0.045
            _spawn_vapor_puff()
    if lifetime_s <= 0.0:
        queue_free()


func _build_frapray_visual() -> void:
    var bolt := MeshInstance3D.new()
    bolt.name = "OrangePlasmaBolt"
    var mesh := BoxMesh.new()
    mesh.size = Vector3(0.22, 0.22, 2.8)
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(1.0, 0.31, 0.025)
    material.emission_enabled = true
    material.emission = Color(1.0, 0.12, 0.005)
    material.emission_energy_multiplier = 7.0
    mesh.material = material
    bolt.mesh = mesh
    add_child(bolt)
    var light := OmniLight3D.new()
    light.name = "PlasmaGlow"
    light.light_color = Color(1.0, 0.24, 0.02)
    light.light_energy = 2.8
    light.omni_range = 5.0
    add_child(light)


func _build_torpedo_visual() -> void:
    var core := MeshInstance3D.new()
    core.name = "BlueCore"
    var mesh := SphereMesh.new()
    mesh.radius = 0.32
    mesh.height = 0.64
    mesh.radial_segments = 10
    mesh.rings = 5
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.06, 0.42, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.015, 0.22, 1.0)
    material.emission_energy_multiplier = 8.0
    mesh.material = material
    core.mesh = mesh
    add_child(core)
    var light := OmniLight3D.new()
    light.name = "BlueCoreGlow"
    light.light_color = Color(0.08, 0.38, 1.0)
    light.light_energy = 4.2
    light.omni_range = 8.0
    add_child(light)


func _spawn_vapor_puff() -> void:
    if not is_inside_tree():
        return
    var puff := MeshInstance3D.new()
    puff.name = "WhiteVaporTrail"
    var mesh := SphereMesh.new()
    mesh.radius = 0.28
    mesh.height = 0.56
    mesh.radial_segments = 6
    mesh.rings = 3
    var material := StandardMaterial3D.new()
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.92, 0.97, 1.0, 0.78)
    material.emission_enabled = true
    material.emission = Color(0.62, 0.76, 1.0)
    material.emission_energy_multiplier = 1.8
    mesh.material = material
    puff.mesh = mesh
    get_parent().add_child(puff)
    puff.global_position = global_position + global_basis.z * 0.34
    puff.scale = Vector3.ONE * 0.55
    var tween := puff.create_tween().set_parallel(true)
    tween.tween_property(puff, "scale", Vector3.ONE * 1.8, 0.62)
    tween.tween_property(puff, "transparency", 1.0, 0.62)
    tween.chain().tween_callback(puff.queue_free)
