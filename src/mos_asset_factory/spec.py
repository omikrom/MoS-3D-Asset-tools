from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ASSET_KINDS = {
    "character",
    "monster",
    "weapon",
    "armour",
    "equipment",
    "prop",
    "building",
    "environment",
    "projectile",
    "effect",
    "blood",
}
SOURCE_MODES = {"image", "text", "model", "blend", "procedural", "frames"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class AssetSpec:
    path: Path
    data: dict[str, Any]

    @property
    def asset_id(self) -> str:
        return str(self.data["asset"]["id"])

    @property
    def kind(self) -> str:
        return str(self.data["asset"]["kind"])

    @property
    def source(self) -> dict[str, Any]:
        return dict(self.data.get("source", {}))

    @property
    def render(self) -> dict[str, Any]:
        return dict(self.data.get("render", {}))

    @property
    def animations(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.data.get("animations", [])]

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.data.get(name, {}))

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.path.parent / path).resolve()


def load_spec(path: Path) -> AssetSpec:
    resolved = path.resolve()
    with resolved.open("rb") as handle:
        data = tomllib.load(handle)
    spec = AssetSpec(resolved, data)
    errors = validate_spec(spec)
    if errors:
        raise SpecError("\n".join(errors))
    return spec


def validate_spec(spec: AssetSpec) -> list[str]:
    errors: list[str] = []
    asset = spec.data.get("asset")
    if not isinstance(asset, dict):
        return ["Missing [asset] section"]

    asset_id = str(asset.get("id", ""))
    if not ID_PATTERN.fullmatch(asset_id):
        errors.append("asset.id must use 2-64 lowercase letters, digits or underscores")

    kind = str(asset.get("kind", ""))
    if kind not in ASSET_KINDS:
        errors.append(f"asset.kind must be one of: {', '.join(sorted(ASSET_KINDS))}")

    dependencies = asset.get("depends_on", [])
    if isinstance(dependencies, str):
        dependencies = [dependencies]
    if not isinstance(dependencies, list):
        errors.append("asset.depends_on must be a string or list of asset ids")
    else:
        for dependency in dependencies:
            if not isinstance(dependency, str) or not ID_PATTERN.fullmatch(dependency):
                errors.append(f"Invalid asset dependency: {dependency!r}")
            elif dependency == asset_id:
                errors.append("An asset cannot depend on itself")

    source = spec.data.get("source")
    if not isinstance(source, dict):
        errors.append("Missing [source] section")
    else:
        mode = str(source.get("mode", ""))
        if mode not in SOURCE_MODES:
            errors.append(f"source.mode must be one of: {', '.join(sorted(SOURCE_MODES))}")
        if mode in {"image", "model", "blend", "frames"} and not source.get("path"):
            errors.append(f"source.path is required when source.mode is {mode!r}")
        if mode == "text" and not source.get("prompt"):
            errors.append("source.prompt is required when source.mode is 'text'")
        frame_size = source.get("frame_size")
        if frame_size is not None and (
            not isinstance(frame_size, list)
            or len(frame_size) != 2
            or any(not isinstance(value, int) or value <= 0 for value in frame_size)
        ):
            errors.append("source.frame_size must contain two positive integers")
        frame_directions = source.get("directions")
        if frame_directions is not None and (
            not isinstance(frame_directions, list)
            or not frame_directions
            or any(not isinstance(value, str) or not value for value in frame_directions)
            or len(set(frame_directions)) != len(frame_directions)
        ):
            errors.append("source.directions must contain unique direction names")

    seen: set[str] = set()
    for index, animation in enumerate(spec.data.get("animations", [])):
        name = str(animation.get("id", ""))
        if not ID_PATTERN.fullmatch(name):
            errors.append(f"animations[{index}].id is invalid")
        if name in seen:
            errors.append(f"Duplicate animation id: {name}")
        seen.add(name)
        fps = animation.get("fps", 0)
        if not isinstance(fps, (int, float)) or fps <= 0:
            errors.append(f"Animation {name or index} must have fps > 0")

    directions = spec.render.get("directions", 8)
    if directions not in {1, 4, 8, 16}:
        errors.append("render.directions must be 1, 4, 8 or 16")
    frame_directions = spec.source.get("directions")
    if isinstance(frame_directions, list) and frame_directions and len(frame_directions) != directions:
        errors.append("source.directions count must match render.directions")
    return errors


def discover_specs(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    yield from sorted(path.rglob("*.toml"))
