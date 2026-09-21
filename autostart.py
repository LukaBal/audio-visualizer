"""Optional 'start with Windows' support.

Writes one value under HKCU\\...\\Run -- the per-user startup list Windows itself
exposes in Task Manager > Startup. Nothing here runs unless you tick the tray
menu item, and unticking removes the value again.
"""

import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AudioVisualizer"


def launch_command():
    """The command Windows should run at login.

    --hidden so logging in lands you in the tray rather than throwing a
    visualizer window across the screen.
    """
    if getattr(sys, "frozen", False):  # packaged .exe
        return f'"{sys.executable}" --hidden'
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    # pythonw keeps a console window from flashing up at login.
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{script}" --hidden'


def is_enabled(key_path=RUN_KEY, name=VALUE_NAME):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return bool(value)
    except OSError:
        return False


def enable(key_path=RUN_KEY, name=VALUE_NAME, command=None):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command or launch_command())
    return True


def disable(key_path=RUN_KEY, name=VALUE_NAME):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass
    return False


def toggle(key_path=RUN_KEY, name=VALUE_NAME):
    """Flip it, returning the new state."""
    if is_enabled(key_path, name):
        return disable(key_path, name)
    return enable(key_path, name)


if __name__ == "__main__":
    print("command:", launch_command())
    print("enabled:", is_enabled())
