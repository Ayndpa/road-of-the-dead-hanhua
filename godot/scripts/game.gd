extends Node2D

## Road of the Dead (Godot port) — startup flow and main menu.
##
## The Flash preloader (Preloading/Ready/ResourceContainer/Init, the
## "please wait" / "click here to play" screens) is gone: Godot has no
## streaming load to wait for. Launch shows only the mature-content
## warning, then goes straight to the interactive main menu. The Newgrounds
## and DogTek logo cinematics are skipped entirely.
##
## In the menu only the "THE GREAT ESCAPE" (亡命大逃亡) button starts the
## game; clicking anywhere else does nothing. That button first plays the
## story opening cinematic (GameIntro) with its streamed narration, then
## drops into the garage hub (RDGameModeGarage) before the first level.
##
## Hovering a menu button lights it up and shows that mode's description on
## the bottom-left signboard (the Flash RDGame.as tooltips).
##
## OPTIONS shows the original Flash settings book that ships inside the Menu
## clip.  Its left "Controls" page lists the ten actions and lets the player
## rebind them (click a key field, then press a key); the right page replaces
## the obsolete Quality/Buildings toggles with Sound and Music volume sliders.
## Audio settings persist to user://settings.cfg, key bindings to
## user://player.cfg (through the PlayerInfo autoload that gameplay reads).
##
## The stage is scaled to always cover the whole window (Flash NO_BORDER
## style), so there are no letterbox bars at any window size.

const SWF_ROOT := "res://assets/swf"
const DESIGN := Vector2(600.0, 400.0)

const FLOW: Array[String] = [
	"Disclaimer",
	"Menu",
]

# interactive menu buttons; each is exported as [up, over] and lights up on hover
const MENU_BUTTONS: Array[String] = [
	"StoryMode",
	"StoryHardcoreMode",
	"TimeMode",
	"MilitaryMode",
	"Options",
	"Achievements",
	"HighScores",
	"Newgrounds",
	"EvilDog",
	"SickDeathFiend",
	"MusicButton",
]

# bottom-left signboard text shown while a menu button is hovered (Flash RDGame.as)
const MENU_TOOLTIPS := {
	"StoryMode": "Speed through the zombie apocalypse and escape the quarantined city!\n\nNormal difficulty",
	"StoryHardcoreMode": "This is the road for survivors with something to prove!\n\nHard difficulty",
	"TimeMode": "You're living on borrowed time.\n\nGet as far as you can by killing zombies to earn extra time!",
	"MilitaryMode": "This is war and you are a one man army on wheels!\n\nGet as far as you can while facing brutal military resistance!",
	"Options": "Adjust the volume of the sound effects and the music.",
	"Achievements": "Surviving the zombie apocalypse requires a complete set of skills.\nDo You have what it takes to complete all the achievements?",
	"HighScores": "Are you trying to be the greatest survivor?\n\nCheck the high scores for the Dead On Time and Police State modes!",
	"Newgrounds": "Play more games at newgrounds.com, where artists, programmers, musicians, writers and voice actors join forces to make pure awesomeness!",
	"EvilDog": "Evil-Dog.com\n\nCheck out my other games, my music and my movies on my official website!",
	"SickDeathFiend": "SickDeathFiend.com\n\nCheck out more movies and art by SickDeathFiend on his official website!",
	"MusicButton": "Music made by\nSymphony of Specters\n\nVisit their website for more amazing music!",
}

# main-timeline stream audio, and the offset (seconds) where the GameIntro
# cinematic starts (SWF frame 709 -> see pipeline/swf/stream_timing.py).
const STORY_AUDIO := "res://assets/swf/sounds/stream_story.mp3"
const STORY_AUDIO_OFFSET := 22.07
const STORY_SEGMENT := "GameIntro"

const SETTINGS_PATH := "user://settings.cfg"
const BUS_MUSIC := "Music"
const BUS_SFX := "SFX"

enum St { PLAY, MENU, CINEMATIC }

