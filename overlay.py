"""Win32 window tricks that turn the SDL window into a desktop gadget.

SDL2 has no per-pixel-alpha window on Windows, so transparency here is a colour
key: pure black becomes see-through. That suits this app exactly, because every
mode already draws onto black and the trails fade back to black.

Everything is applied to the HWND behind pygame's window, and every style has to
be re-applied whenever the display surface is recreated -- set_mode() builds a
new window and the old styles go with it.

All calls are best-effort: a gadget that fails to go click-through is a nuisance,
a crash is not, so failures return False rather than raise.
"""

import ctypes
from ctypes import wintypes

GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000

HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
HWND_BOTTOM = 1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

LWA_COLORKEY = 0x0001
LWA_ALPHA = 0x0002

GA_PARENT = 1

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77

WM_SPAWN_WORKER = 0x052C
SMTO_NORMAL = 0x0000

_user32 = ctypes.windll.user32

_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetParent.restype = wintypes.HWND
_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
_user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND,
    wintypes.COLORREF,
    wintypes.BYTE,
    wintypes.DWORD,
]
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.MoveWindow.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.BOOL,
]

_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def hwnd():
    """The HWND behind pygame's current window, or None."""
    try:
        import pygame

        info = pygame.display.get_wm_info()
    except Exception:
        return None
    handle = info.get("window") if isinstance(info, dict) else None
    return wintypes.HWND(handle) if handle else None


