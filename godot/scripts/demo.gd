extends Node2D

## Gallery demo: plays exported SWF sprite timelines one at a time.
## Left/Right or auto-advance cycles; Space pauses; Esc quits.

const SWF_ROOT := "res://assets/swf"
const DWELL := 1.2

var lib: SwfLibrary
var index: Array = []
var current: int = -1
var clip: SwfMovieClip = null
var label: Label
var hint: Label
var timer: float = 0.0
var want_shot: bool = false
var shot_frames: Array[int] = [10, 150, 300, 480]
var shot_index: int = 0


func _ready() -> void:
	RenderingServer.set_default_clear_color(Color(0.32, 0.32, 0.35))
	want_shot = OS.get_cmdline_user_args().has("--shot")

	lib = SwfLibrary.new(SWF_ROOT)
	var idx_path := SWF_ROOT + "/index.json"
	if FileAccess.file_exists(idx_path):
		var f := FileAccess.open(idx_path, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Array:
			index = parsed

	var layer := CanvasLayer.new()
	add_child(layer)
	label = Label.new()
	label.position = Vector2(18, 12)
	label.add_theme_font_size_override("font_size", 22)
	layer.add_child(label)
	hint = Label.new()
	hint.position = Vector2(18, 44)
	hint.add_theme_font_size_override("font_size", 14)
	hint.modulate = Color(0.8, 0.8, 0.8)
	hint.text = "Left/Right: prev/next    Space: pause    auto-advance %.1fs" % DWELL
	layer.add_child(hint)

	if index.is_empty():
		label.text = "index.json empty - run exporter/swf_to_godot.py first"
		return
	_show(0)


func _show(i: int) -> void:
	if index.is_empty():
		return
	if clip != null and is_instance_valid(clip):
		clip.get_parent().remove_child(clip)
		clip.queue_free()
	current = ((i % index.size()) + index.size()) % index.size()
	var e: Dictionary = index[current]
	clip = SwfMovieClip.create(int(e.get("id", 0)), lib)
	add_child(clip)
	var uargs := OS.get_cmdline_user_args()
	var fi := uargs.find("--frame")
	if fi >= 0 and fi + 1 < uargs.size():
		clip.seek(int(uargs[fi + 1]))
		clip.playing = false
	_fit()
	label.text = "%d / %d   %s   (id %d, %d frames)" % [
		current + 1, index.size(),
		String(e.get("name", "?")), int(e.get("id", 0)), int(e.get("frameCount", 0))
	]
	timer = 0.0


func _process(delta: float) -> void:
	if Input.is_action_just_pressed("ui_right"):
		_show(current + 1)
	if Input.is_action_just_pressed("ui_left"):
		_show(current - 1)
	if Input.is_action_just_pressed("ui_accept"):
		if clip != null and is_instance_valid(clip):
			clip.playing = not clip.playing
	if Input.is_key_pressed(KEY_ESCAPE):
		get_tree().quit()

	if clip != null and is_instance_valid(clip):
		timer += delta
		if timer >= DWELL:
			_show(current + 1)

	if want_shot and shot_index < shot_frames.size() and Engine.get_frames_drawn() >= shot_frames[shot_index]:
		var img := get_viewport().get_texture().get_image()
		var out := "user://shot_%d.png" % shot_index
		img.save_png(out)
		print("saved screenshot: ", ProjectSettings.globalize_path(out), "  (", label.text, ")")
		shot_index += 1
		if shot_index >= shot_frames.size():
			get_tree().quit()


func _fit() -> void:
	if clip == null or not is_instance_valid(clip):
		return
	var rect := _clip_bounds()
	if rect.size.x <= 0.0 or rect.size.y <= 0.0:
		return
	var view := get_viewport_rect().size
	var target := Vector2(view.x * 0.8, view.y * 0.72)
	var s := minf(target.x / rect.size.x, target.y / rect.size.y)
	s = clampf(s, 0.002, 40.0)
	clip.scale = Vector2(s, s)
	var center := rect.position + rect.size * 0.5
	clip.position = Vector2(view.x * 0.5, view.y * 0.55) - center * s
	if OS.get_cmdline_user_args().has("--debug"):
		print("fit rect=", rect, " scale=", s, " pos=", clip.position)


func _clip_bounds() -> Rect2:
	var out := Rect2()
	var first := true
	var stack: Array[Node] = [clip]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Sprite2D:
			var s := n as Sprite2D
			if s.texture != null:
				var r := s.get_rect()
				if OS.get_cmdline_user_args().has("--debug"):
					print("  spr node=", s.get_path(), " tex=", s.texture.resource_path, " gpos=", s.global_position, " gscale=", s.global_scale, " mod=", s.modulate)
				var pts := [
					r.position,
					Vector2(r.end.x, r.position.y),
					r.end,
					Vector2(r.position.x, r.end.y),
				]
				for p in pts:
					var lp: Vector2 = clip.to_local(s.to_global(p))
					if first:
						out = Rect2(lp, Vector2.ZERO)
						first = false
					else:
						out = out.expand(lp)
		for c in n.get_children():
			stack.append(c)
	return out
