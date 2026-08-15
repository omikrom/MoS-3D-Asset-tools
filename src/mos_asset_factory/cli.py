from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from PIL import __version__ as pillow_version

from . import __version__
from .batch import load_batch
from .config import load_config
from .catalog import build_catalog
from .composition import build_composition
from .godot import export_godot_sprite_frames
from .models import install_models, model_statuses, required_models
from .packer import pack_job
from .pipeline import HANDOFF_STAGES, STAGE_ORDER, AssetPipeline
from .soma_legacy import ACTION_SLOTS, DIRECTIONS, LAYERS, WEAPON_TYPES
from .spec import SpecError, discover_specs, load_spec, validate_spec


def _print_plan(pipeline: AssetPipeline) -> None:
    print(f"Asset: {pipeline.spec.asset_id} ({pipeline.spec.kind})")
    print(f"{'STAGE':<10} {'PROVIDER':<16} {'STATUS':<9} OUTPUT")
    for item in pipeline.plan():
        print(f"{item.stage:<10} {item.provider:<16} {item.status:<9} {item.output}")


def command_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    blender = config.tool("blender")
    blender_value = str(blender.get("executable", "blender"))
    blender_path = shutil.which(blender_value) or (blender_value if Path(blender_value).is_file() else None)
    print(f"MoS Asset Factory {__version__}")
    print(f"Project: {config.root}")
    print(f"Python:  {sys.version.split()[0]}")
    print(f"Pillow:  {pillow_version}")
    print(f"Blender: {'ready - ' + str(blender_path) if blender_path else 'not found / disabled'}")
    for category in ("shape", "texture", "rig", "animation"):
        entries = config.data.get("providers", {}).get(category, {})
        for name, provider in entries.items():
            state = "enabled" if provider.get("enabled", False) else "disabled"
            print(f"{category}.{name}: {state} ({provider.get('kind', 'command')})")
    for variable in ("HUNYUAN3D_HOME", "TRELLIS_HOME", "UNIRIG_HOME", "COMFYUI_HOME"):
        if os.environ.get(variable):
            print(f"{variable}: configured")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    failures = 0
    for path in discover_specs(args.path):
        try:
            spec = load_spec(path)
            errors = validate_spec(spec)
            if errors:
                failures += 1
                print(f"FAIL {path}")
                for error in errors:
                    print(f"  - {error}")
            else:
                print(f"OK   {path} ({spec.asset_id})")
        except (OSError, SpecError) as error:
            failures += 1
            print(f"FAIL {path}: {error}")
    return 1 if failures else 0


def command_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    _print_plan(AssetPipeline(config, load_spec(args.spec)))
    return 0


def command_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pipeline = AssetPipeline(config, load_spec(args.spec))
    pipeline.build(dry_run=args.dry_run, from_stage=args.from_stage, force=args.force)
    _print_plan(pipeline)
    return 0


