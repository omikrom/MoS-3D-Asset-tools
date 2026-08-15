from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_string(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        return os.environ.get(name, default or "")

    return _ENV_PATTERN.sub(replace, value)


def expand_environment(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_string(value)
    if isinstance(value, list):
        return [expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_environment(item) for key, item in value.items()}
    return value


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "mos.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not find mos.toml in this directory or its parents")


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


@dataclass(frozen=True)
class FactoryConfig:
    root: Path
    data: dict[str, Any]

    @property
    def workspace(self) -> Path:
        value = self.data.get("project", {}).get("workspace", "workspace")
        return (self.root / value).resolve()

    @property
    def stages(self) -> list[str]:
        return list(
            self.data.get("pipeline", {}).get(
                "stages",
                ["source", "shape", "texture", "prepare", "rig", "animate", "render", "pack", "export"],
            )
        )

    def provider(self, category: str, name: str) -> dict[str, Any]:
        providers = self.data.get("providers", {})
        return dict(providers.get(category, {}).get(name, {}))

    def tool(self, name: str) -> dict[str, Any]:
        return dict(self.data.get("tools", {}).get(name, {}))


def load_config(path: Path | None = None) -> FactoryConfig:
    config_path = path.resolve() if path else find_project_root() / "mos.toml"
    load_dotenv(config_path.parent / ".env")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return FactoryConfig(config_path.parent, expand_environment(raw))
