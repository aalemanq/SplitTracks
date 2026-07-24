#!/usr/bin/env bash
# Build Split Tracks for macOS
# Requirements: Python 3, PyInstaller, create-dmg (brew install create-dmg)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

APP_NAME="SplitTracks"
VENV_PYTHON=".venv/bin/python"
VERSION="${SPLITTRACKS_VERSION:-0.1.0}"
DIST="dist/${APP_NAME}-macos"
BUNDLE="$DIST/$APP_NAME.app"

echo "=== Building Split Tracks for macOS ==="

# 1. Core build using shared build.py
echo "[1/4] Building with PyInstaller..."
$VENV_PYTHON build/build.py

# build.py outputs to dist/SplitTracks-darwin/
SRC_DIR="dist/${APP_NAME}-darwin"

# 2. Create .app bundle structure
echo "[2/4] Creating .app bundle..."
mkdir -p "$BUNDLE/Contents/MacOS"
mkdir -p "$BUNDLE/Contents/Resources"

# Move everything into Resources
if [ -d "$SRC_DIR" ]; then
  for item in "$SRC_DIR"/*; do
    mv "$item" "$BUNDLE/Contents/Resources/" 2>/dev/null || true
  done
  rm -rf "$SRC_DIR"
fi

# Wrapper script in MacOS that launches from Resources
cat > "$BUNDLE/Contents/MacOS/$APP_NAME" << 'WRAPPER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/../Resources"
exec "./SplitTracks"
WRAPPER
chmod +x "$BUNDLE/Contents/MacOS/$APP_NAME"

# 3. Info.plist
echo "[3/4] Writing Info.plist..."
cat > "$BUNDLE/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Split Tracks</string>
  <key>CFBundleIdentifier</key>
  <string>com.splittracks.app</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

# 4. DMG
echo "[4/4] Creating DMG..."
if command -v create-dmg &>/dev/null; then
  create-dmg \
    --volname "Split Tracks" \
    --window-pos 200 120 \
    --window-size 500 350 \
    --app-drop-link 425 180 \
    "$DIST/SplitTracks-macOS.dmg" \
    "$BUNDLE" 2>/dev/null
  echo "DMG: $DIST/SplitTracks-macOS.dmg"
else
  echo "create-dmg not found. Install with: brew install create-dmg"
  echo "App bundle: $BUNDLE"
fi

echo "=== Done ==="
