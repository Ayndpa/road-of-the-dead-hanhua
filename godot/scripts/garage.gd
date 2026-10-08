extends Node2D

## The garage "hub" between the story cinematic and a level, ported from
## RDGameModeGarage / MC_GarageScreen.
##
## Replays the original SWF garage screen (character id 4024) with the
## SwfMovieClip runtime and reimplements its interaction: hover an upgrade to
## see its info box and cost, click to spend RP, and press DRIVE / GO BACK to
## leave. RP and upgrade levels persist through the PlayerInfo autoload.
##
## Flow: GameIntro -> Garage -> Gameplay, and back to the garage on death.

const SWF_ROOT := "res://assets/swf"
const DESIGN := Vector2(600.0, 400.0)
const GARAGE_ID := 4024
# The driver's head clip idles on Flash frame 1 (our frame 0): RDGameModeGarage
# calls Head.gotoAndStop(1) at rest, which is the bare face without the eyelid
# overlay.  Frame 2+ (our 1+) adds the Blink label's eyelid shapes on top of
# the eyes, which reads as a half-lidded stare.
const HEAD_IDLE_FRAME := 0
const CATS := 8
const MAX_ITEM := 24  # RDUnlockItem.Max

const BAR_GROUPS: Array[String] = [
	"PerceptionBarGroup", "BodyArmorBarGroup", "FirearmBarGroup",
	"WindshieldBarGroup", "EngineBarGroup", "BumperBarGroup",
	"TiresBarGroup", "HornBarGroup",
]
const BUTTONS: Array[String] = [
	"PerceptionButton", "BodyArmorButton", "FirearmButton", "WindshieldButton",
	"EngineButton", "BumperButton", "TiresButton", "HornButton",
]
const NAMES: Array[String] = [
	"Perception", "Body Armor", "Firearm", "Windshield",
	"Engine", "Bumper", "Tires", "Horn",
]
const LEVEL_NAMES: Array[String] = [
	"Evans City", "Monroeville", "Red Ridge", "Burgony Street", "Central City",
	"Down Town", "Chinatown", "Brighton Square", "North Side Park",
	"West Ridge", "Tunnel Drive",
]

# upgrade feedback per category, indexed by the level being bought (0..2).
const UPGRADE_SFX: Array = [
	["SND_UpgradePerception"],
	["SND_UpgradeBodyArmor"],
	["SND_UpgradeFirearm", "SND_UpgradeFirearmBullet", "SND_UpgradeFirearmBullet"],
	["SND_UpgradeWindshield"],
	["SND_UpgradeEngine1", "SND_UpgradeEngine2", "SND_UpgradeEngine3"],
	["SND_UpgradeBumper1", "SND_UpgradeBumper2", "SND_UpgradeBumper3"],
	["SND_UpgradeTire"],
	["SND_UpgradeHorn1", "SND_UpgradeHorn2", "SND_UpgradeHorn3"],
]
const CHATTER: Array[String] = [
	"SND_GarageChatter01", "SND_GarageChatter02", "SND_GarageChatter03",
	"SND_GarageChatter04", "SND_GarageChatter05", "SND_GarageChatter06",
	"SND_GarageChatter07", "SND_GarageChatter08", "SND_GarageChatter09",
	"SND_GarageChatter10", "SND_GarageChatter11", "SND_GarageChatter12",
	"SND_GarageChatter13", "SND_GarageChatter14", "SND_GarageChatter15",
	"SND_GarageChatter16", "SND_GarageChatter17", "SND_GarageChatter18",
	"SND_GarageChatter19", "SND_GarageChatter20",
]
const MUSIC := "SND_Music_GarageMusic"
const FIRST_DIALOG := "SND_PlayerFirstTimeInGarage"
const BUS_MUSIC := "Music"
const BUS_SFX := "SFX"

var lib: SwfLibrary
var stage: Node2D
var garage: SwfMovieClip
var _head: SwfMovieClip

var _music: AudioStreamPlayer
var _sfx: AudioStreamPlayer
var _chatter: AudioStreamPlayer
var _dialog: AudioStreamPlayer

