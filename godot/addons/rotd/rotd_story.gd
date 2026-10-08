class_name RotdStory
extends RefCounted

## Story-mode level table, ported 1:1 from RDGameModeStory / RDGameModeStoryHardcore.
##
## The campaign is 22 consecutive segments (11 "areas" each split into a main
## run and a short checkpoint run).  Each segment has an exact length, a hazard
## limit (how many of a pattern's faded/dynamic markers actually spawn), a set
## of normal patterns and a set of hard patterns (used for the periodic hard
## stretch).  Everything here is data only; gameplay.gd drives it.

# m_LevelLengths
const LEVEL_LENGTHS: Array = [
	2000, 300, 2500, 400, 3000, 500, 3500, 600, 4000, 700, 4500,
	800, 5000, 900, 6000, 1000, 5000, 800, 4000, 600, 3500, 400,
]

# LevelNames (RDGameModeStory.LevelNames), one per *area* (every 2 segments)
const LEVEL_NAMES: Array = [
	"Evans City", "Monroeville", "Red Ridge", "Burgony Street", "Central City",
	"Down Town", "Chinatown", "Brighton Square", "North Side Park",
	"West Ridge", "Tunnel Drive",
]

# Chinese names for the garage signboard / message box (mirrors data/paratranz)
const LEVEL_NAMES_ZH: Array = [
	"埃文斯市", "门罗维尔", "赤岭", "布鲁根街", "市中心",
	"市中心", "唐人街", "布莱顿广场", "城北公园", "西岭", "山涧隧道",
]

# m_HazardLimits (story) and the Hardcore variant
const HAZARD_LIMITS: Array = [0, 1, 2, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7]
const HAZARD_LIMITS_HARDCORE: Array = [2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7]

# Spawn geometry (RDGameModeGameplay / RDGameModeStory)
const YELLOW_LINE_VIEW_DISTANCE := 80.0
const YELLOW_LINE_SPACING := 20.0
const BUILDING_VIEW_DISTANCE := 200.0
const BUILDING_SPACING := 40.0
const ROAD_SIGN_VIEW_DISTANCE := 200.0
const ROAD_SIGN_SPACING_MIN := 150.0
const ROAD_SIGN_SPACING_RANDOM := 100.0
const ROAD_SIGN_INITIAL_SPAWN_DISTANCE := 50.0
const WATER_JUG_CHANCE := 0.05

const PATTERN_VIEW_DISTANCE := 200.0
const PATTERN_SPACING_MIN := 20.0
const PATTERN_SPACING_RANDOM := 20.0
const HARD_PATTERN_SPACING_MIN := 300.0
const HARD_PATTERN_SPACING_RANDOM := 100.0
const PATTERN_INITIAL_SPAWN_DISTANCE := 100.0

const HELICOPTER_LEVEL := 8
const HELICOPTER_MISSILE_LEVEL := 16
const JET_LEVEL := 14
const NUKE_LEVEL := 20
const TUNNEL_LEVEL := 21
const NUKE_RUN_DURATION := 120.0

const PRE_CHECKPOINT_DIALOG_MARGINS: Array = [250, 250, 250, 250, 500, 400, 300, 250, 400, 250, 250, 250]
const POST_CHECKPOINT_DIALOG_MARGINS: Array = [20, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100]

# The five random filler obstacles dropped before the first pattern
# (RDObstacleWaterJug / ShoppingCart / TrafficCone / TrafficBarrel / Box /
#  ConstructionSign).  Index matches Math.random()*6 in the original.
const FILLER_TYPES: Array = ["jug", "cart", "cone", "barrel", "box", "sign"]

