from __future__ import annotations

import json
import math
import shutil
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy

from common import armatures, ensure_camera, find_project_root, load_request, top_level_objects, write_json


DEFAULT_DIRECTIONS = [
    "south", "south_west", "west", "north_west",
    "north", "north_east", "east", "south_east",
]


def load_profile(root: Path, request: dict) -> dict:
    name = request["spec"].get("render", {}).get("profile", "character")
    path = root / "profiles" / "render" / f"{name}.toml"
    with path.open("rb") as handle:
        profile = tomllib.load(handle)
    profile.update(request["spec"].get("render", {}))
    return profile


def ensure_lights() -> None:
    if any(obj.type == "LIGHT" and obj.name.startswith("MOS_") for obj in bpy.context.scene.objects):
        return
    settings = [
        ("MOS_Key", "AREA", (4.0, -4.0, 7.0), 1100.0, 5.0),
        ("MOS_Fill", "AREA", (-4.0, -2.0, 4.0), 550.0, 4.0),
        ("MOS_Rim", "AREA", (2.0, 4.0, 6.0), 800.0, 3.0),
    ]
    for name, kind, location, energy, size in settings:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        obj.rotation_euler = ((0.0, 0.0, 0.0))
        obj.rotation_euler = ((0.0, 0.0, 0.0))
        direction = (-obj.location).to_track_quat("-Z", "Y")
        obj.rotation_euler = direction.to_euler()
        bpy.context.scene.collection.objects.link(obj)