var lib: SwfLibrary
var by_name: Dictionary = {}
var stage: Node2D
var current: SwfMovieClip = null
var flow_pos: int = 0
var state: int = St.PLAY
var _shot: bool = false
var _shot_frame: int = 75
var _perf: bool = false
var _t0: int = 0
var _start_story: bool = false
var _music: AudioStreamPlayer
var _sfx: AudioStreamPlayer

# Options: the original Flash settings panel lives inside the Menu clip and is
# shown on demand.  Its Sounds/Music toggles become volume sliders.
var _options_panel: Node2D = null
var _options_configured: bool = false
var _options_open: bool = false
var _rebind_row: int = -1
var _settings := {"sounds": 0.8, "music": 0.8}

# bottom-left menu tooltip signboard, driven by hover
var _tooltip_label: Label = null
var _tooltip_default: String = ""


func _ready() -> void:
	_t0 = Time.get_ticks_msec()
	RenderingServer.set_default_clear_color(Color.BLACK)
	lib = SwfLibrary.new(SWF_ROOT)
	_load_index()

	var uargs := OS.get_cmdline_user_args()
	if uargs.has("--game"):
		get_tree().call_deferred("change_scene_to_file", "res://scenes/gameplay.tscn")
		return
	if uargs.has("--garage"):
		get_tree().call_deferred("change_scene_to_file", "res://scenes/garage.tscn")
		return
	if PlayerInfo.start_at_menu:
		PlayerInfo.start_at_menu = false
		flow_pos = FLOW.find("Menu")
	if uargs.has("--menu") or uargs.has("--options"):
		flow_pos = FLOW.find("Menu")
	if uargs.has("--story"):
		_start_story = true
	var si := uargs.find("--start")
	if si >= 0 and si + 1 < uargs.size():
		var idx := FLOW.find(uargs[si + 1])
		if idx >= 0:
			flow_pos = idx
	_shot = uargs.has("--shot")
	_perf = uargs.has("--perf")
	var sf := uargs.find("--shot-frame")
	if sf >= 0 and sf + 1 < uargs.size():
		_shot_frame = int(uargs[sf + 1])

	stage = Node2D.new()
	stage.name = "Stage"
	add_child(stage)
	_music = AudioStreamPlayer.new()
	add_child(_music)
	_sfx = AudioStreamPlayer.new()
	add_child(_sfx)
	_load_settings()
	_setup_audio_buses()
	get_viewport().size_changed.connect(_apply_fit)
	_apply_fit()
	if _start_story:
		_begin_story()
	else:
		_play_current()
	if uargs.has("--options"):
		_open_options()