# Marker -> logical entity.  Keys are the MC_LevelObject_* names stored in
# patterns.json.  The string is the "kind" gameplay.gd instantiates.
const MARKER_KIND := {
	"MC_LevelObject_ZombieNormalStraight": "zombie_normal_straight",
	"MC_LevelObject_ZombieNormalPatrol": "zombie_normal_patrol",
	"MC_LevelObject_ZombieHardStraight": "zombie_hard_straight",
	"MC_LevelObject_ZombieHardPatrol": "zombie_hard_patrol",
	"MC_LevelObject_ZombieVeryHard": "zombie_veryhard",
	"MC_LevelObject_Civilian": "civilian",
	"MC_LevelObject_Feeders": "feeders",
	"MC_LevelObject_Oil": "oil",
	"MC_LevelObject_Fence": "fence",
	"MC_LevelObject_Spikes": "spikes",
	"MC_LevelObject_ShoppingCart": "cart",
	"MC_LevelObject_ElectronicSign": "electronicsign",
	"MC_LevelObject_Box": "box",
	"MC_LevelObject_TrafficCone": "cone",
	"MC_LevelObject_TrafficBarrel": "barrel",
	"MC_LevelObject_ConstructionSign": "sign",
	"MC_LevelObject_WaterJug": "jug",
	"MC_LevelObject_Ambulance": "car_ambulance",
	"MC_LevelObject_ArmyTruck": "car_armytruck",
	"MC_LevelObject_BurningCar": "car_burning",
	"MC_LevelObject_Bus": "car_bus",
	"MC_LevelObject_FireTruck": "car_firetruck",
	"MC_LevelObject_HummerNarrow": "car_hummer_narrow",
	"MC_LevelObject_HummerWide": "car_hummer_wide",
	"MC_LevelObject_LargeCarNarrow": "car_large_narrow",
	"MC_LevelObject_LargeCarNarrowCrashed": "car_large_narrow_crashed",
	"MC_LevelObject_LargeCarWide": "car_large_wide",
	"MC_LevelObject_LargeCarWideCrashed": "car_large_wide_crashed",
	"MC_LevelObject_MediumCarNarrow": "car_medium_narrow",
	"MC_LevelObject_MediumCarNarrowCrashed": "car_medium_narrow_crashed",
	"MC_LevelObject_MediumCarWide": "car_medium_wide",
	"MC_LevelObject_MediumCarWideCrashed": "car_medium_wide_crashed",
	"MC_LevelObject_PoliceCarNarrow": "car_police_narrow",
	"MC_LevelObject_PoliceCarWide": "car_police_wide",
	"MC_LevelObject_Semi": "car_semi",
	"MC_LevelObject_SmallCarNarrow": "car_small_narrow",
	"MC_LevelObject_SmallCarNarrowCrashed": "car_small_narrow_crashed",
	"MC_LevelObject_SmallCarWide": "car_small_wide",
	"MC_LevelObject_SmallCarWideCrashed": "car_small_wide_crashed",
	"MC_LevelObject_SoldierStationary": "soldier_stationary",
	"MC_LevelObject_SoldierAlign": "soldier_align",
	"MC_LevelObject_SoldierSpikes": "soldier_spikes",
	"MC_LevelObject_SoldierBomb": "soldier_bomb",
}

