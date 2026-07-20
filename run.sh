#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  APP_PYTHON="$PROJECT_DIR/.venv/bin/python"
else
  APP_PYTHON="python3"
fi
exec "$APP_PYTHON" "$PROJECT_DIR/app.py" "$@"
