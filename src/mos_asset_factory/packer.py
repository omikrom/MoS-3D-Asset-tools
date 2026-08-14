from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image


class PackError(RuntimeError):
    pass


def _load_frames(job: dict[str, Any], render_pass: str) -> list[dict[str, Any]]:
    root = Path(job["source_dir"])
    entries: list[dict[str, Any]] = []
    for clip in job["clips"]:
        for direction in job["directions"]:
            for frame in range(int(clip["frames"])):
                relative = Path(render_pass) / clip["id"] / direction / f"{frame:04d}.png"
                source = root / relative
                if not source.is_file():
                    if render_pass == "color":
                        raise PackError(f"Missing required frame: {source}")
                    continue
                entries.append({
                    "clip": clip["id"], "direction": direction, "frame": frame,
                    "fps": clip["fps"], "loop": clip.get("loop", True), "source": source,
                })
    return entries


def pack_job(job: dict[str, Any]) -> dict[str, Any]:
    output_manifest = Path(job["output_manifest"])
    output_dir = output_manifest.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = map(int, job.get("frame_size", [256, 256]))
    max_size = int(job.get("atlas_max_size", 8192))
    passes = list(job.get("passes", ["color"]))
    if width <= 0 or height <= 0:
        raise PackError("frame_size values must be greater than zero")
    max_columns = max_size // width
    max_rows = max_size // height
    if max_columns < 1 or max_rows < 1:
        raise PackError(f"A {width}x{height} frame cannot fit inside a {max_size}px atlas")
    page_capacity = max_columns * max_rows

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "asset_id": job["asset_id"],
        "frame_size": [width, height],
        "directions": job["directions"],
        "clips": job["clips"],
        "metadata": {
            key: job[key]
            for key in ("pivot", "layer", "blend_mode", "draw_order", "rig_profile", "shared_canvas")
            if key in job and job[key] is not None
        },
        "atlases": {},
        "frames": [],
    }

    for render_pass in passes:
        frames = _load_frames(job, render_pass)
        if not frames:
            continue
        pages: list[dict[str, Any]] = []
        page_count = math.ceil(len(frames) / page_capacity)
        for page_index in range(page_count):
            page_frames = frames[page_index * page_capacity : (page_index + 1) * page_capacity]
            if page_count == 1:
                columns = min(max_columns, max(1, math.ceil(math.sqrt(len(page_frames) * height / width))))
            else:
                columns = max_columns
            rows = math.ceil(len(page_frames) / columns)
            atlas = Image.new("RGBA", (columns * width, rows * height), (0, 0, 0, 0))
            atlas_name = (
                f"{job['asset_id']}_{render_pass}.png"
                if page_count == 1
                else f"{job['asset_id']}_{render_pass}_{page_index:03d}.png"
            )
            for index, entry in enumerate(page_frames):
                image = Image.open(entry["source"]).convert("RGBA")
                if image.size != (width, height):
                    if image.width > width or image.height > height:
                        raise PackError(
                            f"Frame {entry['source']} is {image.width}x{image.height}, larger than "
                            f"the declared {width}x{height} canvas"
                        )
                    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
                    image = canvas
                x, y = (index % columns) * width, (index // columns) * height
                atlas.alpha_composite(image, (x, y))
                manifest["frames"].append({
                    "pass": render_pass,
                    "clip": entry["clip"],
                    "direction": entry["direction"],
                    "frame": entry["frame"],
                    "fps": entry["fps"],
                    "loop": entry["loop"],
                    "atlas": atlas_name,
                    "atlas_page": page_index,
                    "region": [x, y, width, height],
                })
            atlas.save(output_dir / atlas_name, optimize=True)
            pages.append({
                "path": atlas_name,
                "page": page_index,
                "size": list(atlas.size),
                "columns": columns,
                "rows": rows,
                "frames": len(page_frames),
            })
        manifest["atlases"][render_pass] = pages

    output_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
    return manifest
