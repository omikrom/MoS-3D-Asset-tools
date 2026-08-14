# Installing the heavy tools

Keep every model in its own environment. Their CUDA/PyTorch/compiled-extension
requirements conflict; the factory itself should remain a small ordinary
Python environment.

Copy `.env.example` to `.env`, edit paths, then enable providers in `mos.toml`.
Do not commit `.env`, model weights, generated meshes or caches.

The factory can download the required upstream code and optionally pre-cache
weights automatically:

```powershell
mos models list --for examples/assets
mos models install --for examples/assets --dry-run
mos models install --for examples/assets --weights
```

The `--for` scan currently selects Hunyuan3D and UniRig for the included asset
specifications; TRELLIS remains optional. Downloads go into ignored `external/`
and `models/huggingface/` directories. Existing Git checkouts are preserved and
non-Git destination directories are never overwritten. Some Hugging Face
repositories may still require accepting their licence or logging in with
`hf auth login`.

Repository and checkpoint downloads can be automated safely, but the Python
environments remain isolated and hardware-specific. Follow each section below
for CUDA/ROCm dependencies, then set its `*_PYTHON` value in `.env` and enable
the corresponding provider in `mos.toml`.

## Hardware reality

| Tool | Official/reported requirement | RX 9070 XT 16 GB assessment |
|---|---|---|
| Hunyuan3D 2.1 shape | About 10 GB VRAM | Capacity fits; AMD/Windows backend needs proving |
| Hunyuan3D Paint 2.1 | About 21 GB VRAM | Requires low-VRAM/offload or a larger remote GPU |
| TRELLIS image-large | NVIDIA CUDA, at least 16 GB, Linux tested | Not a sensible first local target on AMD Windows |
| UniRig | PyTorch plus CUDA-oriented `spconv`, PyG and flash-attn stack | Likely WSL/remote NVIDIA unless the stack gains usable ROCm support |
| Blender render | Cross-platform; GPU optional | Good local fit; CPU rendering is also acceptable offline |

For this specific PC, begin with Blender and the factory locally. Prove
Hunyuan shape generation separately. Treat texture generation and UniRig as
replaceable workers: local if they run reliably, otherwise ComfyUI, WSL, a
temporary rented NVIDIA GPU or manually produced results placed at the declared
stage output.

## Blender

Install Blender 4.3+ (4.5 LTS is a sensible target), set `BLENDER_EXE` in
`.env`, and change:

```toml
[tools.blender]
enabled = true
```

Verify with `mos doctor`.

## Hunyuan3D 2.1

Follow the official repository's current installation exactly; it is tested
with Python 3.10 and its documented PyTorch build. The paint renderer has extra
compiled components beyond shape generation.

```bash
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 external/Hunyuan3D-2.1
```

Set `HUNYUAN3D_HOME` and `HUNYUAN_PYTHON`, then enable
`providers.shape.hunyuan3d` and, once painting works,
`providers.texture.hunyuan3d`.

The supplied adapter follows the official diffusers-like calls:

- `Hunyuan3DDiTFlowMatchingPipeline` for image-to-shape;
- `Hunyuan3DPaintPipeline` for PBR texturing.

Upstream APIs can change. Keep fixes inside the adapter rather than changing
asset specifications.

## TRELLIS

TRELLIS officially targets Linux/CUDA with at least 16 GB NVIDIA VRAM. Its own
documentation recommends image conditioning over direct text conditioning.

```bash
git clone --recurse-submodules https://github.com/microsoft/TRELLIS external/TRELLIS
```

After the official `setup.sh` environment works independently, set
`TRELLIS_HOME`/`TRELLIS_PYTHON` and enable `providers.shape.trellis`. Set an
asset's texture provider to `passthrough`, because TRELLIS already produces the
textured GLB in the shape stage.

## UniRig

The official workflow is three commands: predict skeleton, predict skinning,
then merge the prediction with the source mesh. The included adapter performs
those same stages through the repository's Bash launch scripts.

```bash
git clone https://github.com/VAST-AI-Research/UniRig external/UniRig
```

Set `UNIRIG_HOME`/`UNIRIG_PYTHON`, ensure `bash` is available, enable
`providers.rig.unirig`, and test UniRig on one normalized GLB outside the full
pipeline first.

Auto-rigging is an approval gate, not infallible. Check shoulders, elbows,
wrists, fingers, hips, knees, ankles, cloth and tails before generating hundreds
of frames. Bad weights become much more expensive after sprite production.

## Manual and remote providers

`kind = "manual"` still writes a complete `request.json` and expected output
path. That enables an immediate workflow even when a model only runs through a
web UI or another machine:

1. run `mos request <spec> shape` (or `rig`, `texture`, `prepare`, `animate`);
2. copy the generated `request.json` to the worker or use it beside a web UI;
3. return a GLB for mesh stages or a Blend file for the animation stage;
4. run `mos accept <spec> <stage> <returned-file>`;
5. use the exact resume command printed by `mos accept`.

An automated remote provider can send that same JSON to a GPU worker and
download the declared result without changing any asset specification.
