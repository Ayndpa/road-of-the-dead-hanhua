class_name SwfVectorShape
extends Node2D

## Renders one pre-tessellated SWF ``DefineShape`` from ``assets/swf/shapes.bin``.
##
## All contour/winding/triangulation work is done offline by
## ``exporter/export_shape_vectors.py``, so this only uploads a mesh (fills +
## strokes) and, when the shape has a Flash glow filter, a light offset shadow.
## Multiply colour transforms come from the parent's ``modulate``; the add part
## uses ``swf_color_vec.gdshader``.

var local_rect := Rect2()

var _add_shader: Shader
var _add_color := Color(0, 0, 0, 0)
var _materials: Dictionary = {}
var _items: Array[CanvasItem] = []


func setup(rec: Dictionary, data: PackedByteArray, fx: Dictionary = {}) -> void:
	_add_shader = load("res://addons/swf_timeline/swf_color_vec.gdshader")
	if rec.is_empty() or data.is_empty():
		return
	local_rect = rec.get("rect", Rect2())
	var nv := int(rec.get("nv", 0))
	var ni := int(rec.get("ni", 0))
	var npal := int(rec.get("npal", 0))
	var p := int(rec.get("off", 0))
	var vf := data.slice(p, p + nv * 8).to_float32_array()
	p += nv * 8
	var ii := data.slice(p, p + ni * 4).to_int32_array()
	p += ni * 4
	var cii := data.slice(p, p + nv * 4).to_int32_array()
	p += nv * 4
	var pb := data.slice(p, p + npal * 4)

	var pal := PackedColorArray()
	pal.resize(npal)
	for k in range(npal):
		pal[k] = Color(pb[k * 4] / 255.0, pb[k * 4 + 1] / 255.0, pb[k * 4 + 2] / 255.0, pb[k * 4 + 3] / 255.0)

	var verts := PackedVector3Array()
	verts.resize(nv)
	var cols := PackedColorArray()
	cols.resize(nv)
	for k in range(nv):
		verts[k] = Vector3(vf[k * 2], vf[k * 2 + 1], 0.0)
		cols[k] = pal[int(cii[k])]

	if fx.has("glow"):
		_add_shadow(verts, ii, fx["glow"])
	_add_mesh(verts, cols, ii)
	_apply_materials()


func _add_mesh(verts: PackedVector3Array, cols: PackedColorArray, ii: PackedInt32Array) -> void:
	if verts.is_empty() or ii.is_empty():
		return
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_COLOR] = cols
	arrays[Mesh.ARRAY_INDEX] = ii
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mi := MeshInstance2D.new()
	mi.mesh = mesh
	add_child(mi)
	_items.append(mi)


# A Flash GlowFilter on the menu buttons reads, in practice, as a very light
# shadow under the glyphs: the same triangles, offset down, tinted dark.
func _add_shadow(verts: PackedVector3Array, ii: PackedInt32Array, glow: Dictionary) -> void:
	var col := _color(glow.get("color", [0, 0, 0, 255]))
	var blur := float(glow.get("blur", 5.0))
	var alpha := clampf(col.a * float(glow.get("strength", 1.0)) * 0.12, 0.0, 1.0)
	var sverts := PackedVector3Array()
	sverts.resize(verts.size())
	var scols := PackedColorArray()
	scols.resize(verts.size())
	var shadow := Color(col.r, col.g, col.b, alpha)
	var off := maxf(blur * 0.12, 1.0)
	for k in range(verts.size()):
		sverts[k] = verts[k] + Vector3(0.0, off, 0.0)
		scols[k] = shadow
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = sverts
	arrays[Mesh.ARRAY_COLOR] = scols
	arrays[Mesh.ARRAY_INDEX] = ii
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mi := MeshInstance2D.new()
	mi.mesh = mesh
	add_child(mi)


func set_add_color(add: Color) -> void:
	_add_color = add
	_apply_materials()


func _apply_materials() -> void:
	if _add_shader == null:
		return
	if _add_color == Color(0, 0, 0, 0):
		for it in _items:
			it.material = null
		return
	var key := "%.3f,%.3f,%.3f,%.3f" % [_add_color.r, _add_color.g, _add_color.b, _add_color.a]
	var mat: ShaderMaterial = _materials.get(key)
	if mat == null:
		mat = ShaderMaterial.new()
		mat.shader = _add_shader
		mat.set_shader_parameter("ct_add", _add_color)
		_materials[key] = mat
	for it in _items:
		it.material = mat


func _color(arr: Array) -> Color:
	if arr.size() < 3:
		return Color.WHITE
	var a := 1.0 if arr.size() < 4 else float(arr[3]) / 255.0
	return Color(float(arr[0]) / 255.0, float(arr[1]) / 255.0, float(arr[2]) / 255.0, a)
