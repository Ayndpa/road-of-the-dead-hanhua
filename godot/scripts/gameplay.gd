extends Node2D

## Story-mode level runner, ported from RDGameModeStory / RDGameModeGameplay.
##
## Flow: garage "DRIVE TO <area>" -> this scene starts at PlayerInfo.story_level
## (a 0..21 segment index), spawns the original pattern hats per segment with
## the original lengths, hazard limits and spacing, saves at every checkpoint
## (even segments), plays the pre/post checkpoint radio lines and the area
## message box, and on death shows the exact Road Points breakdown before
## returning to the garage. Reaching the tunnel ends the campaign.
##
## The road/camera/cockpit come from the existing pseudo-3D port; obstacles,
## cars, zombies and civilians are Rotd* entities spawned from patterns.json.

const SWF_ROOT := "res://assets/swf"
const DESIGN := Vector2(600.0, 400.0)
const DT := 1.0 / 30.0

# RDPlayer physics
const MAX_SPEEDS := [110.0, 115.0, 120.0, 125.0]
const ACCEL_TIMES := [0.0, 3.27, 6.1, 11.6, 24.0]
const SPEED_RATIOS := [
	[0.0, 0.40, 0.70, 0.90, 1.0],
	[0.0, 0.46, 0.74, 0.92, 1.0],
	[0.0, 0.52, 0.78, 0.94, 1.0],
	[0.0, 0.58, 0.82, 0.96, 1.0],
]
const X_MAX := 4.0
const X_ACC := 15.0
const X_HB_MAX := 8.0
const X_HB_ACC := 30.0
const LEFT_LIMIT := -9.4
const RIGHT_LIMIT := 9.1
const MIN_CLING_SPEED := 1.0 * 1000.0 / 3600.0
const MAX_CLING_SPEED := 100.0 * 1000.0 / 3600.0
const MIN_GIB_SPEED := 100.0 * 1000.0 / 3600.0
const HARD_COLLISION_SPEED := 60.0 * 1000.0 / 3600.0
const MEDIUM_COLLISION_SPEED := 30.0 * 1000.0 / 3600.0

# scoring (RDGameModeGameplay)
const POINTS_PER_KM := 50
const POINTS_PER_ZOMBIE := 5
const POINTS_PER_SOLDIER := 5
const POINTS_PER_HOOD_COLLISION := 15
const POINTS_PER_HOOD_PISTOL := 40
const POINTS_PER_CHOPPER := 100
const BONUS_PER_PRECISION := 0.01
const PENALTY_PER_CIVILIAN := 0.05
const COMBO_DELAY := 2.0
const COMBO_POINTS := 2

# obstacle response (RDObstacleCar / RDObstacle)
const CAR_HIT_DAMAGE := 20.0
const CAR_HIT_SPEED_LOSS := 0.3
const SHOPPING_CART_HIT_DAMAGE := 4.0
const CAR_AMBIENT_DISTANCE := 100.0

# MC_PlayerCar cockpit depths (see the SWF sprite 2974)
const D_SHARDS := 1
const D_SMOKE := 11
const D_FIRE := 19
const D_SPARK_L := 21
const D_SPARK_R := 23
const D_BUMPER := 25
const D_CLING_HARD := 63
const D_CLING_MALE := 95
const D_CLING_FEMALE := 127
const D_CLING_VERYHARD := 163
const D_CLING_SOLDIER := 195
# the matching MC_PlayerCar "inside" clips; RDPlayer.StartCling shows both the
# outside and inside clinger, and both start hidden in Flash
const D_CLING_HARD_IN := 461
const D_CLING_MALE_IN := 485
const D_CLING_FEMALE_IN := 509
const D_CLING_VERYHARD_IN := 539
const D_WINDSHIELD := 233
const D_WS_BLOOD := 252
const D_GIB := 288
const D_DASH_BLOOD := 403

# RDPlayer / RDHumanoid collision tuning
const BUMPER_BROKEN3_MIN_HP := 36.0
const BUMPER_SMOKE_MIN_HP := 20.0
const BUMPER_DAMAGE_CUTOFFS := [0.0, 2.0, 5.0, 8.0]
const BUMPER_DAMAGE_ABSORB := [0.0, 0.2, 0.4, 0.6]
const BUMPER_SPEED_LOSS := [1.0, 0.85, 0.7, 0.55]
const HUMAN_HIT_DAMAGE := 2.0
const HUMAN_HIT_SPEED_LOSS := 0.25
const DEAD_CENTER_RANGE := 0.1
const CENTER_RANGE := 0.3
const FRONT_SIDE_RANGE := 0.6
const BUMP_MAX_SPEED := 60.0
const BUMP_DECCEL := 4.0
const HARD_SIDE_DAMAGE := 20.0
const HARD_WINDSHIELD_DAMAGE := 7.0
const OIL_DURATIONS := [4.0, 3.5, 3.0, 2.5]
const OIL_CONTROL_FACTOR := [0.25, 0.3, 0.35, 0.4]
const TIRE_SPIKE_DAMAGE := [4.0, 2.0, 1.0, 0.5]
const BLOWN_TIRE_CONTROL := [1.0, 0.7, 0.5, 0.35]

const RP_PER_KM := POINTS_PER_KM

var lib: SwfLibrary
var cam: RotdCamera
var stage: Node2D
var road: RotdRoad
var cockpit: SwfMovieClip

var patterns := {}
var _bags := {}
var _rng := RandomNumberGenerator.new()

# story state
var segment := 0
var spawn_segment := 0
var level_start_z := 0.0
var level_length := 0.0
var next_level_start := 0.0
var spawn_start_z := 0.0
var next_spawn_start := 0.0
var next_pattern_z := 0.0
var next_hard_z := 0.0
var difficulty := 0.0
var pre_dialog_pending := false
var post_dialog_pending := false
var campaign_done := false
var hardcore := false

# player state
var player_x := 0.0
var player_z := 0.0
var vel_z := 0.0
var vel_x := 0.0
var desired_speed_x := 0.0
var engine_time := 0.0
var windshield_hp := 100.0
var body_hp := 100.0
var bumper_hp := 100.0
var bumper_level := 0
var bumper_stage := 0
var bump_vel := 0.0
var oil_time := 0.0
var oil_duration := 0.0
var oil_factor := 1.0
var tire_damage := 0.0
var blown_tires := 0

# camera shake: each entry {i:intensity, fi, d, fo, t}
var shakes: Array = []
var shake_intensity := 0.0
var parallax: Array[RotdParallax] = []
var clinger: RotdZombie = null
var clinger_timer := 0.0
var player_start_z := 0.0

# upgrades
var up_engine := 0
var up_tires := 0
var up_armor := 0
var up_windshield := 0
var up_bumper := 0
var max_speed := 110.0
var x_max := X_MAX
var x_hb_max := X_HB_MAX
var x_acc := X_ACC
var x_hb_acc := X_HB_ACC

# scoring counters
var kills := 0
var soldiers_killed := 0
var civilians_killed := 0
var choppers_defeated := 0
var precision_hits := 0
var hood_collision_kills := 0
var hood_pistol_kills := 0
var combo_points := 0
var combo_count := 0
var combo_time := -9999.0
var game_time := 0.0

# entities
var zombies: Array[RotdZombie] = []
var civilians: Array[RotdCivilian] = []
var obstacles: Array[RotdObstacle] = []
var scenery: Array[RotdScenery] = []

# scenery spawn cursors
var next_yellow_z := 0.0
var next_building_z := 0.0
var next_sign_z := 0.0

# failure / stats
var failed := false
var showing_stats := false
var stats_ready := false
var stats_timer := 0.0
var reached_distance := 0.0
var _leaving := false