def command_plan_all(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    batch = load_batch(args.path)
    print(f"Build order ({len(batch)} assets)")
    for index, item in enumerate(batch, 1):
        pipeline = AssetPipeline(config, item.spec)
        dependencies = ", ".join(item.dependencies) if item.dependencies else "-"
        blockers = [plan for plan in pipeline.plan() if plan.status in {"blocked", "disabled", "manual"}]
        status = f"{blockers[0].stage}:{blockers[0].status}" if blockers else "ready"
        print(f"{index:>3}. {item.spec.asset_id:<24} {status:<18} depends: {dependencies}")
    return 0


def command_build_all(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    batch = load_batch(args.path)
    included = {item.spec.asset_id for item in batch}
    failed: dict[str, str] = {}
    completed: set[str] = set()

    for item in batch:
        internal_blockers = [
            dependency for dependency in item.dependencies if dependency in included and dependency not in completed
        ]
        if internal_blockers:
            message = f"dependency failed: {', '.join(internal_blockers)}"
            failed[item.spec.asset_id] = message
            print(f"SKIP {item.spec.asset_id}: {message}")
            continue
        print(f"BUILD {item.spec.asset_id}")
        try:
            AssetPipeline(config, item.spec).build(
                dry_run=args.dry_run,
                from_stage=args.from_stage,
                force=args.force,
            )
            completed.add(item.spec.asset_id)
            print(f"OK    {item.spec.asset_id}")
        except (OSError, ValueError, RuntimeError) as error:
            failed[item.spec.asset_id] = str(error)
            print(f"FAIL  {item.spec.asset_id}: {error}")
            if not args.keep_going:
                break

    print(f"Batch complete: {len(completed)} succeeded, {len(failed)} failed or skipped")
    return 1 if failed else 0


def command_request(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pipeline = AssetPipeline(config, load_spec(args.spec))
    request = pipeline.request_for_stage(args.stage)
    payload = json.loads(request.read_text("utf-8"))
    print(f"Wrote {args.stage} request -> {request}")
    print(f"Expected result -> {payload['output']}")
    return 0


def command_accept(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    pipeline = AssetPipeline(config, load_spec(args.spec))
    output = pipeline.accept_result(args.stage, args.result, force=args.force)
    next_stage = STAGE_ORDER[STAGE_ORDER.index(args.stage) + 1]
    print(f"Accepted {args.stage} result -> {output}")
    print(f"Resume with: mos build {args.spec} --from-stage {next_stage}")
    return 0


def _selected_models(args: argparse.Namespace, config) -> list[str] | None:
    selected = list(getattr(args, "names", []))
    specs_path = getattr(args, "specs_path", None)
    if specs_path:
        selected.extend(required_models(config, specs_path))
    return list(dict.fromkeys(selected)) if selected or specs_path else None


def command_models_list(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    needed = set(required_models(config, args.specs_path)) if args.specs_path else set()
    for status in model_statuses(config):
        definition = status.definition
        code = "downloaded" if status.code_ready else "missing"
        weights = f"{len(status.cached_weights)}/{len(definition.weight_repositories)} weights cached"
        marker = "needed" if definition.model_id in needed else "optional"
        if not args.specs_path:
            marker = "available"
        print(f"{definition.model_id:<12} {code:<10} {weights:<20} {marker}")
        print(f"  {definition.display_name}; Python {definition.python_version}; {definition.notes}")
    return 0


def command_models_install(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    actions = install_models(
        config,
        _selected_models(args, config),
        include_weights=args.weights,
        dry_run=args.dry_run,
    )
    for action in actions:
        print(f"- {action}")
    if args.dry_run:
        print("Dry run only; nothing downloaded or changed")
    else:
        print("Model download complete. Run 'mos models list', then configure each isolated Python environment.")
    return 0


def command_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    state = config.workspace / "assets" / args.asset_id / "state.json"
    if not state.exists():
        print(f"No build state for {args.asset_id}")
        return 1
    print(state.read_text("utf-8"), end="")
    return 0


def command_pack(args: argparse.Namespace) -> int:
    job = json.loads(args.job.read_text("utf-8"))
    manifest = pack_job(job)
    print(f"Packed {len(manifest['frames'])} frames -> {job['output_manifest']}")
    return 0


def command_export(args: argparse.Namespace) -> int:
    export_godot_sprite_frames(args.manifest, args.output, args.resource_prefix)
    print(f"Wrote {args.output}")
    return 0


def command_original_map(_args: argparse.Namespace) -> int:
    print("Directions")
    for index, name in enumerate(DIRECTIONS):
        print(f"  {index:>2}: {name}")
    print("Animation slots")
    for index, name in ACTION_SLOTS.items():
        print(f"  {index:>2}: {name}")
    print("Equipment layers")
    for index, name in enumerate(LAYERS):
        print(f"  {index:>2}: {name}")
    print("Weapon types")
    for index, name in WEAPON_TYPES.items():
        print(f"  {index:>2}: {name}")
    return 0


def command_catalog(args: argparse.Namespace) -> int:
    catalog = build_catalog(args.source, args.output)
    print(f"Wrote {len(catalog['assets'])} assets -> {args.output}")
    return 0


def command_compose(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output = args.output or config.workspace / "compositions" / f"{args.spec.stem}.json"
    result = build_composition(config, args.spec, output, args.allow_missing)
    ready = sum(1 for layer in result["layers"] if layer["status"] == "ready")
    print(f"Wrote composition {result['id']} ({ready}/{len(result['layers'])} layers ready) -> {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mos", description="Myth of Soma 3D-to-sprite asset factory")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="Path to mos.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local tools and providers")
    doctor.set_defaults(func=command_doctor)

    validate = subparsers.add_parser("validate", help="Validate one specification or a directory")
    validate.add_argument("path", type=Path)
    validate.set_defaults(func=command_validate)

    plan = subparsers.add_parser("plan", help="Show resolved stages without running them")
    plan.add_argument("spec", type=Path)
    plan.set_defaults(func=command_plan)

    build = subparsers.add_parser("build", help="Build an asset")
    build.add_argument("spec", type=Path)
    build.add_argument("--dry-run", action="store_true")
    build.add_argument("--from-stage", choices=STAGE_ORDER)
    build.add_argument("--force", action="store_true")
    build.set_defaults(func=command_build)

    plan_all = subparsers.add_parser("plan-all", help="Show dependency-ordered plans for a specification directory")
    plan_all.add_argument("path", type=Path)
    plan_all.set_defaults(func=command_plan_all)

    build_all = subparsers.add_parser("build-all", help="Build every asset in dependency order")
    build_all.add_argument("path", type=Path)
    build_all.add_argument("--dry-run", action="store_true")
    build_all.add_argument("--from-stage", choices=STAGE_ORDER)
    build_all.add_argument("--force", action="store_true")
    build_all.add_argument("--keep-going", action="store_true", help="Continue after an asset fails")
    build_all.set_defaults(func=command_build_all)

    request = subparsers.add_parser("request", help="Write one portable model/tool handoff request")
    request.add_argument("spec", type=Path)
    request.add_argument("stage", choices=sorted(HANDOFF_STAGES))
    request.set_defaults(func=command_request)

    accept = subparsers.add_parser("accept", help="Accept a model/tool result and record it in the build")
    accept.add_argument("spec", type=Path)
    accept.add_argument("stage", choices=sorted(HANDOFF_STAGES))
    accept.add_argument("result", type=Path)
    accept.add_argument("--force", action="store_true")
    accept.set_defaults(func=command_accept)

    models = subparsers.add_parser("models", help="Discover and download optional AI model repositories and weights")
    model_commands = models.add_subparsers(dest="models_command", required=True)

    models_list = model_commands.add_parser("list", help="Show model code and weight download status")
    models_list.add_argument("--for", dest="specs_path", type=Path, help="Mark models required by these asset specs")
    models_list.set_defaults(func=command_models_list)

    models_install = model_commands.add_parser("install", help="Download model code and optionally weights")
    models_install.add_argument("names", nargs="*", help="Model ids; omit to install all registered models")
    models_install.add_argument("--for", dest="specs_path", type=Path, help="Install only models required by these specs")
    models_install.add_argument("--weights", action="store_true", help="Also cache potentially large Hugging Face weights")
    models_install.add_argument("--dry-run", action="store_true")
    models_install.set_defaults(func=command_models_install)

    status = subparsers.add_parser("status", help="Show resumable build state")
    status.add_argument("asset_id")
    status.set_defaults(func=command_status)

    pack = subparsers.add_parser("pack", help="Pack a render job into atlases")
    pack.add_argument("job", type=Path)
    pack.set_defaults(func=command_pack)

    export = subparsers.add_parser("export-godot", help="Export a Godot SpriteFrames resource")
    export.add_argument("manifest", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--resource-prefix", default="./")
    export.set_defaults(func=command_export)

    original = subparsers.add_parser("original-map", help="Print recovered original-client identifiers")
    original.set_defaults(func=command_original_map)

    catalog = subparsers.add_parser("catalog", help="Build a searchable asset catalogue")
    catalog.add_argument("source", type=Path)
    catalog.add_argument("output", type=Path)
    catalog.set_defaults(func=command_catalog)

    compose = subparsers.add_parser("compose", help="Validate and export a modular layer composition")
    compose.add_argument("spec", type=Path)
    compose.add_argument("--output", type=Path)
    compose.add_argument("--allow-missing", action="store_true")
    compose.set_defaults(func=command_compose)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
