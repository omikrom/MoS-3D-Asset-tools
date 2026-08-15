"""Hunyuan3D 2.1 adapter using the official diffusers-like APIs."""

from __future__ import annotations

import os
from pathlib import Path

from provider_common import add_python_path, export_result, load_request, require_home


def shape(request: dict, home: Path, output: Path) -> None:
    image = request.get("source_resolved")
    if not image or not Path(image).is_file():
        raise RuntimeError("Hunyuan3D shape generation requires an existing source image")
    add_python_path(home / "hy3dshape")
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

    model = os.environ.get("HUNYUAN3D_MODEL", "tencent/Hunyuan3D-2.1")
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(model)
    result = pipeline(image=image)
    export_result(result, output)


def texture(request: dict, home: Path, output: Path) -> None:
    image = request.get("source_resolved")
    mesh = request.get("input")
    if not image or not Path(image).is_file() or not mesh or not Path(mesh).is_file():
        raise RuntimeError("Hunyuan3D painting requires both the source image and generated mesh")
    add_python_path(home / "hy3dpaint")
    from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline

    texture = request["spec"].get("texture", {})
    configuration = Hunyuan3DPaintConfig(
        max_num_view=int(texture.get("max_num_view", 6)),
        resolution=int(texture.get("resolution", 2048)),
    )
    pipeline = Hunyuan3DPaintPipeline(configuration)
    result = pipeline(mesh, image_path=image)
    export_result(result, output)


def main() -> None:
    _path, request = load_request()
    home = require_home("HUNYUAN3D_HOME")
    output = Path(request["output"])
    if request["stage"] == "shape":
        shape(request, home, output)
    elif request["stage"] == "texture":
        texture(request, home, output)
    else:
        raise RuntimeError(f"Unsupported Hunyuan3D stage: {request['stage']}")


if __name__ == "__main__":
    main()
