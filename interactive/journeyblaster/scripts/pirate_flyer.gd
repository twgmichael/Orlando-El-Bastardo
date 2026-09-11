extends AnimatableBody3D

const CombatEffects = preload("res://scripts/combat_effects.gd")

signal objective_completed(flyer: AnimatableBody3D)
signal retreat_started(flyer: AnimatableBody3D)
signal flyer_destroyed(flyer: AnimatableBody3D)
signal defense_perimeter_crossed(flyer: AnimatableBody3D)

const RETREAT_HITS := 3.0
const DESTROY_HITS := 6.0
const DEFENSE_PERIMETER_M := 5000.0
const HYPERSPACE_RANGE_M := 6000.0
const RUN_INGRESS_DISTANCE_M := 235.0
const RUN_EGRESS_DISTANCE_M := 335.0
const RUN_CLEARANCE_M := 54.0
const RUN_WAYPOINT_RADIUS_M := 18.0
const RUN_FIRE_RANGE_M := 168.0

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
var frapray_hits := 0.0
var proton_torpedo_hit := false
var proton_torpedo_hits := 0
var destroyed := false
var perimeter_crossed := false
var hyperspace_departed := false
var flight_velocity := Vector3.ZERO
var fire_timer := 2.0
var preferred_speed := 54.0
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
    var desired_velocity := desired_direction * preferred_speed
    flight_velocity = flight_velocity.lerp(
        desired_velocity, clampf(delta * 1.35, 0.0, 1.0)
    )
    global_position += flight_velocity * delta
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
    ):
        run_shot_fired = true
        runtime.fire_pirate_weapon(self, attack_target)


func _current_attack_position() -> Vector3:
    if attack_run_phase == "INGRESS":
        return run_ingress_point
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
    run_fire_point = target.global_position + outward * RUN_CLEARANCE_M
    run_ingress_point = (
        run_fire_point
        - run_strafe_direction * RUN_INGRESS_DISTANCE_M
        + outward * 48.0
        + vertical_variation
    )
    run_egress_point = (
        run_fire_point
        + run_strafe_direction * RUN_EGRESS_DISTANCE_M
        + outward * 82.0
        - vertical_variation
    )
    attack_run_phase = "INGRESS"
    run_shot_fired = false
    fire_timer = minf(fire_timer, 1.25)


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
    current_target = null
    completed_attack_runs = 0
    _prepare_attack_run()


func assign_station_circle() -> void:
    behavior = "CIRCLE_STATION"
    current_target = null
    target_queue.clear()
    run_shot_fired = true


func assign_pile_on(targets: Array[StaticBody3D]) -> void:
    behavior = "PILE_ON"
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
    global_position += flight_velocity * delta
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
    global_position += flight_velocity * delta
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
        frapray_hits += damage / 1.6
    elif weapon_kind == "starbase_plasma":
        frapray_hits += 1.0
    elif weapon_kind == "proton_torpedo":
        proton_torpedo_hit = true
        proton_torpedo_hits += 1
    damage_taken = frapray_hits + float(proton_torpedo_hits) * 3.0
    CombatEffects.spawn_dust_cloud(get_parent(), hit_position, 0.42, 5)
    if damage_taken >= DESTROY_HITS:
        _destroy_flyer(weapon_kind, impact_direction)
    elif damage_taken >= RETREAT_HITS:
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