func _load_index() -> void:
	var path := SWF_ROOT + "/index.json"
	if not FileAccess.file_exists(path):
		push_error("index.json missing - run exporter/swf_to_godot.py first")
		return
	var f := FileAccess.open(path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	if parsed is Array:
		for entry in parsed:
			if entry is Dictionary:
				by_name[String(entry.get("name", ""))] = entry


func _play_segment(seg_name: String) -> bool:
	if current != null and is_instance_valid(current):
		stage.remove_child(current)
		current.queue_free()
	current = null
	_options_panel = null
	_options_configured = false
	_options_open = false
	_tooltip_label = null
	_tooltip_default = ""
	var entry: Dictionary = by_name.get(seg_name, {})
	if entry.is_empty():
		push_error("segment not found: " + seg_name)
		return false
	current = SwfMovieClip.create(int(entry.get("id", -1)), lib)
	current.name = seg_name
	current.loop = false
	stage.add_child(current)
	current.finished.connect(_on_segment_finished)
	return true


func _play_current() -> void:
	var name := String(FLOW[flow_pos])
	if not _play_segment(name):
		_advance()
		return
	if name == "Menu":
		state = St.MENU
		_start_menu_music()
	else:
		state = St.PLAY


func _on_segment_finished() -> void:
	match state:
		St.MENU:
			return
		St.CINEMATIC:
			_finish_story()
		_:
			_advance()


func _advance() -> void:
	if flow_pos < FLOW.size() - 1:
		flow_pos += 1
		_play_current()


func _unhandled_input(event: InputEvent) -> void:
	# While capturing a new key, the next key press is the binding (Esc cancels).
	if _options_open and _rebind_row >= 0:
		if event is InputEventKey and event.pressed and not event.echo:
			_finish_rebind(event.keycode)
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		if _options_open:
			_close_options()
		else:
			get_tree().quit()
		return

	# Menu buttons respond to left clicks only.  Cinematic / intro screens are
	# ONLY skippable by left-clicking the visible skip button; "press any key
	# or click anywhere to skip" is intentionally not supported.
	var left_click := Vector2.INF
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			left_click = mb.position
	var key_pressed := event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo

	match state:
		St.MENU:
			if _options_open:
				if left_click != Vector2.INF:
					for i in PlayerInfo.bindings.size():
						if _button_rect("SetKey%d" % (i + 1)).has_point(left_click):
							_start_rebind(i)
							return
					if _button_rect("Close").has_point(left_click):
						_close_options()
				return
			# Only the real menu buttons react to a click.
			if left_click != Vector2.INF and _button_rect("StoryMode").has_point(left_click):
				_begin_story()
			elif left_click != Vector2.INF and _button_rect("Options").has_point(left_click):
				_open_options()
		St.CINEMATIC:
			# Opening cinematic: skippable ONLY by clicking the SKIP button.
			if left_click != Vector2.INF and _skip_button_rect().has_point(left_click):
				_finish_story()
		_:
			# Disclaimer warning page: any key or a click skips it.
			if key_pressed or left_click != Vector2.INF:
				_advance()


func _begin_story() -> void:
	Input.set_default_cursor_shape(Input.CURSOR_ARROW)
	state = St.CINEMATIC
	if not _play_segment(STORY_SEGMENT):
		_finish_story()
		return
	# The story reuses the garage car; keep it stock (no upgrade parts).
	if current != null:
		current.hide_upgrades = true
	_play_story_audio()


func _finish_story() -> void:
	_sfx.stop()
	get_tree().change_scene_to_file("res://scenes/garage.tscn")


func _play_story_audio() -> void:
	_music.stop()
	if not FileAccess.file_exists(STORY_AUDIO):
		return
	var stream := load(STORY_AUDIO)
	if stream == null:
		return
	_sfx.stream = stream
	_sfx.play(STORY_AUDIO_OFFSET)


# Screen-space rectangle of a named menu button, so a click can be told
# apart from a click anywhere on the menu.
func _button_rect(btn_name: String) -> Rect2:
	if current == null or not is_instance_valid(current):
		return Rect2()
	var btn := current.find_child(btn_name, true, false)
	if btn == null:
		return Rect2()
	return _subtree_rect(btn)


# Screen-space rect of the in-cinematic "SKIP" button.  Returns an empty rect
# when the current segment has none, so nothing else can skip the cinematic.
func _skip_button_rect() -> Rect2:
	if current == null or not is_instance_valid(current):
		return Rect2()
	var btn := current.find_child("SkipCinematicButton", true, false)
	if btn == null or not (btn is CanvasItem) or not (btn as CanvasItem).visible:
		return Rect2()
	return _subtree_rect(btn)


# Lights up whichever menu button the mouse is over (Flash rollover state).
func _update_menu_hover() -> void:
	if state != St.MENU or current == null or not is_instance_valid(current):
		return
	if _options_open:
		_reset_menu_hover()
		_update_controls_hover()
		return
	var mpos := get_viewport().get_mouse_position()
	var over_any := false
	var hovered_name := ""
	for bname in MENU_BUTTONS:
		var btn := current.find_child(bname, true, false)
		if not (btn is SwfMovieClip):
			continue
		var mc := btn as SwfMovieClip
		var hovered := _subtree_rect(mc).has_point(mpos)
		if hovered:
			over_any = true
			hovered_name = bname
		var want := 1 if hovered else 0
		if mc.frame_count() > 1 and mc.frame_index != want:
			mc.seek(want)
	_set_menu_tooltip(hovered_name)
	Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND if over_any else Input.CURSOR_ARROW)


