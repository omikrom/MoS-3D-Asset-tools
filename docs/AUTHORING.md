# Asset authoring guide

## Choose a category

| Category | Typical rigging | Typical output |
|---|---|---|
| Character | Shared humanoid rig | Modular aligned layers |
| Armour/clothing | Weight transfer to humanoid | One aligned equipment layer |
| Weapon/shield | Rigid socket attachment | Aligned equipment layer and inventory icon |
| Humanoid monster | Shared humanoid/monster rig | Baked body layer |
| Creature | Shared category or bespoke rig | Baked body layer |
| Prop/building/tree | None, optional simple bones | 1/4/8 static directions |
| Magic/projectile/blood | Procedural, frames or simple motion | Alpha/additive effect atlas |

Copy the closest file from `examples/assets/`, change `asset.id`, and run
`mos validate` followed by `mos plan`.

## Reference images

Use a clean full-object image with no cropping or hard background. Characters
should begin in an A-pose. A good front/three-quarter concept is usually more
useful than text-to-3D; multi-view references are better when the provider
supports them.

Generated backs, hands, underarms and thin weapon blades need inspection.
Texture detail cannot repair bad silhouette or topology.

## Approval gates

Stop and review after:

1. shape/texture — silhouette, missing parts, material identity;
2. preparation — scale, origin, forward direction, holes and separate pieces;
3. rig — bone hierarchy and extreme-pose deformation;
4. first animation — foot sliding and weapon grip;
5. one-direction render — framing, pivot and readability at actual game scale;
6. complete atlas — direction consistency and loop seams.

Only batch variants after the base asset clears all six gates.

## Sprite readability

The source can be photorealistic, but a 384 px character still needs strong
silhouettes, larger-than-real details, controlled values and uncluttered
materials. Render large and downsample. Thin straps and delicate engravings may
look wonderful in Blender and disappear completely in play.

Avoid independently trimming modular layers. The shared canvas and pivot are
what make armour and weapon combinations align.

## Importing finished frames

Magic, blood and other effects do not have to pass through 3D. Use
`source.mode = "frames"`, point `source.path` at a directory and arrange PNGs
like this:

```text
frames/
  color/
    impact_small/
      south/
        0000.png
        0001.png
  emission/                 # optional aligned pass
    impact_small/south/...
```

Declare the same clip names, frame counts and directions in the asset TOML.
Set `source.frame_size` when the PNG canvas differs from the chosen render
profile. Running `mos build` then validates the frame sequence, creates as many
atlas pages as required and exports the Godot resource without launching
Blender.
