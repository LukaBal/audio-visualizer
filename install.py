"""Install the built .exe so it can be launched like any other app.

    python install.py            install + Start Menu + Desktop shortcuts
    python install.py --no-desktop
    python install.py --uninstall

Copies the exe out of dist/ into %LOCALAPPDATA%\\Programs\\AudioVisualizer and
points the shortcuts there. Running the installed copy rather than the one in
dist/ also means `python build.py` keeps working while the app is open --
Windows locks a running .exe, and rebuilding over it fails.

Nothing here needs admin rights: it is all per-user.
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "dist", "AudioVisualizer.exe")

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "AudioVisualizer"
)
TARGET = os.path.join(APP_DIR, "AudioVisualizer.exe")

START_MENU = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Microsoft", "Windows", "Start Menu", "Programs",
)
SHORTCUT_NAME = "Audio Visualizer.lnk"


def desktop_dir():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def make_shortcut(path, target, description=""):
    """Create a .lnk through the shell's own COM object."""
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
        "$s.TargetPath = %s;"
        "$s.WorkingDirectory = %s;"
        "$s.IconLocation = %s;"
        "$s.Description = %s;"
        "$s.Save()"
    ) % (
        _ps_quote(path),
        _ps_quote(target),
        _ps_quote(os.path.dirname(target)),
        _ps_quote(target),
        _ps_quote(description),
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  could not create {path}: {result.stderr.strip()[:200]}")
        return False
    return os.path.exists(path)


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def install(desktop=True):
    if not os.path.exists(SOURCE):
        raise SystemExit(
            f"{SOURCE} does not exist yet.\nBuild it first:  python build.py"
        )

    os.makedirs(APP_DIR, exist_ok=True)
    try:
        shutil.copy2(SOURCE, TARGET)
    except PermissionError:
        raise SystemExit(
            "The installed copy is running, so it cannot be replaced.\n"
            "Quit it from the tray icon (right-click > Quit) and try again."
        )
    print("installed:", TARGET)

    targets = [(os.path.join(START_MENU, SHORTCUT_NAME), "Start Menu")]
    if desktop and os.path.isdir(desktop_dir()):
        targets.append((os.path.join(desktop_dir(), SHORTCUT_NAME), "Desktop"))

    for path, label in targets:
        if make_shortcut(path, TARGET, "Audio visualizer that reacts to system sound"):
            print(f"shortcut ({label}):", path)

    print("\nLaunch it from the Start Menu, the Desktop icon, or by searching")
    print("'Audio Visualizer'. To start it with Windows, use the tray menu.")
    return TARGET


def uninstall():
    removed = []
    for path in (
        os.path.join(START_MENU, SHORTCUT_NAME),
        os.path.join(desktop_dir(), SHORTCUT_NAME),
    ):
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)
    if os.path.isdir(APP_DIR):
        try:
            shutil.rmtree(APP_DIR)
            removed.append(APP_DIR)
        except PermissionError:
            print("the app is running; quit it from the tray and try again")
    for path in removed:
        print("removed:", path)
    if not removed:
        print("nothing to remove")
    print("\nSettings and logs in %LOCALAPPDATA%\\AudioVisualizer were left alone.")
    print("Autostart, if you enabled it, is unticked from the tray menu.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-desktop", action="store_true", help="skip the Desktop shortcut")
    p.add_argument("--uninstall", action="store_true", help="remove app and shortcuts")
    args = p.parse_args()
    if args.uninstall:
        uninstall()
    else:
        install(desktop=not args.no_desktop)
