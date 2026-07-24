#!/usr/bin/env bash
# Build Split Tracks for Linux — portable tar.gz
# Requirements: Python 3, PyInstaller, ffmpeg in PATH
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

APP_NAME="SplitTracks"
VERSION="${SPLITTRACKS_VERSION:-0.1.0}"
VENV_PYTHON=".venv/bin/python"
DIST="dist/${APP_NAME}-linux"
ARCHIVE="dist/${APP_NAME}-linux-x86_64.tar.gz"

echo "=== Building Split Tracks for Linux ==="
echo ""

# 1. Install dependencies
echo "[1/5] Installing dependencies..."
$VENV_PYTHON -m pip install -q pyinstaller

# 2. Build with PyInstaller
echo "[2/5] Building .exe..."
$VENV_PYTHON build/build.py

# 3. Bundle FFmpeg
echo "[3/5] Bundling FFmpeg..."
BIN_DIR="$DIST/bin"
mkdir -p "$BIN_DIR"

for tool in ffmpeg ffprobe; do
    if command -v "$tool" &>/dev/null; then
        cp "$(command -v "$tool")" "$BIN_DIR/" 2>/dev/null || true
        echo "  $tool bundled"
    else
        echo "  WARNING: $tool not found in PATH"
    fi
done

# 4. Version file
echo "[4/5] Writing version info..."
cat > "$DIST/VERSION.txt" << EOF
Split Tracks $VERSION
Build: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Platform: Linux x86_64
EOF

# 5. Create tar.gz
echo "[5/5] Creating portable archive..."
rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" -C dist "${APP_NAME}-linux" 2>/dev/null

echo ""
echo "=== Done! ==="
echo "Bundle:   $DIST"
echo "Archive:  $ARCHIVE"
du -sh "$DIST" "$ARCHIVE" 2>/dev/null
