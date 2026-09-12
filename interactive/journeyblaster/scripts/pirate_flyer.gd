extends AnimatableBody3D

const CombatEffects = preload("res://scripts/combat_effects.gd")

signal objective_completed(flyer: AnimatableBody3D)
signal retreat_started(flyer: AnimatableBody3D)
signal flyer_destroyed(flyer: AnimatableBody3D)
signal defense_perimeter_crossed(flyer: AnimatableBody3D)

const RETREAT_HITS := 6
const DESTROY_HITS := 12
const DEFENSE_PERIMETER_M := 5000.0
const HYPERSPACE_RANGE_M := 6000.0
const RUN_INGRESS_DISTANCE_M := 235.0
const RUN_EGRESS_DISTANCE_M := 335.0
const RUN_CLEARANCE_M := 54.0
const RUN_WAYPOINT_RADIUS_M := 18.0
const RUN_FIRE_RANGE_M := 168.0
const FORWARD_FIRE_CONE_DEG := 3.0
const STARBASE_KEEP_OUT_RADIUS_M := 185.0
const REAR_TORPEDO_CONE_DEG := 10.0
const REAR_TORPEDO_MIN_RANGE_M := 35.0
const REAR_TORPEDO_MAX_RANGE_M := 300.0
const REAR_TORPEDO_LOCK_TIME_S := 2.0

var runtime: Node3D
var player: CharacterBody3D
var station_center := Vector3.ZERO
var planet_position := Vector3.ZERO
var objective_category := "shield"
var target_queue: Array[StaticBody3D] = []
var current_target: StaticBody3D
var behavior := "ATTACK_STATION"
var ai_enabled := false
var completed_primary_objective := false
var damage_taken := 0.0
var frapray_hits := 0
var station_weapon_hits := 0
var proton_torpedo_hit := false
var proton_torpedo_hits := 0
var destroyed := false
var perimeter_crossed := false
var hyperspace_departed := false
var flight_velocity := Vector3.ZERO
var fire_timer := 2.0
var preferred_speed := 54.0
var station_attack_aggression := 1.0
var wobble_phase := 0.0
var personality_offset := Vector3.ZERO
var attack_run_phase := "INGRESS"
var run_ingress_point := Vector3.ZERO
var run_fire_point := Vector3.ZERO
var run_egress_point := Vector3.ZERO
var run_strafe_direction := Vector3.FORWARD
var run_shot_fired := false
var completed_attack_runs := 0
var defense_evading := false
var torpedoes_remaining := 3
var rear_torpedo_lock_time := 0.0
var forward_torpedo_lock_time := 0.0


func _ready() -> void:
    # Scripted AI owns the flyer transform. Leaving AnimatableBody3D's
    # physics synchronization enabled causes the physics server to restore the
    # previous transform after every movement update, making flyers appear
    # stationary.
    sync_to_physics = false


func configure(
    mission_runtime: Node3D,
    jb100: CharacterBody3D,
    center: Vector3,
    planet: Vector3,
    category: String,
    targets: Array[StaticBody3D],
    seed_value: int
) -> void:
    runtime = mission_runtime
    player = jb100
    station_center = center
    planet_position = planet
    objective_category = category
    target_queue = targets.duplicate()
    var random := RandomNumberGenerator.new()
    random.seed = seed_value
    randomize_target_order(random)
    preferred_speed = random.randf_range(46.0, 62.0)
    wobble_phase = random.randf_range(0.0, TAU)
    personality_offset = Vector3(
        random.randf_range(-18.0, 18.0),
        random.randf_range(-12.0, 18.0),
        random.randf_range(-18.0, 18.0)
    )
    fire_timer = random.randf_range(2.2, 4.5)
    add_to_group("mission_003_pirate")
    _select_next_station_target()
    _prepare_attack_run()


func randomize_target_order(random: RandomNumberGenerator) -> void:
    for index in range(target_queue.size() - 1, 0, -1):
        var swap_index := random.randi_range(0, index)
        var temporary := target_queue[index]
        target_queue[index] = target_queue[swap_index]
        target_queue[swap_index] = temporary


