extends RefCounted


static func spawn_torpedo_impact_flash(
    parent: Node, world_position: Vector3
) -> Node3D:
    var flash := Node3D.new()
    flash.name = "TorpedoImpactFlash"
    flash.add_to_group("torpedo_impact_flash")
    parent.add_child(flash)
    flash.global_position = world_position

    var flare := MeshInstance3D.new()
    flare.name = "BlueWhiteFlare"
    flare.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    var mesh := SphereMesh.new()
    mesh.radius = 0.85
    mesh.height = 1.7
    mesh.radial_segments = 12
    mesh.rings = 6
    var material := StandardMaterial3D.new()
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.albedo_color = Color(0.82, 0.93, 1.0, 1.0)
    material.emission_enabled = true
    material.emission = Color(0.3, 0.68, 1.0)
    material.emission_energy_multiplier = 14.0
    material.set_flag(BaseMaterial3D.FLAG_DONT_RECEIVE_SHADOWS, true)
    mesh.material = material
    flare.mesh = mesh
    flare.scale = Vector3.ONE * 0.45
    flash.add_child(flare)

    var light := OmniLight3D.new()
    light.name = "ImpactBurstLight"
    light.light_color = Color(0.62, 0.84, 1.0)
    light.light_energy = 24.0
    light.omni_range = 24.0
    light.shadow_enabled = false
    flash.add_child(light)

    var tween := flash.create_tween().set_parallel(true)
    tween.tween_property(flare, "scale", Vector3.ONE * 3.8, 0.22).set_trans(
        Tween.TRANS_QUAD
    ).set_ease(Tween.EASE_OUT)
    tween.tween_property(flare, "transparency", 1.0, 0.24)
    tween.tween_property(light, "light_energy", 0.0, 0.2)
    var cleanup := flash.create_tween()
    cleanup.tween_interval(0.26)
    cleanup.tween_callback(flash.queue_free)
    return flash


static func spawn_dust_cloud(
    parent: Node,
    world_position: Vector3,
    radius: float,
    puff_count: int = 24
) -> Node3D:
    var cloud := Node3D.new()
    cloud.name = "DisappearingDustCloud"
    cloud.add_to_group("combat_dust_cloud")
    parent.add_child(cloud)
    cloud.global_position = world_position

    var random := RandomNumberGenerator.new()
    random.seed = hash(Vector3i(
        roundi(world_position.x * 10.0),
        roundi(world_position.y * 10.0),
        roundi(world_position.z * 10.0)
    ))
    for index in puff_count:
        var puff := MeshInstance3D.new()
        puff.name = "DustPuff_%02d" % index
        var mesh := SphereMesh.new()
        mesh.radius = random.randf_range(0.28, 0.5) * radius
        mesh.height = mesh.radius * 2.0
        mesh.radial_segments = 6
        mesh.rings = 3
        var material := StandardMaterial3D.new()
        material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
        var warmth := random.randf_range(0.72, 1.0)
        material.albedo_color = Color(0.68 * warmth, 0.57 * warmth, 0.46 * warmth, 0.78)
        material.emission_enabled = true
        material.emission = Color(0.28, 0.17, 0.085)
        material.emission_energy_multiplier = 1.6
        mesh.material = material
        puff.mesh = mesh
        var direction := Vector3(
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0),
            random.randf_range(-1.0, 1.0)
        ).normalized()
        var start_offset := direction * random.randf_range(0.05, 0.35) * radius
        puff.position = start_offset
        puff.scale = Vector3.ONE * random.randf_range(0.65, 1.1)
        cloud.add_child(puff)
        var tween := cloud.create_tween().set_parallel(true)
        tween.tween_property(
            puff,
            "position",
            start_offset + direction * random.randf_range(1.2, 2.8) * radius,
            random.randf_range(1.0, 1.55)
        ).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
        tween.tween_property(
            puff,
            "scale",
            Vector3.ONE * random.randf_range(2.0, 3.1),
            random.randf_range(1.0, 1.55)
        )
        tween.tween_property(puff, "transparency", 1.0, random.randf_range(0.9, 1.45))

    var cleanup := cloud.create_tween()
    cleanup.tween_interval(1.65)
    cleanup.tween_callback(cloud.queue_free)
    return cloud
