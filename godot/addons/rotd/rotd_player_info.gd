extends Node

## Persistent player profile shared across scenes.
##
## Mirrors the fields of the original RDPlayerInfo that the garage and the
## patched gameplay slice need: Road Points (RP) plus the eight vehicle
## upgrade levels (each 0..3). Saved next to the audio settings in
## ``user://player.cfg`` so it survives restarts and scene changes.
##
## Registered as the ``PlayerInfo`` autoload in project.godot.

const SAVE_PATH := "user://player.cfg"
const UPGRADE_COUNT := 8
const MAX_LEVEL := 3

# Key rebinding: ten rows on the Flash Controls page, in display order.  Only
# the named rows drive the port; the others are stored so the page round-trips.
const BINDING_ACTIONS: Array[String] = [
	"left", "right", "accel", "brake", "handbrake", "", "", "firearm", "", "horn",
]
const BINDING_DEFAULTS: Array = [
	KEY_A, KEY_D, KEY_W, KEY_S, KEY_SPACE, KEY_SPACE, KEY_SPACE, KEY_F, KEY_RIGHT, KEY_RIGHT,
]

# RDUnlockItem.m_UnlockCosts, grouped by category (level 1..3).
const COSTS: Array = [
	[350, 700, 1400],  # 0 Perception
	[300, 600, 1200],  # 1 Body Armor
	[300, 600, 1200],  # 2 Firearm
	[250, 500, 1000],  # 3 Windshield
	[250, 500, 1000],  # 4 Engine
	[300, 600, 1200],  # 5 Bumper
	[250, 500, 1000],  # 6 Tires
	[100, 250, 500],   # 7 Horn
]

var rp: int = 0
var levels: Array[int] = []
var been_in_garage: bool = false
var story_level: int = 0
var bindings: Array[int] = []

# transient: set by the garage's "go back" button so the main scene skips the
# disclaimer and lands straight on the menu.
var start_at_menu: bool = false


func _ready() -> void:
	_reset()
	load_info()


func _reset() -> void:
	levels = []
	for _i in UPGRADE_COUNT:
		levels.append(0)
	bindings = []
	for code in BINDING_DEFAULTS:
		bindings.append(int(code))


func binding(i: int) -> int:
	if i < 0 or i >= bindings.size():
		return 0
	return bindings[i]


func set_binding(i: int, code: int) -> void:
	if i < 0 or i >= bindings.size():
		return
	bindings[i] = code
	save_info()


func action_index(action: String) -> int:
	return BINDING_ACTIONS.find(action)


func is_action_pressed(action: String) -> bool:
	var i := action_index(action)
	return i >= 0 and Input.is_key_pressed(bindings[i])


func level(category: int) -> int:
	return int(levels[category])


func is_maxed(category: int) -> bool:
	return level(category) >= MAX_LEVEL


func next_cost(category: int) -> int:
	if is_maxed(category):
		return -1
	return int(COSTS[category][level(category)])


func can_afford(category: int) -> bool:
	var cost := next_cost(category)
	return cost >= 0 and rp >= cost


func buy_upgrade(category: int) -> bool:
	if not can_afford(category):
		return false
	rp -= next_cost(category)
	levels[category] = level(category) + 1
	save_info()
	return true


func apply_earned_rp(amount: int) -> void:
	rp = maxi(rp + amount, 0)
	save_info()


func save_info() -> void:
	var cf := ConfigFile.new()
	cf.set_value("player", "rp", rp)
	cf.set_value("player", "been_in_garage", been_in_garage)
	cf.set_value("player", "story_level", story_level)
	for i in UPGRADE_COUNT:
		cf.set_value("upgrades", "u%d" % i, int(levels[i]))
	for i in bindings.size():
		cf.set_value("keys", "b%d" % i, int(bindings[i]))
	cf.save(SAVE_PATH)


func load_info() -> void:
	var cf := ConfigFile.new()
	if cf.load(SAVE_PATH) != OK:
		return
	rp = int(cf.get_value("player", "rp", 0))
	been_in_garage = bool(cf.get_value("player", "been_in_garage", false))
	story_level = int(cf.get_value("player", "story_level", 0))
	for i in UPGRADE_COUNT:
		levels[i] = clampi(int(cf.get_value("upgrades", "u%d" % i, 0)), 0, MAX_LEVEL)
	for i in bindings.size():
		bindings[i] = int(cf.get_value("keys", "b%d" % i, bindings[i]))
	if OS.get_cmdline_user_args().has("--debug"):
		print("PlayerInfo loaded rp=", rp, " levels=", levels, " been=", been_in_garage, " level=", story_level)