func _physics_process(delta: float) -> void:
    if destroyed or not ai_enabled:
        return
    _update_pursuit_torpedoes(delta)
    if behavior in ["RETREAT", "DRIVEN_OFF"]:
        _advance_retreat(delta)
        return
    if behavior == "CIRCLE_STATION":
        _advance_holding_pattern(delta)
        return
    if behavior == "ATTACK_PLAYER" and runtime.is_player_in_safe_hangar():
        _advance_holding_pattern(delta)
        return
    if behavior in ["ATTACK_STATION", "PILE_ON"]:
        if current_target == null or current_target.disabled:
            _select_next_station_target()
            if current_target == null:
                if not completed_primary_objective:
                    completed_primary_objective = true
                    objective_completed.emit(self)
                return

    _advance_attack_run_phase()
    var target_position := _current_attack_position()
    var desired := target_position - global_position
    if desired.length() < 0.01:
        return
    var desired_direction := desired.normalized()
    var player_distance := global_position.distance_to(player.global_position)
    if behavior != "ATTACK_PLAYER" and player_distance < 58.0:
        desired_direction = (
            desired_direction +
            (global_position - player.global_position).normalized() * 1.45
        ).normalized()
    var from_station := global_position - station_center
    if from_station.length() < 82.0:
        desired_direction = (desired_direction + from_station.normalized() * 1.8).normalized()
    for other in get_tree().get_nodes_in_group("mission_003_pirate"):
        var other_pirate := other as AnimatableBody3D
        if other_pirate == self or other_pirate.destroyed:
            continue
        var separation: Vector3 = global_position - other_pirate.global_position
        if separation.length() < 24.0 and separation.length() > 0.01:
            desired_direction = (desired_direction + separation.normalized()).normalized()
    var defense_avoidance := _defense_fire_avoidance()
    defense_evading = defense_avoidance.length_squared() > 0.0001
    if defense_evading:
        desired_direction = (desired_direction + defense_avoidance * 2.6).normalized()
    var attack_speed_scale := (
        station_attack_aggression if behavior in ["ATTACK_STATION", "PILE_ON"] else 1.0
    )
    var desired_velocity := desired_direction * preferred_speed * attack_speed_scale
    flight_velocity = flight_velocity.lerp(
        desired_velocity, clampf(delta * 1.35, 0.0, 1.0)
    )
    var proposed_position := global_position + flight_velocity * delta
    global_position = _enforce_starbase_keep_out(proposed_position)
    if flight_velocity.length() > 0.5:
        look_at(global_position + flight_velocity, Vector3.UP)

    fire_timer -= delta
    var attack_target := _attack_target_node()
    if (
        attack_run_phase == "STRAFE"
        and not run_shot_fired
        and fire_timer <= 0.0
        and attack_target != null
        and global_position.distance_to(attack_target.global_position) <= RUN_FIRE_RANGE_M
        and can_fire_forward_at(attack_target)
    ):
        if runtime.fire_pirate_weapon(self, attack_target):
            run_shot_fired = true
            _begin_post_fire_evasion()


func _update_pursuit_torpedoes(delta: float) -> void:
    if (
        torpedoes_remaining <= 0
        or runtime.mission_state != "DEFEND"
        or runtime.is_player_in_safe_hangar()
        or player.disabled_in_space
    ):
        rear_torpedo_lock_time = 0.0
        forward_torpedo_lock_time = 0.0
        return
    var to_player := player.global_position - global_position
    var player_range := to_player.length()
    var in_range: bool = (
        player_range >= REAR_TORPEDO_MIN_RANGE_M
        and player_range <= REAR_TORPEDO_MAX_RANGE_M
    )
    var to_player_direction := to_player.normalized()
    var rear_alignment := global_basis.z.normalized().dot(to_player_direction)
    var forward_alignment := (-global_basis.z).normalized().dot(to_player_direction)
    var alignment_threshold := cos(deg_to_rad(REAR_TORPEDO_CONE_DEG))
    rear_torpedo_lock_time = (
        rear_torpedo_lock_time + delta
        if in_range and rear_alignment >= alignment_threshold
        else maxf(0.0, rear_torpedo_lock_time - delta * 1.5)
    )
    forward_torpedo_lock_time = (
        forward_torpedo_lock_time + delta
        if in_range and forward_alignment >= alignment_threshold
        else maxf(0.0, forward_torpedo_lock_time - delta * 1.5)
    )
    if rear_torpedo_lock_time >= REAR_TORPEDO_LOCK_TIME_S:
        if runtime.fire_pirate_torpedo(self, global_basis.z.normalized()):
            rear_torpedo_lock_time = 0.0
            forward_torpedo_lock_time = 0.0
    elif forward_torpedo_lock_time >= REAR_TORPEDO_LOCK_TIME_S:
        if runtime.fire_pirate_torpedo(self, -global_basis.z.normalized()):
            rear_torpedo_lock_time = 0.0
            forward_torpedo_lock_time = 0.0


func _update_rear_torpedo(delta: float) -> void:
    # Compatibility entry point retained for focused runtime tests.
    _update_pursuit_torpedoes(delta)


func _current_attack_position() -> Vector3:
    if attack_run_phase == "INGRESS":
        return run_ingress_point
    if not run_shot_fired:
        var target := _attack_target_node()
        if target != null:
            return target.global_position
    return run_egress_point


