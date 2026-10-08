class_name RotdParallax
extends Node2D

## Ported from RDParallaxBackground / RDParallaxBackgroundRising /
## RDParallaxBackgroundSplitting.  These layers are pinned to a fixed camera
## distance (no world Z) so they never approach; the sky is static, the hills
## rise and the two city layers split apart as the player drives on, which is
## what makes the skyline "dolly out" across the campaign.

enum Mode { DISTANCE, RISING, SPLITTING }

var mode := Mode.DISTANCE
var distance := 1000.0
var param_a := 1.0
var param_b := 0.0
var drop_rate := 0.0
var clip: SwfMovieClip
var _base := {}


func setup(library: SwfLibrary, char_id: int, m: int, dist: float, a: float, b: float, drop: float) -> void:
	mode = m
	distance = maxf(dist, 1.0)
	param_a = a
	param_b = b
	drop_rate = drop
	clip = SwfMovieClip.create(char_id, library)
	clip.playing = false
	add_child(clip)


func _capture() -> void:
	if not _base.is_empty() or clip == null:
		return
	for nm in ["Left", "Right", "Center"]:
		var n := clip.find_child(nm, false, false)
		if n is Node2D:
			_base[nm] = (n as Node2D).position


func render(cam: RotdCamera) -> void:
	if clip == null:
		return
	_capture()
	var ty := -cam.y
	var tvx := -cam.x
	var tvz := distance
	var a := -cam.yaw
	var rx := tvx * cos(a) + tvz * sin(a)
	var rz := -tvx * sin(a) + tvz * cos(a)
	if rz <= 0.001:
		return
	var invz := 1.0 / rz
	position = Vector2(rx * cam.render_dist_x * invz + cam.half_w,
		-ty * cam.render_dist_y * invz + cam.half_h)
	var ratio := 1.0
	if param_a > 0.0:
		ratio = clampf(cam.z / param_a, 0.0, 1.0)
	ratio = pow(ratio, 1.5)

	match mode:
		Mode.DISTANCE:
			position.y += cam.z * drop_rate
		Mode.RISING:
			var rise := ratio * param_b
			_move("Center", Vector2(0.0, -rise))
		Mode.SPLITTING:
			var split := ratio * param_b
			var drop := ratio * drop_rate
			_move("Left", Vector2(-split, drop))
			_move("Right", Vector2(split, drop))
			_move("Center", Vector2(0.0, drop))


func _move(nm: String, offset: Vector2) -> void:
	if not _base.has(nm):
		return
	var n := clip.find_child(nm, false, false)
	if n is Node2D:
		(n as Node2D).position = (_base[nm] as Vector2) + offset
