class_name SwfLibrary
extends RefCounted

## Loads the asset bundle produced by exporter/swf_to_godot.py and caches
## textures / sprite definitions for the SwfMovieClip runtime.

var root: String
var characters: Dictionary = {}
var symbols: Dictionary = {}
var fps: float = 30.0
var text_defs: Dictionary = {}
var font_map: Dictionary = {}
var sounds: Dictionary = {}
var sound_by_name: Dictionary = {}
var vectors: Dictionary = {}
var bin_bytes: PackedByteArray = PackedByteArray()
var filters: Dictionary = {}

var _textures: Dictionary = {}
var _sprites: Dictionary = {}
var _fonts: Dictionary = {}
var _add_shader: Shader
var _add_materials: Dictionary = {}


func _init(root_dir: String = "res://assets/swf") -> void:
	root = root_dir.trim_suffix("/")
	_add_shader = load("res://addons/swf_timeline/swf_color.gdshader")
	var path := root + "/characters.json"
	if FileAccess.file_exists(path):
		var f := FileAccess.open(path, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			characters = parsed.get("characters", {})
			symbols = parsed.get("symbols", {})
			var meta: Dictionary = parsed.get("meta", {})
			fps = float(meta.get("fps", 30.0))
	var tpath := root + "/texts.json"
	if FileAccess.file_exists(tpath):
		var tf := FileAccess.open(tpath, FileAccess.READ)
		var tparsed: Variant = JSON.parse_string(tf.get_as_text())
		if tparsed is Dictionary:
			text_defs = tparsed.get("texts", {})
			font_map = tparsed.get("fonts", {})
	var spath := root + "/sounds.json"
	if FileAccess.file_exists(spath):
		var sf := FileAccess.open(spath, FileAccess.READ)
		var sparsed: Variant = JSON.parse_string(sf.get_as_text())
		if sparsed is Dictionary:
			sounds = sparsed
			for sid in sounds.keys():
				var sname := String(sounds[sid].get("name", ""))
				if sname != "":
					sound_by_name[sname] = sounds[sid].get("res", "")
	var vpath := root + "/shapes.bin"
	if FileAccess.file_exists(vpath):
		_load_vectors(vpath)
	var fpath := root + "/filters.json"
	if FileAccess.file_exists(fpath):
		var ff := FileAccess.open(fpath, FileAccess.READ)
		var fparsed: Variant = JSON.parse_string(ff.get_as_text())
		if fparsed is Dictionary:
			filters = fparsed.get("filters", {})


func get_sprite_def(id: int) -> Dictionary:
	if _sprites.has(id):
		return _sprites[id]
	var def: Dictionary = {}
	var path := root + "/sprites/%d.json" % id
	if FileAccess.file_exists(path):
		var f := FileAccess.open(path, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			def = parsed
	_sprites[id] = def
	return def


func get_texture(id: int) -> Texture2D:
	if _textures.has(id):
		return _textures[id]
	var tex: Texture2D = null
	var c: Dictionary = characters.get(str(id), {})
	if c.has("res") and FileAccess.file_exists(String(c["res"])):
		tex = load(String(c["res"])) as Texture2D
	_textures[id] = tex
	return tex


func get_character(id: int) -> Dictionary:
	return characters.get(str(id), {})


func has_vector(id: int) -> bool:
	return vectors.has(str(id))


func get_vector(id: int) -> Dictionary:
	return vectors.get(str(id), {})


# shapes.bin layout: "SVEC", int32 count, then per shape:
# int32 id, 4x float32 rect, int32 nv/ni/npal,
# float32 v[2*nv], int32 i[ni], int32 ci[nv], uint8 pal[4*npal]
func _load_vectors(path: String) -> void:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return
	bin_bytes = f.get_buffer(f.get_length())
	if bin_bytes.size() < 8 or bin_bytes.slice(0, 4).get_string_from_ascii() != "SVEC":
		bin_bytes = PackedByteArray()
		return
	var pos := 4
	var count := bin_bytes.decode_s32(pos)
	pos += 4
	for i in range(count):
		var id := bin_bytes.decode_s32(pos)
		pos += 4
		var rx := bin_bytes.decode_float(pos)
		var ry := bin_bytes.decode_float(pos + 4)
		var rw := bin_bytes.decode_float(pos + 8)
		var rh := bin_bytes.decode_float(pos + 12)
		pos += 16
		var nv := bin_bytes.decode_s32(pos)
		var ni := bin_bytes.decode_s32(pos + 4)
		var npal := bin_bytes.decode_s32(pos + 8)
		pos += 12
		vectors[str(id)] = {"off": pos, "nv": nv, "ni": ni, "npal": npal,
				"rect": Rect2(rx, ry, rw, rh)}
		pos += nv * 8 + ni * 4 + nv * 4 + npal * 4


func get_filter(id: int) -> Dictionary:
	return filters.get(str(id), {})


func get_text_def(id: int) -> Dictionary:
	return text_defs.get(str(id), {})


func get_sound_res(name: String) -> String:
	return String(sound_by_name.get(name, ""))


func get_font(font_id: int) -> Font:
	if _fonts.has(font_id):
		return _fonts[font_id]
	var res := String(font_map.get(str(font_id), ""))
	var font: Font = null
	if res != "" and FileAccess.file_exists(res):
		font = load(res) as Font
	_fonts[font_id] = font
	return font


func make_add_material(add: Color) -> ShaderMaterial:
	var key := "%.3f,%.3f,%.3f,%.3f" % [add.r, add.g, add.b, add.a]
	if _add_materials.has(key):
		return _add_materials[key]
	var m := ShaderMaterial.new()
	m.shader = _add_shader
	m.set_shader_parameter("ct_add", add)
	_add_materials[key] = m
	return m
