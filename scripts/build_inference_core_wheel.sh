#!/usr/bin/env bash
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)/packages/inference-core"
cd "$PKG_DIR"

PY=python3
VENV_DIR=".venv-build"
rm -rf "$VENV_DIR"
$PY -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install --upgrade build >/dev/null

python -m build
echo "Built wheel(s):"
ls -1 dist/*.whl

deactivate
rm -rf "$VENV_DIR"


