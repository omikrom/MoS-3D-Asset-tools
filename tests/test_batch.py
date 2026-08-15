from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mos_asset_factory.batch import BatchError, load_batch


class BatchTests(unittest.TestCase):
    def test_weight_transfer_template_is_ordered_before_equipment(self) -> None:
        batch = load_batch(ROOT / "examples" / "assets")
        ids = [item.spec.asset_id for item in batch]
        self.assertLess(ids.index("human_male"), ids.index("iron_chest_armour"))
        armour = next(item for item in batch if item.spec.asset_id == "iron_chest_armour")
        self.assertEqual(armour.dependencies, ("human_male",))

    def test_dependency_cycle_is_rejected(self) -> None:
        template = """
[asset]
id = "{asset_id}"
kind = "prop"
depends_on = ["{dependency}"]

[source]
mode = "text"
prompt = "test prop"
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset_a.toml").write_text(template.format(asset_id="asset_a", dependency="asset_b"), "utf-8")
            (root / "asset_b.toml").write_text(template.format(asset_id="asset_b", dependency="asset_a"), "utf-8")
            with self.assertRaisesRegex(BatchError, "dependency cycle"):
                load_batch(root)


if __name__ == "__main__":
    unittest.main()
