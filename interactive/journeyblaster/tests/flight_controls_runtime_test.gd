extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("FLIGHT-CONTROLS-RUNTIME-ERROR: %s" % message)
    quit(1)


func _run() -> void:
    var packed := load(
        "res://generated/scenes/missions/mission_001_retrieve_mining_probe.tscn"
    ) as PackedScene
    if packed == null:
        fail("Mission 001 scene did not load")
        return
    var runtime := packed.instantiate()
    root.add_child(runtime)
    await process_frame
    var player := runtime.find_child("player_jb100", true, false) as CharacterBody3D
    if player == null:
        fail("JB100 player is missing")
        return

    var first_step: float = player._smooth_axis(0.0, 1.0, 1.0 / 60.0)
    if first_step <= 0.0 or first_step >= 1.0:
        fail("keyboard steering does not ease into full input")
        return
    var released_step: float = player._smooth_axis(first_step, 0.0, 1.0 / 60.0)
    if released_step < 0.0 or released_step >= first_step:
        fail("keyboard steering does not ease cleanly toward release")
        return

    player.global_transform.basis = Basis.IDENTITY
    player._apply_ship_rotation(0.0, deg_to_rad(12.0), 0.0)
    var upright_forward := -player.global_basis.z.normalized()
    player.global_transform.basis = Basis(Vector3.BACK, PI)
    player._apply_ship_rotation(0.0, deg_to_rad(12.0), 0.0)
    var inverted_forward := -player.global_basis.z.normalized()
    if (
        is_zero_approx(upright_forward.x)
        or is_zero_approx(inverted_forward.x)
        or signf(upright_forward.x) == signf(inverted_forward.x)
    ):
        fail("yaw remained world-relative after the JB100 rolled inverted")
        return
    if not is_equal_approx(upright_forward.z, inverted_forward.z):
        fail("inverted ship-local yaw changed its turn magnitude")
        return

    player._set_mouse_flight_active(true, false)
    player.mouse_flight_delta = Vector2(12.0, -8.0)
    var first_drag: Vector2 = player._consume_mouse_rotation(1.0 / 60.0)
    player._set_mouse_flight_active(false, false)
    if not player.mouse_rotation_step.is_zero_approx():
        fail("mouse smoothing carried stale motion across drag release")
        return
    player._set_mouse_flight_active(true, false)
    player.mouse_flight_delta = Vector2(12.0, -8.0)
    var second_drag: Vector2 = player._consume_mouse_rotation(1.0 / 60.0)
    if not first_drag.is_equal_approx(second_drag):
        fail("the second mouse drag is less responsive than the first")
        return
    if rad_to_deg(first_drag.length()) < 0.35:
        fail("mouse aim remains too sluggish for a deliberate drag")
        return

    print(
        "FLIGHT-CONTROLS-RUNTIME-OK: smooth arrows + ship-local inverted axes + "
        + "repeatable mouse drag"
    )
    runtime.queue_free()
    quit(0)
