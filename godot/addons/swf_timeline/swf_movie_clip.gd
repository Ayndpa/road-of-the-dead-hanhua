class_name SwfMovieClip
extends Node2D

## Plays a Flash timeline (DefineSprite) exported by exporter/swf_to_godot.py.
## Placements are applied per frame; nested sprites become child
## SwfMovieClips, shapes/images become Sprite2D leaves.

var lib: SwfLibrary
var sprite_id: int = 0
var def: Dictionary = {}
var fps: float = 30.0
var playing: bool = true
var frame_index: int = 0

var _acc: float = 0.0
var _depths: Dictionary = {}  # depth -> Node2D


static func create(id: int, library: SwfLibrary) -> SwfMovieClip:
	var c := SwfMovieClip.new()
	c.lib = library
	c.sprite_id = id
	c.def = library.get_sprite_def(id)
	c.fps = library.fps
	c.name = "swf_%d" % id
	return c


func _ready() -> void:
	_apply_frame(0)


func _process(delta: float) -> void:
	if not playing:
		return
	var frames: Array = def.get("frames", [])
	if frames.size() <= 1:
		return
	_acc += delta * fps
	var guard := 0
	while _acc >= 1.0 and guard < 256:
		_acc -= 1.0
		guard += 1
		frame_index = (frame_index + 1) % frames.size()
		_apply_frame(frame_index)


func frame_count() -> int:
	return (def.get("frames", []) as Array).size()


func seek(i: int) -> void:
	for depth in _depths.keys():
		var node: Node2D = _depths[depth]
		if is_instance_valid(node):
			remove_child(node)
			node.queue_free()
	_depths.clear()
	frame_index = clampi(i, 0, maxi(frame_count() - 1, 0))
	_apply_frame(frame_index)


func _apply_frame(i: int) -> void:
	var frames: Array = def.get("frames", [])
	if i < 0 or i >= frames.size():
		return
	for op_v in frames[i]:
		if op_v is Dictionary:
			_apply_op(op_v)


func _apply_op(op: Dictionary) -> void:
	var d := int(op.get("d", 0))
	var kind := String(op.get("op", "p"))
	match kind:
		"p":
			_place(d, op)
		"m":
			var node: Node2D = _depths.get(d)
			if node != null and is_instance_valid(node):
				_set_transform(node, op)
				_set_color(node, op)
		"r":
			_drop(d)


func _place(depth: int, op: Dictionary) -> void:
	var cid := int(op.get("c", 0))
	if cid == 0:
		return
	var existing: Node2D = _depths.get(depth)
	if existing != null and is_instance_valid(existing) and int(existing.get_meta("char_id", -1)) == cid:
		# same character at this depth: update in place so looping never
		# re-adds nodes (which would change draw order / restart children)
		_set_transform(existing, op)
		_set_color(existing, op)
		return

	var index := -1
	if existing != null and is_instance_valid(existing):
		index = existing.get_index()
	_drop(depth)

	var node := _make_node(cid, op)
	if node == null:
		return
	node.name = "d%d" % depth
	node.set_meta("char_id", cid)
	add_child(node)
	if index >= 0:
		move_child(node, index)
	_depths[depth] = node
	_set_transform(node, op)
	_set_color(node, op)


func _drop(depth: int) -> void:
	if not _depths.has(depth):
		return
	var node: Node2D = _depths[depth]
	_depths.erase(depth)
	if is_instance_valid(node):
		remove_child(node)
		node.queue_free()


func _make_node(cid: int, _op: Dictionary) -> Node2D:
	var c := lib.get_character(cid)
	var ctype := String(c.get("type", ""))
	match ctype:
		"shape", "image", "morph":
			var s := Sprite2D.new()
			s.texture = lib.get_texture(cid)
			s.centered = false
			var off := Vector2(float(c.get("x", 0.0)), float(c.get("y", 0.0)))
			s.set_meta("base_pos", off)
			if off != Vector2.ZERO:
				s.transform = Transform2D(0.0, off)
			return s
		"sprite":
			return SwfMovieClip.create(cid, lib)
		_:
			return Node2D.new()


func _set_transform(node: Node2D, op: Dictionary) -> void:
	var xf := Transform2D.IDENTITY
	var m: Array = op.get("m", [])
	if m.size() >= 6:
		xf = Transform2D(
			Vector2(float(m[0]), float(m[1])),
			Vector2(float(m[2]), float(m[3])),
			Vector2(float(m[4]), float(m[5]))
		)
	var base: Vector2 = node.get_meta("base_pos", Vector2.ZERO)
	if base != Vector2.ZERO:
		node.transform = xf * Transform2D(0.0, base)
	else:
		node.transform = xf


func _set_color(node: Node2D, op: Dictionary) -> void:
	var ci := node as CanvasItem
	if ci == null:
		return
	var ct: Array = op.get("ct", [])
	if ct.size() < 8:
		ci.modulate = Color.WHITE
		if node is Sprite2D:
			(node as Sprite2D).material = null
		return
	var mult := Color(float(ct[0]), float(ct[1]), float(ct[2]), float(ct[3]))
	var add := Color(float(ct[4]), float(ct[5]), float(ct[6]), float(ct[7]))
	ci.modulate = mult
	if node is Sprite2D:
		if add == Color(0, 0, 0, 0):
			(node as Sprite2D).material = null
		else:
			(node as Sprite2D).material = lib.make_add_material(add)
