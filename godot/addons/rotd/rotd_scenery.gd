class_name RotdScenery
extends Node2D

## Static roadside scenery, matching ROTD1's RDBuilding / RDYellowLine /
## RDRoadSign: each item is a MovieClip (possibly several) placed at a fixed
## world position, billboard-projected, faded near the render horizon.

var clips: Array[SwfMovieClip] = []
var world_x: float = 0.0
var world_z: float = 0.0
var world_scale: float = 1.0
var fade_distance: float = 150.0
var fade_range: float = 50.0
var base_z: int = -50
var flip := false
var destroy_me := false


func setup(library: SwfLibrary, char_ids: Array, variants: Array, scale_v: float,
		fade_d: float, fade_r: float, zbase: int) -> void:
	world_scale = scale_v
	fade_distance = fade_d
	fade_range = fade_r
	base_z = zbase
	for i in char_ids.size():
		var c := SwfMovieClip.create(int(char_ids[i]), library)
		add_child(c)
		var n := maxi(c.frame_count(), 1)
		c.seek(int(variants[i]) % n)
		c.playing = false
		clips.append(c)
	z_index = zbase


func update_scenery(camera: RotdCamera) -> void:
	var fz := world_z - camera.z
	if fz < -5.0:
		destroy_me = true
		return
	if fz > 200.0 or fz <= 1.0:
		for c in clips:
			c.visible = false
		return
	position = camera.project(Vector3(world_x, 0.0, world_z))
	var s := camera.sprite_scale(world_scale, fz)
	scale = Vector2(-s if flip else s, s)
	var alpha := 1.0 - clampf((fz - fade_distance) / maxf(fade_range, 0.001), 0.0, 1.0)
	for c in clips:
		c.visible = true
		c.modulate.a = alpha
	z_index = base_z + clampi(int(240.0 - fz), 0, 200)