# hud / audio
var message_clip: SwfMovieClip
var stats_clip: SwfMovieClip
var hud_clip: SwfMovieClip
var message_timer := 0.0
var _music: AudioStreamPlayer
var _sfx_pool: Array[AudioStreamPlayer] = []
var _voice: AudioStreamPlayer
var _chatter: AudioStreamPlayer
var _engine: AudioStreamPlayer
var _horn: AudioStreamPlayer
var _engine_state := ""
var accel_held := false
var brake_held := false

var _shot := false
var _shot_frame := 120
var _shot_series := 0
var _shot_series_done := 0
var _shot_series_mark := -1000000
var _shot_dir := "user://seq"
var _noclinger := false
var _audit := false
var _frames := 0
var _auto := false
var _scenery_on := true
var _debug := false
var _invincible := false


func _ready() -> void:
	RenderingServer.set_default_clear_color(Color(0.60, 0.64, 0.68))
	Engine.physics_ticks_per_second = 30
	lib = SwfLibrary.new(SWF_ROOT)
	cam = RotdCamera.new(DESIGN.x * 0.5, DESIGN.y * 0.5)
	_rng.randomize()
	_load_patterns()
	_apply_upgrades()

	segment = clampi(PlayerInfo.story_level, 0, RotdStory.LEVEL_LENGTHS.size() - 1)
	spawn_segment = segment
	level_start_z = RotdStory.level_start(segment)
	level_length = float(RotdStory.LEVEL_LENGTHS[segment])
	next_level_start = level_start_z + level_length
	spawn_start_z = level_start_z
	next_spawn_start = spawn_start_z + float(RotdStory.LEVEL_LENGTHS[spawn_segment])
	player_z = level_start_z
	player_start_z = player_z
	difficulty = minf(player_z / RotdStory.total_length(), 1.0)
	next_pattern_z = player_z + RotdStory.PATTERN_INITIAL_SPAWN_DISTANCE
	next_hard_z = player_z + RotdStory.PATTERN_VIEW_DISTANCE + RotdStory.HARD_PATTERN_SPACING_MIN \
		+ _rng.randf() * RotdStory.HARD_PATTERN_SPACING_RANDOM
	next_yellow_z = player_z
	next_building_z = player_z
	next_sign_z = player_z + RotdStory.ROAD_SIGN_INITIAL_SPAWN_DISTANCE
	pre_dialog_pending = segment < RotdStory.NUKE_LEVEL
	post_dialog_pending = true

	stage = Node2D.new()
	stage.name = "Stage"
	add_child(stage)

	_setup_parallax()

	road = RotdRoad.new()
	road.cam = cam
	road.z_index = 0
	stage.add_child(road)

	cockpit = SwfMovieClip.create(2974, lib)
	cockpit.z_index = 500
	stage.add_child(cockpit)
	cockpit.playing = false
	_init_cockpit_effects()
	if OS.get_cmdline_user_args().has("--nocockpit"):
		cockpit.visible = false

	var layer := CanvasLayer.new()
	layer.name = "Ui"
	add_child(layer)

	# original HUD clip: ScoreTable holds the stats rows, Bloods the overlays
	hud_clip = SwfMovieClip.create(3375, lib)
	hud_clip.playing = false
	hud_clip.position = Vector2(0, 0)
	layer.add_child(hud_clip)
	_hide_hud_defaults()

	message_clip = SwfMovieClip.create(1780, lib)
	message_clip.playing = false
	message_clip.visible = false
	layer.add_child(message_clip)

	stats_clip = SwfMovieClip.create(1804, lib)
	stats_clip.playing = false
	stats_clip.visible = false
	layer.add_child(stats_clip)

	_setup_audio()
	_spawn_fillers()
	_show_message(RotdStory.LEVEL_NAMES_ZH[RotdStory.area_index(segment)])

	var uargs := OS.get_cmdline_user_args()
	_auto = uargs.has("--auto")
	_scenery_on = not uargs.has("--noscenery")
	_debug = uargs.has("--debug")
	_invincible = uargs.has("--invincible")
	_shot = uargs.has("--shot")
	var sf := uargs.find("--shot-frame")
	if sf >= 0 and sf + 1 < uargs.size():
		_shot_frame = int(uargs[sf + 1])
	var ss := uargs.find("--shot-series")
	if ss >= 0 and ss + 1 < uargs.size():
		_shot_series = int(uargs[ss + 1])
	var sd := uargs.find("--shot-dir")
	if sd >= 0 and sd + 1 < uargs.size():
		_shot_dir = uargs[sd + 1]
	_noclinger = uargs.has("--noclinger")
	_audit = uargs.has("--audit")
	var seg := uargs.find("--segment")
	if seg >= 0 and seg + 1 < uargs.size():
		_jump_to_segment(int(uargs[seg + 1]))

	get_viewport().size_changed.connect(_apply_fit)
	_apply_fit()


func _apply_upgrades() -> void:
	up_engine = PlayerInfo.level(4)
	up_tires = PlayerInfo.level(6)
	up_armor = PlayerInfo.level(1)
	up_windshield = PlayerInfo.level(3)
	up_bumper = PlayerInfo.level(5)
	max_speed = MAX_SPEEDS[clampi(up_engine, 0, 3)] * 1000.0 / 3600.0
	x_max = X_MAX * (1.0 + 0.08 * up_tires)
	x_hb_max = X_HB_MAX * (1.0 + 0.08 * up_tires)
	x_acc = X_ACC * (1.0 + 0.10 * up_tires)
	x_hb_acc = X_HB_ACC * (1.0 + 0.10 * up_tires)
	windshield_hp = 100.0
	bumper_level = up_bumper
	bumper_hp = 100.0
	bumper_stage = 0
	blown_tires = 0
	tire_damage = 0.0


func _jump_to_segment(seg_index: int) -> void:
	segment = clampi(seg_index, 0, RotdStory.LEVEL_LENGTHS.size() - 1)
	spawn_segment = segment
	level_start_z = RotdStory.level_start(segment)
	level_length = float(RotdStory.LEVEL_LENGTHS[segment])
	next_level_start = level_start_z + level_length
	spawn_start_z = level_start_z
	next_spawn_start = spawn_start_z + float(RotdStory.LEVEL_LENGTHS[spawn_segment])
	player_z = level_start_z
	player_start_z = player_z
	next_pattern_z = player_z + RotdStory.PATTERN_INITIAL_SPAWN_DISTANCE
	next_hard_z = player_z + RotdStory.PATTERN_VIEW_DISTANCE + RotdStory.HARD_PATTERN_SPACING_MIN
	next_yellow_z = player_z
	next_building_z = player_z
	next_sign_z = player_z + RotdStory.ROAD_SIGN_INITIAL_SPAWN_DISTANCE
	pre_dialog_pending = segment < RotdStory.NUKE_LEVEL
	post_dialog_pending = true
	_show_message(RotdStory.LEVEL_NAMES[RotdStory.area_index(segment)])


func _init_cockpit_effects() -> void:
	# The SWF export carries no initial visibility, so every clip that Flash
	# authored as hidden has to be hidden here.  Missing the *Inside clingers
	# drew one across the whole windshield.
	for d in [D_SHARDS, D_SPARK_L, D_SPARK_R, D_GIB, D_WS_BLOOD, D_DASH_BLOOD,
			D_CLING_HARD, D_CLING_MALE, D_CLING_FEMALE, D_CLING_VERYHARD, D_CLING_SOLDIER,
			D_CLING_HARD_IN, D_CLING_MALE_IN, D_CLING_FEMALE_IN, D_CLING_VERYHARD_IN]:
		cockpit.set_depth_visible(d, false)
	cockpit.set_depth_visible(D_SMOKE, false)
	cockpit.set_depth_visible(D_FIRE, false)
	_update_cockpit()


