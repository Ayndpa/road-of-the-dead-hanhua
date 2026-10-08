class_name RotdRoad
extends Node2D

## Procedural pseudo-3D road, ported from ROTD1 RDRoad.Render.

const SIDE_ROAD_X := 10.0
const ROAD_X := 7.5
const FAR_POS := 200.0
const NEAR_POS := 0.1
const NB_STEPS := 8
const STEP := (FAR_POS - NEAR_POS) / (NB_STEPS - 1.0)
const WALL_H := 2.0
const ROAD_SIDE_H := 0.1

const WALL_NEAR := Color8(98, 101, 105)
const WALL_FAR := Color8(74, 76, 79)
const WALL_NEAR_OFF := Color8(88, 91, 95)
const WALL_FAR_OFF := Color8(64, 66, 69)
const SIDE_NEAR := Color8(110, 107, 101)
const SIDE_FAR := Color8(95, 91, 81)
const SIDE_NEAR_OFF := Color8(100, 97, 91)
const SIDE_FAR_OFF := Color8(85, 81, 71)
const ROAD_NEAR := Color8(58, 57, 63)
const ROAD_FAR := Color8(43, 42, 46)
const ROAD_NEAR_OFF := Color8(48, 47, 53)
const ROAD_FAR_OFF := Color8(33, 32, 36)

var cam: RotdCamera


func _draw() -> void:
	if cam == null:
		return
	var cam_pos := maxf(cam.z, 0.0)
	var looped := fposmod(cam_pos, STEP)
	var slide := int(floor(cam_pos / STEP))
	for i in NB_STEPS:
		var near := maxf(i * STEP - looped, NEAR_POS)
		var far := minf((i + 1) * STEP - looped, FAR_POS)
		var off := (slide + i) % 2 == 0
		var ratio := near / FAR_POS

		var wall := _lerp2(off, WALL_NEAR_OFF, WALL_FAR_OFF, WALL_NEAR, WALL_FAR, ratio)
		var side := _lerp2(off, SIDE_NEAR_OFF, SIDE_FAR_OFF, SIDE_NEAR, SIDE_FAR, ratio)
		var road := _lerp2(off, ROAD_NEAR_OFF, ROAD_FAR_OFF, ROAD_NEAR, ROAD_FAR, ratio)

		_quad(Vector3(-SIDE_ROAD_X, WALL_H, near), Vector3(-SIDE_ROAD_X, WALL_H, far),
			Vector3(-SIDE_ROAD_X, 0, far), Vector3(-SIDE_ROAD_X, 0, near), wall)
		_quad(Vector3(SIDE_ROAD_X, 0, near), Vector3(SIDE_ROAD_X, 0, far),
			Vector3(SIDE_ROAD_X, WALL_H, far), Vector3(SIDE_ROAD_X, WALL_H, near), wall)
		_quad(Vector3(-SIDE_ROAD_X, ROAD_SIDE_H, near), Vector3(-SIDE_ROAD_X, ROAD_SIDE_H, far),
			Vector3(-ROAD_X, 0, far), Vector3(-ROAD_X, 0, near), side)
		_quad(Vector3(ROAD_X, 0, near), Vector3(ROAD_X, 0, far),
			Vector3(SIDE_ROAD_X, ROAD_SIDE_H, far), Vector3(SIDE_ROAD_X, ROAD_SIDE_H, near), side)
		_quad(Vector3(-ROAD_X, 0, near), Vector3(-ROAD_X, 0, far),
			Vector3(ROAD_X, 0, far), Vector3(ROAD_X, 0, near), road)


const NEAR_Z := 1.5


func _quad(a: Vector3, b: Vector3, c: Vector3, d: Vector3, color: Color) -> void:
	if cam == null:
		return
	# a=near-top, b=far-top, c=far-bottom, d=near-bottom -> simple quad order
	var poly := _clip_near([a, b, c, d], NEAR_Z)
	if poly.size() < 3:
		return
	var pts := PackedVector2Array()
	for v in poly:
		pts.append(cam.project_quick(v))
	draw_colored_polygon(pts, color)


func _clip_near(poly: Array, nearz: float) -> Array:
	var out: Array = []
	var n := poly.size()
	for i in n:
		var cur: Vector3 = poly[i]
		var nxt: Vector3 = poly[(i + 1) % n]
		var cur_in := cur.z >= nearz
		var nxt_in := nxt.z >= nearz
		if cur_in:
			out.append(cur)
		if cur_in != nxt_in:
			var t := (nearz - cur.z) / (nxt.z - cur.z)
			out.append(cur.lerp(nxt, t))
	return out


func _lerp2(off: bool, near_off: Color, far_off: Color, near: Color, far: Color, r: float) -> Color:
	var n := near_off if off else near
	var f := far_off if off else far
	return n.lerp(f, r)
