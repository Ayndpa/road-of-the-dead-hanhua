class_name RotdZombie
extends RotdEntity

## Zombie humanoid ported from RDZombie / RDZombieNormalMale / RDZombieHard /
## RDZombieVeryHard.  Handles patrol / straight / align / move-to-player AI,
## car collisions (cling or die) and the fixed hood position while clinging.

const MOVEMENT_PATROL := 0
const MOVEMENT_STRAIGHT := 1
const MOVEMENT_MOVE_TO_PLAYER := 2
const MOVEMENT_ALIGN := 3
const MOVEMENT_STATIONARY := 4

const TYPE_NORMAL := 0
const TYPE_HARD := 1
const TYPE_VERYHARD := 2

const HIT_GIB := 0
const HIT_FRONT := 1
const HIT_ROLLOVER := 2
const HIT_SIDE := 3

const SOUND_DETECT_DISTANCE := 10.0
const VISION_DETECT_DISTANCE := 20.0
const IDLE_CLING_DISTANCE := 1.0
const PATROL_RANGE := 2.0
const PATROL_WAIT := 2.0
const SUPER_ALIGN_DISTANCE := 80.0
const SUPER_LOCK_IN_DISTANCE := 10.0
const HORN_VISION := [20.0, 25.0, 30.0, 35.0]
const HORN_SOUND := [60.0, 70.0, 80.0, 90.0]

var zombie_type := TYPE_NORMAL
var movement_type := MOVEMENT_STRAIGHT
var speed_x := 3.0 * 1000.0 / 3600.0
var speed_z := 5.0 * 1000.0 / 3600.0
var dead := false
var dead_timer := 0.0
var clinging := false
var no_cling := false
var hit_type := -1
var was_run_over := false

var _rng: RandomNumberGenerator
var _going_right := false
var _patrol_wait := 0.0
var _start_x := INF
var _horn_vision := HORN_VISION[0]
var _horn_sound := HORN_SOUND[0]
var _vx := 0.0
var _vz := 0.0


func setup_any(library: SwfLibrary, kind: String, movement: int, rng: RandomNumberGenerator,
		horn_level: int = 0) -> void:
	lib = library
	_rng = rng
	world_y = 0.0
	movement_type = movement
	_going_right = rng.randf() > 0.5
	flip = not _going_right
	var hl := clampi(horn_level, 0, 3)
	_horn_vision = float(HORN_VISION[hl])
	_horn_sound = float(HORN_SOUND[hl])
	var char_id := 947
	match kind:
		"normal_female":
			char_id = 839
			zombie_type = TYPE_NORMAL
			world_scale = 2.0
		"hard":
			char_id = 1096
			zombie_type = TYPE_HARD
			world_scale = 2.2
		"veryhard":
			char_id = 712
			zombie_type = TYPE_VERYHARD
			world_scale = 2.0
			speed_x = 20.0 * 1000.0 / 3600.0
			speed_z = 20.0 * 1000.0 / 3600.0
		_:
			char_id = 947
			zombie_type = TYPE_NORMAL
			world_scale = 2.0
	col_x = -0.5
	col_w = 1.0
	col_z_front = 0.5
	col_z_back = 2.0
	fade_distance = 100.0
	fade_range = 20.0
	layer = LAYER_DYNAMIC
	setup_clip(char_id, -1, "WalkFront")


# movement/animation only; returns the x/z delta applied to the world
func update_ai(dt: float, px: float, pz: float, player_speed: float,
		player_failed: bool, player_horning: bool, player_has_clinger: bool,
		camera: RotdCamera) -> void:
	if dead:
		dead_timer -= dt
		if dead_timer <= 0.0:
			destroy_me = true
		else:
			render(camera)
		return
	if clinging:
		render_cling()
		return
	if _start_x == INF:
		_start_x = world_x

	var prev_x := world_x
	var prev_z := world_z
	var fdist := absf(pz - world_z)

	if world_z < pz:
		movement_type = MOVEMENT_STRAIGHT

	if zombie_type == TYPE_VERYHARD:
		_update_super(fdist, player_failed, player_has_clinger)
	else:
		_update_normal(fdist, px, pz, player_speed, player_failed, player_has_clinger,
			player_horning)

	_move_ai(dt, px, pz)
	flip = _vx < 0.0 if absf(_vx) > 0.001 else flip
	render(camera)