const NORMAL_GENERAL: Array = [
	"MC_LevelPattern_general01", "MC_LevelPattern_general02", "MC_LevelPattern_general03",
	"MC_LevelPattern_general04", "MC_LevelPattern_general05", "MC_LevelPattern_general06",
	"MC_LevelPattern_general07", "MC_LevelPattern_general08", "MC_LevelPattern_general09",
	"MC_LevelPattern_general10", "MC_LevelPattern_general11", "MC_LevelPattern_general12",
	"MC_LevelPattern_general13", "MC_LevelPattern_general14", "MC_LevelPattern_general15",
	"MC_LevelPattern_general16", "MC_LevelPattern_general17", "MC_LevelPattern_general18",
	"MC_LevelPattern_general19", "MC_LevelPattern_general20", "MC_LevelPattern_general21",
	"MC_LevelPattern_general22", "MC_LevelPattern_general23", "MC_LevelPattern_general24",
	"MC_LevelPattern_general25", "MC_LevelPattern_general26", "MC_LevelPattern_general27",
	"MC_LevelPattern_general28", "MC_LevelPattern_general29", "MC_LevelPattern_general30",
	"MC_LevelPattern_general31", "MC_LevelPattern_general32", "MC_LevelPattern_general33",
	"MC_LevelPattern_general34", "MC_LevelPattern_general35", "MC_LevelPattern_general36",
	"MC_LevelPattern_general37", "MC_LevelPattern_general38", "MC_LevelPattern_general39",
	"MC_LevelPattern_general40", "MC_LevelPattern_general41", "MC_LevelPattern_general42",
	"MC_LevelPattern_general43", "MC_LevelPattern_general44", "MC_LevelPattern_general45",
	"MC_LevelPattern_general46", "MC_LevelPattern_general47", "MC_LevelPattern_general48",
	"MC_LevelPattern_general49", "MC_LevelPattern_general50", "MC_LevelPattern_general51",
	"MC_LevelPattern_general52", "MC_LevelPattern_general53", "MC_LevelPattern_general54",
	"MC_LevelPattern_general55",
]

const NORMAL_MILITARY: Array = [
	"MC_LevelPattern_military01", "MC_LevelPattern_military02", "MC_LevelPattern_military03",
	"MC_LevelPattern_military04", "MC_LevelPattern_military05", "MC_LevelPattern_military06",
	"MC_LevelPattern_military07", "MC_LevelPattern_military08", "MC_LevelPattern_military09",
	"MC_LevelPattern_military10", "MC_LevelPattern_military11", "MC_LevelPattern_military12",
	"MC_LevelPattern_military13",
]

# m_LevelNormalPatterns[i]: either the special "GENERAL"/"MILITARY" sentinels or
# an explicit single-pattern hat (the checkpoint / tunnel segments).
const GENERAL := "__general__"
const MILITARY := "__military__"
const NORMAL_PATTERNS: Array = [
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	MILITARY,
	GENERAL,
	["MC_LevelPattern_56hardcheckpoint"],
	GENERAL,
	["MC_LevelPattern_35mediumcheckpoint"],
	GENERAL,
	["__tunnel__"],
]