func _update_cockpit() -> void:
	if cockpit == null or not is_instance_valid(cockpit):
		return
	var frame_level := 3 if bumper_level == 0 else bumper_level - 1
	var stage := bumper_stage
	if bumper_level == 0:
		if bumper_hp >= 84.0:
			stage = 0
		elif bumper_hp >= 68.0:
			stage = 1
		elif bumper_hp >= 52.0:
			stage = 2
		elif bumper_hp >= BUMPER_BROKEN3_MIN_HP:
			stage = 3
		elif bumper_hp >= BUMPER_SMOKE_MIN_HP:
			stage = 4
		elif bumper_hp > 0.0:
			stage = 5
	else:
		if bumper_hp >= 66.0:
			stage = 0
		elif bumper_hp >= 33.0:
			stage = 1
		elif bumper_hp > 0.0:
			stage = 2
	bumper_stage = stage
	cockpit.set_depth_frame(D_BUMPER, 2 + frame_level * 3 + stage - 1)
	cockpit.set_depth_visible(D_SMOKE, bumper_level == 0 and stage >= 4)
	cockpit.set_depth_visible(D_FIRE, bumper_level == 0 and stage >= 5)
	# windshield crack level
	var ws_frame := 0
	if windshield_hp == 100.0:
		ws_frame = 0
	elif windshield_hp > 80.0:
		ws_frame = 1
	elif windshield_hp > 55.0:
		ws_frame = 2
	elif windshield_hp > 27.0:
		ws_frame = 3
	elif windshield_hp > 0.0:
		ws_frame = 4
	else:
		ws_frame = 4
	cockpit.set_depth_frame(D_WINDSHIELD, ws_frame)


func _setup_parallax() -> void:
	var total := RotdStory.total_length()
	var defs := [
		[3506, RotdParallax.Mode.DISTANCE, 2000.0, 0.0, 0.0, 0.0, -420],
		[3738, RotdParallax.Mode.RISING, 1300.0, total, 130.0, 0.0, -380],
		[3733, RotdParallax.Mode.SPLITTING, 500.0, total, 200.0, 13.0, -340],
		[3723, RotdParallax.Mode.SPLITTING, 310.0, total * 0.5, 300.0, 20.0, -300],
	]
	for d in defs:
		var p := RotdParallax.new()
		p.setup(lib, int(d[0]), d[1], float(d[2]), float(d[3]), float(d[4]), float(d[5]))
		p.z_index = int(d[6])
		stage.add_child(p)
		parallax.append(p)


func _update_parallax() -> void:
	for p in parallax:
		if is_instance_valid(p):
			p.render(cam)


# --------------------------------------------------------------------------
# camera shake (RDCamera.AddShake / StopShake, simplified)
# --------------------------------------------------------------------------
func _add_shake(name: String, intensity: float, fade_in: float, duration: float, fade_out: float) -> void:
	shakes.append({"n": name, "i": intensity, "fi": fade_in, "d": duration, "fo": fade_out, "t": 0.0})


func _stop_shake(name: String, fade_out: float) -> void:
	for s in shakes:
		if String(s["n"]) == name:
			s["d"] = 0.0
			s["fi"] = 0.0
			s["fo"] = fade_out
			s["t"] = 0.0


func _update_shake(dt: float) -> void:
	var max_i := 0.0
	var i := 0
	while i < shakes.size():
		var s: Dictionary = shakes[i]
		var intensity := 0.0
		if float(s["d"]) == -1.0:
			intensity = float(s["i"])
		elif float(s["t"]) < float(s["fi"]) + float(s["d"]) + float(s["fo"]):
			if float(s["t"]) < float(s["fi"]):
				intensity = float(s["t"]) / maxf(float(s["fi"]), 0.001) * float(s["i"])
			elif float(s["t"]) > float(s["fi"]) + float(s["d"]):
				intensity = (1.0 - (float(s["t"]) - float(s["d"]) - float(s["fi"])) / maxf(float(s["fo"]), 0.001)) * float(s["i"])
			else:
				intensity = float(s["i"])
			s["t"] = float(s["t"]) + dt
		else:
			shakes.remove_at(i)
			continue
		max_i = maxf(max_i, intensity)
		i += 1
	if max_i > 0.0:
		shake_intensity = max_i
	else:
		shake_intensity = 0.0


# Debug only: --shot-series N grabs one viewport screenshot per wall-clock second
# (N of them) into --shot-dir, so a contact sheet shows what the scene is doing
# over time (e.g. which vehicle timelines keep cycling).
func _process(_delta: float) -> void:
	if _shot_series <= 0:
		return
	var now := Time.get_ticks_msec()
	if _shot_series_mark < 0:
		_shot_series_mark = now
		return
	if now - _shot_series_mark < 1000:
		return
	_shot_series_mark = now
	var img := get_viewport().get_texture().get_image()
	var out := "%s/t%03d.png" % [_shot_dir, _shot_series_done]
	DirAccess.make_dir_recursive_absolute(_shot_dir)
	img.save_png(out)
	print("seq shot ", _shot_series_done, " t=%.1fs z=%d -> %s" % [
		float(_shot_series_done), int(player_z),
		ProjectSettings.globalize_path(out)])
	if _audit:
		print("AUDIT ", _audit_line())
		print("NEAR ", _nearest_car_line())
	_shot_series_done += 1
	if _shot_series_done >= _shot_series:
		get_tree().quit()


# Debug only: list every vehicle obstacle whose clip subtree still has a playing
# timeline.  RDObstacleCar does gotoAndStop(iMCFrame), so a parked wreck must
# never animate; anything reported here is a runaway nested clip.
func _audit_line() -> String:
	var parts: Array[String] = []
	for o in obstacles:
		if not is_instance_valid(o) or not o.is_car or o.clip == null:
			continue
		var live := _playing_clips(o.clip)
		if live.is_empty():
			continue
		parts.append("c%d/f%d@z%d[%d live: %s]" % [o.char_id, o.car_frame, int(o.world_z),
			live.size(), ",".join(live)])
	return ("cars=%d obstacles=%d | %s" % [obstacles.size(), obstacles.size(),
		"  ".join(parts)]).strip_edges()


# Debug only: the nearest vehicle ahead, with the screen rect its art occupies,
# so a capture can be matched against what RDEntity.Render should produce.
func _nearest_car_line() -> String:
	var best: RotdObstacle = null
	var best_fz := INF
	for o in obstacles:
		if not is_instance_valid(o) or not o.is_car or o.clip == null:
			continue
		var fz := o.world_z - cam.z
		if fz > 1.0 and fz < best_fz:
			best_fz = fz
			best = o
	if best == null:
		return "NEAREST none"
	var s := cam.sprite_scale(best.world_scale, best_fz)
	var base := cam.project(Vector3(best.world_x, best.world_y, best.world_z))
	var rect := best.art_rect()
	return "NEAREST char=%d f=%d fz=%.1f scale=%.4f hitbox=%.2f base=%s art=%s screen=%s" % [
		best.char_id, best.car_frame, best_fz, s, best.col_w, str(base), str(rect),
		str(Rect2(base + rect.position * s, rect.size * s))]


func _playing_clips(root: Node) -> Array[String]:
	var out: Array[String] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is SwfMovieClip:
			var mc := n as SwfMovieClip
			if mc.playing and mc.frame_count() > 1:
				out.append("%s@%d" % [mc.name, mc.frame_index])
		for c in n.get_children():
			stack.append(c)
	return out


