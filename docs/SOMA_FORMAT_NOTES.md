# Original Soma asset notes

These notes were derived from the recovered client source in
[`soma-space/files`](https://github.com/soma-space/files), especially
`CharRes`, `ArmatureRes`, `AniObj`, `User`, `MagicRes`, `BloodRes` and
`illstruct`.

They exist to preserve behaviour and naming—not to make the new game depend on
the old binary formats.

## Animation format (`.ani`)

The header stores the `ANI` identifier, remark, direction count and animation
count. Each animation stores a name, flags, frames-per-second value, maximum
frames and a table of signed 16-bit sprite indices.

The lookup is direction-major:

```text
sprite_index = frame_table[direction * frames_per_direction + frame]
```

The original client defines a maximum of 32 sequence frames and uses eight
human directions. Individual human resource pairs are named broadly like
`man<character><action>.ani/.spl`.

## Sprite format (`.spl`)

The sprite header records the sprite count, dimensions, colour key and source
bitmap metadata. Each frame has a clip rectangle, encoded-line count and data
size. Pixel data is a line-oriented transparent-run format using 16-bit
RGB565/555 conversion in the client.

The new factory exports transparent PNGs and JSON/TRES metadata. A legacy SPL
writer may be added for testing old clients, but it is not required by Godot.

## Human action slots

| Slot | Meaning recovered from `CUser::SetMotion` |
|---:|---|
| 0 | Standard combat idle |
| 1 | Two-handed combat idle |
| 2 | Polearm combat idle |
| 3 | Crossbow action |
| 4 | Standard walk |
| 5 | Two-handed walk |
| 6 | Polearm walk |
| 7 | Unarmed attack |
| 8 | One-handed sword/wand attack |
| 9 | Two-handed attack |
| 10 | Spear attack |
| 11 | Bow attack |
| 12 | Axe attack |
| 13 | Hit reaction |
| 14 | Magic/cast |
| 15 | Death |
| 16 | Run |
| 17 | Dual-sword attack |
| 18 | Peaceful idle |

The new game should use named actions and retain `legacy_slot` as compatibility
metadata. It is free to add block, dodge, emotes, alternate attacks and other
modern clips without squeezing them into the 19 old slots.

## Direction order

`Down, DownLeft, Left, UpLeft, Up, UpRight, Right, DownRight` maps to:

`south, south_west, west, north_west, north, north_east, east, south_east`.

## Layered armature resources

The client maintains seven equipment resource groups around the body and
changes draw order by facing direction. Recovered semantic groups include
armour, helmet, boots, trousers/jeans, shield, arms/weapon and shadow. Each
group uses the same action/direction/frame lookup so its pixels align.

This strongly supports a modern layered-atlas system for player equipment.

## Magic and blood

Magic and blood load their own sprite sequences instead of being embedded in
the character sheet. Magic uses additive or normal blending; the source sets a
50 ms default magic frame delay. Blood selects separate resource kinds and
plays ordinary transparent sequences.

The modern equivalent is a standalone effect manifest with colour/emission/
depth frames, a blend mode and named gameplay events.
