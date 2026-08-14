from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mos_asset_factory.config import load_config
from mos_asset_factory.models import install_models, load_model_registry, required_models


class ModelManagerTests(unittest.TestCase):
    def test_registry_contains_supported_workers(self) -> None:
        definitions, cache = load_model_registry(load_config(ROOT / "mos.toml"))
        self.assertEqual(set(definitions), {"hunyuan3d", "trellis", "unirig"})
        self.assertEqual(cache, ROOT / "models" / "huggingface")
        self.assertTrue(definitions["trellis"].recursive)

    def test_required_models_are_inferred_from_asset_specs(self) -> None:
        required = required_models(load_config(ROOT / "mos.toml"), ROOT / "examples" / "assets")
        self.assertEqual(required, ["hunyuan3d", "unirig"])

    def test_dry_run_plans_downloads_without_writing(self) -> None:
        config = load_config(ROOT / "mos.toml")
        actions = install_models(config, ["hunyuan3d"], include_weights=True, dry_run=True)
        self.assertTrue(any("Hunyuan3D-2.1.git" in action for action in actions))
        self.assertTrue(any("tencent/Hunyuan3D-2.1" in action for action in actions))
        self.assertFalse((ROOT / ".env").exists())


if __name__ == "__main__":
    unittest.main()
