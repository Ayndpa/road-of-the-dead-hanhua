class_name SwfMovieClip
extends Node2D

## Plays a Flash timeline (DefineSprite) exported by exporter/swf_to_godot.py.
## Placements are applied per frame; nested sprites become child
## SwfMovieClips, shapes/images become Sprite2D leaves.

signal finished

var lib: SwfLibrary
var sprite_id: int = 0
var def: Dictionary = {}
var fps: float = 30.0
var playing: bool = true:
	set = _set_playing
var loop: bool = true
# Cinematics reuse the garage car, whose upgrade parts (spiked bumper/wheels)
# should not appear on the stock car in the opening animation.
var hide_upgrades: bool = false
var frame_index: int = 0
var labels: Dictionary = {}
var _loop_start: int = 0
var _loop_end: int = -1

var _acc: float = 0.0
var _depths: Dictionary = {}  # depth -> Node2D
var _clips: Dictionary = {}   # mask depth -> clip depth


static func create(id: int, library: SwfLibrary) -> SwfMovieClip:
	var c := SwfMovieClip.new()
	c.lib = library
	c.sprite_id = id
	c.def = library.get_sprite_def(id)
	c.fps = library.fps
	c.labels = c.def.get("labels", {})
	c.name = "swf_%d" % id
	return c


func _ready() -> void:
	_apply_frame(0)


# Flash's gotoAndStop/gotoAndPlay governs the whole subtree, not just the
# timeline you address: stopping a parent freezes every nested clip it placed.
# Without this a parked car (RDObstacleCar does gotoAndStop(iMCFrame)) kept its
# nested timelines cycling for as long as the car was on screen.
func _set_playing(value: bool) -> void:
	if playing == value:
		return
	playing = value
	for depth in _depths:
		var n: Node2D = _depths[depth]
		if n is SwfMovieClip:
			(n as SwfMovieClip).playing = value


func _process(delta: float) -> void:
	if not playing:
		return
	var frames: Array = def.get("frames", [])
	if frames.size() <= 1:
		return
	var hi := _loop_end if _loop_end >= 0 else frames.size() - 1
	_acc += delta * fps
	var guard := 0
	while _acc >= 1.0 and guard < 512:
		_acc -= 1.0
		guard += 1
		if frame_index + 1 > hi:
			if loop:
				frame_index = _loop_start
				_apply_frame(frame_index)
			else:
				playing = false
				finished.emit()
				return
		else:
			frame_index += 1
			_apply_frame(frame_index)


func play_label(label: String, loop_segment: bool = true) -> void:
	if not labels.has(label):
		_loop_start = 0
		_loop_end = -1
		loop = loop_segment
		playing = true
		return
	var start := int(labels[label])
	_loop_start = start
	var next := -1
	for key in labels.keys():
		var v := int(labels[key])
		if v > start and (next < 0 or v < next):
			next = v
	_loop_end = next - 1 if next > start else -1
	# loop the segment for continuous states (walk); play once for one-shots (hit/death)
	loop = loop_segment
	frame_index = start
	_apply_frame(start)
	playing = true


func frame_count() -> int:
	return (def.get("frames", []) as Array).size()


func set_depth_visible(depth: int, vis: bool) -> void:
	var n: Node2D = _depths.get(depth)
	if n != null and is_instance_valid(n):
		n.visible = vis


func set_depth_frame(depth: int, frame: int) -> void:
	var n: Node2D = _depths.get(depth)
	if n is SwfMovieClip:
		var mc := n as SwfMovieClip
		if mc.frame_index != frame:
			mc.seek(frame)
			mc.playing = false


func node_at_depth(depth: int) -> Node2D:
	return _depths.get(depth)


func play_at_depth(depth: int, label: String, loop_segment: bool = false) -> void:
	var n: Node2D = _depths.get(depth)
	if n is SwfMovieClip:
		(n as SwfMovieClip).play_label(label, loop_segment)