# Bottom-left signboard: shows the hovered button's description, and falls back
# to the menu's authored default text when nothing is hovered.
func _set_menu_tooltip(btn_name: String) -> void:
	if _tooltip_label == null or not is_instance_valid(_tooltip_label):
		if current == null or not is_instance_valid(current):
			return
		var tt := current.find_child("MenuTooltip", true, false)
		if tt == null:
			return
		_tooltip_label = _find_label(tt)
		if _tooltip_label == null:
			return
		_tooltip_default = _tooltip_label.text
		# the signboard is a fixed graphic; keep the text inside it
		_tooltip_label.clip_text = true
		var td := lib.get_text_def(4340)
		var b: Array = td.get("bounds", [])
		if b.size() == 4:
			_tooltip_label.size.y = float(b[3]) - float(b[1])
			_tooltip_label.custom_minimum_size.y = _tooltip_label.size.y
	var text := _tooltip_default
	if MENU_TOOLTIPS.has(btn_name):
		text = String(MENU_TOOLTIPS[btn_name])
	if _tooltip_label.text != text:
		_tooltip_label.text = text


func _find_label(root: Node) -> Label:
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Label:
			return n as Label
		for c in n.get_children():
			stack.append(c)
	return null


func _reset_menu_hover() -> void:
	if current == null or not is_instance_valid(current):
		return
	for bname in MENU_BUTTONS:
		var btn := current.find_child(bname, true, false)
		if btn is SwfMovieClip:
			var mc := btn as SwfMovieClip
			if mc.frame_count() > 1 and mc.frame_index != 0:
				mc.seek(0)


# Lights up the key-rebind rows and the Close button while the panel is open.
func _update_controls_hover() -> void:
	var over_any := false
	if _options_panel != null and is_instance_valid(_options_panel):
		var mpos := get_viewport().get_mouse_position()
		var names: Array[String] = []
		for i in PlayerInfo.bindings.size():
			names.append("SetKey%d" % (i + 1))
		names.append("Close")
		for nm in names:
			var btn := _options_panel.find_child(nm, true, false)
			if not (btn is SwfMovieClip):
				continue
			var mc := btn as SwfMovieClip
			var hovered := _subtree_rect(mc).has_point(mpos)
			if hovered:
				over_any = true
			var want := 1 if hovered else 0
			if mc.frame_count() > 1 and mc.frame_index != want:
				mc.seek(want)
	Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND if over_any else Input.CURSOR_ARROW)


func _subtree_rect(node: Node) -> Rect2:
	var rect := Rect2()
	var first := true
	var stack: Array[Node] = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Sprite2D:
			var tex := (n as Sprite2D).texture
			if tex != null:
				var size := tex.get_size()
				for corner in [Vector2.ZERO, Vector2(size.x, 0.0), Vector2(0.0, size.y), size]:
					var p: Vector2 = (n as CanvasItem).get_global_transform() * corner
					if first:
						rect = Rect2(p, Vector2.ZERO)
						first = false
					else:
						rect = rect.expand(p)
		elif n is SwfVectorShape:
			var lr := (n as SwfVectorShape).local_rect
			if lr.size != Vector2.ZERO:
				for corner in [lr.position, Vector2(lr.end.x, lr.position.y), Vector2(lr.position.x, lr.end.y), lr.end]:
					var p: Vector2 = (n as CanvasItem).get_global_transform() * corner
					if first:
						rect = Rect2(p, Vector2.ZERO)
						first = false
					else:
						rect = rect.expand(p)
		elif n is Label:
			var lr := (n as Label).get_global_rect()
			if first:
				rect = lr
				first = false
			else:
				rect = rect.merge(lr)
		for c in n.get_children():
			stack.append(c)
	return rect


func _start_menu_music() -> void:
	_sfx.stop()
	var res := lib.get_sound_res("SND_Music_MenuMusic")
	if res == "" or not FileAccess.file_exists(res):
		return
	var stream := load(res)
	if stream == null:
		return
	if stream is AudioStreamMP3:
		(stream as AudioStreamMP3).loop = true
	elif stream is AudioStreamOggVorbis:
		(stream as AudioStreamOggVorbis).loop = true
	_music.stream = stream
	_music.play()


