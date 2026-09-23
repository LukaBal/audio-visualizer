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


def monitor_rects(work_area=False):
    """[(x, y, w, h), ...] for every monitor, primary first.

    With work_area=True the taskbar (and any other appbar) is excluded, which
    is what you want when placing something that should stay visible.

    Returns [] on anything unexpected; callers fall back to SDL's own sizes.
    """
    found = []

    def _callback(hmonitor, hdc, lprect, lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcWork if work_area else info.rcMonitor
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


def monitor_containing(point, work_area=True):
    """The monitor a screen point falls on, or None if it falls in dead space.

    Monitors need not tile the virtual desktop -- they can sit at different
    offsets with gaps between them -- so "inside the bounding box" is not the
    same as "on a screen".
    """
    if point is None:
        return None
    px, py = point
    for x, y, w, h in monitor_rects(work_area):
        if x <= px < x + w and y <= py < y + h:
            return (x, y, w, h)
    return None


def monitor_overlapping(rect, work_area=True):
    """The monitor a window rect overlaps most, or the nearest one to it."""
    x, y, w, h = rect
    monitors = monitor_rects(work_area)
    if not monitors:
        return None
    best, best_area = None, 0
    for mx, my, mw, mh in monitors:
        overlap = max(0, min(x + w, mx + mw) - max(x, mx)) * max(
            0, min(y + h, my + mh) - max(y, my)
        )
        if overlap > best_area:
            best, best_area = (mx, my, mw, mh), overlap
    if best is not None:
        return best
    # No overlap at all (monitor unplugged, say): fall back to the closest.
    cx, cy = x + w / 2, y + h / 2
    return min(
        monitors,
        key=lambda m: (cx - (m[0] + m[2] / 2)) ** 2 + (cy - (m[1] + m[3] / 2)) ** 2,
    )


def clamp_to_monitor(pos, size, cursor=None, work_area=True, anchor=None):
    """Keep a window fully on one screen.

    The target is the monitor under the cursor when there is one, so dragging
    onto a second monitor works; otherwise it is whichever monitor the window
    already overlaps most. Clamping happens inside that single monitor rather
    than the virtual bounding box, which would happily allow a position in the
    gap between two monitors.
    """
    w, h = size
    # `anchor` is where the window already is. Using it for the fallback keeps
    # a drag on its current monitor when the cursor is somewhere unusable,
    # rather than teleporting to whichever monitor is nearest the new position.
    base = anchor if anchor is not None else pos
    target = monitor_containing(cursor, work_area) or monitor_overlapping(
        (base[0], base[1], w, h), work_area
    )
    if target is None:
        return tuple(pos)
    mx, my, mw, mh = target
    # max() second guards a window larger than the monitor: pin to top-left
    # instead of inverting the range.
    x = max(mx, min(int(pos[0]), mx + mw - w))
    y = max(my, min(int(pos[1]), my + mh - h))
    return (x, y)


if __name__ == "__main__":
    for i, rect in enumerate(monitor_rects()):
        work = monitor_rects(work_area=True)[i]
        print(f"monitor {i}: full x={rect[0]} y={rect[1]} {rect[2]}x{rect[3]}"
              f" | work x={work[0]} y={work[1]} {work[2]}x{work[3]}")