# Set a dynamic text field placed by instance name (MC_MessageBox.Title,
# PointsScreen.Slot1.Description ...).  Walks the whole subtree, preferring an
# exact node-name match whose child is a Label.
func set_text(inst_name: String, text: String) -> bool:
	# "Slot1.Description" -> find the "Slot1" subtree, then a Label under a
	# node named "Description" inside it.
	var parts := inst_name.split(".", false)
	if parts.size() == 2:
		var scope := find_child(parts[0], true, false)
		if scope != null:
			for lbl in scope.find_children("*", "Label", true, false):
				if lbl is Label and String((lbl as Label).get_parent().name) == parts[1]:
					(lbl as Label).text = text
					return true
			return false
	for lbl in find_children("*", "Label", true, false):
		if lbl is Label:
			var l := lbl as Label
			var n := l.get_parent()
			if n != null and String(n.name) == inst_name:
				l.text = text
				return true
	for lbl in find_children("*", "Label", true, false):
		if lbl is Label and String((lbl as Label).name) == inst_name:
			(lbl as Label).text = text
			return true
	return false



func seek(i: int) -> void:
	for depth in _depths.keys():
		var node: Node2D = _depths[depth]
		if is_instance_valid(node):
			remove_child(node)
			node.queue_free()
	_depths.clear()
	_clips.clear()
	frame_index = clampi(i, 0, maxi(frame_count() - 1, 0))
	# Flash keeps placements from earlier frames, so seeking must replay from
	# the start rather than applying only the target frame.
	for f in range(0, frame_index + 1):
		_apply_frame(f)


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
				# A Flash timeline "modify" op only carries the fields that
				# change; an absent matrix/color/ratio means "keep current".
				# Resetting them to identity here used to wipe the placement
				# matrix of anything that faded (e.g. the Disclaimer text).
				if op.has("m"):
					_set_transform(node, op)
				if op.has("ct"):
					_set_color(node, op)
				if op.has("ratio"):
					_apply_morph(node, op)
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
		_apply_morph(existing, op)
		return

	var index := -1
	if existing != null and is_instance_valid(existing):
		index = existing.get_index()
	_drop(depth)

	var node := _make_node(cid, op)
	if node == null:
		return
	var inst_v: Variant = op.get("n", "")
	var inst := inst_v if inst_v is String else ""
	node.name = _sanitize_name(inst) if inst != "" else "d%d" % depth
	node.set_meta("char_id", cid)
	node.set_meta("depth", depth)
	if hide_upgrades and (node.name == "Bumper" or node.name == "Wheel"):
		node.visible = false
	if node.name == "SkipCinematicButton":
		# keep the skip button above any full-screen fade / flash overlays,
		# otherwise it "disappears" part-way through the cinematic
		var ci := node as CanvasItem
		if ci != null:
			ci.z_index = 4096

	var clip_depth := int(op.get("clip", -1))
	var mask_depth := _active_mask_for(depth)
	var parent: Node = self
	if mask_depth >= 0 and _depths.has(mask_depth):
		parent = _depths[mask_depth]
	parent.add_child(node)
	if index >= 0 and parent == self:
		move_child(node, index)
	_depths[depth] = node
	_set_transform(node, op)
	_set_color(node, op)
	_apply_morph(node, op)
	if clip_depth >= 0:
		var ci := node as CanvasItem
		if ci != null:
			ci.clip_children = CanvasItem.CLIP_CHILDREN_ONLY
		_clips[depth] = clip_depth
	else:
		# a newly placed masked object must sit behind its mask's siblings
		if parent != self and parent is Node2D:
			var mask_node := parent as Node2D
			mask_node.move_child(node, mask_node.get_child_count() - 1)


func _active_mask_for(depth: int) -> int:
	for md in _clips.keys():
		if depth > int(md) and depth <= int(_clips[md]):
			return int(md)
	return -1


func _drop(depth: int) -> void:
	if not _depths.has(depth):
		return
	var node: Node2D = _depths[depth]
	_depths.erase(depth)
	if _clips.has(depth):
		# unclip: move masked children back to this timeline, keeping their place
		for child in node.get_children():
			if child is Node2D:
				var world := node.transform * (child as Node2D).transform
				node.remove_child(child)
				add_child(child)
				(child as Node2D).transform = world
		_clips.erase(depth)
	if is_instance_valid(node):
		if node.get_parent() == self:
			remove_child(node)
		else:
			node.get_parent().remove_child(node)
		node.queue_free()


