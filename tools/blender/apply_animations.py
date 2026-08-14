from __future__ import annotations

import json
import math
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from common import armatures, find_project_root, import_asset, import_asset_into_current, load_request, mesh_objects, write_json


BONE_PATH = re.compile(r'pose\.bones\["([^"]+)"\]')


def load_bone_map(root: Path, request: dict) -> dict[str, str]:
    map_name = request["spec"].get("rig", {}).get("bone_map")
    if not map_name:
        return {}
    path = root / "profiles" / "bone_maps" / f"{map_name}.toml"
    with path.open("rb") as handle:
        return dict(tomllib.load(handle).get("bones", {}))


def import_animation(path: Path) -> tuple[list[bpy.types.Object], list[bpy.types.Action]]:
    object_names = set(bpy.data.objects.keys())
    action_names = set(bpy.data.actions.keys())
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=True)
    elif suffix == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, destination):
            destination.actions = source.actions
    else:
        raise RuntimeError(f"Unsupported animation source: {path}")
    objects = [obj for obj in bpy.data.objects if obj.name not in object_names]
    actions = [action for action in bpy.data.actions if action.name not in action_names]
    return objects, actions


def mapped_action(action: bpy.types.Action, bone_map: dict[str, str]) -> None:
    if not bone_map:
        return
    for curve in getattr(action, "fcurves", []):
        for old_name, new_name in bone_map.items():
            curve.data_path = curve.data_path.replace(f'pose.bones["{old_name}"]', f'pose.bones["{new_name}"]')


def action_bones(action: bpy.types.Action) -> set[str]:
    names: set[str] = set()
    for curve in getattr(action, "fcurves", []):
        match = BONE_PATH.search(curve.data_path)
        if match:
            names.add(match.group(1))
    return names


def main() -> None:
    request_path, request = load_request()
    source = Path(request["input"])
    output = Path(request["output"])
    import_asset(source)
    root = find_project_root(request_path)
    equipment_meshes = list(mesh_objects())
    rigs = armatures()
    clips = request["spec"].get("animations", [])
    attachment = request["spec"].get("attachment", {})
    rig_source_value = attachment.get("rig_source")
    if clips and not rigs and rig_source_value:
        rig_source = Path(rig_source_value)
        if not rig_source.is_absolute():
            spec_candidate = (Path(request["spec_path"]).parent / rig_source).resolve()
            rig_source = spec_candidate if spec_candidate.exists() else (root / rig_source).resolve()
        if not rig_source.is_file():
            raise RuntimeError(f"Attachment rig source not found: {rig_source}")
        import_asset_into_current(rig_source)
        rigs = armatures()
    if clips and not rigs:
        raise RuntimeError("Animation stage requires a rigged scene")
    target = max(rigs, key=lambda obj: len(obj.data.bones)) if rigs else None
    target_bones = set(target.data.bones.keys()) if target else set()
    rig_profile_name = request["spec"].get("rig", {}).get("profile") or attachment.get("rig_profile")
    if target and rig_profile_name:
        rig_profile_path = root / "profiles" / "rigs" / f"{rig_profile_name}.toml"
        with rig_profile_path.open("rb") as handle:
            rig_profile = tomllib.load(handle)
        required = set(rig_profile.get("required_bones", {}).get("body", []))
        missing_required = sorted(required - target_bones)
        if missing_required:
            raise RuntimeError(
                f"Rig {target.name} does not satisfy {rig_profile_name}; missing: {', '.join(missing_required)}. "
                "Rename/refine the auto-rig before animation."
            )
    bone_map = load_bone_map(root, request)
    imported: list[dict] = []

    if target and attachment.get("socket"):
        socket_profile = attachment.get("rig_profile", request["spec"].get("rig", {}).get("profile", "soma_humanoid_v1"))
        profile_path = root / "profiles" / "rigs" / f"{socket_profile}.toml"
        with profile_path.open("rb") as handle:
            profile = tomllib.load(handle)
        bone_name = profile.get("sockets", {}).get(attachment["socket"], attachment["socket"])
        if bone_name not in target.data.bones:
            raise RuntimeError(f"Attachment socket bone {bone_name!r} does not exist on {target.name}")
        for obj in equipment_meshes:
            obj.parent = target
            obj.parent_type = "BONE"
            obj.parent_bone = bone_name
            obj.location = tuple(float(value) for value in attachment.get("offset_metres", [0.0, 0.0, 0.0]))
            obj.rotation_euler = tuple(math.radians(float(value)) for value in attachment.get("rotation_degrees", [0.0, 0.0, 0.0]))


    for clip in clips:
        value = clip.get("source")
        if not value:
            continue
        clip_path = Path(value)
        if not clip_path.is_absolute():
            clip_path = (Path(request["spec_path"]).parent / clip_path).resolve()
        if not clip_path.is_file():
            root_candidate = (root / value).resolve()
            if root_candidate.is_file():
                clip_path = root_candidate
        if not clip_path.is_file():
            raise RuntimeError(f"Animation source not found: {clip_path}")
        new_objects, new_actions = import_animation(clip_path)
        if not new_actions:
            raise RuntimeError(f"No Blender actions found in {clip_path}")
        action = max(new_actions, key=lambda candidate: candidate.frame_range[1] - candidate.frame_range[0])
        mapped_action(action, bone_map)
        missing = sorted(action_bones(action) - target_bones)
        if missing:
            raise RuntimeError(
                f"Animation {clip['id']} is incompatible with the target rig; missing bones: {', '.join(missing[:12])}. "
                "Add/select a bone map or retarget it before rendering."
            )
        action.name = f"mos::{clip['id']}"
        action.use_fake_user = True
        action["mos_clip_id"] = clip["id"]
        action["mos_fps"] = float(clip["fps"])
        action["mos_frames"] = int(clip["frames"])
        action["mos_loop"] = bool(clip.get("loop", True))
        action["mos_events"] = json.dumps(clip.get("events", []))
        imported.append({"id": clip["id"], "action": action.name, "source": str(clip_path), "missing_bones": []})
        for obj in new_objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    if target and target.animation_data is None:
        target.animation_data_create()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    write_json(output.with_suffix(".animations.json"), {"target": target.name if target else None, "clips": imported})


if __name__ == "__main__":
    main()
