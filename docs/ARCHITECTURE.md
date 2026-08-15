# Architecture

## Goal

The factory treats 3D as an **offline authoring format** and sprites as the
runtime format. Source models can therefore be extremely detailed: runtime
performance depends on the exported atlas size and frame count, not the source
polygon count.

The important constraints are visual consistency, shared animation, stable
camera/pivots and repeatability. Those are encoded as data rather than left as
per-artist Blender settings.

`profiles/asset_taxonomy.toml` is the coverage checklist for characters,
weapon families, equipment slots, creature rigs, world objects, effects and UI
derivatives. It prevents the first character proof from hard-coding assumptions
that block later asset categories.

## Stages

| Stage | Input | Output | Default implementation |
|---|---|---|---|
| `source` | Prompt, image, model or frames | Resolved source record | Built in |
| `shape` | Reference image or existing mesh | High-resolution GLB | Hunyuan3D, TRELLIS, manual/import |
| `texture` | Mesh plus reference | Textured PBR GLB | Hunyuan Paint or passthrough |
| `prepare` | Arbitrary GLB/FBX/OBJ | Normalized GLB plus inventory | Headless Blender |
| `rig` | Normalized deformable mesh | Skinned GLB | UniRig or manual |
| `animate` | Rigged GLB plus motion library | Blender scene with named actions | Headless Blender |
| `render` | Prepared scene | Direction/action/pass PNG frames | Headless Blender |
| `pack` | Frame tree | Deterministic atlases and JSON | Pillow |
| `export` | Atlas manifest | Godot `SpriteFrames` `.tres` | Built in |

Every stage receives a self-contained `request.json` and has a declared output.
An external provider only needs to understand that contract; it does not import
the pipeline package. This makes model upgrades and remote GPU execution much
less disruptive.

`mos plan-all` topologically sorts asset dependencies. In particular,
`rig.transfer_weights_from = "human_male"` guarantees that the shared skinned
body is built before an armour worker attempts weight transfer. Dependency
cycles are rejected before any heavyweight process starts.

For disconnected workers, `mos request <spec> <stage>` emits just one portable
job and `mos accept <spec> <stage> <result>` records the returned file and its
SHA-256 hash. The generating model, machine and Python environment therefore do
not need to be coupled to Blender, Pillow or Godot export.

## Canonical coordinate and sprite contract

- Blender coordinates: Z up, metres, model centred on X/Y with its feet at Z=0.
- Default character forward axis: -Y (towards the south camera).
- Original direction order: south, south-west, west, north-west, north,
  north-east, east, south-east.
- Every frame for a modular rig uses the same canvas size and pivot.
- Modular layers must never be independently trimmed.
- Animation sampling is declared by clip (`fps`, exported frame count, loop and
  events), independent of the source animation's native frame range.
- Render passes are aligned pixel-for-pixel.

## Modular humans and equipment

Soma's original client already composited aligned body/equipment resources. The
new pipeline keeps that useful property while replacing the old LSP pixels with
PNG atlases.

Canonical humanoid layers are:

1. shadow/effect-under;
2. base body;
3. trousers/legs;
4. boots;
5. chest armour;
6. helmet/hair;
7. arms and active weapon;
8. shield;
9. front effects.

All skinned clothing targets `soma_humanoid_v1`. Rigid equipment targets named
sockets such as `weapon_right`, `shield`, `back` and `head`. Each layer is
rendered with the same rig, action, direction, camera and frame sampling.

Whole-layer draw order is stored per direction in `profiles/soma_legacy.toml`.
For weapons or capes that pass both behind and in front of the body, the planned
production refinement is an object-ID/depth compositor that exports `_back`
and `_front` fragments from the same render. Until then, items can be authored
as explicit back/front render groups.

## Monsters

Humanoid monsters can reuse the Soma humanoid rig and motion library. Creatures
use category-specific shared rigs:

- `soma_quadruped_v1`;
- `soma_winged_v1`;
- `soma_serpentine_v1`;
- bespoke boss rigs where needed.

Unlike player armour, most monsters should be baked as a single colour layer.
This prevents unnecessary combinations and makes unusual silhouettes easier.

## Effects, magic and blood

VFX are normal assets with a smaller stage set:

- projectile travel and impact;
- cast/charge/release;
- ground decal and area loop;
- aura/buff/debuff;
- blood impact, droplets and optional ground decal;
- death dissolve, smoke and debris;
- environmental fire, water, portals and weather.

Blender geometry nodes/particles are ideal for deterministic physical effects;
image/video generation can supply flipbooks; hand-painted frames can enter at
`source.mode = "frames"`. The render contract records blend mode (`mix`, `add`,
`multiply`), anchor and gameplay events independently of the artwork.

## Caching and reproducibility

Each asset has `workspace/assets/<id>/` with one directory per stage. Requests,
outputs and `state.json` make a build resumable. A production extension will
hash the specification, source files, provider version and profile so a stage
is automatically invalidated when one of its true inputs changes.

Generated files do not belong in Git. Specifications, profiles, prompts,
provider adapters and small curated reference images do.

## Recommended delivery phases

### Phase 1 — vertical slice

One male human, iron armour, sword and shield; peaceful idle, walk, attack, hit,
cast and death; eight directions; colour atlas imported into Godot.

### Phase 2 — modular catalogue

Female body, complete 19-slot compatibility motion set, weapon families,
armour/helmet/boot layers, composition metadata and inventory portraits.

### Phase 3 — creatures and world

Shared monster rigs, props, trees, buildings, doors, map objects and collision
metadata.

### Phase 4 — VFX

Magic families, projectiles, impacts, blood variants, ground decals, deaths,
weather and screen-space polish.

### Phase 5 — factory UI and farm

Queue dashboard, thumbnails, approve/reject gates, batch variants, remote GPU
workers and automatic Godot content-package publishing.
