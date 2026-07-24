#!/usr/bin/env python3
"""Build Split Tracks standalone executable with PyInstaller."""

import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_APP = ROOT
STATIC = ROOT / "static"
DIST = ROOT / "dist"
NAME = "SplitTracks"

def run(cmd):
    print(f"  {''.join(cmd)}")
    subprocess.run(cmd, check=True)

def main():
    platform = sys.platform
    print(f"Building for {platform}...")
    DIST.mkdir(exist_ok=True)

    sep = ";" if platform == "win32" else ":"
    add_data = f"static{sep}static"
    if (ROOT / "assets").exists():
        add_data += f"{sep}assets{sep}assets"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--windowed", "--name", NAME,
        f"--add-data={add_data}",
        "--distpath", str(DIST),
        "--workpath", str(DIST / "build"),
        "--specpath", str(DIST), "--clean", "--noconfirm",
        str(WEB_APP / "launcher.py"),
    ]

    run(cmd)

    bundle = DIST / f"{NAME}-{platform}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir()

    exe_dir = DIST / NAME
    exe_name = f"{NAME}{'.exe' if platform == 'win32' else ''}"
    shutil.move(str(exe_dir / exe_name), str(bundle / exe_name))

    # Copy bin tools
    bin_dest = bundle / "bin"
    bin_dest.mkdir(exist_ok=True)
    bin_src = ROOT / "bin"
    if bin_src.exists():
        for item in bin_src.iterdir():
            if item.is_file():
                shutil.copy2(item, bin_dest / item.name)

    # Copy .venv if exists (for demucs)
    venv_dest = bundle / ".venv"
    venv_src = ROOT / ".venv"
    if venv_src.exists() and not venv_dest.exists():
        shutil.copytree(venv_src, venv_dest, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Launcher
    if platform == "win32":
        (bundle / "SplitTracks.vbs").write_text('CreateObject("Wscript.Shell").Run "SplitTracks.exe", 0, False\r\n')
    else:
        (bundle / "SplitTracks").write_text("#!/bin/bash\ncd \"$(dirname \"$0\")\"\n./SplitTracks\n")
        (bundle / "SplitTracks").chmod(0o755)

    print(f"\nBundle ready: {bundle}")

if __name__ == "__main__":
    main()