# --------------------------------------------------------------------------
# main update
# --------------------------------------------------------------------------
func _physics_process(delta: float) -> void:
	game_time += DT
	_update_player(DT)
	_update_shake(DT)
	_update_camera()
	_update_parallax()
	_update_cockpit()
	_update_scenery()
	_update_scenery_nodes()
	if message_timer > 0.0:
		message_timer -= DT
		if message_timer <= 0.0:
			message_clip.visible = false
	if not failed and not campaign_done:
		_update_story(DT)
		_update_spawns()
	_update_zombies(DT)
	_update_civilians(DT)
	_update_obstacles(DT)
	_update_effects(DT)
	_update_engine_sound()
	_update_hud()
	road.queue_redraw()
	_frames += 1
	if _debug and _frames % 300 == 0:
		print("[debug] t=", _frames, " z=", int(player_z), " seg=", segment,
			" spawn_seg=", spawn_segment, " zombies=", zombies.size(), " civ=", civilians.size(),
			" obs=", obstacles.size(), " scenery=", scenery.size(), " kills=", kills,
			" body=", int(body_hp), " shield=", int(windshield_hp), " failed=", failed,
			" stats=", showing_stats)
	if showing_stats:
		_update_stats(DT)
	if _shot and Engine.get_frames_drawn() >= _shot_frame:
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://play.png")
		print("saved: ", ProjectSettings.globalize_path("user://play.png"))
		get_tree().quit()


func _update_player(dt: float) -> void:
	if failed:
		vel_z = maxf(vel_z - 40.0 * dt, 0.0)
		player_z += vel_z * dt
		return
	var accel := _auto or PlayerInfo.is_action_pressed("accel") or Input.is_key_pressed(KEY_UP)
	var brake := PlayerInfo.is_action_pressed("brake") or Input.is_key_pressed(KEY_DOWN)
	var handbrake := PlayerInfo.is_action_pressed("handbrake")
	accel_held = accel and not handbrake
	brake_held = brake
	_play_horn(PlayerInfo.is_action_pressed("horn"))
	var steer := 0
	if PlayerInfo.is_action_pressed("left") or Input.is_key_pressed(KEY_LEFT):
		steer -= 1
	if PlayerInfo.is_action_pressed("right") or Input.is_key_pressed(KEY_RIGHT):
		steer += 1

	if handbrake and vel_z > 0.0:
		engine_time = maxf(engine_time - dt * 6.0, 0.0)
	elif accel:
		engine_time = minf(engine_time + dt, 24.0)
	elif brake and vel_z > 0.0:
		engine_time = maxf(engine_time - dt * 8.0, 0.0)
	elif vel_z > 0.0:
		engine_time = maxf(engine_time - dt * 0.8, 0.0)

	vel_z = _speed_ratio(engine_time) * max_speed

	var tire_control := 1.0
	if blown_tires > 0:
		tire_control = float(BLOWN_TIRE_CONTROL[clampi(blown_tires - 1, 0, 3)])
	if oil_time > 0.0:
		oil_time = maxf(oil_time - dt, 0.0)
		oil_factor = 1.0 - pow(1.0 - oil_time / maxf(oil_duration, 0.001), 2.0)
	var steer_eff := float(steer)
	if oil_time > 0.0:
		steer_eff = steer * float(OIL_CONTROL_FACTOR[clampi(up_tires, 0, 3)])
		vel_x += signf(_rng.randf() - 0.5) * oil_factor * 6.0 * dt

	var r := minf(vel_z / (max_speed * 0.75), 1.0)
	r = 1.0 - pow(1.0 - r, 3.0)
	var xmax := r * (x_hb_max if handbrake else x_max) * tire_control
	var xacc := x_hb_acc if handbrake else x_acc

	vel_x = _integrate_lateral(vel_x, steer_eff, xacc, xmax, dt)
	desired_speed_x = vel_x

	player_x += (vel_x + bump_vel) * dt
	bump_vel = move_toward(bump_vel, 0.0, BUMP_DECCEL * dt)
	player_x = clampf(player_x, LEFT_LIMIT, RIGHT_LIMIT)
	player_z += vel_z * dt
	_update_speedometer()


func _integrate_lateral(v: float, steer: int, acc: float, vmax: float, dt: float) -> float:
	if steer < 0:
		if v > -vmax:
			return maxf(v - acc * dt, -vmax)
		return minf(v + acc * dt, -vmax)
	elif steer > 0:
		if v < vmax:
			return minf(v + acc * dt, vmax)
		return maxf(v - acc * dt, vmax)
	return move_toward(v, 0.0, acc * dt)


func _speed_ratio(et: float) -> float:
	var ratios: Array = SPEED_RATIOS[clampi(up_engine, 0, 3)]
	for i in ACCEL_TIMES.size() - 1:
		if et <= float(ACCEL_TIMES[i + 1]):
			var span: float = float(ACCEL_TIMES[i + 1]) - float(ACCEL_TIMES[i])
			var t: float = 0.0 if span <= 0.0 else (et - float(ACCEL_TIMES[i])) / span
			return lerpf(float(ratios[i]), float(ratios[i + 1]), t)
	return 1.0


func _update_speedometer() -> void:
	if cockpit == null or not is_instance_valid(cockpit):
		return
	var vis := clampf(vel_z / max_speed, 0.0, 1.0)
	cockpit.set_depth_frame(329, int(round(vis * 100.0)))


func _update_camera() -> void:
	cam.x = player_x
	cam.y = RotdCamera.TARGET_OFFSET_Y
	cam.z = player_z - 1.0
	cam.yaw = (desired_speed_x / x_hb_max) * (1.0 / 180.0 * PI)
	if shake_intensity > 0.0:
		cam.x += (_rng.randf() * 2.0 - 1.0) * shake_intensity
		cam.y += (_rng.randf() * 2.0 - 1.0) * shake_intensity
	_place_cockpit()


# RDPlayer hands MC_PlayerCar to the normal entity renderer, so the interior gets
# the same projected anchor + scale as any other entity: the camera sits 1 unit
# behind the player at TARGET_OFFSET_Y (RDCamera.Update) and m_fScale is 1, so
# the clip scales by renderDistY * m_fRenderScale.  Drawing it 1:1 at a
# hand-picked y instead left the whole roof header inside the viewport -- at the
# real scale its top edge is clipped off the top and only a thin strip shows.
func _place_cockpit() -> void:
	if cockpit == null or not is_instance_valid(cockpit):
		return
	var fz := maxf(player_z - cam.z, 0.05)
	cockpit.position = cam.project(Vector3(player_x, 0.0, player_z))
	var s := cam.sprite_scale(1.0, fz)
	cockpit.scale = Vector2(s, s)


# --------------------------------------------------------------------------
# story progression
# --------------------------------------------------------------------------
func _update_story(_dt: float) -> void:
	difficulty = minf(player_z / RotdStory.total_length(), 1.0)
	# spawn-level cursor (patterns use the spawn segment's hats)
	while spawn_segment < RotdStory.TUNNEL_LEVEL and player_z + RotdStory.PATTERN_VIEW_DISTANCE >= next_spawn_start:
		spawn_segment += 1
		spawn_start_z = next_spawn_start
		next_spawn_start = spawn_start_z + float(RotdStory.LEVEL_LENGTHS[spawn_segment])

	# level cursor / checkpoints
	while segment < RotdStory.TUNNEL_LEVEL and player_z >= next_level_start:
		segment += 1
		level_start_z = next_level_start
		level_length = float(RotdStory.LEVEL_LENGTHS[segment])
		next_level_start = level_start_z + level_length
		if segment % 2 == 0:
			pre_dialog_pending = segment < RotdStory.NUKE_LEVEL
			post_dialog_pending = true
			if not failed:
				PlayerInfo.story_level = segment
				PlayerInfo.save_info()
				_show_message("进度已保存…… %s" % RotdStory.LEVEL_NAMES_ZH[RotdStory.area_index(segment)])

	var area := RotdStory.area_index(segment)
	if pre_dialog_pending and player_z >= next_level_start - float(RotdStory.PRE_CHECKPOINT_DIALOG_MARGINS[area]):
		pre_dialog_pending = false
		_play_radio(RotdStory.pre_sound(segment))
	if post_dialog_pending and player_z >= level_start_z + float(RotdStory.POST_CHECKPOINT_DIALOG_MARGINS[area]):
		post_dialog_pending = false
		_play_radio(RotdStory.post_sound(segment))

	if not campaign_done and player_z >= RotdStory.total_length():
		_complete_campaign()