func _update_normal(fdist: float, px: float, pz: float, player_speed: float,
		player_failed: bool, player_has_clinger: bool, player_horning: bool) -> void:
	if movement_type == MOVEMENT_MOVE_TO_PLAYER:
		if player_failed or player_has_clinger:
			movement_type = MOVEMENT_STRAIGHT
		elif player_speed <= 0.001 and fdist <= IDLE_CLING_DISTANCE and not no_cling:
			cling()
		return
	if fdist < SOUND_DETECT_DISTANCE:
		movement_type = MOVEMENT_MOVE_TO_PLAYER
	elif (movement_type == MOVEMENT_STRAIGHT
			or (movement_type == MOVEMENT_PATROL and _patrol_wait > 0.0)) \
			and fdist < VISION_DETECT_DISTANCE:
		movement_type = MOVEMENT_MOVE_TO_PLAYER
	elif player_horning and movement_type != MOVEMENT_ALIGN:
		if fdist < _horn_vision:
			movement_type = MOVEMENT_MOVE_TO_PLAYER
		elif fdist < _horn_sound:
			movement_type = MOVEMENT_ALIGN


func _update_super(fdist: float, player_failed: bool, player_has_clinger: bool) -> void:
	if movement_type == MOVEMENT_STATIONARY:
		if fdist < SUPER_ALIGN_DISTANCE:
			movement_type = MOVEMENT_ALIGN
	elif movement_type == MOVEMENT_ALIGN:
		if player_failed or player_has_clinger:
			movement_type = MOVEMENT_STRAIGHT
		elif fdist < SUPER_LOCK_IN_DISTANCE:
			movement_type = MOVEMENT_MOVE_TO_PLAYER


func _move_ai(dt: float, px: float, pz: float) -> void:
	_vx = 0.0
	_vz = 0.0
	match movement_type:
		MOVEMENT_PATROL:
			if _patrol_wait > 0.0:
				_patrol_wait -= dt
			else:
				_vx = speed_x if _going_right else -speed_x
				if (_going_right and (world_x > _start_x + PATROL_RANGE or world_x >= 9.1)) \
						or (not _going_right and (world_x < _start_x - PATROL_RANGE or world_x <= -9.4)):
					_patrol_wait = PATROL_WAIT
					_going_right = not _going_right
		MOVEMENT_STRAIGHT:
			_vz = -speed_z
		MOVEMENT_MOVE_TO_PLAYER:
			var dx := px - world_x
			var dz := pz - world_z
			var d := sqrt(dx * dx + dz * dz)
			if d > 0.001:
				_vx = (dx / d) * speed_x
				_vz = (dz / d) * speed_z
		MOVEMENT_ALIGN:
			_vx = signf(px - world_x) * speed_x
			var dz2 := pz - world_z
			var d2 := sqrt(pow(px - world_x, 2.0) + dz2 * dz2)
			_vz = (dz2 / maxf(d2, 0.001)) * speed_z
	world_x += _vx * dt
	world_z += _vz * dt


func render_cling() -> void:
	if clip == null:
		return
	clip.visible = true
	position = Vector2(300.0, 312.0)
	scale = Vector2(1.05, 1.05)
	flip = false
	z_index = 50


func hit(hit: int = HIT_FRONT) -> void:
	if dead or clinging:
		return
	dead = true
	hit_type = hit
	was_run_over = hit == HIT_ROLLOVER
	dead_timer = 0.9
	match hit:
		HIT_GIB:
			clip.play_label("GibHit", false)
		HIT_ROLLOVER:
			clip.play_label("RollOverHit", false)
		HIT_SIDE:
			clip.play_label("SideHit", false)
		_:
			clip.play_label("FrontHit", false)


func cling() -> void:
	if dead or clinging or no_cling:
		return
	clinging = true
	clip.play_label("Clinging", true)


func shoot_down() -> void:
	if dead:
		return
	clinging = false
	hit(HIT_GIB)