var _highlight: int = -2
var _forced_highlight: int = -99
var _talking: bool = false
var _blink_timer: float = 0.0
var _blink_delay: float = 5.0
var _chatter_timer: float = 0.0
var _chatter_delay: float = 8.0
var _hover_btn: Array[int] = []
var _over_ready: bool = false
var _over_back: bool = false
var _failed: bool = false

var _shot: bool = false
var _shot_frame: int = 60


func _ready() -> void:
	RenderingServer.set_default_clear_color(Color.BLACK)
	lib = SwfLibrary.new(SWF_ROOT)

	stage = Node2D.new()
	stage.name = "Stage"
	add_child(stage)

	garage = SwfMovieClip.create(GARAGE_ID, lib)
	garage.playing = false
	stage.add_child(garage)
	garage.seek(0)
	_freeze_tree(garage)
	# In Flash every nested MovieClip autoplays, so the protagonist breathes and
	# his cigarette smoke drifts while the garage is open; freezing the whole
	# screen to keep the UI still also killed those idle motions.  Restart just
	# the body, the smoke plume and the blowtorch flame - the face stays
	# script-driven for blinking/talking.
	_start_idle_clips()

	_hover_btn.resize(CATS)
	_hover_btn.fill(-1)

	_setup_audio()
	_bind()
	_fill_bars()
	_update_rp()
	_update_scene()
	_update_drive_to()
	_apply_highlight(-1)
	_play_music()
	_maybe_dialog()

	get_viewport().size_changed.connect(_apply_fit)
	_apply_fit()

	var uargs := OS.get_cmdline_user_args()
	_shot = uargs.has("--shot")
	var sf := uargs.find("--shot-frame")
	if sf >= 0 and sf + 1 < uargs.size():
		_shot_frame = int(uargs[sf + 1])
	var hi := uargs.find("--highlight")
	if hi >= 0 and hi + 1 < uargs.size():
		_forced_highlight = int(uargs[hi + 1])
		_apply_highlight(_forced_highlight, true)
	var bi := uargs.find("--buy")
	if bi >= 0 and bi + 1 < uargs.size():
		_try_buy(int(uargs[bi + 1]))


# --------------------------------------------------------------------------
# node lookup helpers
# --------------------------------------------------------------------------
func _find(node_name: String) -> Node:
	if garage == null or not is_instance_valid(garage):
		return null
	return garage.find_child(node_name, true, false)


func _clip(node_name: String) -> SwfMovieClip:
	return _find(node_name) as SwfMovieClip


func _label_of(root: Node, node_name: String) -> Label:
	if root == null:
		return null
	var n := root.find_child(node_name, true, false)
	if n == null:
		return null
	for c in n.get_children():
		if c is Label:
			return c
	return null


func _text_label(node_name: String) -> Label:
	var n := _find(node_name)
	if n == null:
		return null
	for c in n.get_children():
		if c is Label:
			return c
	return null


func _freeze_tree(n: Node) -> void:
	for c in n.get_children():
		if c is SwfMovieClip:
			var mc := c as SwfMovieClip
			mc.playing = false
			_freeze_tree(mc)


# Decorative timelines Flash kept running on the garage screen: the driver's
# body/breathing, the cigarette smoke plume and the blowtorch flame.  They are
# anonymous child clips, so they are reached by their SWF character ids.
const IDLE_SPRITE_IDS: Array[int] = [3952, 3951, 3921]


func _start_idle_clips() -> void:
	for cid in IDLE_SPRITE_IDS:
		var clip := _find_sprite_by_id(garage, cid)
		if clip != null:
			clip.playing = true


func _find_sprite_by_id(root: Node, cid: int) -> SwfMovieClip:
	if root is SwfMovieClip and int(root.get_meta("char_id", -1)) == cid:
		return root as SwfMovieClip
	for c in root.get_children():
		var found := _find_sprite_by_id(c, cid)
		if found != null:
			return found
	return null