func _make_node(cid: int, _op: Dictionary) -> Node2D:
	var c := lib.get_character(cid)
	var ctype := String(c.get("type", ""))
	match ctype:
		"shape", "image":
			var off := Vector2(float(c.get("x", 0.0)), float(c.get("y", 0.0)))
			if ctype == "shape" and lib.has_vector(cid):
				var vs := SwfVectorShape.new()
				vs.setup(lib.get_vector(cid), lib.bin_bytes, _resolve_fx(cid))
				vs.set_meta("base_pos", off)
				if off != Vector2.ZERO:
					vs.transform = Transform2D(0.0, off)
				return vs
			var s := Sprite2D.new()
			s.texture = lib.get_texture(cid)
			s.centered = false
			s.set_meta("base_pos", off)
			if off != Vector2.ZERO:
				s.transform = Transform2D(0.0, off)
			return s
		"sprite":
			var mc := SwfMovieClip.create(cid, lib)
			mc.hide_upgrades = hide_upgrades
			# a clip placed on a stopped timeline must not start running on its own
			mc.playing = playing
			var fx := _resolve_fx(cid)
			if not fx.is_empty():
				mc.set_meta("fx", fx)
			if bool(c.get("button", false)):
				# A button is exported as [up, over]; keep it on the up frame
				# until the game switches it to the over frame on hover.
				mc.playing = false
			return mc
		"morph":
			return _make_morph_node(cid)
		"text":
			return _make_text_node(cid)
		_:
			return Node2D.new()


func _make_morph_node(cid: int) -> AnimatedSprite2D:
	var c := lib.get_character(cid)
	var spr := AnimatedSprite2D.new()
	var count := int(c.get("frames", 0))
	var dir := String(c.get("dir", ""))
	if count > 0 and dir != "":
		var sf := SpriteFrames.new()
		sf.remove_animation("default")
		sf.add_animation("default")
		sf.set_animation_loop("default", false)
		sf.set_animation_speed("default", 1.0)
		for i in range(1, count + 1):
			var tex := load("%s/%d.png" % [dir, i]) as Texture2D
			if tex != null:
				sf.add_frame("default", tex)
		spr.sprite_frames = sf
		spr.animation = "default"
		spr.frame = 0
		spr.stop()
	spr.centered = false
	var off := Vector2(float(c.get("x", 0.0)), float(c.get("y", 0.0)))
	spr.set_meta("base_pos", off)
	if off != Vector2.ZERO:
		spr.transform = Transform2D(0.0, off)
	return spr


func _apply_morph(node: Node, op: Dictionary) -> void:
	if not (node is AnimatedSprite2D):
		return
	var spr := node as AnimatedSprite2D
	if spr.sprite_frames == null:
		return
	var total := spr.sprite_frames.get_frame_count("default")
	if total <= 0 or not op.has("ratio"):
		return
	var ratio := float(op["ratio"]) / 65535.0
	spr.frame = clampi(int(round(ratio * float(total - 1))), 0, total - 1)


static func _to_color(arr: Array) -> Color:
	if arr.size() < 3:
		return Color.WHITE
	var a := 1.0 if arr.size() < 4 else float(arr[3]) / 255.0
	return Color(float(arr[0]) / 255.0, float(arr[1]) / 255.0, float(arr[2]) / 255.0, a)


static func _sanitize_name(raw: String) -> String:
	var out := raw
	for ch in [".", ":", "/", "\"", "@", "%"]:
		out = out.replace(ch, "_")
	return out if out != "" else "node"


