"""Remembered gadget settings -- position, size, look.

A gadget you have to re-place every launch is a gadget you stop using. Stored
next to the log in %LOCALAPPDATA%, never in the app folder, which may be
read-only when running from a packaged .exe.
"""

import json
import os

FOLDER = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AudioVisualizer"
)
PATH = os.path.join(FOLDER, "config.json")

KEYS = (
    "mode",
    "palette",
    "gadget",
    "wallpaper",
    "gadget_size",
    "gadget_pos",
    "opacity",
    "click_through",
    "topmost",
    "layer",
    "locked",
    "display",
    "visible",
)


def load():
    """Saved settings, or {} if there are none / the file is unusable."""
    try:
        with open(PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {k: v for k, v in data.items() if k in KEYS} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data):
    try:
        os.makedirs(FOLDER, exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as handle:
            json.dump({k: v for k, v in data.items() if k in KEYS}, handle, indent=2)
        return True
    except (OSError, TypeError, ValueError) as exc:
        print("could not save settings:", exc)
        return False


if __name__ == "__main__":
    print(PATH)
    print(load())
