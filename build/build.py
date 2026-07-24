#!/usr/bin/env python3
"""Build Split Tracks standalone executable with PyInstaller."""

import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
NAME = "SplitTracks"

def run(cmd):
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _strip_venv(venv_dir: Path) -> None:
    site_packages = venv_dir / "lib"
    if not site_packages.exists():
        return
    sp_root = next(site_packages.glob("python3.*/site-packages"), None)
    if not sp_root:
        return

    removed = 0
    extensions = (".pyx", ".pxd", ".h", ".hpp", ".c", ".cpp", ".cxx", ".cc")
    for ext in extensions:
        for f in sp_root.rglob(f"*{ext}"):
            f.unlink(missing_ok=True)
            removed += 1

    for pth_file in sp_root.rglob("*.pth"):
        if pth_file.name not in ("distutils-precedence.pth",):
            pth_file.unlink(missing_ok=True)

    print(f"  Stripped {removed} non-essential files from .venv")

def main():
    platform = sys.platform
    print(f"Building for {platform}...")
    DIST.mkdir(exist_ok=True)

    sep = ";" if platform == "win32" else ":"
    add_data_args = [f"--add-data={ROOT / 'static'}{sep}static"]
    if (ROOT / "assets").exists():
        add_data_args.append(f"--add-data={ROOT / 'assets'}{sep}assets")

    platform_args = ["--windowed"] if platform == "win32" else []
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--name", NAME,
        *platform_args,
        *add_data_args,
        "--distpath", str(DIST),
        "--workpath", str(DIST / "build"),
        "--specpath", str(DIST), "--clean", "--noconfirm",
        str(ROOT / "launcher.py"),
    ]

    run(cmd)

    bundle = DIST / f"{NAME}-{platform}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir()

    exe_dir = DIST / NAME
    for item in exe_dir.iterdir():
        dest = bundle / item.name
        if item.is_file() and item.name == NAME and platform != "win32":
            dest = bundle / f"{NAME}.bin"
        shutil.move(str(item), str(dest))
    shutil.rmtree(exe_dir, ignore_errors=True)

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
        shutil.copytree(venv_src, venv_dest, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        _strip_venv(venv_dest)

    # Launcher
    if platform == "win32":
        (bundle / "SplitTracks.vbs").write_text('CreateObject("Wscript.Shell").Run "SplitTracks.exe", 0, False\r\n')
    else:
        (bundle / "SplitTracks").write_text(f"#!/bin/bash\ncd \"$(dirname \"$0\")\"\n./{NAME}.bin\n")
        (bundle / "SplitTracks").chmod(0o755)

    # Fix venv portability: set PYTHONHOME to bundled stdlib
    _make_venv_portable(bundle)

    print(f"\nBundle ready: {bundle}")


def _make_venv_portable(bundle: Path) -> None:
    venv_python = bundle / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return
    stdlib_src = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    stdlib_dst = bundle / "_internal" / "python3.12" / "lib" / "python3.12"
    if not (stdlib_dst / "encodings").exists() and stdlib_src.exists():
        shutil.copytree(stdlib_src, stdlib_dst, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test", "tests",
                                                      "idlelib", "tkinter", "turtledemo",
                                                      "distutils", "ensurepip", "venv"))
    venv_python_orig = venv_python.parent / "python.orig"
    if not venv_python_orig.exists():
        shutil.move(str(venv_python), str(venv_python_orig))
    venv_python.write_text(
        '#!/bin/bash\n'
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        'BUNDLE="$(cd "$HERE/../.." && pwd)"\n'
        'export PYTHONHOME="$BUNDLE/_internal/python3.12"\n'
        'export PYTHONPATH="$BUNDLE/.venv/lib/python3.12/site-packages"\n'
        'exec "$HERE/python.orig" "$@"\n'
    )
    venv_python.chmod(0o755)
    print("  Made .venv portable")

if __name__ == "__main__":
    main()