def compositor_outputs(scene: bpy.types.Scene, requested: list[str], root: Path) -> dict[str, bpy.types.Node]:
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render = tree.nodes.new("CompositorNodeRLayers")
    outputs: dict[str, bpy.types.Node] = {}

    def file_node(name: str, source_socket) -> None:
        node = tree.nodes.new("CompositorNodeOutputFile")
        node.name = f"MOS_{name}"
        node.base_path = str(root)
        node.format.file_format = "PNG"
        node.format.color_mode = "RGBA"
        node.format.color_depth = "16" if name in {"normal", "depth"} else "8"
        tree.links.new(source_socket, node.inputs[0])
        outputs[name] = node

    sockets = render.outputs
    if "normal" in requested and sockets.get("Normal"):
        multiply = tree.nodes.new("CompositorNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1.0
        multiply.inputs[2].default_value = (0.5, 0.5, 0.5, 1.0)
        tree.links.new(sockets["Normal"], multiply.inputs[1])
        add = tree.nodes.new("CompositorNodeMixRGB")
        add.blend_type = "ADD"
        add.inputs[0].default_value = 1.0
        add.inputs[2].default_value = (0.5, 0.5, 0.5, 0.0)
        tree.links.new(multiply.outputs[0], add.inputs[1])
        file_node("normal", add.outputs[0])
    if "depth" in requested and sockets.get("Depth"):
        mapping = tree.nodes.new("CompositorNodeMapRange")
        mapping.inputs[1].default_value = 0.0
        mapping.inputs[2].default_value = 20.0
        mapping.inputs[3].default_value = 1.0
        mapping.inputs[4].default_value = 0.0
        tree.links.new(sockets["Depth"], mapping.inputs[0])
        file_node("depth", mapping.outputs[0])
    emission_socket = sockets.get("Emit") or sockets.get("Emission")
    if "emission" in requested and emission_socket:
        file_node("emission", emission_socket)
    if "mask" in requested and sockets.get("Alpha"):
        file_node("mask", sockets["Alpha"])
    if "shadow" in requested and sockets.get("Alpha"):
        # A neutral matte. A later style pass can turn this into a soft,
        # direction-aware contact shadow without contaminating colour sprites.
        file_node("shadow", sockets["Alpha"])
    return outputs


def action_for(clip_id: str):
    return bpy.data.actions.get(f"mos::{clip_id}") or bpy.data.actions.get(clip_id)


def sampled_frame(action, index: int, count: int) -> int:
    if action is None or count <= 1:
        return int(action.frame_range[0]) if action else 1
    start, end = action.frame_range
    return round(start + index * (end - start) / (count - 1))


def move_compositor_file(node, destination: Path) -> None:
    candidates = sorted(destination.parent.glob(f"__{node.name[4:].lower()}_{destination.stem}_*.png"))
    if not candidates:
        raise RuntimeError(f"Blender did not produce compositor pass {node.name} for {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidates[-1].replace(destination)


def main() -> None:
    request_path, request = load_request()
    source = Path(request["input"])
    manifest_path = Path(request["output"])
    render_root = manifest_path.parent / "frames"
    bpy.ops.wm.open_mainfile(filepath=str(source))
    root = find_project_root(request_path)
    profile = load_profile(root, request)
    scene = bpy.context.scene
    width, height = map(int, profile.get("frame_size", [384, 384]))
    scale_percent = int(profile.get("resolution_percentage", 100))
    scene.render.engine = profile.get("engine", "BLENDER_EEVEE_NEXT")
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = scale_percent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = bool(profile.get("transparent", True))
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.035, 0.035, 0.035)
    scene.view_layers[0].use_pass_normal = True
    scene.view_layers[0].use_pass_z = True
    scene.view_layers[0].use_pass_emit = True
    ensure_camera(float(profile.get("camera_elevation_degrees", 35.264)), 8.0,
                  float(profile.get("orthographic_scale", 2.45)))
    ensure_lights()

    count = int(profile.get("directions", 8))
    all_directions = list(profile.get("direction_order", DEFAULT_DIRECTIONS))
    if count == 1:
        directions = [all_directions[0]]
    else:
        step = max(1, 8 // count)
        directions = all_directions[::step][:count]
    requested_passes = list(profile.get("passes", ["color"]))
    pass_nodes = compositor_outputs(scene, [value for value in requested_passes if value != "color"], render_root)
    generated_passes = ["color", *pass_nodes.keys()]
    clips = list(request["spec"].get("animations", [])) or [{"id": "static", "fps": 1, "frames": 1, "loop": True}]
    rig = max(armatures(), key=lambda obj: len(obj.data.bones), default=None)
    roots = [obj for obj in top_level_objects() if obj.type not in {"CAMERA", "LIGHT"}]
    original_rotations = {obj.name: obj.rotation_euler.copy() for obj in roots}

    for direction_index, direction in enumerate(directions):
        angle = -2.0 * math.pi * direction_index / count
        for obj in roots:
            rotation = original_rotations[obj.name].copy()
            rotation.z += angle
            obj.rotation_euler = rotation
        for clip in clips:
            action = action_for(clip["id"])
            if request["spec"].get("animations") and action is None:
                raise RuntimeError(f"Missing prepared Blender action for clip {clip['id']}")
            if rig:
                rig.animation_data_create()
                rig.animation_data.action = action
            for frame_index in range(int(clip["frames"])):
                scene.frame_set(sampled_frame(action, frame_index, int(clip["frames"])))
                color_path = render_root / "color" / clip["id"] / direction / f"{frame_index:04d}.png"
                color_path.parent.mkdir(parents=True, exist_ok=True)
                scene.render.filepath = str(color_path)
                for pass_name, node in pass_nodes.items():
                    relative = Path(pass_name) / clip["id"] / direction
                    (render_root / relative).mkdir(parents=True, exist_ok=True)
                    node.file_slots[0].path = str(relative / f"__{pass_name}_{frame_index:04d}_")
                bpy.ops.render.render(write_still=True)
                for pass_name, node in pass_nodes.items():
                    destination = render_root / pass_name / clip["id"] / direction / f"{frame_index:04d}.png"
                    move_compositor_file(node, destination)

    for obj in roots:
        obj.rotation_euler = original_rotations[obj.name]
    manifest = {
        "schema_version": 1,
        "asset_id": request["asset_id"],
        "source_dir": str(render_root),
        "output_manifest": str(manifest_path.parent.parent / "pack" / "atlas_manifest.json"),
        "frame_size": [width * scale_percent // 100, height * scale_percent // 100],
        "directions": directions,
        "clips": [{"id": clip["id"], "fps": clip["fps"], "frames": clip["frames"],
                   "loop": clip.get("loop", True), "events": clip.get("events", [])} for clip in clips],
        "passes": generated_passes,
        "atlas_max_size": int(profile.get("atlas_max_size", 8192)),
        "pivot": request["spec"].get("sprite", {}).get("pivot", profile.get("pivot")),
        "layer": request["spec"].get("render", {}).get("layer", "body"),
        "blend_mode": request["spec"].get("render", {}).get("blend_mode", profile.get("blend_mode", "mix")),
        "rig_profile": request["spec"].get("rig", {}).get("profile"),
        "shared_canvas": request["spec"].get("sprite", {}).get("shared_canvas"),
    }
    write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
