from __future__ import annotations

import hashlib
import json
import copy
import shutil
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import FactoryConfig
from .godot import export_godot_sprite_frames
from .packer import pack_job
from .providers import ProviderRequest, run_provider, write_provider_request
from .spec import AssetSpec


STAGE_ORDER = ["source", "shape", "texture", "prepare", "rig", "animate", "render", "pack", "export"]
HANDOFF_STAGES = {"shape", "texture", "prepare", "rig", "animate"}


@dataclass(frozen=True)
class StagePlan:
    stage: str
    provider: str
    input: str | None
    output: str
    status: str


class PipelineError(RuntimeError):
    pass


class AssetPipeline:
    def __init__(self, config: FactoryConfig, spec: AssetSpec):
        self.config = config
        self.spec = spec
        self.root = config.workspace / "assets" / spec.asset_id

    def _source_path(self) -> Path | None:
        value = self.spec.source.get("path")
        return self.spec.resolve_path(str(value)) if value else None

    def _shape_suffix(self) -> str:
        source = self._source_path()
        if self.spec.source.get("mode") == "frames":
            return ".frames.json"
        if self.spec.source.get("mode") in {"model", "blend"} and source:
            return source.suffix.lower()
        return ".glb"

    def outputs(self) -> dict[str, Path]:
        suffix = self._shape_suffix()
        frame_source = self.spec.source.get("mode") == "frames"
        return {
            "source": self.root / "source" / "source.json",
            "shape": self.root / "shape" / f"{self.spec.asset_id}{suffix}",
            "texture": self.root / "texture" / f"{self.spec.asset_id}{suffix}",
            "prepare": self.root / "prepare" / f"{self.spec.asset_id}{'.frames.json' if frame_source else '.glb'}",
            "rig": self.root / "rig" / f"{self.spec.asset_id}{'.frames.json' if frame_source else '.glb'}",
            "animate": self.root / "animate" / f"{self.spec.asset_id}{'.frames.json' if frame_source else '.blend'}",
            "render": self.root / "render" / "render_manifest.json",
            "pack": self.root / "pack" / "atlas_manifest.json",
            "export": self.root / "export" / f"{self.spec.asset_id}.tres",
        }

    def provider_for(self, stage: str) -> str:
        frame_source = self.spec.source.get("mode") == "frames"
        if stage == "shape":
            if self.spec.source.get("mode") in {"model", "blend"}:
                return "passthrough"
            if frame_source:
                return "builtin"
            return str(self.spec.section("geometry").get("provider", "manual"))
        if stage == "rig":
            rig = self.spec.section("rig")
            return "passthrough" if not rig.get("enabled", False) or rig.get("pre_rigged", False) else str(rig.get("provider", "manual"))
        if stage == "texture":
            texture = self.spec.section("texture")
            if self.spec.source.get("mode") in {"model", "blend", "frames"} or not texture.get("enabled", True):
                return "passthrough"
            return str(texture.get("provider", "passthrough"))
        if stage in {"prepare", "animate", "render"}:
            return "builtin" if frame_source else "blender"
        if stage in {"pack", "export", "source"}:
            return "builtin"
        return "unknown"

    def _provider_availability(self, stage: str) -> str:
        provider = self.provider_for(stage)
        if provider in {"builtin", "passthrough"}:
            return "ready"
        if provider == "blender" or (stage == "rig" and provider == "blender_weight_transfer"):
            return "ready" if self.config.tool("blender").get("enabled", False) else "disabled"
        category = {"shape": "shape", "texture": "texture", "rig": "rig"}.get(stage)
        if category is None:
            return "ready"
        configured = self.config.provider(category, provider)
        if not configured or not configured.get("enabled", False):
            return "disabled"
        return "manual" if configured.get("kind") == "manual" else "ready"

    def plan(self) -> list[StagePlan]:
        outputs = self.outputs()
        source_path = self._source_path()
        previous = str(source_path) if source_path else None
        plans: list[StagePlan] = []
        prior_will_complete = True
        for index, stage in enumerate(self.config.stages):
            output = outputs[stage]
            availability = self._provider_availability(stage)
            if output.exists():
                status = "cached"
                prior_will_complete = True
            elif not prior_will_complete:
                status = "blocked"
            elif availability in {"disabled", "manual"}:
                status = availability
                prior_will_complete = False
            elif index == 0:
                source = self._source_path()
                source_required = self.spec.source.get("mode") in {"image", "model", "blend", "frames"}
                status = "blocked" if source_required and (source is None or not source.exists()) else "ready"
                prior_will_complete = status == "ready"
            else:
                status = "ready" if Path(previous or "").exists() else "waiting"
                prior_will_complete = True
            plans.append(StagePlan(stage, self.provider_for(stage), previous, str(output), status))
            previous = str(output)
        return plans

    def request_for_stage(self, stage: str) -> Path:
        if stage not in self.config.stages:
            raise PipelineError(f"Unknown stage {stage!r}")
        output = self.outputs()[stage]
        request_path = self.root / stage / "request.json"
        write_provider_request(request_path, self._request_payload(stage, output))
        return request_path

    def accept_result(self, stage: str, result: Path, force: bool = False) -> Path:
        if stage not in HANDOFF_STAGES:
            allowed = ", ".join(sorted(HANDOFF_STAGES))
            raise PipelineError(f"Stage {stage!r} cannot be accepted as a single file; choose one of: {allowed}")
        source = result.resolve()
        if not source.is_file():
            raise PipelineError(f"Result does not exist: {source}")
        if source.stat().st_size == 0:
            raise PipelineError(f"Result is empty: {source}")
        output = self.outputs()[stage]
        if source.suffix.lower() != output.suffix.lower():
            raise PipelineError(
                f"Result for {stage} must be {output.suffix} (received {source.suffix or 'no extension'})"
            )
        if output.exists() and not force:
            raise PipelineError(f"Output already exists: {output}; use --force to replace it")

        self.request_for_stage(stage)
        output.parent.mkdir(parents=True, exist_ok=True)
        if source != output.resolve():
            shutil.copy2(source, output)
        self._record_state(stage, output, {"accepted_from": str(source)})
        return output

    def build(self, dry_run: bool = False, from_stage: str | None = None, force: bool = False) -> list[StagePlan]:
        stages = self.config.stages
        if from_stage and from_stage not in stages:
            raise PipelineError(f"Unknown stage {from_stage!r}")
        start = stages.index(from_stage) if from_stage else 0
        plans = self.plan()
        self.root.mkdir(parents=True, exist_ok=True)

        for plan in plans[start:]:
            output = Path(plan.output)
            request_path = self.root / plan.stage / "request.json"
            payload = self._request_payload(plan.stage, output)
            write_provider_request(request_path, payload)
            if dry_run:
                continue
            if output.exists() and not force:
                continue
            getattr(self, f"_run_{plan.stage}")(output, request_path, payload)
            self._record_state(plan.stage, output)
        return self.plan()

    def _request_payload(self, stage: str, output: Path) -> dict[str, Any]:
        prior = None
        outputs = self.outputs()
        index = self.config.stages.index(stage)
        if index:
            prior = str(outputs[self.config.stages[index - 1]])
        spec_data = copy.deepcopy(self.spec.data)
        if not spec_data.get("animations"):
            profile_name = spec_data.get("render", {}).get("animation_profile")
            if profile_name:
                profile_path = self.config.root / "profiles" / "animations" / f"{profile_name}.toml"
                with profile_path.open("rb") as handle:
                    spec_data["animations"] = tomllib.load(handle).get("clips", [])
        return {
            "schema_version": 1,
            "asset_id": self.spec.asset_id,
            "asset_kind": self.spec.kind,
            "stage": stage,
            "provider": self.provider_for(stage),
            "input": prior,
            "output": str(output),
            "spec_path": str(self.spec.path),
            "source_resolved": str(self._source_path()) if self._source_path() else None,
            "spec": spec_data,
        }

    def _record_state(self, stage: str, output: Path, metadata: dict[str, Any] | None = None) -> None:
        state_path = self.root / "state.json"
        state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {"stages": {}}
        digest = None
        if output.is_file():
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
        state["asset_id"] = self.spec.asset_id
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        record = {"output": str(output), "sha256": digest, "complete": output.exists()}
        if metadata:
            record.update(metadata)
        state["stages"][stage] = record
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", "utf-8")

    def _run_source(self, output: Path, _request: Path, payload: dict[str, Any]) -> None:
        source_path = self._source_path()
        mode = self.spec.source.get("mode")
        if source_path and not source_path.exists():
            raise PipelineError(f"Source does not exist: {source_path}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"mode": mode, "path": str(source_path) if source_path else None,
                                      "prompt": self.spec.source.get("prompt")}, indent=2) + "\n", "utf-8")

    def _run_shape(self, output: Path, request: Path, payload: dict[str, Any]) -> None:
        source = self._source_path()
        mode = self.spec.source.get("mode")
        if mode in {"model", "blend"}:
            if source is None or not source.exists():
                raise PipelineError("Existing model source is missing")
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            return
        if mode == "frames":
            if source is None or not source.exists():
                raise PipelineError("Frame source is missing")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "schema_version": 1,
                "asset_id": self.spec.asset_id,
                "source": str(source),
                "kind": "frame_directory" if source.is_dir() else "render_manifest",
            }, indent=2) + "\n", "utf-8")
            return
        provider = self.provider_for("shape")
        run_provider(self.config, ProviderRequest("shape", provider, request, source, output, self.spec.asset_id))

    def _blender(self, script: str, request: Path) -> None:
        tool = self.config.tool("blender")
        if not tool.get("enabled", False):
            raise PipelineError("Blender is disabled in mos.toml")
        executable = shutil.which(str(tool.get("executable", "blender"))) or str(tool.get("executable", "blender"))
        script_path = self.config.root / self.config.data["project"].get("blender_scripts", "tools/blender") / script
        result = subprocess.run([executable, "--background", "--python", str(script_path), "--", "--request", str(request)],
                                cwd=self.config.root, check=False)
        if result.returncode:
            raise PipelineError(f"Blender stage {script} failed with {result.returncode}")

    def _run_prepare(self, _output: Path, request: Path, _payload: dict[str, Any]) -> None:
        if self.spec.source.get("mode") == "frames":
            _output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.outputs()["texture"], _output)
            return
        self._blender("prepare_scene.py", request)

    def _run_texture(self, output: Path, request: Path, _payload: dict[str, Any]) -> None:
        input_path = self.outputs()["shape"]
        provider = self.provider_for("texture")
        if provider == "passthrough":
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output)
            return
        run_provider(self.config, ProviderRequest("texture", provider, request, input_path, output,
                                                  self.spec.asset_id))

    def _run_rig(self, output: Path, request: Path, _payload: dict[str, Any]) -> None:
        input_path = self.outputs()["prepare"]
        if self.spec.source.get("mode") == "frames":
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output)
            return
        rig = self.spec.section("rig")
        if not rig.get("enabled", False) or rig.get("pre_rigged", False):
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output)
            return
        if self.provider_for("rig") == "blender_weight_transfer":
            self._blender("rig_equipment.py", request)
            return
        run_provider(self.config, ProviderRequest("rig", self.provider_for("rig"), request, input_path, output,
                                                  self.spec.asset_id))

    def _run_animate(self, output: Path, request: Path, _payload: dict[str, Any]) -> None:
        if self.spec.source.get("mode") == "frames":
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.outputs()["rig"], output)
            return
        self._blender("apply_animations.py", request)

    def _run_render(self, _output: Path, request: Path, _payload: dict[str, Any]) -> None:
        if self.spec.source.get("mode") == "frames":
            self._write_frame_render_manifest(_output, _payload)
            return
        self._blender("render_sprites.py", request)

    def _write_frame_render_manifest(self, output: Path, payload: dict[str, Any]) -> None:
        source = self._source_path()
        if source is None or not source.exists():
            raise PipelineError("Frame source is missing")
        output.parent.mkdir(parents=True, exist_ok=True)

        if source.is_file():
            if source.suffix.lower() != ".json":
                raise PipelineError("source.mode='frames' expects a frame directory or a JSON render manifest")
            job = json.loads(source.read_text("utf-8"))
            source_dir = Path(str(job.get("source_dir", "")))
            if not source_dir.is_absolute():
                job["source_dir"] = str((source.parent / source_dir).resolve())
            job["asset_id"] = self.spec.asset_id
            job["output_manifest"] = str(self.outputs()["pack"])
            output.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n", "utf-8")
            return

        render = dict(payload["spec"].get("render", {}))
        profile_name = str(render.get("profile", "effect"))
        profile_path = self.config.root / "profiles" / "render" / f"{profile_name}.toml"
        with profile_path.open("rb") as handle:
            profile = tomllib.load(handle)
        profile.update(render)

        direction_count = int(profile.get("directions", 8))
        direction_order = list(profile.get("direction_order", []))
        declared_directions = self.spec.source.get("directions")
        if isinstance(declared_directions, list) and declared_directions:
            directions = [str(value) for value in declared_directions]
        elif direction_count == 1 and direction_order:
            directions = direction_order[:1]
        elif 0 < direction_count <= len(direction_order):
            step = max(1, len(direction_order) // direction_count)
            directions = direction_order[::step][:direction_count]
        else:
            raise PipelineError(
                f"Render profile {profile_name!r} needs at least {direction_count} entries in direction_order"
            )

        width, height = map(int, self.spec.source.get("frame_size", profile.get("frame_size", [256, 256])))
        if "frame_size" not in self.spec.source:
            scale = int(profile.get("resolution_percentage", 100))
            width, height = width * scale // 100, height * scale // 100
        clips = list(payload["spec"].get("animations", [])) or [
            {"id": "static", "fps": 1, "frames": 1, "loop": True}
        ]
        job = {
            "schema_version": 1,
            "asset_id": self.spec.asset_id,
            "source_dir": str(source),
            "output_manifest": str(self.outputs()["pack"]),
            "frame_size": [width, height],
            "directions": directions,
            "clips": [
                {
                    "id": clip["id"],
                    "fps": clip["fps"],
                    "frames": clip["frames"],
                    "loop": clip.get("loop", True),
                    "events": clip.get("events", []),
                }
                for clip in clips
            ],
            "passes": list(profile.get("passes", ["color"])),
            "atlas_max_size": int(profile.get("atlas_max_size", 8192)),
            "pivot": payload["spec"].get("sprite", {}).get("pivot", profile.get("pivot")),
            "layer": render.get("layer", "effect_front"),
            "blend_mode": render.get("blend_mode", profile.get("blend_mode", "mix")),
            "shared_canvas": payload["spec"].get("sprite", {}).get("shared_canvas"),
        }
        output.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n", "utf-8")

    def _run_pack(self, output: Path, _request: Path, payload: dict[str, Any]) -> None:
        render_manifest = self.outputs()["render"]
        if not render_manifest.exists():
            raise PipelineError(f"Missing render manifest: {render_manifest}")
        job = json.loads(render_manifest.read_text("utf-8"))
        job["output_manifest"] = str(output)
        pack_job(job)

    def _run_export(self, output: Path, _request: Path, _payload: dict[str, Any]) -> None:
        manifest_path = self.outputs()["pack"]
        manifest = json.loads(manifest_path.read_text("utf-8"))
        output.parent.mkdir(parents=True, exist_ok=True)
        for atlas_value in manifest.get("atlases", {}).values():
            pages = [atlas_value] if isinstance(atlas_value, dict) else atlas_value
            for atlas in pages:
                source = manifest_path.parent / atlas["path"]
                shutil.copy2(source, output.parent / source.name)
        export_godot_sprite_frames(manifest_path, output, "./")
        shutil.copy2(manifest_path, output.with_suffix(".json"))
