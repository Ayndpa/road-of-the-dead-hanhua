class_name RotdCivilian
extends RotdEntity

## Bystander ported from RDCivilian: wanders across the road, panics and runs
## when the player uses the horn, and is a scoring penalty when run over.

const DIRECTION_DELAY_MIN := 2.0
const DIRECTION_DELAY_RANDOM := 2.0
const HORN_DETECT := [20.0, 30.0, 40.0, 50.0]
const SPEED_X := 12.0 * 1000.0 / 3600.0
const SPEED_Z := 15.0 * 1000.0 / 3600.0

var dead := false
var dead_timer := 0.0
var fleeing := false

var _rng: RandomNumberGenerator
var _going_right := true
var _dir_timer := 0.0
var _dir_delay := 3.0
var _horn_detect := HORN_DETECT[0]


func setup_any(library: SwfLibrary, rng: RandomNumberGenerator, horn_level: int = 0) -> void:
	lib = library
	_rng = rng
	world_scale = 2.0
	col_x = -0.5
	col_w = 1.0
	col_z_front = 0.5
	col_z_back = 2.0
	fade_distance = 100.0
	fade_range = 20.0
	layer = LAYER_DYNAMIC
	_going_right = rng.randf() > 0.5
	flip = not _going_right
	_dir_delay = DIRECTION_DELAY_MIN + rng.randf() * DIRECTION_DELAY_RANDOM
	_horn_detect = float(HORN_DETECT[clampi(horn_level, 0, 3)])
	setup_clip(3262, -1, "WalkFront")


func update_ai(dt: float, px: float, pz: float, player_horning: bool,
		camera: RotdCamera) -> void:
	if dead:
		dead_timer -= dt
		if dead_timer <= 0.0:
			destroy_me = true
		else:
			render(camera)
		return
	var fdist := absf(pz - world_z)
	if player_horning and fdist < _horn_detect:
		fleeing = true
	if fleeing:
		_going_right = px < world_x
		world_x += (SPEED_X if _going_right else -SPEED_X) * dt
		world_z += SPEED_Z * dt
		flip = not _going_right
	else:
		_dir_timer += dt
		if _dir_timer >= _dir_delay:
			_dir_timer = 0.0
			_dir_delay = DIRECTION_DELAY_MIN + _rng.randf() * DIRECTION_DELAY_RANDOM
			_going_right = not _going_right
			flip = not _going_right
		world_x += (SPEED_X if _going_right else -SPEED_X) * dt
	render(camera)


func hit() -> void:
	if dead:
		return
	dead = true
	dead_timer = 0.9
	if clip != null:
		clip.play_label("FrontHit", false)
