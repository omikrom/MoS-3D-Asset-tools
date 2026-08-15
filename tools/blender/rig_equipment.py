from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from common import armatures, find_project_root, import_asset, import_asset_into_current, load_request, mesh_objects, write_json


def workspace_path(root: Path) -> Path:
    with (root / "mos.toml").open("rb") as handle:
        value = tomllib.load(handle).get("project", {}).get("workspace", "workspace")
    return (root / value).resolve()


def main() -> None:
    request_path, request = load_request()
    root = find_project_root(request_path)
    source = Path(request["input"])
    output = Path(request["output"])
    rig_spec = request["spec"].get("rig", {})
    template_asset = rig_spec.get("transfer_weights_from")
    if not template_asset:
        raise RuntimeError("blender_weight_transfer requires rig.transfer_weights_from")
    template = workspace_path(root) / "assets" / template_asset / "rig" / f"{template_asset}.glb"
    if not template.is_file():
        raise RuntimeError(f"Build the weight-transfer template first: {template}")

    import_asset(source)
    targets = list(mesh_objects())
    before = set(bpy.data.objects.keys())
    import_asset_into_current(template)
    imported = [obj for obj in bpy.data.objects if obj.name not in before]
    sources = [obj for obj in imported if obj.type == "MESH" and obj.vertex_groups]
    imported_rigs = [obj for obj in imported if obj.type == "ARMATURE"]
    if not sources or not imported_rigs:
        raise RuntimeError("Template must contain a skinned mesh and armature")
    body = max(sources, key=lambda obj: len(obj.data.vertices))
    rig = max(imported_rigs, key=lambda obj: len(obj.data.bones))

    for target in targets:
        for group in body.vertex_groups:
            if target.vertex_groups.get(group.name) is None:
                target.vertex_groups.new(name=group.name)
        modifier = target.modifiers.new("MOS_WeightTransfer", "DATA_TRANSFER")
        modifier.object = body
        modifier.use_vert_data = True
        modifier.data_types_verts = {"VGROUP_WEIGHTS"}
        modifier.vert_mapping = "POLYINTERP_NEAREST"
        bpy.context.view_layer.objects.active = target
        target.select_set(True)
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        target.select_set(False)
        armature_modifier = target.modifiers.new("MOS_Armature", "ARMATURE")
        armature_modifier.object = rig
        world = target.matrix_world.copy()
        target.parent = rig
        target.matrix_world = world

    for obj in sources:
        bpy.data.objects.remove(obj, do_unlink=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix(".blend")))
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_apply=True,
                              export_animations=False, export_materials="EXPORT")
    write_json(output.with_suffix(".weights.json"), {
        "template_asset": template_asset,
        "template": str(template),
        "armature": rig.name,
        "targets": [target.name for target in targets],
    })


if __name__ == "__main__":
    main()