func _bind() -> void:
	_head = _clip("Head")
	# Drop the "More games at Newgrounds" badge; the port has no web hub to send
	# players to.
	var newgrounds := _find("Newgrounds")
	if newgrounds != null:
		newgrounds.visible = false
		newgrounds.get_parent().remove_child(newgrounds)
		newgrounds.queue_free()


# --------------------------------------------------------------------------
# state -> screen
# --------------------------------------------------------------------------
func _item_for(category: int) -> int:
	if category < 0 or category >= CATS:
		return MAX_ITEM
	var lvl := PlayerInfo.level(category)
	if lvl >= 3:
		return MAX_ITEM
	return category * 3 + lvl


func _bar_of(category: int, bar_index: int) -> SwfMovieClip:
	var group := _find(BAR_GROUPS[category])
	if group == null:
		return null
	return group.find_child("Bar%d" % (bar_index + 1), true, false) as SwfMovieClip


func _fill_bars() -> void:
	for cat in CATS:
		var lvl := PlayerInfo.level(cat)
		for i in 3:
			var bar := _bar_of(cat, i)
			if bar != null:
				bar.seek(2 if lvl > i else 0)


func _update_rp() -> void:
	var lbl := _text_label("RP")
	if lbl != null:
		lbl.text = "%d RP" % PlayerInfo.rp


func _update_scene() -> void:
	var character := _find("Character")
	if character != null:
		_set_child_frame(character, "Chest", PlayerInfo.level(1))
		_set_child_frame(character, "Hand", PlayerInfo.level(2))
		_set_child_frame(character, "Belt", PlayerInfo.level(2))
	var car := _find("Car")
	if car != null:
		_set_child_frame(car, "Bumper", PlayerInfo.level(5))
		_set_child_frame(car, "Wheel", PlayerInfo.level(6))


func _set_child_frame(root: Node, node_name: String, frame: int) -> void:
	var mc := root.find_child(node_name, true, false) as SwfMovieClip
	if mc != null:
		mc.playing = false
		mc.seek(frame)


func _update_drive_to() -> void:
	var drive := _clip("DriveTo")
	if drive != null:
		drive.playing = false
		drive.seek(0)
	var lbl := _text_label("DriveToName")
	if lbl != null:
		var area := RotdStory.area_index(PlayerInfo.story_level)
		lbl.text = RotdStory.LEVEL_NAMES_ZH[area]
		lbl.add_theme_color_override("font_color", Color8(204, 204, 204))


func _apply_highlight(category: int, force: bool = false) -> void:
	if category == _highlight and not force:
		return
	# reset the previously highlighted bar to its "off" frame
	if _highlight >= 0 and _highlight < CATS:
		var prev_item := _item_for(_highlight)
		if prev_item < MAX_ITEM:
			var prev_bar := _bar_of(_highlight, prev_item % 3)
			if prev_bar != null:
				prev_bar.seek(0)
	_highlight = category

	var info := _find("InfoBox")
	if category < 0:
		if info != null:
			info.visible = false
		return
	var item := _item_for(category)
	if item >= MAX_ITEM:
		if info != null:
			info.visible = false
		return
	if info == null:
		return
	var lvl := item % 3
	info.visible = true
	var bar := _bar_of(category, lvl)
	if bar != null:
		bar.seek(1)  # highlight frame
	var panels := info.find_child("Panels", true, false) as SwfMovieClip
	if panels != null:
		panels.playing = false
		panels.seek(item)
	var name_lbl := _label_of(info, "Name")
	if name_lbl != null:
		name_lbl.text = NAMES[category]
	var cost_lbl := _label_of(info, "Cost")
	if cost_lbl != null:
		cost_lbl.text = "%d RP" % PlayerInfo.next_cost(category)
	var cost_label := info.find_child("CostLabel", true, false)
	if cost_label != null:
		cost_label.visible = true


func _set_drive_to_hover(on: bool) -> void:
	if _over_ready == on:
		return
	_over_ready = on
	var drive := _clip("DriveTo")
	if drive != null:
		drive.seek(1 if on else 0)
	var lbl := _text_label("DriveToName")
	if lbl != null:
		lbl.add_theme_color_override("font_color", Color.WHITE if on else Color8(204, 204, 204))


