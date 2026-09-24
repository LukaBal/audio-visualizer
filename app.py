"""Tray-resident audio visualizer.

Lives in the notification area: toggle the window from the tray menu or with
Ctrl+Alt+V, any time. Closing the window (X or ESC) hides it rather than
quitting; Quit in the tray menu is what actually exits.

The pygame loop must own the main thread, so the tray icon and the hotkey both
run on their own threads and hand work back through a queue.
"""

import argparse
import os
import queue
import sys
import threading
import time

import pystray

import appicon
import autostart
import settings
from displays import monitor_rects
from engine import LAYERS, MODE_NAMES, PALETTE_NAMES, Visualizer
from hotkey import GlobalHotkey

APP_NAME = "Audio Visualizer"
HOTKEY_LABEL = "Ctrl+Alt+V"
IDLE_SLEEP = 0.1


def redirect_output_if_frozen():
    """A windowed .exe has nowhere to print, so keep a log to diagnose from."""
    if not getattr(sys, "frozen", False):
        return None
    folder = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AudioVisualizer"
    )
    try:
        os.makedirs(folder, exist_ok=True)
        stream = open(os.path.join(folder, "log.txt"), "a", buffering=1, encoding="utf-8")
    except OSError:
        return None
    sys.stdout = sys.stderr = stream
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---")
    return stream


