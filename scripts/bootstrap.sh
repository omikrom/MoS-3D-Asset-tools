#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env; edit the Blender/model paths before enabling providers."
fi

.venv/bin/mos doctor
.venv/bin/python -m unittest discover -s tests -v
