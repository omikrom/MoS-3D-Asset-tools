from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import json

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mos_asset_factory.config import FactoryConfig, load_config
from mos_asset_factory.pipeline import AssetPipeline, PipelineError
from mos_asset_factory.spec import load_spec


class PipelineTests(unittest.TestCase):
    def test_plan_has_replaceable_stages(self) -> None:
        base = load_config(ROOT / "mos.toml")
        with tempfile.TemporaryDirectory() as directory:
            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=directory)
            config = FactoryConfig(ROOT, data)
            spec = load_spec(ROOT / "examples" / "assets" / "human_male.toml")
            pipeline = AssetPipeline(config, spec)
            plans = pipeline.plan()
            self.assertEqual(
                [plan.stage for plan in plans],
                ["source", "shape", "texture", "prepare", "rig", "animate", "render", "pack", "export"],
            )
            self.assertEqual(plans[1].provider, "hunyuan3d")
            self.assertEqual(plans[2].provider, "hunyuan3d")
            self.assertEqual(plans[4].provider, "unirig")

    def test_dry_run_writes_requests_without_models(self) -> None:
        base = load_config(ROOT / "mos.toml")
        with tempfile.TemporaryDirectory() as directory:
            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=directory)
            config = FactoryConfig(ROOT, data)
            spec = load_spec(ROOT / "examples" / "assets" / "human_male.toml")
            pipeline = AssetPipeline(config, spec)
            pipeline.build(dry_run=True)
            for stage in config.stages:
                self.assertTrue((Path(directory) / "assets" / "human_male" / stage / "request.json").is_file())

    def test_equipment_expands_shared_animation_profile(self) -> None:
        base = load_config(ROOT / "mos.toml")
        with tempfile.TemporaryDirectory() as directory:
            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=directory)
            pipeline = AssetPipeline(FactoryConfig(ROOT, data), load_spec(ROOT / "examples" / "assets" / "iron_sword.toml"))
            pipeline.build(dry_run=True)
            request = json.loads((Path(directory) / "assets" / "iron_sword" / "animate" / "request.json").read_text("utf-8"))
            self.assertEqual([clip["id"] for clip in request["spec"]["animations"]], [
                "peaceful_idle", "combat_idle_standard", "walk_standard", "run", "hit_reaction", "cast", "die"
            ])

    def test_accept_external_result_records_provenance_and_hash(self) -> None:
        base = load_config(ROOT / "mos.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=str(root / "workspace"))
            pipeline = AssetPipeline(FactoryConfig(ROOT, data), load_spec(ROOT / "examples" / "assets" / "human_male.toml"))
            external = root / "generated.glb"
            external.write_bytes(b"synthetic glb result")

            output = pipeline.accept_result("shape", external)

            self.assertEqual(output.read_bytes(), b"synthetic glb result")
            state = json.loads((root / "workspace" / "assets" / "human_male" / "state.json").read_text("utf-8"))
            self.assertTrue(state["stages"]["shape"]["complete"])
            self.assertEqual(state["stages"]["shape"]["accepted_from"], str(external))
            self.assertEqual(len(state["stages"]["shape"]["sha256"]), 64)
            self.assertTrue((output.parent / "request.json").is_file())

    def test_accept_rejects_wrong_file_type(self) -> None:
        base = load_config(ROOT / "mos.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=str(root / "workspace"))
            pipeline = AssetPipeline(FactoryConfig(ROOT, data), load_spec(ROOT / "examples" / "assets" / "human_male.toml"))
            wrong = root / "generated.obj"
            wrong.write_text("v 0 0 0\n", "utf-8")
            with self.assertRaisesRegex(PipelineError, "must be .glb"):
                pipeline.accept_result("shape", wrong)

    def test_frame_source_builds_to_godot_without_blender(self) -> None:
        base = load_config(ROOT / "mos.toml")
        spec_text = """
schema_version = 1

[asset]
id = "frame_fire"
kind = "effect"

[source]
mode = "frames"
path = "frames"
frame_size = [16, 16]
directions = ["south"]

[texture]
enabled = false

[rig]
enabled = false

[render]
profile = "effect"
directions = 1
passes = ["color"]
blend_mode = "add"

[sprite]
pivot = [8, 12]

[[animations]]
id = "burn"
fps = 12
frames = 2
loop = true
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path = root / "frame_fire.toml"
            spec_path.write_text(spec_text, "utf-8")
            for index in range(2):
                frame = root / "frames" / "color" / "burn" / "south" / f"{index:04d}.png"
                frame.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (16, 16), (255, index * 80, 0, 255)).save(frame)

            data = dict(base.data)
            data["project"] = dict(data["project"], workspace=str(root / "workspace"))
            pipeline = AssetPipeline(FactoryConfig(ROOT, data), load_spec(spec_path))
            plans = pipeline.build()

            self.assertTrue(pipeline.outputs()["export"].is_file())
            self.assertTrue(pipeline.outputs()["pack"].is_file())
            self.assertEqual({plan.status for plan in plans}, {"cached"})
            resource = pipeline.outputs()["export"].read_text("utf-8")
            self.assertIn('&"burn_south"', resource)
            manifest = json.loads(pipeline.outputs()["pack"].read_text("utf-8"))
            self.assertEqual(manifest["metadata"]["blend_mode"], "add")


if __name__ == "__main__":
    unittest.main()