class TrayApp:
    def __init__(self, start_hidden=False, **viz_kwargs):
        self.commands = queue.Queue()
        self.viz = Visualizer(
            escape_label=f"ESC           hide  ({HOTKEY_LABEL})", **viz_kwargs
        )
        self.viz.on_close = lambda: self.post("hide")
        self.visible = not start_hidden
        self.alive = True
        self.icon = None
        self.hotkey = None
        self.monitors = monitor_rects()
        self._last_saved_pos = self.viz.gadget_pos

    def post(self, name, arg=None):
        """Thread-safe: tray and hotkey threads must not touch pygame directly."""
        self.commands.put((name, arg))

    # -------------------------------------------------------------- tray menu

    def _action(self, name, arg=None):
        return lambda icon, item: self.post(name, arg)

    def _menu(self):
        item = pystray.MenuItem
        modes = pystray.Menu(
            *[
                item(
                    name.capitalize(),
                    self._action("mode", i),
                    checked=lambda it, i=i: self.viz.mode_idx == i,
                    radio=True,
                )
                for i, name in enumerate(MODE_NAMES)
            ]
        )
        palettes = pystray.Menu(
            *[
                item(
                    name.capitalize(),
                    self._action("palette", i),
                    checked=lambda it, i=i: self.viz.pal_idx == i,
                    radio=True,
                )
                for i, name in enumerate(PALETTE_NAMES)
            ]
        )

        items = [
            item(
                "Show visualizer",
                self._action("toggle"),
                checked=lambda it: self.visible,
                default=True,  # left-clicking the tray icon toggles
            ),
            pystray.Menu.SEPARATOR,
            item("Mode", modes),
            item("Palette", palettes),
        ]

        if len(self.monitors) > 1:
            screens = pystray.Menu(
                *[
                    item(
                        f"Monitor {i + 1}  ({w}x{h})",
                        self._action("display", i),
                        checked=lambda it, i=i: self.viz.display == i,
                        radio=True,
                    )
                    for i, (_x, _y, w, h) in enumerate(self.monitors)
                ]
            )
            items.append(item("Monitor", screens))

        opacities = pystray.Menu(
            *[
                item(
                    f"{int(level * 100)}%",
                    self._action("opacity", level),
                    checked=lambda it, level=level: abs(self.viz.opacity - level) < 0.01,
                    radio=True,
                )
                for level in (1.0, 0.85, 0.7, 0.55, 0.4)
            ]
        )

        layers = pystray.Menu(
            *[
                item(
                    label,
                    self._action("layer", key),
                    checked=lambda it, key=key: self.viz.layer == key,
                    radio=True,
                )
                for key, label in (
                    ("desktop", "Stuck to the desktop"),
                    ("normal", "Normal window"),
                    ("top", "Always on top"),
                )
            ]
        )

        items += [
            pystray.Menu.SEPARATOR,
            item(
                "Desktop gadget",
                self._action("gadget"),
                checked=lambda it: self.viz.gadget,
            ),
            item(
                "Behind desktop icons (experimental)",
                self._action("wallpaper"),
                checked=lambda it: self.viz.wallpaper,
            ),
            item("Re-attach to desktop", self._action("reattach")),
            item("Opacity", opacities),
            item(
                "Click-through",
                self._action("clickthrough"),
                checked=lambda it: self.viz.click_through,
            ),
            item("Window layer", layers),
            item(
                "Lock position",
                self._action("lock"),
                checked=lambda it: self.viz.locked,
            ),
            item(
                "Resize by dragging edges",
                self._action("resizable"),
                checked=lambda it: self.viz.resizable,
            ),
            pystray.Menu.SEPARATOR,
            item("Fullscreen", self._action("fullscreen"), checked=lambda it: self.viz.fullscreen),
            item("Overlay", self._action("hud"), checked=lambda it: self.viz.show_hud),
            item("Save screenshot", self._action("screenshot")),
            pystray.Menu.SEPARATOR,
            item(
                "Start with Windows",
                self._action("autostart"),
                checked=lambda it: autostart.is_enabled(),
            ),
            item("Quit", self._action("quit")),
        ]
        return pystray.Menu(*items)

    # ---------------------------------------------------------------- command

    def _handle(self, name, arg):
        viz = self.viz
        if name == "toggle":
            self.visible = not self.visible
        elif name == "show":
            self.visible = True
        elif name == "hide":
            self.visible = False
        elif name == "mode":
            viz.set_mode_index(arg)
        elif name == "palette":
            viz.set_palette_index(arg)
        elif name == "display":
            viz.set_display(arg)
        elif name == "fullscreen":
            viz.set_fullscreen(not viz.fullscreen)
        elif name == "hud":
            viz.show_hud = not viz.show_hud
        elif name == "screenshot":
            if viz.is_open:
                viz.screenshot()
        elif name == "gadget":
            viz.set_gadget(not viz.gadget)
        elif name == "wallpaper":
            viz.set_wallpaper(not viz.wallpaper)
            if viz.wallpaper and not viz._attached:
                print("desktop layer refused the window; it is floating instead")
        elif name == "reattach":
            viz.reattach()
        elif name == "opacity":
            viz.set_opacity(arg)
        elif name == "clickthrough":
            viz.set_click_through(not viz.click_through)
        elif name == "layer":
            viz.set_layer(arg)
        elif name == "lock":
            viz.set_locked(not viz.locked)
        elif name == "resizable":
            viz.set_resizable(not viz.resizable)
        elif name == "autostart":
            autostart.toggle()
        elif name == "quit":
            self.alive = False

        if name != "quit":
            self.save_settings()
        if self.icon is not None:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _save_moved_position(self):
        """Persist a drag as soon as it ends.

        Settings are otherwise written on a menu action or a clean quit, so
        being force-killed used to lose wherever you had just dragged it.
        """
        if self.viz._dragging:
            return
        pos = self.viz.gadget_pos
        if pos and tuple(pos) != tuple(self._last_saved_pos or ()):
            self._last_saved_pos = pos
            self.save_settings()

    def save_settings(self):
        viz = self.viz
        settings.save(
            {
                "mode": MODE_NAMES[viz.mode_idx],
                "palette": PALETTE_NAMES[viz.pal_idx],
                "gadget": viz.gadget,
                "wallpaper": viz.wallpaper,
                "gadget_size": list(viz.gadget_size),
                "gadget_pos": list(viz.gadget_pos) if viz.gadget_pos else None,
                "opacity": round(viz.opacity, 3),
                "click_through": viz.click_through,
                "layer": viz.layer,
                "locked": viz.locked,
                "resizable": viz.resizable,
                "display": viz.display,
                "visible": self.visible,
            }
        )

    def _drain(self):
        while True:
            try:
                name, arg = self.commands.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(name, arg)
            except Exception as exc:  # a bad menu click must not kill the app
                print(f"command {name!r} failed: {exc}")

    # ------------------------------------------------------------------- run

    def run(self):
        self.icon = pystray.Icon(
            "audio-visualizer", appicon.make_image(64), APP_NAME, self._menu()
        )
        threading.Thread(target=self._run_icon, name="tray", daemon=True).start()

        self.hotkey = GlobalHotkey(lambda: self.post("toggle"), label=HOTKEY_LABEL)
        self.hotkey.start()
        time.sleep(0.3)  # let registration settle so the tooltip can report it
        if self.hotkey.error:
            print("hotkey:", self.hotkey.error)
            try:
                self.icon.title = f"{APP_NAME} - {self.hotkey.error}"
            except Exception:
                pass

        try:
            self._loop()
        finally:
            self.shutdown()

    def _run_icon(self):
        try:
            self.icon.run()
        except Exception as exc:  # no tray? keep going, the hotkey still works
            print("tray icon failed:", exc)

    def _loop(self):
        while self.alive:
            self._drain()
            if self.visible:
                if not self.viz.is_open:
                    self.viz.open()
                self.viz.frame()
                self._save_moved_position()
                if not self.viz.running:  # engine asked to exit outright
                    self.alive = False
            else:
                if self.viz.is_open:
                    self.viz.close()
                time.sleep(IDLE_SLEEP)

    def shutdown(self):
        self.save_settings()  # dragging moves the gadget without issuing a command
        self.viz.close()
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        import pygame

        pygame.quit()