func _complete_campaign() -> void:
	campaign_done = true
	PlayerInfo.story_level = RotdStory.TUNNEL_LEVEL
	PlayerInfo.save_info()
	_begin_stats(true)


# --------------------------------------------------------------------------
# spawning
# --------------------------------------------------------------------------
func _load_patterns() -> void:
	var path := SWF_ROOT + "/patterns.json"
	if not FileAccess.file_exists(path):
		return
	var f := FileAccess.open(path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	if parsed is Dictionary:
		patterns = parsed


func _bag_pick(bag_name: String, source: Array) -> String:
	var bag: Array = _bags.get(bag_name, [])
	if bag.is_empty():
		bag = source.duplicate()
		bag.shuffle()
	var v := String(bag.pop_back())
	_bags[bag_name] = bag
	return v


func _hat_for(spawn_index: int) -> Array:
	var normal := RotdStory.normal_hat(spawn_index)
	if normal.size() > 0:
		return normal
	var kind: Variant = RotdStory.NORMAL_PATTERNS[clampi(spawn_index, 0, RotdStory.NORMAL_PATTERNS.size() - 1)]
	if kind == RotdStory.GENERAL:
		return RotdStory.NORMAL_GENERAL
	if kind == RotdStory.MILITARY:
		return RotdStory.NORMAL_MILITARY
	return []


func _update_spawns() -> void:
	if patterns.is_empty():
		return
	while cam.z + RotdStory.PATTERN_VIEW_DISTANCE >= next_pattern_z:
		var hard: Array = RotdStory.hard_hat(spawn_segment)
		var name := ""
		if not hard.is_empty() and cam.z + RotdStory.PATTERN_VIEW_DISTANCE >= next_hard_z:
			name = _bag_pick("hard%d" % spawn_segment, hard)
			next_hard_z += RotdStory.HARD_PATTERN_SPACING_MIN + _rng.randf() * RotdStory.HARD_PATTERN_SPACING_RANDOM
		else:
			var hat := _hat_for(spawn_segment)
			if hat.is_empty():
				next_pattern_z += 20.0
				continue
			name = _bag_pick("normal%d" % spawn_segment, hat)
		var space := _load_pattern(name, next_pattern_z, difficulty)
		next_pattern_z += space + RotdStory.PATTERN_SPACING_MIN + _rng.randf() * RotdStory.PATTERN_SPACING_RANDOM


func _load_pattern(name: String, start_z: float, diff: float) -> float:
	var markers: Array = patterns.get(name, [])
	if markers.is_empty():
		return 20.0
	var flip_sign := -1.0 if _rng.randf() < 0.5 else 1.0
	var stretch := 1.0 + _rng.randf() * (0.25 + (1.0 - diff) * 0.25)
	var dynamic := name.begins_with("MC_LevelPattern_general") or name.begins_with("MC_LevelPattern_military")
	var max_z := 10.0

	if dynamic:
		# RDLevelPatternDynamicCustom: alpha==1 is static, alpha<1 spawns only
		# up to the segment's hazard limit.
		var faded: Array = []
		for mk_v in markers:
			if not (mk_v is Dictionary):
				continue
			var mk: Dictionary = mk_v
			var kind := _marker_kind(String(mk.get("marker", "")))
			if kind == "":
				continue
			if float(mk.get("alpha", 1.0)) < 0.999:
				if _can_spawn(kind, segment):
					faded.append(mk)
			else:
				var z := _spawn_marker(kind, mk, start_z, flip_sign, stretch)
				max_z = maxf(max_z, z)
		faded.shuffle()
		var limit := RotdStory.hazard_limit(segment, hardcore)
		for i in mini(limit, faded.size()):
			var mk2: Dictionary = faded[i]
			var z2 := _spawn_marker(_marker_kind(String(mk2.get("marker", ""))), mk2, start_z, flip_sign, stretch)
			max_z = maxf(max_z, z2)
	else:
		for mk_v in markers:
			if not (mk_v is Dictionary):
				continue
			var mk: Dictionary = mk_v
			var kind := _marker_kind(String(mk.get("marker", "")))
			if kind == "" or not _can_spawn(kind, segment):
				continue
			var z3 := _spawn_marker(kind, mk, start_z, flip_sign, stretch)
			max_z = maxf(max_z, z3)
	return max_z


func _marker_kind(marker: String) -> String:
	return String(RotdStory.MARKER_KIND.get(marker, ""))


func _can_spawn(kind: String, seg: int) -> bool:
	if kind.begins_with("zombie_hard") or kind == "zombie_veryhard":
		if kind == "zombie_veryhard":
			return seg >= 12
		return seg >= 6
	if kind == "feeders":
		return seg >= 2
	if kind == "spikes":
		return seg >= 4
	if kind.begins_with("soldier"):
		if seg >= 18:
			return false
		if kind == "soldier_stationary":
			return seg >= 1
		if kind == "soldier_align":
			return seg >= 4
		if kind == "soldier_spikes":
			return seg >= 6
		if kind == "soldier_bomb":
			return seg >= 10
	return true


func _spawn_marker(kind: String, mk: Dictionary, start_z: float, flip_sign: float, stretch: float) -> float:
	if not _can_spawn(kind, segment):
		return 0.0
	var x := float(mk.get("x", 0.0)) / 50.0 * flip_sign
	var z := start_z + (-float(mk.get("y", 0.0)) / 50.0 * stretch)
	if kind.begins_with("car_"):
		var car_kind := kind
		if kind in ["car_large_narrow", "car_large_wide", "car_medium_narrow",
				"car_medium_wide", "car_police_narrow", "car_police_wide",
				"car_small_narrow", "car_small_wide"]:
			if _rng.randf() < 0.1 + difficulty * 0.7:
				car_kind = kind + "_crashed"
			else:
				car_kind = kind + "_intact"
		var car := RotdObstacle.new()
		car.setup_car(lib, car_kind, _rng)
		car.world_x = x
		car.world_z = z
		stage.add_child(car)
		obstacles.append(car)
	elif kind == "zombie_veryhard":
		_spawn_zombie("veryhard", RotdZombie.MOVEMENT_STATIONARY, x, z)
	elif kind == "zombie_normal_straight":
		_spawn_zombie("normal_male" if _rng.randf() < 0.5 else "normal_female", RotdZombie.MOVEMENT_STRAIGHT, x, z)
	elif kind == "zombie_normal_patrol":
		_spawn_zombie("normal_male" if _rng.randf() < 0.5 else "normal_female", RotdZombie.MOVEMENT_PATROL, x, z)
	elif kind == "zombie_hard_straight":
		_spawn_zombie("hard", RotdZombie.MOVEMENT_STRAIGHT, x, z)
	elif kind == "zombie_hard_patrol":
		_spawn_zombie("hard", RotdZombie.MOVEMENT_PATROL, x, z)
	elif kind == "civilian":
		var c := RotdCivilian.new()
		c.setup_any(lib, _rng, PlayerInfo.level(7))
		c.world_x = x
		c.world_z = z
		stage.add_child(c)
		civilians.append(c)
	elif kind.begins_with("soldier"):
		return 0.0
	else:
		if kind == "oil" and _rng.randf() >= 0.1 + difficulty * 0.3:
			return 0.0
		var prop := RotdObstacle.new()
		prop.setup_prop(lib, kind)
		prop.world_x = x
		prop.world_z = z
		stage.add_child(prop)
		obstacles.append(prop)
	return z - start_z


func _spawn_zombie(kind: String, movement: int, x: float, z: float) -> void:
	if zombies.size() >= 90:
		return
	var zb := RotdZombie.new()
	zb.setup_any(lib, kind, movement, _rng, PlayerInfo.level(7))
	zb.no_cling = _noclinger
	zb.world_x = x
	zb.world_z = z
	stage.add_child(zb)
	zombies.append(zb)


func _spawn_fillers() -> void:
	var step := RotdStory.PATTERN_INITIAL_SPAWN_DISTANCE / 6.0
	for i in 5:
		var kind: String = RotdStory.FILLER_TYPES[_rng.randi_range(0, 5)]
		var prop := RotdObstacle.new()
		prop.setup_prop(lib, kind)
		prop.world_x = -7.0 + _rng.randf() * 14.0
		prop.world_z = level_start_z + (i + 1) * step
		stage.add_child(prop)
		obstacles.append(prop)


# --------------------------------------------------------------------------
# scenery (yellow lines / buildings / road signs)
# --------------------------------------------------------------------------
func _update_scenery() -> void:
	if not _scenery_on:
		return
	while cam.z + RotdStory.YELLOW_LINE_VIEW_DISTANCE >= next_yellow_z:
		for x in [-2.67, 2.67]:
			_spawn_scenery([3264], [0], 1.0, 50.0, 30.0, 2, x, next_yellow_z, false)
		next_yellow_z += RotdStory.YELLOW_LINE_SPACING
	while cam.z + RotdStory.BUILDING_VIEW_DISTANCE >= next_building_z:
		var variant := _building_variant(difficulty)
		_spawn_scenery([3684], [variant], 40.0, 180.0, 20.0, -50,
			-12.0 - _rng.randf() * 15.0, next_building_z + _rng.randf() * 20.0, true)
		_spawn_scenery([3684], [_building_variant(difficulty)], 40.0, 180.0, 20.0, -50,
			12.0 + _rng.randf() * 15.0, next_building_z + 20.0 + _rng.randf() * 20.0, false)
		next_building_z += RotdStory.BUILDING_SPACING
	if cam.z + RotdStory.ROAD_SIGN_VIEW_DISTANCE >= next_sign_z:
		var left := _rng.randf() < 0.5
		var x := -10.0 if left else 10.0
		_spawn_scenery([3618 if left else 3617], [0], 1.0, 150.0, 50.0, 5, x, next_sign_z, left)
		_spawn_scenery([3567], [0], 1.0, 150.0, 50.0, -40, x, next_sign_z, left)
		next_sign_z += RotdStory.ROAD_SIGN_SPACING_MIN + _rng.randf() * RotdStory.ROAD_SIGN_SPACING_RANDOM


func _building_variant(diff: float) -> int:
	if _rng.randf() < diff * 2.0:
		return _rng.randi_range(0, 23)
	return _rng.randi_range(0, 11)


func _spawn_scenery(chars: Array, variants: Array, scale_v: float, fade_d: float, fade_r: float,
		zbase: int, x: float, z: float, flip: bool) -> void:
	var sc := RotdScenery.new()
	sc.setup(lib, chars, variants, scale_v, fade_d, fade_r, zbase)
	sc.world_x = x
	sc.world_z = z
	sc.flip = flip
	stage.add_child(sc)
	scenery.append(sc)


func _update_scenery_nodes() -> void:
	var alive: Array[RotdScenery] = []
	for sc in scenery:
		if not is_instance_valid(sc):
			continue
		sc.update_scenery(cam)
		if sc.destroy_me:
			sc.queue_free()
		else:
			alive.append(sc)
	scenery = alive


# --------------------------------------------------------------------------
# entity updates + collisions
# --------------------------------------------------------------------------
func _update_zombies(dt: float) -> void:
	var alive: Array[RotdZombie] = []
	for z in zombies:
		if not is_instance_valid(z):
			continue
		z.update_ai(dt, player_x, player_z, vel_z, failed, PlayerInfo.is_action_pressed("horn"),
			clinger != null, cam)
		if not z.dead and not z.clinging and not failed and not campaign_done:
			_check_car_hit(z)
		if z.destroy_me:
			z.queue_free()
		else:
			alive.append(z)
	zombies = alive
	if clinger != null and is_instance_valid(clinger):
		clinger_timer -= dt
		if clinger_timer <= 0.0:
			clinger_timer = 5.0
			var wl := clampi(up_windshield, 0, 3)
			var absorb: float = [0.0, 0.15, 0.3, 0.45][wl]
			var punch := 10.0
			if clinger.zombie_type == RotdZombie.TYPE_HARD:
				punch = 15.0
			elif clinger.zombie_type == RotdZombie.TYPE_VERYHARD:
				punch = 30.0
			windshield_hp -= punch * (1.0 - absorb)
			if windshield_hp <= 0.0 and not _invincible:
				windshield_hp = 0.0
				_fail("KILLED BY ZOMBIES")


func _check_car_hit(z: RotdZombie) -> void:
	var dz := z.world_z - player_z
	if dz >= 0.5 or dz <= -2.0:
		if dz <= -2.0:
			z.destroy_me = true
		return
	if absf(z.world_x - player_x) >= 1.0:
		return
	var cling_chance := 0.0
	if clinger == null and not _noclinger:
		cling_chance = 1.0 - clampf((vel_z - MIN_CLING_SPEED) / (MAX_CLING_SPEED - MIN_CLING_SPEED), 0.0, 1.0)
	if cling_chance > 0.0 and _rng.randf() < cling_chance:
		clinger = z
		clinger_timer = 5.0
		z.cling()
		_add_shake("HitHumanoidCling", 0.1, 0.0, 0.0, 0.5)
		return
	var align := _hit_align(z.world_x)
	var hit_type := RotdZombie.HIT_SIDE
	if vel_z >= HARD_COLLISION_SPEED:
		if align == 0:
			if vel_z >= MIN_GIB_SPEED:
				hit_type = RotdZombie.HIT_GIB
				precision_hits += 1
			else:
				hit_type = RotdZombie.HIT_FRONT if _rng.randf() < 0.5 else RotdZombie.HIT_ROLLOVER
		elif align == 1:
			hit_type = RotdZombie.HIT_FRONT if _rng.randf() < 0.5 else RotdZombie.HIT_ROLLOVER
		elif align == 2 or align == 3:
			hit_type = (RotdZombie.HIT_FRONT if _rng.randf() < 0.5 else RotdZombie.HIT_ROLLOVER) if _rng.randf() < 0.4 else RotdZombie.HIT_SIDE
		else:
			hit_type = RotdZombie.HIT_SIDE
	else:
		hit_type = RotdZombie.HIT_ROLLOVER
	z.flip = player_x > z.world_x
	z.hit(hit_type)
	kills += 1
	_register_combo()
	_add_shake("HitHumanoid", 0.03, 0.0, 0.0, 0.5)
	_apply_speed_loss(HUMAN_HIT_SPEED_LOSS)
	if windshield_hp > 0.0:
		_spawn_windshield_blood(align)
	else:
		_spawn_dashboard_blood(align)
	_play_sfx("SND_HitZombie01")


func _hit_align(ex: float) -> int:
	var dist := absf(ex - player_x)
	var right := ex > player_x
	if dist < DEAD_CENTER_RANGE:
		return 0
	if dist < CENTER_RANGE:
		return 1
	if dist < FRONT_SIDE_RANGE:
		return 3 if right else 2
	return 5 if right else 4


func _update_civilians(dt: float) -> void:
	var alive: Array[RotdCivilian] = []
	for c in civilians:
		if not is_instance_valid(c):
			continue
		c.update_ai(dt, player_x, player_z, PlayerInfo.is_action_pressed("horn"), cam)
		if not c.dead and not failed and not campaign_done:
			var dz := c.world_z - player_z
			if dz < 0.5 and dz > -2.0 and absf(c.world_x - player_x) < 1.0:
				c.hit()
				civilians_killed += 1
				combo_count = 0
				combo_time = -9999.0
				_add_shake("HitHumanoid", 0.03, 0.0, 0.0, 0.5)
				_apply_speed_loss(HUMAN_HIT_SPEED_LOSS)
				if windshield_hp > 0.0:
					_spawn_windshield_blood(_hit_align(c.world_x))
				_play_sfx("SND_HitZombie01")
		if c.destroy_me:
			c.queue_free()
		else:
			alive.append(c)
	civilians = alive


func _update_obstacles(dt: float) -> void:
	var alive: Array[RotdObstacle] = []
	for o in obstacles:
		if not is_instance_valid(o):
			continue
		o.render(cam)
		if o.world_z - cam.z < -6.0:
			o.destroy_me = true
		elif not failed and not campaign_done and not o.destroy_me:
			_check_obstacle_hit(o)
		if o.destroy_me:
			o.queue_free()
		else:
			alive.append(o)
	obstacles = alive


func _check_obstacle_hit(o: RotdObstacle) -> void:
	# RDPlayer: m_CollisionBounds.X = -0.9, W = 1.8
	if not o.overlaps(player_x, player_z, 0.9):
		return
	if o.is_oil:
		_hit_oil()
		o.destroy_me = true
		return
	if o.is_spikes:
		_hit_spikes()
		o.destroy_me = true
		return
	var speed_ratio := absf(vel_z) / maxf(max_speed, 0.001)
	_add_shake("HitObstacle", o.hit_shake_intensity * speed_ratio, 0.0, 0.0,
		o.hit_shake_duration * speed_ratio)
	if not o.run_through:
		bump_vel = -BUMP_MAX_SPEED if o.world_x > player_x else BUMP_MAX_SPEED
		var collision_pos := clampf((player_x - o.world_x) / maxf(o.col_w, 0.001), -1.0, 1.0)
		if windshield_hp > 0.0:
			_deal_windshield_damage((1.0 - collision_pos) * speed_ratio * HARD_WINDSHIELD_DAMAGE)
		_play_impact_shards(_hit_align(o.world_x))
		_play_sfx("SND_MediumCollision01")
	else:
		_play_sfx("SND_TrafficConeHit")
	_apply_speed_loss(o.hit_speed_loss)
	_deal_bumper_damage(speed_ratio * o.hit_damage, o.min_hit_hp)
	o.destroy_me = true


func _deal_bumper_damage(damage: float, min_hp: float) -> void:
	var level := clampi(bumper_level, 0, 3)
	if damage <= float(BUMPER_DAMAGE_CUTOFFS[level]):
		_update_cockpit()
		return
	damage -= damage * float(BUMPER_DAMAGE_ABSORB[level])
	if min_hp > 0.0 and bumper_hp - damage < min_hp:
		damage = maxf(bumper_hp - min_hp, 0.0)
	bumper_hp = maxf(bumper_hp - damage, 0.0)
	if _invincible:
		bumper_hp = 100.0
	if bumper_hp <= 0.0:
		if bumper_level > 0:
			bumper_level -= 1
			bumper_hp = 100.0
		elif not _invincible:
			bumper_hp = 0.0
			_fail("WRECKED")
			return
	_update_cockpit()


func _apply_speed_loss(loss: float) -> void:
	if loss <= 0.0:
		return
	var factor: float = float(BUMPER_SPEED_LOSS[clampi(bumper_level, 0, 3)])
	engine_time = maxf(engine_time - loss * factor * engine_time, 0.0)
	vel_z = _speed_ratio(engine_time) * max_speed


func _deal_windshield_damage(damage: float) -> void:
	windshield_hp = maxf(windshield_hp - damage, 0.0)
	if windshield_hp <= 0.0:
		cockpit.set_depth_visible(D_WS_BLOOD, false)
		_add_shake("WindshieldBreak", 0.05, 0.0, 0.0, 1.0)
		_play_sfx("SND_WindshieldBreak")
	_update_cockpit()


func _hit_spikes() -> void:
	_add_shake("HitSpikeStrip", 0.05, 0.0, 0.0, 0.5)
	if blown_tires < 4:
		_play_sfx("SND_TireBlow")
		tire_damage = minf(tire_damage + float(TIRE_SPIKE_DAMAGE[clampi(up_tires, 0, 3)]), 4.0)
		blown_tires = int(floor(tire_damage))


func _hit_oil() -> void:
	_play_sfx("SND_OilSlick")
	_add_shake("HitOilSlick", 0.03, 0.0, 0.0, 0.5)
	oil_duration = float(OIL_DURATIONS[clampi(up_tires, 0, 3)])
	oil_time = oil_duration


func _spawn_windshield_blood(_align: int) -> void:
	cockpit.set_depth_visible(D_WS_BLOOD, true)
	cockpit.set_depth_frame(D_WS_BLOOD, 1)


func _spawn_dashboard_blood(_align: int) -> void:
	cockpit.set_depth_visible(D_DASH_BLOOD, true)
	cockpit.set_depth_frame(D_DASH_BLOOD, 1)


func _play_impact_shards(align: int) -> void:
	var labels := ["ImpactCenter", "ImpactCenter", "ImpactFrontLeft", "ImpactFrontRight",
		"ImpactSideLeft", "ImpactSideRight"]
	cockpit.set_depth_visible(D_SHARDS, true)
	cockpit.play_at_depth(D_SHARDS, labels[clampi(align, 0, 5)], false)


func _update_effects(_dt: float) -> void:
	pass


func _register_combo() -> void:
	if game_time - combo_time < COMBO_DELAY:
		combo_count += 1
		combo_points += combo_count * COMBO_POINTS
	else:
		combo_count = 0
	combo_time = game_time


# --------------------------------------------------------------------------
# fail / stats (RDGameModeGameplay.UpdateStats)
# --------------------------------------------------------------------------
func _fail(reason: String) -> void:
	if failed:
		return
	failed = true
	if clinger != null and is_instance_valid(clinger):
		clinger.destroy_me = true
		clinger = null
	_play_sfx("SND_PlayerDeathZombie1")
	_begin_stats(false, reason)


func _begin_stats(done: bool, _reason: String = "") -> void:
	showing_stats = true
	stats_ready = false
	stats_timer = 0.0
	reached_distance = floorf(player_z - player_start_z)
	hud_clip.set_depth_visible(81, true)   # PointsScreen
	stats_clip.visible = done              # distance stats only on campaign end


# RDGameModeGameplay.UpdateStats + RDHud.ShowPointsScreen: fills the original
# MC_Hud.PointsScreen slots (Description / Points text fields) with the exact
# Road Points breakdown, then banks the RP once.
func _update_stats(dt: float) -> void:
	var delay := 2.5 if stats_ready else 0.5
	stats_timer += dt
	if stats_timer < delay:
		return
	if stats_ready:
		return
	var km := roundf(reached_distance / 10.0) / 100.0
	var km_points := int(roundf(km * POINTS_PER_KM))
	var base := km_points
	base += kills * POINTS_PER_ZOMBIE
	base += soldiers_killed * POINTS_PER_SOLDIER
	base += hood_collision_kills * POINTS_PER_HOOD_COLLISION
	base += hood_pistol_kills * POINTS_PER_HOOD_PISTOL
	base += choppers_defeated * POINTS_PER_CHOPPER
	base += combo_points
	var precision := minf(precision_hits * BONUS_PER_PRECISION, 1.0)
	var precision_points := int(roundf(precision * base))
	var civ_penalty := minf(civilians_killed * PENALTY_PER_CIVILIAN, 1.0)
	var civ_points := int(roundf(civ_penalty * base))
	var total := base + precision_points - civ_points
	PlayerInfo.apply_earned_rp(total)

	var rows := [
		["%.2f 公里，已抵达：" % km, "%d RP" % km_points],
		["%d 只僵尸命中：" % kills, "%d RP" % (kills * POINTS_PER_ZOMBIE)],
		["%d 名士兵命中：" % soldiers_killed, "%d RP" % (soldiers_killed * POINTS_PER_SOLDIER)],
		["%d 个撞车敌人被甩下：" % hood_collision_kills, "%d RP" % (hood_collision_kills * POINTS_PER_HOOD_COLLISION)],
		["%d 个撞车敌人被击落：" % hood_pistol_kills, "%d RP" % (hood_pistol_kills * POINTS_PER_HOOD_PISTOL)],
		["%d 架直升机被击落：" % choppers_defeated, "%d RP" % (choppers_defeated * POINTS_PER_CHOPPER)],
		["连击点数：", "%d RP" % combo_points],
		["%d 次飞溅命中：" % precision_hits, "%d RP 奖励" % precision_points],
		["%d 名平民被撞：" % civilians_killed, "-%d RP 惩罚" % civ_points],
	]
	for i in 9:
		var slot := ""
		if i < rows.size():
			slot = "Slot%d" % (i + 1)
			hud_clip.set_text(slot + ".Description", rows[i][0])
			hud_clip.set_text(slot + ".Points", rows[i][1])
			hud_clip.set_depth_visible(_hud_slot_depth(i + 1), true)
		else:
			hud_clip.set_depth_visible(_hud_slot_depth(i + 1), false)
	hud_clip.set_text("PointsScreen.Total.Description", "公路点数总计：")
	hud_clip.set_text("PointsScreen.Total.Points", "%d RP" % total)
	stats_ready = true


# MC_Hud.PointsScreen places Slot1..Slot9 on known depths
func _hud_slot_depth(slot: int) -> int:
	return 3 + (slot - 1) * 3


func _leave_stats() -> void:
	if _leaving:
		return
	_leaving = true
	_stop_audio()
	PlayerInfo.save_info()
	if campaign_done:
		PlayerInfo.story_level = 0
		PlayerInfo.save_info()
		PlayerInfo.start_at_menu = true
		get_tree().change_scene_to_file("res://scenes/main.tscn")
	else:
		get_tree().change_scene_to_file("res://scenes/garage.tscn")


func _return_to_garage() -> void:
	if _leaving:
		return
	_leaving = true
	_stop_audio()
	PlayerInfo.save_info()
	get_tree().change_scene_to_file("res://scenes/garage.tscn")


# --------------------------------------------------------------------------
# input
# --------------------------------------------------------------------------
func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if showing_stats:
			if stats_ready and (event.keycode == KEY_SPACE or event.keycode == KEY_ENTER
					or event.keycode == KEY_KP_ENTER):
				_leave_stats()
			return
		if event.keycode == PlayerInfo.binding(PlayerInfo.action_index("firearm")):
			_shoot_clinger()
		elif event.keycode == KEY_ESCAPE:
			_return_to_garage()
		elif event.keycode == KEY_R and failed:
			_return_to_garage()


func _shoot_clinger() -> void:
	if clinger != null and is_instance_valid(clinger):
		clinger.shoot_down()
		hood_pistol_kills += 1
		clinger = null


# --------------------------------------------------------------------------
# hud / messages / audio
# --------------------------------------------------------------------------
func _hide_hud_defaults() -> void:
	# the HUD clip also carries the flash overlays, death screens and the
	# points screen (shown later by _begin_stats)
	for d in [1, 57, 59, 61, 74, 76, 79, 81, 112, 121]:
		hud_clip.set_depth_visible(d, false)
	hud_clip.set_depth_visible(81, false)


func _update_hud() -> void:
	pass


func _show_message(text: String) -> void:
	message_clip.set_text("Title", text)
	message_clip.set_text("InfoMessage", "")
	message_clip.visible = true
	message_timer = 3.0


func _setup_audio() -> void:
	for bus_name in ["Music", "SFX"]:
		if AudioServer.get_bus_index(bus_name) < 0:
			AudioServer.add_bus()
			AudioServer.set_bus_name(AudioServer.bus_count - 1, bus_name)
	_music = AudioStreamPlayer.new()
	_music.bus = "Music"
	add_child(_music)
	_sfx_pool = []
	for i in 8:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_sfx_pool.append(p)
	_voice = AudioStreamPlayer.new()
	_voice.bus = "SFX"
	_voice.volume_db = linear_to_db(1.4)
	add_child(_voice)
	_chatter = AudioStreamPlayer.new()
	_chatter.bus = "SFX"
	add_child(_chatter)
	_engine = AudioStreamPlayer.new()
	_engine.bus = "SFX"
	_engine.volume_db = linear_to_db(0.9)
	add_child(_engine)
	_horn = AudioStreamPlayer.new()
	_horn.bus = "SFX"
	add_child(_horn)
	var res := lib.get_sound_res("SND_Music_GameMusic")
	if res != "" and FileAccess.file_exists(res):
		var stream := load(res)
		if stream != null:
			if stream is AudioStreamMP3:
				(stream as AudioStreamMP3).loop = true
			elif stream is AudioStreamOggVorbis:
				(stream as AudioStreamOggVorbis).loop = true
			_music.stream = stream
			_music.play()


func _looped_stream(name: String) -> AudioStream:
	var res := lib.get_sound_res(name)
	if res == "" or not FileAccess.file_exists(res):
		return null
	var s := load(res)
	if s is AudioStreamMP3:
		(s as AudioStreamMP3).loop = true
	elif s is AudioStreamOggVorbis:
		(s as AudioStreamOggVorbis).loop = true
	return s


# Engine state follows RDPlayer.EngineState_*; each upgrade level has its own
# 5-track set (idle / accel / max-speed / coast / brake).
func _update_engine_sound() -> void:
	if failed or showing_stats:
		if _engine.playing:
			_engine.stop()
		return
	var lvl := clampi(up_engine, 0, 3) + 1
	var state := ""
	if vel_z <= 0.1:
		state = "Idle"
	elif accel_held:
		state = "Accel" if vel_z < max_speed else "MaxSpeed"
	elif brake_held:
		state = "DeccelBrake"
	else:
		state = "DeccelNoBrake"
	var wanted := "SND_Car%s%d" % [state, lvl]
	if wanted != _engine_state:
		_engine_state = wanted
		var s := _looped_stream(wanted)
		if s != null:
			_engine.stream = s
			_engine.play()
		else:
			_engine.stop()
	elif not _engine.playing and _engine.stream != null:
		_engine.play()


func _play_radio(name: String) -> void:
	var res := lib.get_sound_res(name)
	if res == "" or not FileAccess.file_exists(res):
		return
	_voice.stream = load(res)
	_voice.play()


func _play_sfx(name: String) -> void:
	var res := lib.get_sound_res(name)
	if res == "" or not FileAccess.file_exists(res):
		return
	# find a free voice in the pool so overlapping hits don't cut each other off
	for p in _sfx_pool:
		if not p.playing:
			p.stream = load(res)
			p.play()
			return
	_sfx_pool[0].stream = load(res)
	_sfx_pool[0].play()


func _play_horn(pressed: bool) -> void:
	if pressed and not _horn.playing:
		var s := _looped_stream("SND_Horn%d" % (clampi(PlayerInfo.level(7), 0, 3) + 1))
		if s != null:
			_horn.stream = s
			_horn.play()
	elif not pressed and _horn.playing:
		_horn.stop()


func _stop_audio() -> void:
	for p in [_music, _voice, _chatter, _engine, _horn]:
		if p != null and is_instance_valid(p):
			p.stop()
	for p in _sfx_pool:
		if is_instance_valid(p):
			p.stop()


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------
func _apply_fit() -> void:
	if stage == null:
		return
	var vp := get_viewport_rect().size
	if vp.x <= 0.0 or vp.y <= 0.0:
		return
	var s := minf(vp.x / DESIGN.x, vp.y / DESIGN.y)
	stage.scale = Vector2(s, s)
	stage.position = vp * 0.5 - DESIGN * 0.5 * s
