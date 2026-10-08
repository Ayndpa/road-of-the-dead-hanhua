class_name RotdObstacle
extends RotdEntity

## Road obstacles ported from RDObstacle* / RDObstacleCar.  One class covers the
## static props (box, cone, barrel, water jug, shopping cart, signs, fence,
## feeders, oil slick, spike strip) and, with `is_car`, the abandoned-vehicle
## obstacles that pick a random MC_Vehicle* variant like RDCarSpawnInfos.

# static prop table: kind -> {id, scale, w, col_x, ...}.  run-through props are
# swept aside (still applying speed loss / bumper damage) like RDObstacle.
const PROPS := {
	"box": {"id": 3619, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 0.0, "loss": 0.0},
	"cone": {"id": 3560, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 0.0, "loss": 0.0, "shake": 0.01},
	"barrel": {"id": 3561, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 0.0, "loss": 0.0, "shake": 0.01},
	"jug": {"id": 3714, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 2.0, "loss": 0.0, "shake": 0.04},
	"cart": {"id": 3562, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 0.5, "loss": 0.0},
	"sign": {"id": 3685, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 0.5, "loss": 0.0},
	"electronicsign": {"id": 3559, "scale": 1.0, "w": 1.0, "col_x": -0.5, "run": true, "dmg": 4.0, "loss": 0.2, "shake": 0.03},
	"fence": {"id": 3769, "scale": 3.5, "w": 4.0, "col_x": -2.0, "run": true, "dmg": 1.0, "loss": 0.1, "shake": 0.1, "shake_dur": 0.5},
	"feeders": {"id": 661, "scale": 3.0, "w": 2.0, "col_x": -1.0, "run": true, "dmg": 3.0, "loss": 0.75, "shake": 0.1, "shake_dur": 0.5},
	"oil": {"id": 3376, "scale": 1.0, "w": 3.0, "col_x": -1.5, "oil": true},
	"spikes": {"id": 3503, "scale": 6.0, "w": 2.5, "col_x": -1.25, "spikes": true},
}

