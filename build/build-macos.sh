#!/usr/bin/env bash
# Build Split Tracks for macOS
# Requirements: Python 3, PyInstaller, create-dmg (brew install create-dmg)
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="SplitTracks"
VENV_PYTHON=".venv/bin/python"
DIST="dist/$APP_NAME-macos"
BUNDLE="$DIST/$APP_NAME.app"

echo "=== Building Split Tracks for macOS ==="

# 1. Install dependencies
echo "[1/5] Installing dependencies..."
$VENV_PYTHON -m pip install -q -r requirements-web.txt pyinstaller

# 2. Build with PyInstaller
echo "[2/5] Building .app bundle..."
$VENV_PYTHON -m PyInstaller \
  --onedir \
  --name "$APP_NAME" \
  --add-data "static:static" \
  --distpath "$DIST" \
  --workpath "$DIST/build" \
  --specpath "$DIST" \
  --noconfirm \
  --clean \
  --windowed \
  --osx-bundle-identifier "com.splittracks.app" \
  launcher.py

# 3. Copy binary tools into bundle
echo "[3/5] Bundling tools..."
RESOURCES="$BUNDLE/Contents/Resources"
mkdir -p "$RESOURCES/bin"

# yt-dlp
YTDLP="bin/yt-dlp"
[ -f "$YTDLP" ] && cp "$YTDLP" "$RESOURCES/bin/"

# FFmpeg from system or homebrew
if command -v ffmpeg &>/dev/null; then
  cp "$(command -v ffmpeg)" "$RESOURCES/bin/" 2>/dev/null || true
  cp "$(command -v ffprobe)" "$RESOURCES/bin/" 2>/dev/null || true
elif [ -f "/opt/homebrew/bin/ffmpeg" ]; then
  cp /opt/homebrew/bin/ffmpeg "$RESOURCES/bin/"
  cp /opt/homebrew/bin/ffprobe "$RESOURCES/bin/"
fi

# 4. Create Info.plist
echo "[4/5] Writing Info.plist..."
cat > "$BUNDLE/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Split Tracks</string>
  <key>CFBundleIdentifier</key>
  <string>com.splittracks.app</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>SplitTracks</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>CFBundleIconFile</key>
  <string>icon.icns</string>
</dict>
</plist>
PLIST

# 5. Create DMG
echo "[5/5] Creating DMG..."
if command -v create-dmg &>/dev/null; then
  create-dmg \
    --volname "Split Tracks" \
    --window-pos 200 120 \
    --window-size 500 350 \
    --app-drop-link 425 180 \
    "$DIST/SplitTracks-macOS.dmg" \
    "$BUNDLE" 2>/dev/null
  echo "DMG created: $DIST/SplitTracks-macOS.dmg"
else
  echo "create-dmg not found. Install with: brew install create-dmg"
  echo "App bundle is at: $BUNDLE"
fi

echo ""
echo "=== Done! ==="
echo "Bundle: $BUNDLE"
[ -f "$DIST/SplitTracks-macOS.dmg" ] && echo "DMG: $DIST/SplitTracks-macOS.dmg"