func _advance_attack_run_phase() -> void:
    if attack_run_phase == "INGRESS":
        if global_position.distance_to(run_ingress_point) <= RUN_WAYPOINT_RADIUS_M:
            attack_run_phase = "STRAFE"
    elif global_position.distance_to(run_egress_point) <= RUN_WAYPOINT_RADIUS_M:
        completed_attack_runs += 1
        _prepare_attack_run()


func _prepare_attack_run() -> void:
    var target := _attack_target_node()
    if target == null:
        run_ingress_point = station_center + personality_offset
        run_egress_point = run_ingress_point
        attack_run_phase = "INGRESS"
        run_shot_fired = false
        return
    var outward := target.global_position - station_center
    if behavior == "ATTACK_PLAYER" or outward.length_squared() < 0.01:
        outward = target.global_position - global_position
    if outward.length_squared() < 0.01:
        outward = Vector3.UP
    outward = outward.normalized()
    var tangent := outward.cross(Vector3.UP)
    if tangent.length_squared() < 0.01:
        tangent = outward.cross(Vector3.RIGHT)
    tangent = tangent.normalized()
    if completed_attack_runs % 2 == 1:
        tangent = -tangent
    run_strafe_direction = tangent
    var vertical_variation := Vector3.UP * personality_offset.y * 0.35
    run_fire_point = target.global_position + outward * RUN_FIRE_RANGE_M * 0.92
    var run_distance_scale := 1.0 / station_attack_aggression
    # Approach nose-first down the target's outward normal. During STRAFE,
    # _current_attack_position keeps the nose on the target until the shot.
    run_ingress_point = (
        target.global_position
        + outward * (RUN_FIRE_RANGE_M + RUN_INGRESS_DISTANCE_M * run_distance_scale)
        + vertical_variation
    )
    run_egress_point = (
        target.global_position
        + outward * (RUN_CLEARANCE_M + 70.0)
        + run_strafe_direction * RUN_EGRESS_DISTANCE_M * run_distance_scale
        - vertical_variation
    )
    attack_run_phase = "INGRESS"
    run_shot_fired = false
    fire_timer = minf(fire_timer, 1.25 / station_attack_aggression)


func can_fire_forward_at(target: Node3D) -> bool:
    if target == null or not is_instance_valid(target):
        return false
    var to_target := target.global_position - global_position
    if to_target.length_squared() < 0.01:
        return false
    return (-global_basis.z).normalized().dot(to_target.normalized()) >= cos(
        deg_to_rad(FORWARD_FIRE_CONE_DEG)
    )


func _begin_post_fire_evasion() -> void:
    var target := _attack_target_node()
    if target == null:
        return
    var outward := target.global_position - station_center
    if behavior == "ATTACK_PLAYER" or outward.length_squared() < 0.01:
        outward = global_position - target.global_position
    if outward.length_squared() < 0.01:
        outward = Vector3.UP
    outward = outward.normalized()
    var run_distance_scale := 1.0 / station_attack_aggression
    run_egress_point = (
        target.global_position
        + outward * (RUN_CLEARANCE_M + 70.0)
        + run_strafe_direction * RUN_EGRESS_DISTANCE_M * run_distance_scale
        - Vector3.UP * personality_offset.y * 0.35
    )


func _enforce_starbase_keep_out(proposed_position: Vector3) -> Vector3:
    var proposed_offset := proposed_position - station_center
    if proposed_offset.length() >= STARBASE_KEEP_OUT_RADIUS_M:
        return proposed_position
    var safe_normal := proposed_offset.normalized()
    if safe_normal.length_squared() < 0.01:
        safe_normal = (global_position - station_center).normalized()
    if safe_normal.length_squared() < 0.01:
        safe_normal = Vector3.UP
    var inward_speed := flight_velocity.dot(safe_normal)
    if inward_speed < 0.0:
        flight_velocity -= safe_normal * inward_speed
    return station_center + safe_normal * STARBASE_KEEP_OUT_RADIUS_M


func _defense_fire_avoidance() -> Vector3:
    var avoidance := Vector3.ZERO
    for node in get_tree().get_nodes_in_group("weapon_projectile"):
        var projectile := node as Node3D
        if projectile == null or projectile.weapon_kind != "starbase_plasma":
            continue
        var bolt_velocity: Vector3 = projectile.travel_velocity
        var speed_squared := bolt_velocity.length_squared()
        if speed_squared < 0.01:
            continue
        var relative := global_position - projectile.global_position
        var closest_time := relative.dot(bolt_velocity) / speed_squared
        if closest_time <= 0.0 or closest_time > 0.9:
            continue
        var closest_offset := relative - bolt_velocity * closest_time
        var miss_distance := closest_offset.length()
        if miss_distance >= 32.0:
            continue
        var evade_direction := closest_offset.normalized()
        if evade_direction.length_squared() < 0.01:
            evade_direction = bolt_velocity.normalized().cross(Vector3.UP).normalized()
            if evade_direction.length_squared() < 0.01:
                evade_direction = Vector3.RIGHT
        var urgency := (1.0 - miss_distance / 32.0) * (1.0 - closest_time / 0.9)
        avoidance += evade_direction * urgency
    return avoidance


