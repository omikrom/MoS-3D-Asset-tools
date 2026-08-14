from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import FactoryConfig


class ProviderError(RuntimeError):
    pass


class ManualActionRequired(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderRequest:
    category: str
    name: str
    request_path: Path
    input_path: Path | None
    output_path: Path
    asset_id: str


def run_provider(config: FactoryConfig, request: ProviderRequest) -> None:
    provider = config.provider(request.category, request.name)
    if not provider:
        raise ProviderError(f"Unknown {request.category} provider: {request.name}")
    if not provider.get("enabled", False):
        raise ProviderError(
            f"Provider {request.category}.{request.name} is disabled in mos.toml; "
            "install/configure it first or use a manual provider"
        )

    kind = provider.get("kind", "command")
    if kind == "manual":
        raise ManualActionRequired(
            f"Manual {request.category} step prepared at {request.request_path}. "
            f"Place the result at {request.output_path} and resume the build."
        )
    if kind == "passthrough":
        if request.input_path is None or not request.input_path.exists():
            raise ProviderError("Passthrough provider requires an existing input")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(request.input_path, request.output_path)
        return
    if kind != "command":
        raise ProviderError(f"Unsupported provider kind: {kind}")

    command = provider.get("command")
    if not isinstance(command, list) or not command:
        raise ProviderError(f"Provider {request.name} has no command")
    replacements = {
        "request": str(request.request_path),
        "input": str(request.input_path or ""),
        "output": str(request.output_path),
        "asset_id": request.asset_id,
        "root": str(config.root),
    }
    resolved = [str(part).format(**replacements) for part in command]
    result = subprocess.run(resolved, cwd=config.root, check=False)
    if result.returncode:
        raise ProviderError(f"Provider {request.name} exited with {result.returncode}")
    if not request.output_path.exists():
        raise ProviderError(f"Provider completed but did not write {request.output_path}")


def write_provider_request(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
