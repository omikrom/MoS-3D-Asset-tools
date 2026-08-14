from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


def load_request() -> tuple[Path, dict[str, Any]]:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parsed = parser.parse_args(args)
    path = parsed.request.resolve()
    return path, json.loads(path.read_text("utf-8"))


def find_project_root(path: Path) -> Path:
    for candidate in (path.resolve(), *path.resolve().parents):
        if (candidate / "mos.toml").is_file():
            return candidate
    raise RuntimeError(f"Could not locate mos.toml from {path}")


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_asset(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
        return
    reset_scene()
    import_asset_into_current(path)


def import_asset_into_current(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=True)
    elif suffix == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(path))
        else:
            bpy.ops.import_scene.obj(filepath=str(path))
    elif suffix == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, destination):
            destination.objects = source.objects
        for obj in destination.objects:
            if obj is not None:
                bpy.context.scene.collection.objects.link(obj)
    else:
        raise RuntimeError(f"Unsupported Blender input: {path}")


def mesh_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def armatures() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]


def world_bounds(objects: list[bpy.types.Object] | None = None) -> tuple[Vector, Vector]:
    objects = objects or mesh_objects()
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise RuntimeError("Scene contains no renderable mesh")
    return (
        Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
    )


def top_level_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.parent is None]


def normalize_scene(target_height: float | None) -> dict[str, Any]:
    minimum, maximum = world_bounds()
    height = maximum.z - minimum.z
    scale = float(target_height) / height if target_height and height > 1e-6 else 1.0
    centre = Vector(((minimum.x + maximum.x) / 2, (minimum.y + maximum.y) / 2, minimum.z))

    for obj in top_level_objects():
        obj.location = (obj.location - centre) * scale
        obj.scale = obj.scale * scale

    minimum, maximum = world_bounds()
    return {
        "bounds_min": list(minimum),
        "bounds_max": list(maximum),
        "height": maximum.z - minimum.z,
        "scale_applied": scale,
    }


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def ensure_camera(elevation_degrees: float, distance: float, orthographic_scale: float) -> bpy.types.Object:
    camera_data = bpy.data.cameras.get("MOS_Camera") or bpy.data.cameras.new("MOS_Camera")
    camera = bpy.data.objects.get("MOS_Camera") or bpy.data.objects.new("MOS_Camera", camera_data)
    if camera.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(camera)
    elevation = math.radians(elevation_degrees)
    camera.location = (0.0, -distance * math.cos(elevation), distance * math.sin(elevation))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = orthographic_scale
    point_camera(camera, Vector((0.0, 0.0, orthographic_scale * 0.34)))
    bpy.context.scene.camera = camera
    return camera


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", "utf-8")
