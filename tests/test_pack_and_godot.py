from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mos_asset_factory.godot import export_godot_sprite_frames
from mos_asset_factory.packer import pack_job


class PackTests(unittest.TestCase):
    def test_pack_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            for direction, colour in (("south", (255, 0, 0, 255)), ("north", (0, 0, 255, 255))):
                for index in range(2):
                    path = frames / "color" / "idle" / direction / f"{index:04d}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGBA", (16, 20), colour).save(path)
            manifest_path = root / "packed" / "atlas_manifest.json"
            job = {
                "asset_id": "test_actor",
                "source_dir": str(frames),
                "output_manifest": str(manifest_path),
                "frame_size": [16, 20],
                "directions": ["south", "north"],
                "clips": [{"id": "idle", "fps": 8, "frames": 2, "loop": True}],
                "passes": ["color"],
                "atlas_max_size": 128,
            }
            manifest = pack_job(job)
            self.assertEqual(len(manifest["frames"]), 4)
            self.assertTrue((manifest_path.parent / "test_actor_color.png").is_file())
            output = root / "export" / "test_actor.tres"
            export_godot_sprite_frames(manifest_path, output, "./")
            text = output.read_text("utf-8")
            self.assertIn('&"idle_south"', text)
            self.assertIn('&"idle_north"', text)
            self.assertIn("AtlasTexture", text)

    def test_multi_page_atlas_and_godot_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            for index in range(5):
                path = frames / "color" / "attack" / "south" / f"{index:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (16, 16), (index * 30, 20, 20, 255)).save(path)
            manifest_path = root / "packed" / "atlas_manifest.json"
            manifest = pack_job({
                "asset_id": "paged_actor",
                "source_dir": str(frames),
                "output_manifest": str(manifest_path),
                "frame_size": [16, 16],
                "directions": ["south"],
                "clips": [{"id": "attack", "fps": 10, "frames": 5, "loop": False}],
                "passes": ["color"],
                "atlas_max_size": 32,
            })
            self.assertEqual(len(manifest["atlases"]["color"]), 2)
            self.assertEqual({frame["atlas_page"] for frame in manifest["frames"]}, {0, 1})
            output = root / "export" / "paged_actor.tres"
            export_godot_sprite_frames(manifest_path, output, "./")
            text = output.read_text("utf-8")
            self.assertIn("paged_actor_color_000.png", text)
            self.assertIn("paged_actor_color_001.png", text)
            self.assertIn('ExtResource("2_atlas")', text)

    def test_oversized_frame_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "frames" / "color" / "idle" / "south" / "0000.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (33, 16), (255, 255, 255, 255)).save(path)
            with self.assertRaisesRegex(Exception, "larger than"):
                pack_job({
                    "asset_id": "bad_actor",
                    "source_dir": str(root / "frames"),
                    "output_manifest": str(root / "atlas.json"),
                    "frame_size": [16, 16],
                    "directions": ["south"],
                    "clips": [{"id": "idle", "fps": 1, "frames": 1}],
                    "passes": ["color"],
                    "atlas_max_size": 64,
                })


if __name__ == "__main__":
    unittest.main()
