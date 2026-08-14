"""UniRig adapter following the official skeleton -> skin -> merge workflow."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from provider_common import load_request, require_home


def run(command: list[str], cwd: Path) -> None:
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).resolve().parent) + os.pathsep + environment.get("PATH", "")
    result = subprocess.run(command, cwd=cwd, env=environment, check=False)
    if result.returncode:
        raise RuntimeError(f"UniRig command failed ({result.returncode}): {' '.join(command)}")


def main() -> None:
    _path, request = load_request()
    home = require_home("UNIRIG_HOME")
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("UniRig's official launch scripts require bash (Linux, WSL or Git Bash)")
    source = Path(request["input"]).resolve()
    output = Path(request["output"]).resolve()
    if not source.is_file():
        raise RuntimeError(f"UniRig input is missing: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mos-unirig-") as directory:
        temporary = Path(directory)
        skeleton = temporary / "skeleton.fbx"
        skin = temporary / "skin.fbx"
        run([bash, "launch/inference/generate_skeleton.sh", "--input", str(source), "--output", str(skeleton)], home)
        run([bash, "launch/inference/generate_skin.sh", "--input", str(skeleton), "--output", str(skin)], home)
        run([bash, "launch/inference/merge.sh", "--source", str(skin), "--target", str(source), "--output", str(output)], home)
    if not output.is_file():
        raise RuntimeError(f"UniRig completed without producing {output}")


if __name__ == "__main__":
    main()
