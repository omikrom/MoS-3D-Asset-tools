from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import FactoryConfig
from .spec import discover_specs, load_spec


class ModelInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    display_name: str
    repository: str
    destination: Path
    environment_variable: str
    python_version: str
    recursive: bool
    providers: tuple[str, ...]
    weight_repositories: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ModelStatus:
    definition: ModelDefinition
    code_ready: bool
    cached_weights: tuple[str, ...]


def load_model_registry(config: FactoryConfig) -> tuple[dict[str, ModelDefinition], Path]:
    registry_value = config.data.get("project", {}).get("model_registry", "models.toml")
    registry_path = (config.root / str(registry_value)).resolve()
    with registry_path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ModelInstallError(f"Unsupported model registry schema: {data.get('schema_version')!r}")

    cache = _inside_project(config.root, str(data.get("weights", {}).get("cache", "models/huggingface")))
    definitions: dict[str, ModelDefinition] = {}
    for model_id, raw in data.get("models", {}).items():
        destination = _inside_project(config.root, str(raw["destination"]))
        definitions[model_id] = ModelDefinition(
            model_id=model_id,
            display_name=str(raw.get("display_name", model_id)),
            repository=str(raw["repository"]),
            destination=destination,
            environment_variable=str(raw["environment_variable"]),
            python_version=str(raw.get("python_version", "3.11")),
            recursive=bool(raw.get("recursive", False)),
            providers=tuple(str(value) for value in raw.get("providers", [])),
            weight_repositories=tuple(str(value) for value in raw.get("weight_repositories", [])),
            notes=str(raw.get("notes", "")),
        )
    return definitions, cache


def _inside_project(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ModelInstallError(f"Model registry path escapes the project: {value}")
    return path


def required_models(config: FactoryConfig, specs_path: Path) -> list[str]:
    definitions, _cache = load_model_registry(config)
    requested_providers: set[str] = set()
    for path in discover_specs(specs_path):
        spec = load_spec(path)
        source_mode = spec.source.get("mode")
        if source_mode not in {"model", "blend", "frames"}:
            requested_providers.add(f"shape.{spec.section('geometry').get('provider', 'manual')}")
        texture = spec.section("texture")
        if texture.get("enabled", True) and source_mode not in {"model", "blend", "frames"}:
            requested_providers.add(f"texture.{texture.get('provider', 'passthrough')}")
        rig = spec.section("rig")
        if rig.get("enabled", False) and not rig.get("pre_rigged", False):
            requested_providers.add(f"rig.{rig.get('provider', 'manual')}")

    return [
        model_id
        for model_id, definition in definitions.items()
        if requested_providers.intersection(definition.providers)
    ]


def model_statuses(config: FactoryConfig, selected: Iterable[str] | None = None) -> list[ModelStatus]:
    definitions, cache = load_model_registry(config)
    names = _resolve_names(definitions, selected)
    statuses: list[ModelStatus] = []
    for name in names:
        definition = definitions[name]
        cached = tuple(repo for repo in definition.weight_repositories if _weight_is_cached(cache, repo))
        statuses.append(ModelStatus(definition, (definition.destination / ".git").is_dir(), cached))
    return statuses


def install_models(
    config: FactoryConfig,
    selected: Iterable[str] | None = None,
    *,
    include_weights: bool = False,
    dry_run: bool = False,
) -> list[str]:
    definitions, cache = load_model_registry(config)
    names = _resolve_names(definitions, selected)
    git = shutil.which("git")
    if not git and any(not definitions[name].destination.exists() for name in names):
        raise ModelInstallError("Git is required to download model repositories")

    actions: list[str] = []
    environment: dict[str, str] = {"HF_HOME": str(cache)}
    for name in names:
        definition = definitions[name]
        environment[definition.environment_variable] = str(definition.destination)
        if definition.destination.exists():
            if not (definition.destination / ".git").is_dir():
                raise ModelInstallError(
                    f"Refusing to overwrite non-Git path for {name}: {definition.destination}"
                )
            actions.append(f"keep existing {name} repository at {definition.destination}")
        else:
            command = [str(git), "clone"]
            if definition.recursive:
                command.append("--recurse-submodules")
            command.extend([definition.repository, str(definition.destination)])
            actions.append(f"clone {definition.repository} -> {definition.destination}")
            if not dry_run:
                definition.destination.parent.mkdir(parents=True, exist_ok=True)
                _run(command, config.root)

        if include_weights:
            for repository in definition.weight_repositories:
                actions.append(f"cache Hugging Face weights {repository} -> {cache}")
                if not dry_run:
                    _download_weights(repository, cache)

    actions.append(f"update {config.root / '.env'} with model and cache paths")
    if not dry_run:
        cache.mkdir(parents=True, exist_ok=True)
        _update_dotenv(config.root / ".env", environment)
    return actions


def _resolve_names(definitions: dict[str, ModelDefinition], selected: Iterable[str] | None) -> list[str]:
    names = list(selected) if selected is not None else list(definitions)
    unknown = sorted(set(names) - definitions.keys())
    if unknown:
        raise ModelInstallError(f"Unknown models: {', '.join(unknown)}")
    return list(dict.fromkeys(names))


def _weight_is_cached(cache: Path, repository: str) -> bool:
    model_cache = cache / f"models--{repository.replace('/', '--')}"
    snapshots = model_cache / "snapshots"
    return snapshots.is_dir() and any(path.is_dir() for path in snapshots.iterdir())


def _download_weights(repository: str, cache: Path) -> None:
    if importlib.util.find_spec("huggingface_hub") is None:
        _run([sys.executable, "-m", "pip", "install", "huggingface_hub>=0.34"], Path.cwd())
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repository, cache_dir=str(cache))


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise ModelInstallError(f"Command failed ({result.returncode}): {' '.join(command)}")


def _update_dotenv(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    positions: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            positions[stripped.split("=", 1)[0].strip()] = index
    for name, value in values.items():
        rendered = f'{name}="{value}"'
        if name in positions:
            lines[positions[name]] = rendered
        else:
            lines.append(rendered)
    path.write_text("\n".join(lines).rstrip() + "\n", "utf-8")