# --------------------------------------------------------------------------
# interaction
# --------------------------------------------------------------------------
func _process(delta: float) -> void:
	_update_hover()
	_update_face(delta)
	_update_chatter(delta)
	if _shot and Engine.get_frames_drawn() >= _shot_frame:
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://garage.png")
		print("saved: ", ProjectSettings.globalize_path("user://garage.png"))
		get_tree().quit()


func _update_hover() -> void:
	var mpos := get_viewport().get_mouse_position()
	var found := -1
	if _forced_highlight >= 0:
		found = _forced_highlight
	for cat in CATS:
		var rect := _subtree_rect(_find(BUTTONS[cat]))
		var over := rect.size.x > 0.0 and rect.has_point(mpos)
		if over:
			found = cat
		var want := 1 if over else 0
		if _hover_btn[cat] != want:
			_hover_btn[cat] = want
			var btn := _clip(BUTTONS[cat])
			if btn != null:
				btn.seek(want)

	_apply_highlight(found)
	_set_drive_to_hover(found < 0 and _rect_has(_find("ReadyButton"), mpos))

	var back_over := _rect_has(_find("GoBackButton"), mpos)
	if back_over != _over_back:
		_over_back = back_over
		var back := _clip("GoBackButton")
		if back != null:
			back.seek(1 if back_over else 0)

	Input.set_default_cursor_shape(
		Input.CURSOR_POINTING_HAND if (found >= 0 or _over_ready or back_over) else Input.CURSOR_ARROW
	)


func _rect_has(node: Node, point: Vector2) -> bool:
	var rect := _subtree_rect(node)
	return rect.size.x > 0.0 and rect.has_point(point)


func _subtree_rect(node: Node) -> Rect2:
	var rect := Rect2()
	if node == null:
		return rect
	var first := true
	var stack: Array[Node] = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Sprite2D and (n as Sprite2D).visible:
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
		elif n is SwfVectorShape and (n as SwfVectorShape).visible:
			var lr := (n as SwfVectorShape).local_rect
			if lr.size != Vector2.ZERO:
				for corner in [lr.position, Vector2(lr.end.x, lr.position.y), Vector2(lr.position.x, lr.end.y), lr.end]:
					var p: Vector2 = (n as CanvasItem).get_global_transform() * corner
					if first:
						rect = Rect2(p, Vector2.ZERO)
						first = false
					else:
						rect = rect.expand(p)
		for c in n.get_children():
			stack.append(c)
	return rect


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_ESCAPE:
				_go_back()
			KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
				if _highlight >= 0:
					_try_buy(_highlight)
				else:
					_start_game()
		return
	var pos := Vector2.INF
	if event is InputEventMouseButton and event.pressed:
		pos = (event as InputEventMouseButton).position
	elif event is InputEventScreenTouch and event.pressed:
		pos = (event as InputEventScreenTouch).position
	if pos == Vector2.INF:
		return
	for cat in CATS:
		if _rect_has(_find(BUTTONS[cat]), pos):
			_try_buy(cat)
			return
	if _rect_has(_find("ReadyButton"), pos):
		_start_game()
	elif _rect_has(_find("GoBackButton"), pos):
		_go_back()


func _try_buy(category: int) -> void:
	var lvl := PlayerInfo.level(category)
	if lvl >= 3:
		return
	var cost := PlayerInfo.next_cost(category)
	if PlayerInfo.rp < cost:
		_play_sfx("SND_ErrorSound")
		return
	var sound_name := String(UPGRADE_SFX[category][lvl])
	PlayerInfo.buy_upgrade(category)
	_play_sfx(sound_name)
	_update_rp()
	_fill_bars()
	_update_scene()
	_apply_highlight(category, true)
	if category == 3:
		var base := _find("Car")
		if base != null:
			var b := base.find_child("Base", true, false) as SwfMovieClip
			if b != null:
				b.playing = true


