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

    player.capture_mouse()
    var hover_motion := InputEventMouseMotion.new()
    hover_motion.relative = Vector2(45.0, -20.0)
    player._unhandled_input(hover_motion)
    player._update_mouse_virtual_stick(1.0 / 60.0)
    var hover_turn: Vector2 = player._consume_mouse_rotation(1.0 / 60.0)
    if player.mouse_flight_target.is_zero_approx() or hover_turn.is_zero_approx():
        fail("ship did not steer toward the mouse without a held button")
        return
    if rad_to_deg(hover_turn.length()) >= 0.5:
        fail("mouse-follow steering was not sufficiently damped near center")
        return
    player._update_mouse_virtual_stick(0.25)
    if (
        not player.mouse_virtual_displacement.is_zero_approx()
        or not player.mouse_flight_target.is_zero_approx()
    ):
        fail("idle virtual stick did not spring back to neutral")
        return
    player.recenter_mouse_flight(false)
    var edge_motion := InputEventMouseMotion.new()
    edge_motion.relative = Vector2(player.mouse_control_radius_pixels, 0.0)
    player._unhandled_input(edge_motion)
    player._update_mouse_virtual_stick(1.0 / 60.0)
    var edge_turn: Vector2 = player._consume_mouse_rotation(1.0 / 60.0)
    if rad_to_deg(edge_turn.length()) < 0.35:
        fail("precision mouse curve removed too much edge turn authority")
        return
    player._unhandled_input(hover_motion)
    player._consume_mouse_rotation(1.0 / 60.0)
    player._on_flight_window_inactive()
    if (
        not player.mouse_virtual_displacement.is_zero_approx()
        or not player.mouse_flight_target.is_zero_approx()
        or player.mouse_capture_active
        or not player.mouse_capture_prompt.visible
    ):
        fail("focus loss did not neutralize steering and release the mouse")
        return
    player.capture_mouse()
    player._unhandled_input(hover_motion)
    player._consume_mouse_rotation(1.0 / 60.0)
    player.recenter_mouse_flight(false)
    if (
        not player.mouse_flight_target.is_zero_approx()
        or not player.mouse_rotation_step.is_zero_approx()
        or not player.mouse_virtual_displacement.is_zero_approx()
    ):
        fail("X-style recenter did not clear the mouse heading command")
        return

    var throttle_presets := [0.10, 0.30, 0.50, 0.80, 1.00]
    for preset in throttle_presets:
        player.set_throttle_preset(preset)
        if not is_equal_approx(player.throttle, preset):
            fail("numeric thrust preset did not set the requested throttle")
            return

    var chair := player.find_child("SeatPivot", true, false)
    chair.snap_to_preset(0)
    var expected_view_cycle := [
        "LEFT SIDE", "RIGHT SIDE", "STRAIGHT BACK", "FORWARD-UP", "FORWARD"
    ]
    for expected_view in expected_view_cycle:
        chair.cycle_view(1)
        if chair.current_view_label() != expected_view:
            fail("plus did not advance the requested cockpit view cycle")
            return
    chair.cycle_view(-1)
    if chair.current_view_label() != "FORWARD-UP":
        fail("minus did not reverse the requested cockpit view cycle")
        return

    player.frapray_cooldown_remaining = 0.0
    player.frapray_power_percent = 100.0
    var left_down := InputEventMouseButton.new()
    left_down.button_index = MOUSE_BUTTON_LEFT
    left_down.pressed = true
    player._unhandled_input(left_down)
    var left_up := InputEventMouseButton.new()
    left_up.button_index = MOUSE_BUTTON_LEFT
    left_up.pressed = false
    player._unhandled_input(left_up)
    if player.frapray_shots_fired != 1 or not is_equal_approx(player.frapray_power_percent, 90.0):
        fail("left mouse click did not fire one ten-percent FrapRay volley")
        return
    player._unhandled_input(hover_motion)
    if player.frapray_shots_fired != 1:
        fail("passive mouse steering fired FrapRay without a click")
        return
    player.controls_enabled = false
    player._physics_process(1.0)
    player.controls_enabled = true
    if not is_equal_approx(player.frapray_power_percent, 92.0):
        fail("FrapRay power did not recharge at two percent per second")
        return

    player.torpedo_cooldown_remaining = 0.0
    player.proton_torpedoes_remaining = 5
    player.global_transform.basis = Basis.IDENTITY
    var lock_target := StaticBody3D.new()
    lock_target.add_to_group("destructible_asteroid")
    runtime.add_child(lock_target)
    lock_target.global_position = player.global_position + Vector3(0.0, 0.0, -100.0)
    var right_down := InputEventMouseButton.new()
    right_down.button_index = MOUSE_BUTTON_RIGHT
    right_down.pressed = true
    player._unhandled_input(right_down)
    player._physics_process(2.99)
    if (
        player.proton_torpedoes_remaining != 5
        or not player.torpedo_charging
        or player.torpedo_acquired_target != lock_target
    ):
        fail("torpedo build-up did not hold fire and acquire the reticle target")
        return
    lock_target.global_position = player.global_position + Vector3(0.0, 0.0, -1200.0)
    player.torpedo_lock_candidate = lock_target
    player.torpedo_lock_distance_m = 1200.0
    player.torpedo_acquired_target = null
    var out_of_range_scale: float = player.torpedo_lock_reticle_scale()
    if (
        player.torpedo_acquired_target != null or out_of_range_scale >= 0.5
    ):
        fail("out-of-range torpedo target did not shrink and release its lock")
        return
    lock_target.global_position = player.global_position + Vector3(0.0, 0.0, -850.0)
    player.torpedo_lock_distance_m = 850.0
    player.torpedo_acquired_target = lock_target
    if (
        player.torpedo_acquired_target != lock_target
        or player.torpedo_lock_reticle_scale() <= out_of_range_scale
    ):
        fail("torpedo reticle did not grow again when its target returned in range")
        return
    lock_target.global_position = player.global_position + Vector3(0.0, 0.0, -100.0)
    player.call("_update_torpedo_acquisition")
    player._physics_process(0.02)
    if player.proton_torpedoes_remaining != 5 or not player.torpedo_charging:
        fail("fully charged torpedo fired before right mouse was released")
        return
    var right_up := InputEventMouseButton.new()
    right_up.button_index = MOUSE_BUTTON_RIGHT
    right_up.pressed = false
    player._unhandled_input(right_up)
    if player.proton_torpedoes_remaining != 4 or player.torpedo_charging:
        fail("right mouse release did not fire the fully charged torpedo")
        return
    var launched_torpedoes := get_nodes_in_group("weapon_projectile").filter(
        func(projectile: Node) -> bool:
            return projectile.weapon_kind == "proton_torpedo"
    )
    if (
        launched_torpedoes.is_empty()
        or launched_torpedoes[-1].acquired_target != lock_target
        or launched_torpedoes[-1].travel_velocity.length() < 250.0
        or launched_torpedoes[-1].lifetime_s < 11.9
    ):
        fail("released proton torpedo did not retain its acquired target")
        return
    var impact_flashes_before := get_nodes_in_group("torpedo_impact_flash").size()
    var launched_torpedo := launched_torpedoes[-1] as Node3D
    launched_torpedo.call(
        "_finish_impact", null, launched_torpedo.global_position
    )
    if (
        launched_torpedo.visible
        or not launched_torpedo.is_queued_for_deletion()
        or get_nodes_in_group("torpedo_impact_flash").size()
        != impact_flashes_before + 1
    ):
        fail("torpedo impact did not flash and remove its projectile immediately")
        return

    if player.mouse_capture_prompt == null:
        fail("mouse-capture prompt is missing")
        return
    if player.get_node_or_null("DesktopControls/FullscreenButton") != null:
        fail("fullscreen toggle must not be visible in the game HUD")
        return

    player.throttle = 0.8
    player.velocity = Vector3(10.0, 0.0, 0.0)
    var escape := InputEventKey.new()
    escape.physical_keycode = KEY_ESCAPE
    escape.pressed = true
    player._unhandled_input(escape)
    if (
        not is_equal_approx(player.throttle, 0.8)
        or not player.velocity.is_equal_approx(Vector3(10.0, 0.0, 0.0))
        or player.mouse_capture_active
        or not player.mouse_capture_prompt.visible
    ):
        fail("Escape did not release the mouse while preserving flight")
        return
    var shots_before_recapture: int = player.frapray_shots_fired
    player.frapray_cooldown_remaining = 0.0
    player._unhandled_input(left_down)
    if (
        not player.mouse_capture_active
        or player.frapray_shots_fired != shots_before_recapture
        or player.mouse_capture_prompt.visible
    ):
        fail("first click did not safely recapture flight without firing")
        return
    var tab_stop := InputEventKey.new()
    tab_stop.physical_keycode = KEY_TAB
    tab_stop.pressed = true
    player._unhandled_input(tab_stop)
    if not is_zero_approx(player.throttle) or not player.velocity.is_zero_approx():
        fail("Tab did not command all stop")
        return

    print(
        "FLIGHT-CONTROLS-RUNTIME-OK: smooth arrows + ship-local inverted axes + "
        + "virtual stick + X recenter + mouse capture + Tab all stop"
    )
    runtime.queue_free()
    quit(0)
