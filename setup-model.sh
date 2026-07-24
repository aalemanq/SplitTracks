#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  python3 -m venv --copies --system-site-packages "$VENV_DIR"
fi

"$VENV_PYTHON" -m pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cpu \
  "torch==2.11.0+cpu" "torchaudio==2.11.0+cpu"
"$VENV_PYTHON" -m pip install --no-cache-dir \
  "demucs==4.1.0" "numpy>=2,<3" "scipy>=1.13,<2" \
  "requests>=2.31,<3" "beautifulsoup4>=4.12,<5"

printf '%s\n' "Split Tracks ML listo: Demucs htdemucs_6s en CPU."
