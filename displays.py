"""Monitor geometry via the Win32 API.

SDL only reports desktop *sizes*, not where each monitor sits on the virtual
desktop, and its fullscreen `display=` hint is unreliable here -- asking for
monitor 1 still opens on monitor 0. Knowing the origins lets us place a
borderless window on the monitor we actually meant.
"""

import ctypes
from ctypes import wintypes

MONITORINFOF_PRIMARY = 0x1


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(_RECT), wintypes.LPARAM
)


def monitor_rects():
    """[(x, y, w, h), ...] for every monitor, primary first.

    Returns [] on anything unexpected; callers fall back to SDL's own sizes.
    """
    found = []

    def _callback(hmonitor, hdc, lprect, lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            found.append(
                (
                    bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    (r.left, r.top, r.right - r.left, r.bottom - r.top),
                )
            )
        return True

    try:
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, _MONITORENUMPROC(_callback), 0
        )
    except Exception:
        return []

    found.sort(key=lambda item: not item[0])  # primary first
    return [rect for _, rect in found]


if __name__ == "__main__":
    for i, rect in enumerate(monitor_rects()):
        print(f"monitor {i}: x={rect[0]} y={rect[1]} {rect[2]}x{rect[3]}")