func _start_game() -> void:
	if _failed:
		return
	_failed = true
	PlayerInfo.save_info()
	_music.stop()
	_chatter.stop()
	_dialog.stop()
	get_tree().change_scene_to_file("res://scenes/gameplay.tscn")


func _go_back() -> void:
	if _failed:
		return
	_failed = true
	PlayerInfo.save_info()
	PlayerInfo.start_at_menu = true
	_music.stop()
	_chatter.stop()
	_dialog.stop()
	get_tree().change_scene_to_file("res://scenes/main.tscn")


# --------------------------------------------------------------------------
# face animation + garage chatter
# --------------------------------------------------------------------------
func _update_face(delta: float) -> void:
	if _head == null or not is_instance_valid(_head):
		return
	if _talking:
		if _dialog.playing:
			return
		_talking = false
		_head.playing = false
		_head.seek(HEAD_IDLE_FRAME)
		_blink_timer = 0.0
		_blink_delay = 1.0 + randf() * 5.0
		return
	if not _head.playing and _head.frame_index != HEAD_IDLE_FRAME:
		_head.seek(HEAD_IDLE_FRAME)
	_blink_timer += delta
	if _blink_timer >= _blink_delay:
		_blink_timer = 0.0
		_blink_delay = 1.0 + randf() * 5.0
		_head.play_label("Blink", false)


func _update_chatter(delta: float) -> void:
	if _chatter.playing or CHATTER.is_empty():
		return
	_chatter_timer += delta
	if _chatter_timer < _chatter_delay:
		return
	_chatter_timer = 0.0
	_chatter_delay = 5.0 + randf() * 10.0
	var res := lib.get_sound_res(CHATTER[randi() % CHATTER.size()])
	if res != "" and FileAccess.file_exists(res):
		_chatter.stream = load(res)
		_chatter.play()


func _maybe_dialog() -> void:
	if _dialog == null:
		return
	var name := FIRST_DIALOG if not PlayerInfo.been_in_garage else ""
	if name == "":
		return
	var res := lib.get_sound_res(name)
	if res == "" or not FileAccess.file_exists(res):
		return
	_dialog.stream = load(res)
	_dialog.volume_db = linear_to_db(1.5)
	_dialog.play()
	_talking = true
	if _head != null:
		_head.play_label("Talking", true)
	if not PlayerInfo.been_in_garage:
		PlayerInfo.been_in_garage = true
		PlayerInfo.save_info()


# --------------------------------------------------------------------------
# audio + layout
# --------------------------------------------------------------------------
func _setup_audio() -> void:
	for bus_name in [BUS_MUSIC, BUS_SFX]:
		if AudioServer.get_bus_index(bus_name) < 0:
			AudioServer.add_bus()
			AudioServer.set_bus_name(AudioServer.bus_count - 1, bus_name)
	_music = AudioStreamPlayer.new()
	_music.bus = BUS_MUSIC
	add_child(_music)
	_sfx = AudioStreamPlayer.new()
	_sfx.bus = BUS_SFX
	add_child(_sfx)
	_chatter = AudioStreamPlayer.new()
	_chatter.bus = BUS_SFX
	_chatter.volume_db = linear_to_db(0.35)
	add_child(_chatter)
	_dialog = AudioStreamPlayer.new()
	_dialog.bus = BUS_SFX
	add_child(_dialog)


func _play_music() -> void:
	var res := lib.get_sound_res(MUSIC)
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


func _play_sfx(name: String) -> void:
	var res := lib.get_sound_res(name)
	if res == "" or not FileAccess.file_exists(res):
		return
	_sfx.stream = load(res)
	_sfx.play()


func _apply_fit() -> void:
	if stage == null:
		return
	var vp := get_viewport_rect().size
	if vp.x <= 0.0 or vp.y <= 0.0:
		return
	var s := minf(vp.x / DESIGN.x, vp.y / DESIGN.y)
	stage.scale = Vector2(s, s)
	stage.position = vp * 0.5 - DESIGN * 0.5 * s
