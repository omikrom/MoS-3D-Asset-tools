from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from common import armatures, import_asset, load_request, mesh_objects, normalize_scene, write_json


def main() -> None:
    _request_path, request = load_request()
    source = Path(request["input"])
    output = Path(request["output"])
    if not source.is_file():
        raise RuntimeError(f"Prepared mesh input does not exist: {source}")
    import_asset(source)
    meshes = mesh_objects()
    if not meshes:
        raise RuntimeError("Imported source contains no mesh objects")

    asset_id = request["asset_id"]
    layer = request["spec"].get("render", {}).get("layer", "body")
    for index, obj in enumerate(meshes):
        obj.name = f"{asset_id}__{layer}__{index:03d}"
        obj["mos_asset_id"] = asset_id
        obj["mos_layer"] = layer
        for polygon in obj.data.polygons:
            polygon.use_smooth = True

    geometry = request["spec"].get("geometry", {})
    inventory = normalize_scene(geometry.get("height_metres"))
    inventory.update({
        "asset_id": asset_id,
        "meshes": [obj.name for obj in meshes],
        "armatures": [obj.name for obj in armatures()],
        "materials": sorted({slot.material.name for obj in meshes for slot in obj.material_slots if slot.material}),
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix(".blend")))
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_apply=True,
        export_animations=True,
        export_materials="EXPORT",
    )
    write_json(output.with_suffix(".inventory.json"), inventory)


if __name__ == "__main__":
    main()
