class_name RotdCamera
extends RefCounted

## Road-of-the-Dead camera + pseudo-3D projection (ported from RDCamera /
## RDEntity.Project3DTo2D / RDRoad.Project3DTo2DQuick).
##
## World space: X = right, Y = up, Z = forward. The camera looks along +Z.

const MAX_VIEW_DISTANCE := 200.0
const RAMP_DISTANCE := 300.0
const RAMP_FACTOR := 3500.0 / RAMP_DISTANCE
const RAMP_POWER := 2.0
const RENDER_SCALE := 0.0034959
const TARGET_OFFSET_Y := 1.15
const FOV := 60.0

var x: float = 0.0
var y: float = 0.0
var z: float = 0.0
var yaw: float = 0.0

var half_w: float = 300.0
var half_h: float = 200.0
var render_dist_x: float = 0.0
var render_dist_y: float = 0.0


func _init(hw: float = 300.0, hh: float = 200.0) -> void:
	half_w = hw
	half_h = hh
	var half_angle := deg_to_rad(FOV * 0.5)
	var cot := cos(half_angle) / sin(half_angle)
	render_dist_x = cot * half_w
	render_dist_y = cot * half_h


# project a world point (relative Z handled internally, as RDEntity does)
func project(loc: Vector3) -> Vector2:
	var dz := loc.z - z
	var tx := loc.x - x
	var ty := loc.y - y + pow(dz / RAMP_DISTANCE, RAMP_POWER) * RAMP_FACTOR
	# RotationY(-yaw): X' = tx*cos(a) + tz*sin(a); Z' = -tx*sin(a) + tz*cos(a)
	var a := -yaw
	var rx := tx * cos(a) + dz * sin(a)
	var rz := -tx * sin(a) + dz * cos(a)
	rz = maxf(rz, 0.1)
	var invz := 1.0 / rz
	return Vector2(rx * render_dist_x * invz + half_w, -ty * render_dist_y * invz + half_h)


# project a point whose Z is already camera-relative (RDRoad.Project3DTo2DQuick)
func project_quick(loc: Vector3) -> Vector2:
	var tx := loc.x - x
	var ty := loc.y - y + pow(loc.z / MAX_VIEW_DISTANCE, RAMP_POWER) * RAMP_FACTOR
	var a := -yaw
	var rx := tx * cos(a) + loc.z * sin(a)
	var rz := -tx * sin(a) + loc.z * cos(a)
	rz = maxf(rz, 0.1)
	var invz := 1.0 / rz
	return Vector2(rx * render_dist_x * invz + half_w, -ty * render_dist_y * invz + half_h)


# billboard scale for a world-space height, matching RDEntity.Render
func sprite_scale(world_scale: float, fz: float) -> float:
	if fz <= 0.0:
		return 0.0
	return world_scale * render_dist_y * RENDER_SCALE / fz
