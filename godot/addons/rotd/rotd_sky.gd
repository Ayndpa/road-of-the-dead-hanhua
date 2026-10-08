class_name RotdSky
extends Node2D

## Simple vertical sky gradient drawn behind the road.

const W := 600.0
const H := 400.0

var _tex: GradientTexture2D


func _init() -> void:
	var g := Gradient.new()
	g.set_color(0, Color(0.55, 0.59, 0.63))
	g.set_color(1, Color(0.83, 0.86, 0.89))
	g.add_point(0.55, Color(0.72, 0.76, 0.80))
	var t := GradientTexture2D.new()
	t.gradient = g
	t.width = 4
	t.height = 256
	t.fill_from = Vector2(0.0, 0.0)
	t.fill_to = Vector2(0.0, 1.0)
	_tex = t
	z_index = -100


func _draw() -> void:
	draw_texture_rect(_tex, Rect2(0, 0, W, H), false)
