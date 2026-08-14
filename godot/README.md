# Godot runtime helpers

`mos_sprite_actor.gd` layers multiple exported `SpriteFrames` resources and
keeps action/direction changes synchronized. Use it for player characters and
other equipment-bearing humanoids. Monsters normally need only one registered
body layer.

`mos_effect_player.gd` plays a generated effect animation and emits declared
frame events such as `damage`, `release_magic` or `spawn_decal`.

The helpers intentionally do not assume a particular game repository layout.
Copy them into the Godot project or turn this directory into an addon when the
game-side API is settled.
