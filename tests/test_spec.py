from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mos_asset_factory.spec import discover_specs, load_spec


class SpecTests(unittest.TestCase):
    def test_all_examples_are_valid(self) -> None:
        specs = list(discover_specs(ROOT / "examples" / "assets"))
        self.assertGreaterEqual(len(specs), 6)
        loaded = [load_spec(path) for path in specs]
        self.assertIn("human_male", {spec.asset_id for spec in loaded})

    def test_human_preserves_core_legacy_slots(self) -> None:
        spec = load_spec(ROOT / "examples" / "assets" / "human_male.toml")
        slots = {animation.get("legacy_slot") for animation in spec.animations}
        self.assertTrue({0, 4, 13, 14, 15, 16, 18}.issubset(slots))


if __name__ == "__main__":
    unittest.main()