# RDCarSpawnInfos groups.  Each entry is [char id, AS3 frame (1-based)].
const CAR_GROUPS := {
	"car_small_wide": [[384, 1], [384, 2], [384, 3], [193, 1], [3794, 1], [3806, 1], [3806, 2]],
	"car_small_narrow": [[3788, 1], [3788, 2], [3788, 3], [189, 1], [189, 2], [189, 3], [189, 4],
		[3791, 1], [3791, 2], [3791, 3], [3791, 4], [3803, 1], [3800, 1], [3785, 1], [3785, 2],
		[3785, 3], [286, 1], [3797, 1], [3797, 2], [3797, 3], [3797, 4]],
	"car_small_wide_intact": [[384, 1], [384, 2], [3794, 1]],
	"car_small_narrow_intact": [[3788, 1], [3788, 2], [189, 1], [189, 2], [189, 3], [3791, 1],
		[3791, 2], [3791, 3], [3785, 1], [3785, 2], [3797, 1], [3797, 2], [3797, 3]],
	"car_small_wide_crashed": [[193, 1], [3806, 1], [3806, 2]],
	"car_small_narrow_crashed": [[3803, 1], [3800, 1], [286, 1]],
	"car_medium_wide": [[369, 1], [369, 2], [3812, 1], [3812, 2], [3815, 1], [3815, 2],
		[281, 2], [281, 3]],
	"car_medium_narrow": [[374, 1], [374, 2], [3809, 1], [3809, 2], [3818, 1], [3818, 2],
		[3818, 3], [3818, 4], [180, 1], [180, 2], [180, 3], [180, 4], [184, 1], [184, 2],
		[3822, 1], [3822, 2], [3822, 3], [3822, 4], [3825, 1], [3825, 2], [3828, 1], [3828, 2],
		[3828, 3], [3828, 4], [3831, 1], [3831, 2], [3831, 3], [3831, 4], [3834, 1], [3834, 2]],
	"car_medium_wide_intact": [[369, 1], [281, 1], [281, 2]],
	"car_medium_narrow_intact": [[374, 1], [3818, 1], [3818, 2], [3818, 3], [180, 1], [180, 2],
		[180, 3], [3822, 1], [3822, 2], [3822, 3], [3828, 1], [3828, 2], [3828, 3],
		[3831, 1], [3831, 2], [3831, 3]],
	"car_medium_wide_crashed": [[3812, 1], [3812, 2], [3815, 1], [3815, 2], [281, 2], [281, 3]],
	"car_medium_narrow_crashed": [[3809, 1], [3809, 2], [184, 1], [184, 2], [3825, 1],
		[3825, 2], [3834, 1], [3834, 2]],
	"car_large_wide": [[292, 1], [292, 2], [292, 3], [292, 4], [3847, 1], [3847, 2],
		[3851, 1], [3851, 2], [3851, 3], [3851, 4], [3868, 1], [3868, 2], [3868, 3], [3868, 4],
		[3877, 1], [3877, 2], [3877, 3], [3877, 4], [3874, 1], [3874, 2], [3874, 3], [3874, 4],
		[301, 1], [301, 2], [3871, 1], [3871, 2], [3881, 1], [3881, 2]],
	"car_large_narrow": [[175, 1], [175, 2], [175, 3], [175, 4], [3837, 1], [3837, 2],
		[3837, 3], [3837, 4], [3840, 1], [3840, 2], [3858, 1], [3858, 2], [3858, 3], [3858, 4],
		[3855, 1], [3855, 2], [3855, 3], [3855, 4], [3861, 1], [3861, 2], [3861, 3], [3861, 4],
		[3864, 1], [3864, 2]],
	"car_large_wide_intact": [[292, 1], [292, 2], [292, 3], [3868, 1], [3868, 2], [3868, 3],
		[3877, 1], [3877, 2], [3877, 3], [3874, 1], [3874, 2], [3874, 3], [3881, 1]],
	"car_large_narrow_intact": [[175, 1], [175, 2], [175, 3], [3837, 1], [3837, 2], [3837, 3],
		[3858, 1], [3858, 2], [3858, 3], [3855, 1], [3855, 2], [3855, 3], [3861, 1], [3861, 2],
		[3861, 3]],
	"car_large_wide_crashed": [[3847, 1], [3847, 2], [3851, 1], [3851, 2], [3851, 3], [3851, 4],
		[301, 1], [301, 2], [3871, 1], [3871, 2]],
	"car_large_narrow_crashed": [[3840, 1], [3840, 2], [343, 1], [343, 2], [3864, 1], [3864, 2]],
	"car_police_wide": [[369, 1], [369, 2], [3812, 1], [3812, 2]],
	"car_police_narrow": [[374, 1], [374, 2], [3809, 1], [3809, 2]],
	"car_police_wide_intact": [[369, 1]],
	"car_police_narrow_intact": [[3809, 1]],
	"car_police_wide_crashed": [[369, 1], [369, 2], [3812, 1], [3812, 2]],
	"car_police_narrow_crashed": [[374, 1], [374, 2], [3809, 1], [3809, 2]],
	"car_firetruck": [[363, 1], [363, 2]],
	"car_ambulance": [[3881, 1], [3881, 2]],
	"car_hummer_wide": [[159, 1]],
	"car_hummer_narrow": [[164, 1]],
	"car_armytruck": [[128, 1]],
	"car_bus": [[433, 1]],
	"car_semi": [[442, 1]],
	"car_burning": [[3885, 1], [357, 1]],
}

# approximate collision half-width by car family (world units, from
# m_Bounds.W * GlobalMCWidthToWorldWidthFactor / Scale)
const CAR_WIDTH := {
	"small": 1.8, "medium": 2.2, "large": 2.6, "police": 2.2,
	"hummer": 2.4, "armytruck": 2.6, "bus": 2.8, "semi": 3.0,
	"firetruck": 2.8, "ambulance": 2.6, "burning": 2.0,
}