# --------------------------------------------------------------------------
# audio buses + persisted settings
# --------------------------------------------------------------------------
func _setup_audio_buses() -> void:
	for bus_name in [BUS_MUSIC, BUS_SFX]:
		if AudioServer.get_bus_index(bus_name) < 0:
			AudioServer.add_bus()
			AudioServer.set_bus_name(AudioServer.bus_count - 1, bus_name)
	_music.bus = BUS_MUSIC
	_sfx.bus = BUS_SFX
	_apply_volumes()


func _apply_volumes() -> void:
	_set_bus_volume(BUS_MUSIC, float(_settings["music"]))
	_set_bus_volume(BUS_SFX, float(_settings["sounds"]))


func _set_bus_volume(bus_name: String, v: float) -> void:
	var idx := AudioServer.get_bus_index(bus_name)
	if idx < 0:
		return
	AudioServer.set_bus_mute(idx, v <= 0.001)
	AudioServer.set_bus_volume_db(idx, linear_to_db(clampf(v, 0.0001, 1.0)))


func _load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(SETTINGS_PATH) == OK:
		_settings["sounds"] = clampf(float(cf.get_value("audio", "sounds", 0.8)), 0.0, 1.0)
		_settings["music"] = clampf(float(cf.get_value("audio", "music", 0.8)), 0.0, 1.0)


func _save_settings() -> void:
	var cf := ConfigFile.new()
	cf.set_value("audio", "sounds", float(_settings["sounds"]))
	cf.set_value("audio", "music", float(_settings["music"]))
	cf.save(SETTINGS_PATH)


# --------------------------------------------------------------------------
# options panel (the original Flash settings book, embedded in the Menu clip)
# --------------------------------------------------------------------------
func _sync_options_panel() -> void:
	if state != St.MENU or current == null or not is_instance_valid(current):
		return
	if _options_panel == null or not is_instance_valid(_options_panel):
		_options_panel = current.find_child("OptionsPanel", true, false) as Node2D
		if _options_panel == null:
			return
		_options_configured = false
	if _options_open:
		if not _options_configured:
			_configure_options_panel()
		_options_panel.visible = true
	elif _options_panel.visible:
		_options_panel.visible = false


func _find_by_char_id(root: Node, cid: int) -> Node2D:
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Node2D and int(n.get_meta("char_id", -1)) == cid:
			return n as Node2D
		for c in n.get_children():
			stack.append(c)
	return null


# Replace the obsolete Flash Quality/Buildings sections and the Sounds/Music
# on-off toggles with volume sliders.  The left "Controls" page stays and its
# key fields are wired to the rebinding system.
func _configure_options_panel() -> void:
	_options_configured = true
	for nm in ["QualityLow", "QualityMedium", "QualityHigh",
			"BuildingsOn", "BuildingsOff", "SoundsOn", "SoundsOff",
			"MusicOn", "MusicOff"]:
		var n: Node = _options_panel.find_child(nm, true, false)
		if n is CanvasItem:
			(n as CanvasItem).visible = false
	for cid in [4414, 4407]:  # the "Quality" and "Buildings" section labels
		var n := _find_by_char_id(_options_panel, cid)
		if n != null:
			n.visible = false
	_add_option_slider("SoundsOn", "SoundsOff", "sounds")
	_add_option_slider("MusicOn", "MusicOff", "music")
	_setup_controls_page()


