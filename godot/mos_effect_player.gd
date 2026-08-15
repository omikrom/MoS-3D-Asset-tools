class_name MosEffectPlayer
extends AnimatedSprite2D

signal gameplay_event(event_id: StringName)

var _frame_events: Dictionary = {}


func _ready() -> void:
	frame_changed.connect(_on_frame_changed)


func configure_events(events: Array) -> void:
	_frame_events.clear()
	for event: Dictionary in events:
		_frame_events[int(event.get("frame", -1))] = StringName(event.get("id", ""))


func play_effect(animation_name: StringName, events: Array = []) -> void:
	configure_events(events)
	play(animation_name)


func _on_frame_changed() -> void:
	if _frame_events.has(frame):
		gameplay_event.emit(_frame_events[frame])
