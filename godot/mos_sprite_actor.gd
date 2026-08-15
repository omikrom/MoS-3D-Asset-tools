class_name MosSpriteActor
extends Node2D

## Runtime controller for aligned, modular MoS SpriteFrames layers.

@export var direction: StringName = &"south"
@export var action: StringName = &"peaceful_idle"

var _layers: Dictionary = {}
var _draw_orders: Dictionary = {}


func register_layer(layer_name: StringName, frames: SpriteFrames, default_z: int = 0) -> AnimatedSprite2D:
	var sprite := AnimatedSprite2D.new()
	sprite.name = String(layer_name)
	sprite.sprite_frames = frames
	sprite.z_index = default_z
	add_child(sprite)
	_layers[layer_name] = sprite
	_play_layer(sprite)
	_apply_draw_order()
	return sprite


func remove_layer(layer_name: StringName) -> void:
	var sprite: AnimatedSprite2D = _layers.get(layer_name)
	if sprite:
		_layers.erase(layer_name)
		sprite.queue_free()


func set_draw_orders(value: Dictionary) -> void:
	_draw_orders = value
	_apply_draw_order()


func play_action(next_action: StringName) -> void:
	action = next_action
	for sprite: AnimatedSprite2D in _layers.values():
		_play_layer(sprite)


func face(next_direction: StringName) -> void:
	if direction == next_direction:
		return
	direction = next_direction
	for sprite: AnimatedSprite2D in _layers.values():
		_play_layer(sprite)
	_apply_draw_order()


func set_layer_visible(layer_name: StringName, visible: bool) -> void:
	var sprite: AnimatedSprite2D = _layers.get(layer_name)
	if sprite:
		sprite.visible = visible


func _play_layer(sprite: AnimatedSprite2D) -> void:
	var animation := StringName("%s_%s" % [action, direction])
	if sprite.sprite_frames and sprite.sprite_frames.has_animation(animation):
		sprite.play(animation)
	else:
		sprite.stop()


func _apply_draw_order() -> void:
	var order: Array = _draw_orders.get(String(direction), [])
	for index in order.size():
		var sprite: AnimatedSprite2D = _layers.get(StringName(order[index]))
		if sprite:
			sprite.z_index = index
