from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .spec import AssetSpec, discover_specs, load_spec


class BatchError(ValueError):
    pass


@dataclass(frozen=True)
class BatchAsset:
    spec: AssetSpec
    dependencies: tuple[str, ...]


def asset_dependencies(spec: AssetSpec) -> tuple[str, ...]:
    """Return asset-to-asset build dependencies declared by a specification."""
    values: list[str] = []
    explicit = spec.data.get("asset", {}).get("depends_on", [])
    if isinstance(explicit, str):
        explicit = [explicit]
    if isinstance(explicit, list):
        values.extend(str(value) for value in explicit if value)

    weight_source = spec.section("rig").get("transfer_weights_from")
    if weight_source:
        values.append(str(weight_source))

    # Preserve declaration order while removing duplicates and self references.
    return tuple(dict.fromkeys(value for value in values if value != spec.asset_id))


def load_batch(path: Path) -> list[BatchAsset]:
    specs = [load_spec(spec_path) for spec_path in discover_specs(path)]
    by_id: dict[str, AssetSpec] = {}
    for spec in specs:
        if spec.asset_id in by_id:
            raise BatchError(
                f"Duplicate asset id {spec.asset_id!r}: {by_id[spec.asset_id].path} and {spec.path}"
            )
        by_id[spec.asset_id] = spec

    ordered = _topological_order(specs)
    return [BatchAsset(spec, asset_dependencies(spec)) for spec in ordered]


def _topological_order(specs: Iterable[AssetSpec]) -> list[AssetSpec]:
    ordered_input = list(specs)
    by_id = {spec.asset_id: spec for spec in ordered_input}
    visiting: list[str] = []
    visited: set[str] = set()
    result: list[AssetSpec] = []

    def visit(asset_id: str) -> None:
        if asset_id in visited:
            return
        if asset_id in visiting:
            start = visiting.index(asset_id)
            cycle = visiting[start:] + [asset_id]
            raise BatchError(f"Asset dependency cycle: {' -> '.join(cycle)}")

        visiting.append(asset_id)
        spec = by_id[asset_id]
        for dependency in asset_dependencies(spec):
            if dependency in by_id:
                visit(dependency)
        visiting.pop()
        visited.add(asset_id)
        result.append(spec)

    for spec in ordered_input:
        visit(spec.asset_id)
    return result