# m_LevelHardPatterns[i]
const HARD_PATTERNS: Array = [
	["MC_LevelPattern_06easy", "MC_LevelPattern_07easy", "MC_LevelPattern_18easy",
		"MC_LevelPattern_20easy", "MC_LevelPattern_33easy"],
	["MC_LevelPattern_55easycheckpoint"],
	["MC_LevelPattern_31easy", "MC_LevelPattern_32easy", "MC_LevelPattern_34medium",
		"MC_LevelPattern_36easy", "MC_LevelPattern_50easy", "MC_LevelPattern_52easy",
		"MC_LevelPattern_71medium", "MC_LevelPattern_72medium"],
	["MC_LevelPattern_49easycheckpoint"],
	["MC_LevelPattern_01medium", "MC_LevelPattern_10medium", "MC_LevelPattern_17easy",
		"MC_LevelPattern_74medium", "MC_LevelPattern_42easy", "MC_LevelPattern_69medium",
		"MC_LevelPattern_70medium"],
	["MC_LevelPattern_51mediumcheckpoint"],
	["MC_LevelPattern_08medium", "MC_LevelPattern_09easy", "MC_LevelPattern_15medium",
		"MC_LevelPattern_16medium", "MC_LevelPattern_43easy", "MC_LevelPattern_44easy",
		"MC_LevelPattern_68medium", "MC_LevelPattern_73hard", "MC_LevelPattern_24hard"],
	["MC_LevelPattern_54mediumcheckpoint"],
	["MC_LevelPattern_02medium", "MC_LevelPattern_11medium", "MC_LevelPattern_19medium",
		"MC_LevelPattern_25medium", "MC_LevelPattern_27hard", "MC_LevelPattern_38hard",
		"MC_LevelPattern_46medium", "MC_LevelPattern_47medium"],
	["MC_LevelPattern_03hardcheckpoint"],
	["MC_LevelPattern_12hard", "MC_LevelPattern_13hard", "MC_LevelPattern_26hard",
		"MC_LevelPattern_29medium", "MC_LevelPattern_30medium", "MC_LevelPattern_37medium",
		"MC_LevelPattern_53medium"],
	["MC_LevelPattern_22mediumcheckpoint"],
	["MC_LevelPattern_05hard", "MC_LevelPattern_14hard", "MC_LevelPattern_28hard",
		"MC_LevelPattern_39hard", "MC_LevelPattern_67medium", "MC_LevelPattern_75hard",
		"MC_LevelPattern_76medium", "MC_LevelPattern_77hard"],
	["MC_LevelPattern_23hardcheckpoint"],
	["MC_LevelPattern_04hard", "MC_LevelPattern_41hard", "MC_LevelPattern_48hard",
		"MC_LevelPattern_61medium", "MC_LevelPattern_81hard", "MC_LevelPattern_82medium",
		"MC_LevelPattern_83hard"],
	["MC_LevelPattern_40hardcheckpoint"],
	["MC_LevelPattern_45hard", "MC_LevelPattern_57hard", "MC_LevelPattern_58hard",
		"MC_LevelPattern_59hard", "MC_LevelPattern_60hard", "MC_LevelPattern_65hard",
		"MC_LevelPattern_66hard"],
	[],
	["MC_LevelPattern_62hard", "MC_LevelPattern_63hard", "MC_LevelPattern_64hard",
		"MC_LevelPattern_78hard", "MC_LevelPattern_79hard", "MC_LevelPattern_80medium"],
	[],
	["MC_LevelPattern_83hard", "MC_LevelPattern_80medium", "MC_LevelPattern_79hard",
		"MC_LevelPattern_78hard", "MC_LevelPattern_77hard", "MC_LevelPattern_75hard",
		"MC_LevelPattern_64hard", "MC_LevelPattern_62hard", "MC_LevelPattern_59hard",
		"MC_LevelPattern_57hard", "MC_LevelPattern_45hard", "MC_LevelPattern_41hard"],
	[],
]


static func total_length() -> float:
	var out := 0.0
	for i in LEVEL_LENGTHS.size() - 1:
		out += float(LEVEL_LENGTHS[i])
	return out


static func level_start(index: int) -> float:
	var out := 0.0
	for i in range(mini(index, LEVEL_LENGTHS.size())):
		out += float(LEVEL_LENGTHS[i])
	return out


static func area_index(segment: int) -> int:
	return clampi(segment / 2, 0, LEVEL_NAMES.size() - 1)


static func normal_hat(segment: int) -> Array:
	var v: Variant = NORMAL_PATTERNS[clampi(segment, 0, NORMAL_PATTERNS.size() - 1)]
	if v is Array:
		return v
	return []


static func hard_hat(segment: int) -> Array:
	var v: Variant = HARD_PATTERNS[clampi(segment, 0, HARD_PATTERNS.size() - 1)]
	if v is Array:
		return v
	return []


static func hazard_limit(segment: int, hardcore: bool = false) -> int:
	var table: Array = HAZARD_LIMITS_HARDCORE if hardcore else HAZARD_LIMITS
	return int(table[clampi(segment, 0, table.size() - 1)])


static func pre_sound(segment: int) -> String:
	var i := clampi(area_index(segment), 0, 10)
	return "SND_CheckPoint%dPre" % (i + 1)


static func post_sound(segment: int) -> String:
	var i := clampi(area_index(segment), 0, 10)
	return "SND_CheckPoint%dPost" % i