# A slider takes the place of a pair of present/absent toggle buttons, so it is
# laid out from those buttons' real screen rectangle.
func _add_option_slider(on_name: String, off_name: String, key: String) -> void:
	var on_node := _options_panel.find_child(on_name, true, false) as Node2D
	var off_node := _options_panel.find_child(off_name, true, false) as Node2D
	if on_node == null or off_node == null:
		return
	var r := _subtree_rect(on_node).merge(_subtree_rect(off_node))
	var tl := _options_panel.to_local(r.position)
	var br := _options_panel.to_local(r.end)
	var cx := (tl.x + br.x) * 0.5
	var cy := (tl.y + br.y) * 0.5
	var w := maxf(br.x - tl.x, 70.0)
	var slider := HSlider.new()
	slider.min_value = 0.0
	slider.max_value = 100.0
	slider.step = 1.0
	slider.value = roundf(float(_settings[key]) * 100.0)
	slider.position = Vector2(cx - w * 0.5, cy - 7.0)
	slider.custom_minimum_size = Vector2(w, 14.0)
	slider.size = slider.custom_minimum_size
	slider.value_changed.connect(func(v: float) -> void:
		_settings[key] = v / 100.0
		_apply_volumes()
		_save_settings())
	_options_panel.add_child(slider)


# --------------------------------------------------------------------------
# controls page (key rebinding)
# --------------------------------------------------------------------------
func _setup_controls_page() -> void:
	for i in PlayerInfo.bindings.size():
		_display_key(i, OS.get_keycode_string(PlayerInfo.binding(i)))


func _key_label(i: int) -> Label:
	var node := _options_panel.find_child("KeyName%d" % (i + 1), true, false)
	return _find_label(node)


func _display_key(i: int, text: String) -> void:
	var lbl := _key_label(i)
	if lbl != null:
		lbl.text = text


func _start_rebind(i: int) -> void:
	_rebind_row = i
	_display_key(i, "Press a key...")
	Input.set_default_cursor_shape(Input.CURSOR_ARROW)


func _finish_rebind(code: int) -> void:
	if _rebind_row < 0:
		return
	var row := _rebind_row
	_rebind_row = -1
	if code != KEY_ESCAPE and code != 0:
		PlayerInfo.set_binding(row, code)
	_display_key(row, OS.get_keycode_string(PlayerInfo.binding(row)))


func _open_options() -> void:
	_options_open = true
	Input.set_default_cursor_shape(Input.CURSOR_ARROW)
	_sync_options_panel()


func _close_options() -> void:
	_options_open = false
	_rebind_row = -1
	_save_settings()
	if _options_panel != null and is_instance_valid(_options_panel):
		_options_panel.visible = false


func _apply_fit() -> void:
	# Fit the whole 3:2 stage inside the window (letterbox / pillarbox) instead
	# of cover-cropping, so 16:9 and wider screens never cut off the original
	# Flash framing (the title, HUD, etc.).
	if stage == null:
		return
	var vp := get_viewport_rect().size
	if vp.x <= 0.0 or vp.y <= 0.0:
		return
	var s := minf(vp.x / DESIGN.x, vp.y / DESIGN.y)
	stage.scale = Vector2(s, s)
	stage.position = vp * 0.5 - DESIGN * 0.5 * s


func _update_skip_hover() -> void:
	if current == null or not is_instance_valid(current):
		return
	var btn := current.find_child("SkipCinematicButton", true, false)
	if not (btn is SwfMovieClip):
		return
	var mc := btn as SwfMovieClip
	var over := _subtree_rect(mc).has_point(get_viewport().get_mouse_position())
	var want := 1 if over else 0
	if mc.frame_count() > 1 and mc.frame_index != want:
		mc.seek(want)
	if over:
		Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND)


func _process(_delta: float) -> void:
	_sync_options_panel()
	_update_menu_hover()
	_update_skip_hover()
	if _perf:
		var fd := Engine.get_frames_drawn()
		if fd == 2:
			print("[perf] load->first frame: ", Time.get_ticks_msec() - _t0, " ms | nodes=",
					Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
					" draw=", Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		elif fd % 60 == 0 and fd > 0:
			print("[perf] frame ", fd, ": fps=", Performance.get_monitor(Performance.TIME_FPS),
					" process=", Performance.get_monitor(Performance.TIME_PROCESS),
					" nodes=", Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
					" draw=", Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
					" vmem=", Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED))
		if fd >= 480 or Time.get_ticks_msec() - _t0 > 30000:
			get_tree().quit()
	if _shot and Engine.get_frames_drawn() >= _shot_frame:
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://menu.png")
		print("saved: ", ProjectSettings.globalize_path("user://menu.png"))
		get_tree().quit()
