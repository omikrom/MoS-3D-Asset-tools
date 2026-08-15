from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from .config import FactoryConfig


class CompositionError(RuntimeError):
    pass


def build_composition(config: FactoryConfig, spec_path: Path, output: Path, allow_missing: bool = False) -> dict[str, Any]:
    with spec_path.open("rb") as handle:
        spec = tomllib.load(handle)
    header = spec.get("composition", {})
    composition_id = header.get("id")
    if not composition_id:
        raise CompositionError("Composition requires [composition].id")
    layers = spec.get("layers", {})
    if not layers:
        raise CompositionError("Composition requires at least one [layers] entry")

    resolved_layers = []
    baselines: dict[str, Any] | None = None
    for layer, asset_id in layers.items():
        export_dir = config.workspace / "assets" / str(asset_id) / "export"
        manifest_path = export_dir / f"{asset_id}.json"
        resource_path = export_dir / f"{asset_id}.tres"
        if not manifest_path.is_file() or not resource_path.is_file():
            if not allow_missing:
                raise CompositionError(f"Layer {layer} asset {asset_id} has not been exported")
            resolved_layers.append({"layer": layer, "asset_id": asset_id, "status": "missing",
                                    "resource": str(resource_path), "manifest": str(manifest_path)})
            continue
        manifest = json.loads(manifest_path.read_text("utf-8"))
        signature = {
            "frame_size": manifest.get("frame_size"),
            "directions": manifest.get("directions"),
            "clips": [(clip["id"], clip["frames"], clip["fps"]) for clip in manifest.get("clips", [])],
        }
        if baselines is None:
            baselines = signature
        elif signature != baselines:
            raise CompositionError(f"Layer {layer} ({asset_id}) does not share the composition frame contract")
        resolved_layers.append({"layer": layer, "asset_id": asset_id, "status": "ready",
                                "resource": str(resource_path), "manifest": str(manifest_path)})

    result = {
        "schema_version": 1,
        "id": composition_id,
        "rig_profile": header.get("rig_profile"),
        "profile": header.get("profile", "soma_legacy"),
        "layers": resolved_layers,
        "draw_order": spec.get("draw_order", {}),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    return result
