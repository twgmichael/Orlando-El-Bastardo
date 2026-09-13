extends SceneTree


func _initialize() -> void:
    call_deferred("_run")


func fail(message: String) -> void:
    push_error("MISSION-002-RUNTIME-ERROR: %s" % message)
    quit(1)


func _run() -> void:
    var packed := load("res://scenes/mission_002_planetfall.tscn") as PackedScene
    if packed == null:
        fail("Mission 002 scene did not load")
        return
    var shell := packed.instantiate()
    root.add_child(shell)
    await process_frame
    await process_frame
    var runtime: Node3D = shell.active_mission
    var player := shell.player as CharacterBody3D
    var primary := runtime.find_child(
        "planetfall_primary_asteroid", true, false
    ) as StaticBody3D
    if player == null or primary == null:
        fail("JB100 or primary asteroid is missing")
        return
    if primary.scale.x < 8.0 or runtime.charge_sites.size() != 3:
        fail("large primary asteroid or its three fracture sites are missing")
        return
    if runtime.current_state() != "INTERCEPT":
        fail("Mission 002 did not begin immediately on load")
        return
    if (
        runtime.mission_announcement == null
        or not runtime.mission_announcement.visible
        or runtime.mission_announcement.text != "GO"
        or runtime.mission_announcement.get_theme_color("font_color").b < 0.9
    ):
        fail("Mission 002 did not begin with the blue GO announcement")
        return
    runtime.mission_announcement.call("_process", 3.0)
    if runtime.mission_announcement.visible:
        fail("Mission 002 GO announcement did not clear after three seconds")
        return
    if not is_equal_approx(runtime.CHARGE_PLACEMENT_WINDOW_S, 180.0):
        fail("charge-placement window is not three minutes")
        return
    if not is_equal_approx(runtime.DEBRIS_CHASE_WINDOW_S, 60.0):
        fail("post-detonation debris chase is not one minute")
        return
    if get_nodes_in_group("mission_002_planet").size() != 1:
        fail("lightweight planet surface is missing")
        return
    if get_nodes_in_group("mission_002_atmosphere").size() != 1:
        fail("planet atmosphere shell is missing")
        return
    var blue_reticle := get_nodes_in_group("mission_002_blue_reticle")
    if blue_reticle.size() != 1 or blue_reticle[0].text != "○":
        fail("blue explosive-placement reticle is missing")
        return
    var beam := get_nodes_in_group("mission_002_placement_beam")
    if beam.size() != 1:
        fail("reverse tow-beam placement effect is missing")
        return

    player.global_position = primary.global_position + Vector3(0.0, 0.0, 110.0)
    runtime.call("_process", 0.0)
    if runtime.current_state() != "PLACEMENT_READY":
        fail("intercept did not unlock demolition placement")
        return
    runtime.toggle_towbeam_mode()
    if runtime.current_state() != "CHARGE_PLACEMENT":
        fail("reverse tow-beam placement mode did not activate")
        return
    if player.mouse_flight_suppressed:
        fail("tow-beam mode disabled mouse steering")
        return
    if not player.frapray_fire_suppressed:
        fail("tow-beam mode did not suppress FrapRay firing on Space")
        return
    runtime.call("_update_hud")
    if not blue_reticle[0].visible or runtime.weapon_aim.visible:
        fail("tow-beam mode did not swap red weapon markers for the blue reticle")
        return
    if not runtime.cockpit.mission_screen_label.text.contains("TOW BEAM  READY · SPACE"):
        fail("HUD did not identify Space as the selected tow-beam trigger")
        return
    await physics_frame
    player.look_at(runtime.charge_sites[0].global_position, Vector3.UP)
    runtime.call("_update_placement_acquisition")
    if runtime.acquired_site != runtime.charge_sites[0]:
        fail("ship-forward blue reticle did not acquire a visible fracture site")
        return
    if beam[0].visible:
        fail("tow beam appeared before Space fired it")
        return
    var beam_start: Vector3 = runtime._beam_visible_start(
        runtime.charge_sites[0].global_position
    )
    var effect_origin := player.find_child(
        "effect_exclusion_center", true, false
    ) as Node3D
    if not is_equal_approx(
        beam_start.distance_to(effect_origin.global_position), 3.35
    ):
        fail("placement beam begins inside the JB100 effect-exclusion bubble")
        return
    if not runtime.fire_towbeam_charge():
        fail("Space-style tow-beam firing did not begin charge placement")
        return
    runtime.call("_update_placement", runtime.placement_duration)
    for index in range(1, 3):
        runtime.force_place_charge_for_test(index)
    if runtime.charges_placed != 3 or runtime.current_state() != "CLEAR_BLAST":
        fail("three placed charges did not unlock blast clearance")
        return
    if runtime.placed_charge_packs.size() != 3:
        fail("three placements did not create three explosive-pack hero assets")
        return
    for charge in runtime.placed_charge_packs:
        var animation_players: Array[Node] = charge.find_children(
            "*", "AnimationPlayer", true, false
        )
        var animation_player := (
            animation_players[0] as AnimationPlayer
            if not animation_players.is_empty()
            else null
        )
        if (
            charge.get_meta("asset_id", "") != "prop_explosive_pack_A"
            or charge.get_meta("warning_animation", "")
            != "warning_beacons_alternate"
            or animation_player == null
            or not animation_player.is_playing()
        ):
            fail("placed explosive pack did not use and animate the Blender hero asset")
            return
        if absf(charge.global_basis.get_scale().x - 1.0) > 0.02:
            fail("explosive pack did not preserve its authored one-meter scale")
            return
    if player.frapray_fire_suppressed:
        fail("FrapRay firing was not restored after charge placement")
        return

    player.global_position = primary.global_position + Vector3(0.0, 0.0, 170.0)
    runtime.call("_process", 0.0)
    if runtime.current_state() != "DETONATION_READY":
        fail("safe blast distance did not unlock detonation")
        return
    runtime.request_interaction()
    runtime.state_elapsed = 1.0
    runtime.call("_process", 0.0)
    if runtime.current_state() != "DEBRIS_CHASE":
        fail("charge detonation did not begin the debris chase")
        return
    var majors := get_nodes_in_group("planetfall_major")
    if majors.size() != 3:
        fail("controlled breakup did not create three major fragments")
        return

    runtime.chase_elapsed = 26.0
    runtime.call("_trigger_natural_breakup_if_due")
    await process_frame
    runtime.call("_register_new_fragments")
    if (
        not runtime.natural_breakup_triggered
        or get_nodes_in_group("planetfall_debris").size() < 3
    ):
        fail("staged natural breakup did not create easier small debris")
        return
    majors = get_nodes_in_group("planetfall_major").filter(
        func(node: Node) -> bool: return is_instance_valid(node) and not node.destroyed
    )
    if majors.size() != 2:
        fail("natural breakup did not leave the expected major threats")
        return

    var projectile_target := majors[0] as StaticBody3D
    projectile_target.global_position = (
        player.global_position - player.global_basis.z * 46.0
    )
    player.torpedo_cooldown_remaining = 0.0
    if not player.fire_proton_torpedo(projectile_target):
        fail("JB100 could not fire at Mission 002 debris")
        return
    for frame in 45:
        await physics_frame
        if not is_instance_valid(projectile_target) or projectile_target.destroyed:
            break
    if is_instance_valid(projectile_target) and not projectile_target.destroyed:
        fail("proton torpedo did not break the targeted major fragment")
        return
    for major in majors.slice(1):
        major.apply_weapon_hit(
            4.0,
            "proton_torpedo",
            major.global_position,
            Vector3(0.0, 0.0, -1.0)
        )
    await process_frame
    runtime.call("_register_new_fragments")
    var fragments := get_nodes_in_group("planetfall_debris")
    if fragments.size() < 9:
        fail("shooting major debris did not produce smaller chase fragments")
        return
    for fragment in fragments:
        fragment.apply_weapon_hit(
            1.0,
            "frapray",
            fragment.global_position,
            Vector3(0.0, 0.0, -1.0)
        )
    await process_frame
    runtime.call("_evaluate_debris_outcome")
    if runtime.current_state() != "COMPLETE":
        fail("atomizing all debris did not complete Mission 002")
        return
    if (
        not runtime.mission_announcement.visible
        or runtime.mission_announcement.text != "SUCCESS"
        or runtime.mission_announcement.get_theme_color("font_color").g < 0.9
    ):
        fail("Mission 002 completion did not show the green SUCCESS announcement")
        return

    print(
        "MISSION-002-RUNTIME-OK: intercept + blue-reticle charges + "
        + "controlled breakup + debris atomization + planetfall"
    )
    shell.queue_free()
    quit(0)