def _ex_style(h, add=0, remove=0):
    try:
        style = _user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
        style = (style | add) & ~remove
        _user32.SetWindowLongPtrW(h, GWL_EXSTYLE, style)
        _user32.SetWindowPos(
            h, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        return True
    except Exception:
        return False


def set_transparent(h, opacity=1.0, colorkey=0x000000):
    """Make `colorkey` (default pure black) see-through, and dim the rest.

    LWA_COLORKEY and LWA_ALPHA combine: keyed pixels vanish completely, every
    other pixel is drawn at `opacity`.
    """
    if h is None:
        return False
    if not _ex_style(h, add=WS_EX_LAYERED):
        return False
    alpha = max(0, min(255, int(round(opacity * 255))))
    try:
        return bool(
            _user32.SetLayeredWindowAttributes(
                h, colorkey, alpha, LWA_COLORKEY | LWA_ALPHA
            )
        )
    except Exception:
        return False


def set_opaque(h):
    """Drop the layered style entirely, back to a normal window."""
    return _ex_style(h, remove=WS_EX_LAYERED | WS_EX_TRANSPARENT) if h else False


def set_click_through(h, enabled):
    """Let clicks fall through to whatever is underneath."""
    if h is None:
        return False
    flags = WS_EX_TRANSPARENT
    return _ex_style(h, add=flags) if enabled else _ex_style(h, remove=flags)


def set_topmost(h, enabled):
    if h is None:
        return False
    try:
        _user32.SetWindowPos(
            h,
            wintypes.HWND(HWND_TOPMOST if enabled else HWND_NOTOPMOST),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        return True
    except Exception:
        return False


def set_bottom(h):
    """Park the window at the bottom of the z-order: above the wallpaper and
    desktop icons, below every ordinary window."""
    if h is None:
        return False
    try:
        _user32.SetWindowPos(
            h, wintypes.HWND(HWND_BOTTOM), 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        return True
    except Exception:
        return False


def set_no_activate(h, enabled):
    """Stop the window from ever taking focus -- clicking it must not pull it
    in front of what you are working in."""
    if h is None:
        return False
    return (
        _ex_style(h, add=WS_EX_NOACTIVATE)
        if enabled
        else _ex_style(h, remove=WS_EX_NOACTIVATE)
    )


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def cursor_pos():
    """Cursor position in screen coordinates.

    Dragging has to work from absolute positions: pygame reports motion
    RELATIVE to the window, so moving the window changes the next reading and
    the drag feeds back on itself.
    """
    try:
        point = _POINT()
        if _user32.GetCursorPos(ctypes.byref(point)):
            return (point.x, point.y)
    except Exception:
        pass
    return None


def left_button_down():
    """Asked directly, because a no-activate window can miss the button-up
    event if the release happens outside it."""
    try:
        return bool(_user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:
        return False


def foreground_window():
    try:
        return _user32.GetForegroundWindow()
    except Exception:
        return None


def restore_foreground(h):
    """Hand focus back to whatever had it. Allowed here because our process is
    the foreground one at this point -- Windows only lets the current
    foreground process give focus away."""
    if not h:
        return False
    try:
        return bool(_user32.SetForegroundWindow(wintypes.HWND(h)))
    except Exception:
        return False


def set_tool_window(h, enabled):
    """Tool windows stay out of the taskbar and the alt-tab list."""
    if h is None:
        return False
    if enabled:
        return _ex_style(h, add=WS_EX_TOOLWINDOW, remove=WS_EX_APPWINDOW)
    return _ex_style(h, add=WS_EX_APPWINDOW, remove=WS_EX_TOOLWINDOW)


# --------------------------------------------------------------- wallpaper

def find_worker_w():
    """The desktop's WorkerW window -- the layer that lives behind the icons.

    Poking Progman with the undocumented 0x052C message makes Explorer split
    the desktop into a WorkerW behind the icon view; the one we want is the
    WorkerW that is a sibling of the window owning SHELLDLL_DefView.
    """
    try:
        progman = _user32.FindWindowW("Progman", None)
        if not progman:
            return None
        result = ctypes.c_ulonglong()
        _user32.SendMessageTimeoutW(
            progman, WM_SPAWN_WORKER, 0, 0, SMTO_NORMAL, 1000, ctypes.byref(result)
        )

        found = []

        def _callback(window, _lparam):
            if _user32.FindWindowExW(window, None, "SHELLDLL_DefView", None):
                sibling = _user32.FindWindowExW(None, window, "WorkerW", None)
                if sibling:
                    found.append(sibling)
            return True

        _user32.EnumWindows(_ENUMPROC(_callback), 0)
        return found[0] if found else None
    except Exception:
        return None


def virtual_origin():
    """Top-left of the virtual desktop; WorkerW coordinates are relative to it."""
    try:
        return (
            _user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            _user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        )
    except Exception:
        return (0, 0)


def attach_to_desktop(h, rect=None):
    """Parent the window to WorkerW so it renders behind the desktop icons.

    `rect` is a screen-space (x, y, w, h); it gets translated into WorkerW's
    coordinate space, which starts at the virtual desktop origin.
    """
    if h is None:
        return False
    worker = find_worker_w()
    if not worker:
        return False
    try:
        # SetParent returns the PREVIOUS parent, which is NULL for a top-level
        # window -- success and failure look identical, so check GetAncestor.
        _user32.SetParent(h, worker)
        if rect:
            ox, oy = virtual_origin()
            x, y, w, hgt = rect
            _user32.MoveWindow(h, x - ox, y - oy, w, hgt, True)
        # A freshly re-parented window lands at the BOTTOM of its new siblings,
        # underneath whichever child is painting the wallpaper. Raise it.
        _user32.SetWindowPos(
            h, wintypes.HWND(HWND_TOP), 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        return int(_user32.GetAncestor(h, GA_PARENT) or 0) == int(worker)
    except Exception:
        return False


RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100


def refresh_desktop():
    """Force Explorer to repaint the wallpaper.

    Explorer does not redraw the desktop when a window parented into WorkerW
    goes away, so the last rendered frame stays burnt onto the background until
    something else happens to invalidate it.
    """
    flags = RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW
    done = False
    try:
        for window in (find_worker_w(), _user32.FindWindowW("Progman", None)):
            if window:
                _user32.RedrawWindow(wintypes.HWND(window), None, None, flags)
                done = True
    except Exception:
        return False
    return done


def detach_from_desktop(h):
    """Back to a normal top-level window, leaving the desktop clean."""
    if h is None:
        return False
    try:
        _user32.SetParent(h, None)
    except Exception:
        return False
    refresh_desktop()
    return True


if __name__ == "__main__":
    worker = find_worker_w()
    print("WorkerW:", hex(worker) if worker else "not found")
    print("virtual origin:", virtual_origin())
