from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


def load_request() -> tuple[Path, dict[str, Any]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parsed = parser.parse_args()
    path = parsed.request.resolve()
    return path, json.loads(path.read_text("utf-8"))


def require_home(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise RuntimeError(f"{variable} is not configured")
    path = Path(value).resolve()
    if not path.is_dir():
        raise RuntimeError(f"{variable} does not point to a directory: {path}")
    return path


def add_python_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def export_result(result: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    candidates = result if isinstance(result, (list, tuple)) else [result]
    for candidate in candidates:
        if hasattr(candidate, "export"):
            candidate.export(str(output))
            return
        if isinstance(candidate, (str, Path)) and Path(candidate).is_file():
            shutil.copy2(candidate, output)
            return
    raise RuntimeError(f"Model returned {type(result).__name__}, which the adapter cannot export")