def parse_size(value, fallback):
    """Accept both "460x260" from the command line and [460, 260] from the
    saved settings -- JSON gives back a list, and treating it as a string
    silently fell back to the default, losing any resize."""
    if isinstance(value, (list, tuple)):
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError, IndexError):
            return fallback
    try:
        w, h = (int(v) for v in str(value).lower().split("x"))
        return (w, h)
    except (ValueError, AttributeError):
        return fallback


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hidden", action="store_true", help="start in the tray, no window")
    p.add_argument("--reset", action="store_true", help="ignore saved settings")
    p.add_argument("--device", help="partial name of the output device to capture")
    p.add_argument("--mode", choices=MODE_NAMES)
    p.add_argument("--palette", choices=PALETTE_NAMES)
    p.add_argument("--gadget", action="store_const", const=True, help="transparent desktop gadget")
    p.add_argument(
        "--wallpaper", action="store_const", const=True, help="behind the desktop icons"
    )
    p.add_argument("--click-through", dest="click_through", action="store_const", const=True)
    p.add_argument(
        "--locked", action="store_const", const=True, help="pin the gadget in place"
    )
    p.add_argument(
        "--no-drag-resize",
        dest="resizable",
        action="store_const",
        const=False,
        help="do not resize when dragging the edges",
    )
    p.add_argument(
        "--layer",
        choices=LAYERS,
        help="desktop = behind every window (default), normal, or top",
    )
    p.add_argument(
        "--no-topmost", dest="layer", action="store_const", const="normal",
        help=argparse.SUPPRESS,
    )
    p.add_argument("--opacity", type=float, help="0.1 to 1.0")
    p.add_argument("--gadget-size", dest="gadget_size", help="gadget size, e.g. 520x300")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--display", type=int, help="monitor index")
    p.add_argument("--size", default="1280x720", help="plain-window size")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--bands", type=int, default=72)
    return p.parse_args(argv)


def main(argv=None):
    redirect_output_if_frozen()
    args = parse_args(argv)
    # Saved settings are defaults; anything passed on the command line wins.
    saved = {} if args.reset else settings.load()

    def pick(name, default):
        value = getattr(args, name, None)
        return value if value is not None else saved.get(name, default)

    gadget_pos = saved.get("gadget_pos")
    TrayApp(
        start_hidden=args.hidden or not saved.get("visible", True),
        size=parse_size(args.size, (1280, 720)),
        mode=pick("mode", "rings"),
        palette=pick("palette", "ember"),
        bands=args.bands,
        fps=args.fps,
        fullscreen=args.fullscreen,
        display=pick("display", 0),
        device=args.device,
        gadget=pick("gadget", True),  # the tray app is a gadget by default
        wallpaper=pick("wallpaper", False),
        gadget_size=parse_size(pick("gadget_size", None) or "460x260", (460, 260)),
        gadget_pos=tuple(gadget_pos) if gadget_pos else None,
        opacity=pick("opacity", 0.9),
        click_through=pick("click_through", False),
        layer=pick("layer", "desktop"),  # stay out of the way unless told otherwise
        locked=pick("locked", False),
        resizable=pick("resizable", True),
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
