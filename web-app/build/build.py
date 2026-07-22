#!/usr/bin/env python3
"""Build standalone Split Tracks executable for macOS / Windows / Linux."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_APP = Path(__file__).resolve().parent.parent
STATIC = WEB_APP / "static"
DIST = ROOT / "dist"
NAME = "SplitTracks"

def run(cmd, **kwargs):
    print(f"  \033[36m{' '.join(cmd)}\033[0m")
    subprocess.run(cmd, check=True, **kwargs)

def main():
    print(f"\033[1;32m=== Split Tracks Builder ===\033[0m")
    platform = sys.platform  # 'darwin', 'win32', 'linux'

    DIST.mkdir(exist_ok=True)
    os.chdir(str(ROOT))

    # Ensure static files are discoverable
    print("\n[1/4] Preparing...")
    shutil.rmtree(DIST / NAME, ignore_errors=True)

    # Build with PyInstaller
    print("\n[2/4] Building executable...")
    add_data = f"web-app/static{os.pathsep}static"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", NAME,
        f"--add-data={add_data}",
        "--distpath", str(DIST),
        "--workpath", str(DIST / "build"),
        "--specpath", str(DIST),
        "--clean",
        "--noconfirm",
        str(WEB_APP / "launcher.py"),
    ]

    if platform == "darwin":
        cmd.append("--windowed")
    elif platform == "win32":
        cmd.append("--console")

    run(cmd)

    # Copy ffmpeg and yt-dlp binaries
    print("\n[3/4] Bundling tools...")
    exe_dir = DIST / NAME if not (DIST / NAME).is_dir() else DIST
    exe_dir = DIST

    if platform == "darwin":
        # On macOS, use homebrew ffmpeg or bundled
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        ytdlp = ROOT / "bin" / "yt-dlp"
        if ytdlp.exists():
            shutil.copy2(ytdlp, DIST / "yt-dlp")
    elif platform == "win32":
        ytdlp = ROOT / "bin" / "yt-dlp.exe"
        if ytdlp.exists():
            shutil.copy2(ytdlp, DIST / "yt-dlp.exe")

    # Copy bin directory
    print("\n[4/4] Creating distribution bundle...")
    _bundle = DIST / f"{NAME}-{platform}"
    _bundle.mkdir(exist_ok=True)

    executable = DIST / f"{NAME}{'.exe' if platform == 'win32' else ''}"
    if executable.exists():
        shutil.move(str(executable), str(_bundle / executable.name))

    # Copy bin tools
    bin_dir = _bundle / "bin"
    bin_dir.mkdir(exist_ok=True)
    for item in (ROOT / "bin").iterdir():
        if item.is_file():
            shutil.copy2(item, bin_dir / item.name)

    # Create convenience launchers in root of bundle
    if platform == "win32":
        (_bundle / "run.bat").write_text(
            '@echo off\r\nstart "" "SplitTracks.exe"\r\n', encoding="utf-8"
        )
    else:
        (_bundle / "run.sh").write_text("#!/bin/bash\n./SplitTracks\n")
        (_bundle / "run.sh").chmod(0o755)

    print(f"\n\033[1;32mDone! Bundle at: {_bundle}\033[0m")

if __name__ == "__main__":
    main()