func _make_text_node(cid: int) -> Node2D:
	var root := Node2D.new()
	var td: Dictionary = lib.get_text_def(cid)
	if td.is_empty():
		return root
	var kind := String(td.get("kind", ""))
	if kind == "edit":
		var bounds: Array = td.get("bounds", [0, 0, 0, 0])
		var w := maxf(float(bounds[2]) - float(bounds[0]), 1.0)
		var h := maxf(float(bounds[3]) - float(bounds[1]), 1.0)
		var lbl := Label.new()
		lbl.text = String(td.get("text", ""))
		var font := lib.get_font(int(td.get("font", 0)))
		if font != null:
			lbl.add_theme_font_override("font", font)
		lbl.add_theme_font_size_override("font_size", int(round(float(td.get("size", 12.0)))))
		lbl.add_theme_color_override("font_color", _to_color(td.get("color", [255, 255, 255, 255])))
		if bool(td.get("multiline", false)):
			lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		# The field rectangle is relative to the character origin, so its
		# x/y offset must be applied (the Controls key fields start ~60px in).
		lbl.position = Vector2(float(bounds[0]), float(bounds[1]))
		lbl.size = Vector2(w, h)
		lbl.custom_minimum_size = Vector2(w, h)
		if int(td.get("align", 0)) == 2:
			lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		elif int(td.get("align", 0)) == 1:
			lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		root.add_child(lbl)
	else:
		var x := 0.0
		var baseline := 0.0
		var entries: Array = []
		for rec_v in td.get("records", []):
			if not (rec_v is Dictionary):
				continue
			var rec: Dictionary = rec_v
			if rec.get("x") != null:
				x = float(rec["x"])
			if rec.get("y") != null:
				baseline = float(rec["y"])
			var size := float(rec.get("size", 12.0))
			var font := lib.get_font(int(rec.get("font", 0)))
			var lbl := Label.new()
			lbl.text = String(rec.get("text", ""))
			if font != null:
				lbl.add_theme_font_override("font", font)
			lbl.add_theme_font_size_override("font_size", int(round(size)))
			lbl.add_theme_color_override("font_color", _to_color(rec.get("color", [255, 255, 255, 255])))
			var ascent := size * 0.8
			if font != null:
				ascent = font.get_ascent(int(round(size)))
			lbl.position = Vector2(x, baseline - ascent)
			root.add_child(lbl)
			entries.append({"label": lbl, "font": font, "size": int(round(size)),
					"left": x, "adv": float(rec.get("adv", 0.0))})
			x += float(rec.get("adv", 0.0))
		_recentre_static_records(entries)
	root.set_meta("base_pos", Vector2(float(td.get("x", 0.0)), float(td.get("y", 0.0))))
	return root


# A static text's per-record xOffsets centre a block for the Flash font's own
# glyph advances.  The exported TTFs advance by different amounts, so a block
# that was centred in Flash drifts off-centre (the disclaimer warning does).
# Detect such a block and re-centre it around its original centre using the
# widths Godot actually renders.  Left-aligned blocks are left untouched.
func _recentre_static_records(entries: Array) -> void:
	if entries.size() < 2:
		return
	var min_left := INF
	var orig_right := -INF
	var rendered_right := -INF
	for e in entries:
		var font: Font = e["font"]
		var lbl: Label = e["label"]
		if font == null or lbl.text == "":
			return
		min_left = minf(min_left, float(e["left"]))
		orig_right = maxf(orig_right, float(e["left"]) + float(e["adv"]))
		var w := font.get_string_size(lbl.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, int(e["size"])).x
		rendered_right = maxf(rendered_right, float(e["left"]) + w)
	for e in entries:
		var left := float(e["left"])
		var left_margin := left - min_left
		var right_margin := orig_right - (left + float(e["adv"]))
		if absf(left_margin - right_margin) > 2.0:
			return
	var shift := (orig_right - rendered_right) * 0.5
	if absf(shift) < 0.5:
		return
	for e in entries:
		var lbl: Label = e["label"]
		lbl.position.x += shift


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
		xf = xf * Transform2D(0.0, base)
	# masked nodes are reparented under the mask; keep them in timeline space
	var parent := node.get_parent()
	if parent != self and parent is Node2D:
		node.transform = (parent as Node2D).transform.affine_inverse() * xf
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
		if node.has_method("set_add_color"):
			node.set_add_color(Color(0, 0, 0, 0))
		return
	var mult := Color(float(ct[0]), float(ct[1]), float(ct[2]), float(ct[3]))
	var add := Color(float(ct[4]), float(ct[5]), float(ct[6]), float(ct[7]))
	ci.modulate = mult
	if node.has_method("set_add_color"):
		node.set_add_color(add)
	elif node is Sprite2D:
		if add == Color(0, 0, 0, 0):
			(node as Sprite2D).material = null
		else:
			(node as Sprite2D).material = lib.make_add_material(add)


# A placement's own filter wins; otherwise inherit the nearest ancestor's, so
# a glow on a button movie clip reaches the shapes drawn inside it.
func _resolve_fx(cid: int) -> Dictionary:
	var fx := lib.get_filter(cid)
	if not fx.is_empty():
		return fx
	return get_meta("fx", {})
