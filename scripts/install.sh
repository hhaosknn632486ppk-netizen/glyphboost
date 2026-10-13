#!/usr/bin/env bash
# glyphboost installer (macOS / Linux)
# Creates a local venv with rapidocr + onnxruntime (CPU only).
# Usage: bash install.sh [--mirror mirrors.aliyun.com/pypi/simple/]
#   (tuna mirror returns 403 to some pip versions; aliyun is the tested fallback)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIRROR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mirror) MIRROR="$2"; shift 2 ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
done

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found in PATH"; exit 1; }

VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then
  echo "[1/3] creating venv at $VENV ..."
  "$PY" -m venv "$VENV"
else
  echo "[1/3] venv already exists, reusing"
fi

PIP="$VENV/bin/pip"
if [ -n "$MIRROR" ]; then
  PIP="$PIP -i https://$MIRROR"
fi

echo "[2/3] installing rapidocr + onnxruntime (CPU) ..."
$PIP install --quiet rapidocr onnxruntime

echo "[3/3] verifying ..."
"$VENV/bin/python" - <<'EOF'
from rapidocr import RapidOCR
import cv2, numpy
print("glyphboost deps OK:",
      "cv2", cv2.__version__, "| numpy", numpy.__version__)
EOF

echo "done. run: $VENV/bin/python $SCRIPT_DIR/scripts/glyphboost.py IMAGE.png"
