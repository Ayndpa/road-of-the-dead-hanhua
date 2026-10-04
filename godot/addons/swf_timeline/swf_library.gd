class_name SwfLibrary
extends RefCounted

## Loads the asset bundle produced by exporter/swf_to_godot.py and caches
## textures / sprite definitions for the SwfMovieClip runtime.

var root: String
var characters: Dictionary = {}
var symbols: Dictionary = {}
var fps: float = 30.0

var _textures: Dictionary = {}
var _sprites: Dictionary = {}
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


func make_add_material(add: Color) -> ShaderMaterial:
	var key := "%.3f,%.3f,%.3f,%.3f" % [add.r, add.g, add.b, add.a]
	if _add_materials.has(key):
		return _add_materials[key]
	var m := ShaderMaterial.new()
	m.shader = _add_shader
	m.set_shader_parameter("ct_add", add)
	_add_materials[key] = m
	return m
