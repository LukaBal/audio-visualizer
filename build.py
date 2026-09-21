"""Build AudioVisualizer.exe with PyInstaller.

    python build.py            one file, ~slower first start
    python build.py --onedir   a folder, starts instantly

The result lands in dist/. Nothing outside this folder is touched.
"""

import argparse
import os
import subprocess
import sys
import time

import appicon

HERE = os.path.dirname(os.path.abspath(__file__))


def check_not_running():
    """A running copy holds dist\\AudioVisualizer.exe open, and PyInstaller then
    fails with a bare 'Access is denied' traceback. Say so in English instead."""
    target = os.path.join(HERE, "dist", "AudioVisualizer.exe")
    if not os.path.exists(target):
        return
    try:
        # Windows happily RENAMES a running exe but refuses write access to it,
        # so opening for write is the test that actually detects this.
        with open(target, "r+b"):
            pass
    except OSError:
        raise SystemExit(
            "AudioVisualizer.exe is running, so it cannot be replaced.\n"
            "Quit it from the tray icon (right-click > Quit) and build again."
        )


def build(onefile=True, console=False):
    check_not_running()
    icon_path = os.path.join(HERE, "assets", "icon.ico")
    os.makedirs(os.path.dirname(icon_path), exist_ok=True)
    appicon.save_ico(icon_path)
    print("icon:", icon_path)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "AudioVisualizer",
        "--icon",
        icon_path,
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
        # soundcard binds Windows audio through cffi at runtime, so the
        # dependency scanner cannot see what it needs -- collect it wholesale.
        "--collect-all",
        "soundcard",
        "--collect-all",
        "cffi",
        "--collect-all",
        "pycparser",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "matplotlib",
        os.path.join(HERE, "app.py"),
    ]
    print(" ".join(cmd))
    started = time.perf_counter()
    subprocess.check_call(cmd, cwd=HERE)

    exe = os.path.join(HERE, "dist", "AudioVisualizer.exe" if onefile else "AudioVisualizer")
    print(f"\nbuilt in {time.perf_counter() - started:.0f}s -> {exe}")
    if onefile and os.path.exists(exe):
        print(f"size: {os.path.getsize(exe) / 1e6:.1f} MB")
    return exe


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--onedir", action="store_true", help="folder build instead of one .exe")
    p.add_argument("--console", action="store_true", help="keep a console window for debugging")
    a = p.parse_args()
    build(onefile=not a.onedir, console=a.console)
