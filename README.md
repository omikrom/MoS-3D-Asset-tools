# MoS Asset Factory

Model-agnostic tooling for producing modern, high-detail 3D source assets and
rendering them into direction-aware sprite sheets for a Godot remake of
**Myth of Soma**.

The factory is deliberately split into light orchestration code and optional
heavy tools. The repository can be cloned, validated, planned and tested
without Blender or an AI model installed. Hunyuan3D, TRELLIS, UniRig, Blender
and animation libraries are connected later through configurable providers.

## What it produces

- Characters and monsters with a shared rig and animation vocabulary.
- Modular body, armour, helmet, boots, weapon and shield sprite layers.
- Static and animated weapons, props, buildings and environment objects.
- Magic, projectile, impact, aura, blood and death-effect sprite sequences.
- Eight-direction colour sprites plus optional normal, depth, emission, mask
  and shadow passes.
- Deterministic atlases, JSON manifests and Godot `SpriteFrames` resources.
- Automatic multi-page atlases when a complete Soma action set exceeds one texture.
- A resumable build record with inputs, tool versions and output hashes.

## Pipeline

```text
concept/reference -> 3D generation/import -> mesh preparation -> rigging
 -> animation -> multi-direction render -> atlas pack -> Godot export
```

Every stage is cached and replaceable. A character made with Hunyuan3D can be
re-rigged with UniRig, animated from a shared GLB library and rendered again
without regenerating its geometry.

## Quick start (no models required)

Requires Python 3.11+.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
mos doctor
mos validate examples/assets/human_male.toml
mos plan examples/assets/human_male.toml
mos plan-all examples/assets
```

On Linux/macOS, activate with `source .venv/bin/activate`.

Run the built-in tests:

```bash
python -m unittest discover -s tests -v
```

## Useful commands

```bash
mos doctor
mos models list --for examples/assets
mos models install --for examples/assets --dry-run
mos models install --for examples/assets --weights
mos validate examples/assets
mos plan examples/assets/human_male.toml
mos build examples/assets/human_male.toml --dry-run
mos build-all examples/assets --dry-run
mos build examples/assets/human_male.toml --from-stage render
mos request examples/assets/human_male.toml shape
mos accept examples/assets/human_male.toml shape D:\generated\human_male.glb
mos status human_male
mos pack path/to/render-job.json
```

`mos plan` never launches heavyweight tools. It shows the resolved stages,
providers, inputs and outputs. `mos build --dry-run` additionally writes the
resolved job requests into the workspace.

`mos request` and `mos accept` are the handoff boundary for tools that run in a
different Python environment or on another computer. The request contains the
prompt, resolved source, provider settings, input and exact expected output;
`accept` copies a returned GLB/Blend result into the build, records its hash and
prints the command that resumes the next stage.

`mos models install --for <specs>` reads the asset providers and downloads only
the model repositories those assets require. Add `--weights` to pre-cache their
Hugging Face checkpoints; without it, compatible upstream pipelines download
weights on first use. The installer is resumable, refuses to overwrite non-Git
directories, supports recursive repositories such as TRELLIS, and records
`HF_HOME` plus repository locations in the ignored local `.env` file. Use
`--dry-run` first to see the exact downloads.

`source.mode = "frames"` is a complete no-Blender path for generated or painted
VFX flipbooks. Place frames under
`color/<clip>/<direction>/<frame>.png`; the normal pack and Godot export stages
then run directly. This is suitable for magic, blood, smoke and impact effects.

## Repository map

| Path | Purpose |
|---|---|
| `examples/assets/` | Character, equipment, monster, prop and VFX specifications |
| `profiles/` | Soma-compatible actions, directions, rigs and render presets |
| `schemas/` | Machine-readable asset specification schema |
| `src/mos_asset_factory/` | CLI, pipeline, providers, packer and exporters |
| `tools/blender/` | Headless Blender preparation, inspection and rendering scripts |
| `tools/providers/` | Stable adapter boundary for external AI repositories |
| `docs/` | Architecture, installation, original-format notes and authoring guide |
| `workspace/` | Generated/intermediate files; ignored by Git |

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system design and
[docs/INSTALL_MODELS.md](docs/INSTALL_MODELS.md) when installing the heavyweight
tools on the production PC.

## Original Soma compatibility

The recovered client source uses eight directions in this order:

`south, south-west, west, north-west, north, north-east, east, south-east`

Human resources use 19 numbered animation slots (`0..18`) and separate aligned
layers for body, trousers, boots, armour, helmet, weapon/arms, shield and
shadow. The factory preserves those semantics in `profiles/soma_legacy.toml`
while exporting friendlier named actions for Godot.

The `soma-space/files` repository is treated as research/reference material and
is not copied into generated deliverables.
