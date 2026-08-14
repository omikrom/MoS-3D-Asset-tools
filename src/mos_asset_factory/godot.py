from __future__ import annotations

import json
from pathlib import Path


def export_godot_sprite_frames(manifest_path: Path, output_path: Path, resource_prefix: str = "res://") -> None:
    manifest = json.loads(manifest_path.read_text("utf-8"))
    color_frames = [frame for frame in manifest["frames"] if frame["pass"] == "color"]
    if not color_frames:
        raise ValueError("Atlas manifest contains no colour frames")

    atlas_pages = manifest["atlases"]["color"]
    if isinstance(atlas_pages, dict):
        atlas_pages = [atlas_pages]
    atlas_names = [page["path"] for page in atlas_pages]
    atlas_ids = {name: f"{index + 1}_atlas" for index, name in enumerate(atlas_names)}
    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={len(color_frames) + len(atlas_names) + 1} format=3]',
        "",
    ]
    for atlas_name in atlas_names:
        lines.extend([
            f'[ext_resource type="Texture2D" path="{resource_prefix}{atlas_name}" id="{atlas_ids[atlas_name]}"]',
            "",
        ])
    identifiers: dict[tuple[str, str, int], str] = {}
    for index, frame in enumerate(color_frames):
        identifier = f"AtlasTexture_{index:05d}"
        identifiers[(frame["clip"], frame["direction"], int(frame["frame"]))] = identifier
        x, y, width, height = frame["region"]
        lines.extend([
            f'[sub_resource type="AtlasTexture" id="{identifier}"]',
            f'atlas = ExtResource("{atlas_ids[frame["atlas"]]}")',
            f"region = Rect2({x}, {y}, {width}, {height})",
            "",
        ])

    animations: list[str] = []
    for clip in manifest["clips"]:
        for direction in manifest["directions"]:
            frame_values = []
            for frame_index in range(int(clip["frames"])):
                identifier = identifiers.get((clip["id"], direction, frame_index))
                if identifier:
                    frame_values.append(f'{{"duration": 1.0, "texture": SubResource("{identifier}")}}')
            if not frame_values:
                continue
            animations.append(
                "{\n"
                f'"frames": [{", ".join(frame_values)}],\n'
                f'"loop": {str(bool(clip.get("loop", True))).lower()},\n'
                f'"name": &"{clip["id"]}_{direction}",\n'
                f'"speed": {float(clip["fps"]):g}\n'
                "}"
            )
    lines.extend(["[resource]", f"animations = [{', '.join(animations)}]", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), "utf-8")
