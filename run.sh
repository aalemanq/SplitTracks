#!/usr/bin/env bash
# Split Tracks — macOS / Linux launcher
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements-web.txt

echo "Starting Split Tracks at http://127.0.0.1:8745"
python launcher.py
