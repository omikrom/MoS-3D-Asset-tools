"""TRELLIS image-to-GLB adapter using Microsoft's official pipeline API."""

from __future__ import annotations

import os
from pathlib import Path

from provider_common import add_python_path, load_request, require_home


def main() -> None:
    _path, request = load_request()
    home = require_home("TRELLIS_HOME")
    add_python_path(home)
    os.environ.setdefault("SPCONV_ALGO", "native")
    image_path = request.get("source_resolved")
    if not image_path or not Path(image_path).is_file():
        raise RuntimeError("TRELLIS requires an existing source image")

    from PIL import Image
    from trellis.pipelines import TrellisImageTo3DPipeline
    from trellis.utils import postprocessing_utils

    model = os.environ.get("TRELLIS_MODEL", "microsoft/TRELLIS-image-large")
    pipeline = TrellisImageTo3DPipeline.from_pretrained(model)
    pipeline.cuda()
    geometry = request["spec"].get("geometry", {})
    outputs = pipeline.run(Image.open(image_path), seed=int(geometry.get("seed", 1)))
    glb = postprocessing_utils.to_glb(
        outputs["gaussian"][0],
        outputs["mesh"][0],
        simplify=float(geometry.get("simplify", 0.5)),
        texture_size=int(request["spec"].get("texture", {}).get("resolution", 2048)),
    )
    output = Path(request["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    glb.export(str(output))


if __name__ == "__main__":
    main()