# RDEntity.GlobalMCWidthToWorldWidthFactor.  RDObstacleCar sizes its hitbox
# from the sprite it was handed (m_Bounds.W is already multiplied by Scale,
# which cancels out), so a semi is ~12.6 world units wide -- 84% of the road.
const MC_WIDTH_TO_WORLD := 0.015

var kind := ""
var is_car := false
var is_oil := false
var is_spikes := false
var is_solid := false
var run_through := false
var hit_damage := 0.0
var hit_speed_loss := 0.0
var hit_shake_intensity := 0.015
var hit_shake_duration := 0.3
var min_hit_hp := 1.0
var char_id := 0
var car_frame := 0
var car_width := 2.0
var _rng: RandomNumberGenerator


func setup_prop(library: SwfLibrary, prop_kind: String) -> void:
	lib = library
	kind = prop_kind
	var d: Dictionary = PROPS.get(prop_kind, PROPS["box"])
	char_id = int(d["id"])
	world_scale = float(d["scale"])
	col_x = float(d["col_x"])
	col_w = float(d["w"])
	col_z_front = 0.6
	col_z_back = 1.5
	is_oil = bool(d.get("oil", false))
	is_spikes = bool(d.get("spikes", false))
	is_solid = bool(d.get("solid", false))
	run_through = bool(d.get("run", false))
	hit_damage = float(d.get("dmg", 0.0))
	hit_speed_loss = float(d.get("loss", 0.0))
	hit_shake_intensity = float(d.get("shake", 0.015))
	hit_shake_duration = float(d.get("shake_dur", 0.3))
	min_hit_hp = float(d.get("min_hp", 1.0))
	fade_distance = 150.0
	fade_range = 50.0
	setup_clip(char_id)


func setup_car(library: SwfLibrary, car_kind: String, rng: RandomNumberGenerator) -> void:
	lib = library
	_rng = rng
	kind = car_kind
	is_car = true
	var group: Array = CAR_GROUPS.get(car_kind, CAR_GROUPS["car_small_wide"])
	var entry: Array = group[rng.randi_range(0, group.size() - 1)]
	char_id = int(entry[0])
	var frame := int(entry[1]) - 1
	car_frame = frame
	world_scale = 6.0
	fade_distance = 150.0
	fade_range = 50.0
	flip = rng.randf() > 0.5
	car_width = _car_family_width(car_kind)
	col_x = -car_width * 0.5
	col_w = car_width
	col_z_front = 0.6
	col_z_back = 2.5
	run_through = false
	hit_damage = 20.0
	hit_speed_loss = 0.3
	hit_shake_intensity = 0.2
	hit_shake_duration = 1.0
	min_hit_hp = 0.0
	setup_clip(char_id, frame)
	# the hitbox follows the art, as in the RDObstacleCar constructor
	var w := art_rect().size.x * MC_WIDTH_TO_WORLD
	if w > 0.0:
		car_width = w
		col_x = -car_width * 0.5
		col_w = car_width


func _car_family_width(car_kind: String) -> float:
	var key := "small"
	if car_kind.find("medium") >= 0 or car_kind.find("police") >= 0:
		key = "medium"
	if car_kind.find("large") >= 0:
		key = "large"
	if car_kind.find("hummer") >= 0:
		key = "hummer"
	if car_kind.find("armytruck") >= 0:
		key = "armytruck"
	if car_kind.find("bus") >= 0:
		key = "bus"
	if car_kind.find("semi") >= 0:
		key = "semi"
	if car_kind.find("firetruck") >= 0:
		key = "firetruck"
	if car_kind.find("ambulance") >= 0:
		key = "ambulance"
	if car_kind.find("burning") >= 0:
		key = "burning"
	if car_kind.find("police") >= 0:
		key = "police"
	return float(CAR_WIDTH.get(key, 2.0))
