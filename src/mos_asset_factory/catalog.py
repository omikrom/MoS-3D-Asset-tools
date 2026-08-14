from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .spec import discover_specs, load_spec


def build_catalog(source: Path, output: Path) -> dict[str, Any]:
    assets = []
    for path in discover_specs(source):
        spec = load_spec(path)
        assets.append({
            "id": spec.asset_id,
            "kind": spec.kind,
            "display_name": spec.data["asset"].get("display_name", spec.asset_id),
            "tags": spec.data["asset"].get("tags", []),
            "spec": str(path.resolve()),
            "rig_profile": spec.section("rig").get("profile"),
            "layer": spec.render.get("layer"),
        })
    catalog = {"schema_version": 1, "assets": sorted(assets, key=lambda item: (item["kind"], item["id"]))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", "utf-8")
    return catalog
