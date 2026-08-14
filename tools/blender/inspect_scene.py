from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from common import armatures, import_asset, load_request, mesh_objects, world_bounds, write_json


def main() -> None:
    _request_path, request = load_request()
    import_asset(Path(request["input"]))
    minimum, maximum = world_bounds()
    report = {
        "input": request["input"],
        "bounds_min": list(minimum),
        "bounds_max": list(maximum),
        "meshes": [{"name": obj.name, "vertices": len(obj.data.vertices), "polygons": len(obj.data.polygons)} for obj in mesh_objects()],
        "armatures": [{"name": obj.name, "bones": [bone.name for bone in obj.data.bones]} for obj in armatures()],
        "actions": [{"name": action.name, "frame_range": list(action.frame_range)} for action in bpy.data.actions],
    }
    write_json(Path(request["output"]), report)


if __name__ == "__main__":
    main()
