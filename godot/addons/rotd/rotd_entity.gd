class_name RotdEntity
extends Node2D

## Base billboard entity for the pseudo-3D road, matching RDEntity.Render:
## a fixed world point (x, y, z) projected by RotdCamera, scaled by the
## projected height of one world unit, faded out near the render horizon and
## depth-sorted into a layer band.

const BASE_DYNAMIC_Z := 300
const LAYER_ROAD := 0
const LAYER_SIDE := 100
const LAYER_DYNAMIC := 300

var lib: SwfLibrary
var clip: SwfMovieClip = null

var world_x := 0.0
var world_y := 0.0
var world_z := 0.0
var world_scale := 1.0
var flip := false
var fade_distance := 150.0
var fade_range := 50.0
var layer := LAYER_DYNAMIC
var group := "obstacle"
var destroy_me := false
var off_road_ok := false

# collision box: x extent relative to world_x, and z extents relative to world_z
var col_x := -0.5
var col_w := 1.0
var col_z_front := 0.5   # closer to the player (larger z)
var col_z_back := 2.0    # already passed the player (smaller z)
var alive := true


func setup_clip(char_id: int, frame: int = -1, play_label: String = "") -> void:
	clip = SwfMovieClip.create(char_id, lib)
	add_child(clip)
	if play_label != "":
		clip.play_label(play_label, true)
	elif frame >= 0:
		clip.seek(frame)
		clip.playing = false


# Union of the placed art in the clip's own timeline space (Flash's
# MovieClip.getBounds(self)).  RDEntity derives its height and collision box
# from exactly this, so anything sized off the sprite must use it too.
func art_rect() -> Rect2:
	var out := Rect2()
	var first := true
	if clip == null:
		return out
	var stack: Array[Node] = [clip]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		var r := Rect2()
		if n is Sprite2D:
			var s := n as Sprite2D
			if s.texture != null:
				r = s.get_rect()
		elif n is SwfVectorShape:
			r = (n as SwfVectorShape).local_rect
		else:
			for c in n.get_children():
				stack.append(c)
			continue
		for p in [r.position, Vector2(r.end.x, r.position.y), r.end,
				Vector2(r.position.x, r.end.y)]:
			var lp: Vector2 = clip.to_local((n as Node2D).to_global(p))
			if first:
				out = Rect2(lp, Vector2.ZERO)
				first = false
			else:
				out = out.expand(lp)
		for c in n.get_children():
			stack.append(c)
	return out


func render(camera: RotdCamera) -> void:
	if clip == null:
		return
	var fz := world_z - camera.z
	if fz > RotdCamera.MAX_VIEW_DISTANCE or fz <= 1.0:
		clip.visible = false
		return
	clip.visible = true
	position = camera.project(Vector3(world_x, world_y, world_z))
	var s := camera.sprite_scale(world_scale, fz)
	scale = Vector2(-s if flip else s, s)
	var alpha := 1.0 - clampf((fz - fade_distance) / maxf(fade_range, 0.001), 0.0, 1.0)
	clip.modulate.a = alpha
	z_index = layer + clampi(int(200.0 - fz), 0, 199)


func z_distance(camera: RotdCamera) -> float:
	return world_z - camera.z


func is_visible_near(camera: RotdCamera) -> bool:
	var fz := world_z - camera.z
	return fz > 1.0 and fz <= RotdCamera.MAX_VIEW_DISTANCE


# relative x/z to a player position
func dx_to(px: float) -> float:
	return world_x - px


func dz_to(pz: float) -> float:
	return world_z - pz


# true when the player point overlaps this entity's world collision box
func overlaps(px: float, pz: float, half_w: float) -> bool:
	var left := col_x - half_w
	var right := col_x + col_w + half_w
	if world_x - px < left or world_x - px > right:
		return false
	var dz := world_z - pz
	return dz >= -col_z_back and dz <= col_z_front


func update_entity(dt: float, player_x: float, player_z: float, camera: RotdCamera) -> void:
	render(camera)