func _attack_target_node() -> Node3D:
    if behavior == "ATTACK_PLAYER":
        return player
    return current_target


func _select_next_station_target() -> void:
    while not target_queue.is_empty():
        var candidate := target_queue.pop_front() as StaticBody3D
        if is_instance_valid(candidate) and not candidate.disabled:
            current_target = candidate
            _prepare_attack_run()
            return
    current_target = null


func assign_player_attack() -> void:
    behavior = "ATTACK_PLAYER"
    station_attack_aggression = 1.0
    current_target = null
    completed_attack_runs = 0
    _prepare_attack_run()


func assign_station_circle() -> void:
    behavior = "CIRCLE_STATION"
    current_target = null
    target_queue.clear()
    run_shot_fired = true


func assign_pile_on(
    targets: Array[StaticBody3D], aggression: float = 1.0
) -> void:
    behavior = "PILE_ON"
    station_attack_aggression = maxf(1.0, aggression)
    target_queue = targets.duplicate()
    current_target = null
    _select_next_station_target()


func begin_retreat() -> void:
    if behavior in ["RETREAT", "DRIVEN_OFF"] or destroyed:
        return
    behavior = "RETREAT"
    current_target = null
    retreat_started.emit(self)


func _advance_retreat(delta: float) -> void:
    var away_from_planet := global_position - planet_position
    if away_from_planet.length() < 0.01:
        away_from_planet = Vector3(0.0, 0.0, -1.0)
    var retreat_direction := away_from_planet.normalized()
    flight_velocity = flight_velocity.lerp(
        retreat_direction * 76.0, clampf(delta * 1.6, 0.0, 1.0)
    )
    global_position = _enforce_starbase_keep_out(
        global_position + flight_velocity * delta
    )
    if flight_velocity.length() > 0.5:
        look_at(global_position + flight_velocity, Vector3.UP)
    var station_distance := global_position.distance_to(station_center)
    if station_distance >= DEFENSE_PERIMETER_M and not perimeter_crossed:
        perimeter_crossed = true
        behavior = "DRIVEN_OFF"
        defense_perimeter_crossed.emit(self)
    if station_distance >= HYPERSPACE_RANGE_M and not hyperspace_departed:
        hyperspace_departed = true
        visible = false
        collision_layer = 0
        collision_mask = 0


func _advance_holding_pattern(delta: float) -> void:
    wobble_phase += delta * 0.45
    var holding_point := station_center + Vector3(
        cos(wobble_phase) * 220.0,
        120.0 + sin(wobble_phase * 0.6) * 45.0,
        sin(wobble_phase) * 220.0
    )
    var direction := (holding_point - global_position).normalized()
    flight_velocity = flight_velocity.lerp(
        direction * preferred_speed, clampf(delta, 0.0, 1.0)
    )
    global_position = _enforce_starbase_keep_out(
        global_position + flight_velocity * delta
    )
    if flight_velocity.length() > 0.5:
        look_at(global_position + flight_velocity, Vector3.UP)


func apply_weapon_hit(
    damage: float,
    weapon_kind: String,
    hit_position: Vector3,
    impact_direction: Vector3
) -> void:
    if destroyed or hyperspace_departed:
        return
    if weapon_kind == "frapray":
        # Count physical bolts, independent of their numeric damage payload.
        # One trigger pull launches two separately collidable bolts.
        frapray_hits += 1
    elif weapon_kind == "starbase_plasma":
        station_weapon_hits += 1
    elif weapon_kind == "proton_torpedo":
        proton_torpedo_hit = true
        proton_torpedo_hits += 1
    var bolt_hits := frapray_hits + station_weapon_hits
    damage_taken = float(bolt_hits) + float(proton_torpedo_hits) * 3.0
    CombatEffects.spawn_dust_cloud(get_parent(), hit_position, 0.42, 5)
    if (
        proton_torpedo_hits >= 2
        or (proton_torpedo_hits >= 1 and bolt_hits >= RETREAT_HITS)
        or bolt_hits >= DESTROY_HITS
    ):
        _destroy_flyer(weapon_kind, impact_direction)
    elif bolt_hits >= RETREAT_HITS:
        begin_retreat()


func _destroy_flyer(_weapon_kind: String, _impact_direction: Vector3) -> void:
    if destroyed:
        return
    destroyed = true
    ai_enabled = false
    collision_layer = 0
    collision_mask = 0
    CombatEffects.spawn_dust_cloud(get_parent(), global_position, 3.2, 26)
    var visual := get_node_or_null("Visual") as Node3D
    if visual:
        visual.visible = false
    flyer_destroyed.emit(self)
