extends Node3D

const CombatEffects = preload("res://scripts/combat_effects.gd")

var weapon_kind := "frapray"
var travel_velocity := Vector3.ZERO
var damage := 1.0
var lifetime_s := 2.5
var shooter_rid: RID
var additional_exclusions: Array[RID] = []
var vapor_clock := 0.0
var acquired_target: Node3D
var vapor_puffs: Array[MeshInstance3D] = []


func configure(
    kind: String,
    start_position: Vector3,
    direction: Vector3,
    speed_mps: float,
    hit_damage: float,
    source_rid: RID,
    extra_exclusions: Array[RID] = [],
    target: Node3D = null
) -> void:
    weapon_kind = kind
    position = start_position
    travel_velocity = direction.normalized() * speed_mps
    damage = hit_damage
    shooter_rid = source_rid
    additional_exclusions = extra_exclusions.duplicate()
    acquired_target = target
    basis = Basis.looking_at(direction.normalized(), Vector3.UP)


func _ready() -> void:
    add_to_group("weapon_projectile")
    if weapon_kind == "proton_torpedo":
        name = "ProtonTorpedo"
        lifetime_s = 12.0
        _build_torpedo_visual()
        _spawn_vapor_puff()
    elif weapon_kind == "pirate_torpedo":
        name = "PirateRearTorpedo"
        lifetime_s = 6.0
        _build_pirate_torpedo_visual()
        _spawn_vapor_puff()
    elif weapon_kind == "starbase_plasma":
        name = "StarbaseDefenseBolt"
        _build_colored_bolt(
            Color(0.12, 1.0, 0.72), Color(0.02, 0.72, 0.48), 4.2
        )
    elif weapon_kind == "pirate_plasma":
        name = "PiratePlasmaBolt"
        _build_colored_bolt(
            Color(1.0, 0.08, 0.035), Color(1.0, 0.025, 0.01), 5.8
        )
    else:
        name = "FrapRayBolt"
        _build_frapray_visual()


func _physics_process(delta: float) -> void:
    if (
        weapon_kind == "proton_torpedo"
        and acquired_target != null
        and is_instance_valid(acquired_target)
        and acquired_target.visible
    ):
        if (
            acquired_target.is_in_group("mission_003_pirate")
            and bool(acquired_target.get("destroyed"))
        ):
            _finish_impact(null, global_position)
            return
        if global_position.distance_to(acquired_target.global_position) <= 2.8:
            _finish_impact(acquired_target, acquired_target.global_position)
            return
        var target_direction := (
            acquired_target.global_position - global_position
        ).normalized()
        var speed := travel_velocity.length()
        travel_velocity = travel_velocity.lerp(
            target_direction * speed, clampf(delta * 8.0, 0.0, 1.0)
        )
        if travel_velocity.length_squared() > 0.01:
            basis = Basis.looking_at(travel_velocity.normalized(), Vector3.UP)
    var start := global_position
    var finish := start + travel_velocity * delta
    var query := PhysicsRayQueryParameters3D.create(start, finish)
    var exclusions: Array[RID] = additional_exclusions.duplicate()
    if shooter_rid.is_valid():
        exclusions.append(shooter_rid)
    query.exclude = exclusions
    var result := get_world_3d().direct_space_state.intersect_ray(query)
    if not result.is_empty():
        var collider: Object = result.get("collider")
        _finish_impact(collider, result.get("position", finish))
        return
    global_position = finish
    lifetime_s -= delta
    if weapon_kind in ["proton_torpedo", "pirate_torpedo"]:
        vapor_clock -= delta
        if vapor_clock <= 0.0:
            vapor_clock = 0.045
            _spawn_vapor_puff()
    if lifetime_s <= 0.0:
        queue_free()


func _finish_impact(collider: Object, impact_position: Vector3) -> void:
    if weapon_kind in ["proton_torpedo", "pirate_torpedo"]:
        # Hide the projectile immediately; queue_free() is deferred until the
        # end of the frame and otherwise leaves a frozen blue core at impact.
        visible = false
        set_physics_process(false)
        for puff in vapor_puffs:
            if is_instance_valid(puff):
                puff.queue_free()
        vapor_puffs.clear()
        CombatEffects.spawn_torpedo_impact_flash(get_parent(), impact_position)
        CombatEffects.spawn_dust_cloud(get_parent(), impact_position, 0.84, 10)
    if collider and collider.has_method("apply_weapon_hit"):
        collider.apply_weapon_hit(
            damage,
            weapon_kind,
            impact_position,
            travel_velocity.normalized()
        )
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


func _build_colored_bolt(
    color: Color, emission_color: Color, emission_energy: float
) -> void:
    var bolt := MeshInstance3D.new()
    bolt.name = "CombatPlasmaBolt"
    var mesh := BoxMesh.new()
    mesh.size = Vector3(0.3, 0.3, 3.8)
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = color
    material.emission_enabled = true
    material.emission = emission_color
    material.emission_energy_multiplier = emission_energy
    mesh.material = material
    bolt.mesh = mesh
    add_child(bolt)
    var light := OmniLight3D.new()
    light.name = "CombatPlasmaGlow"
    light.light_color = color
    light.light_energy = 3.2
    light.omni_range = 6.0
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


func _build_pirate_torpedo_visual() -> void:
    var core := MeshInstance3D.new()
    core.name = "RedRearTorpedoCore"
    var mesh := SphereMesh.new()
    mesh.radius = 0.34
    mesh.height = 0.68
    mesh.radial_segments = 10
    mesh.rings = 5
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(1.0, 0.12, 0.035)
    material.emission_enabled = true
    material.emission = Color(1.0, 0.025, 0.008)
    material.emission_energy_multiplier = 9.0
    mesh.material = material
    core.mesh = mesh
    add_child(core)
    var light := OmniLight3D.new()
    light.name = "RedRearTorpedoGlow"
    light.light_color = Color(1.0, 0.08, 0.025)
    light.light_energy = 5.0
    light.omni_range = 9.0
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
    vapor_puffs.append(puff)
    puff.global_position = global_position + global_basis.z * 0.34
    puff.scale = Vector3.ONE * 0.55
    var tween := puff.create_tween().set_parallel(true)
    tween.tween_property(puff, "scale", Vector3.ONE * 1.8, 0.62)
    tween.tween_property(puff, "transparency", 1.0, 0.62)
    tween.chain().tween_callback(puff.queue_free)
