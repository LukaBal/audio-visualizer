"""Window, input and render loop, shared by the CLI (viz.py) and the tray app.

The visualizer owns its window and its audio capture, and can open and close
both at runtime -- that is what lets the tray app switch it off completely
(no window, no taskbar entry, no audio device held) without exiting.
"""

import os
import time

os.environ.setdefault("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1")

import pygame

from analysis import FFT_SIZE, Analyzer
from capture import SAMPLERATE, AudioCapture
from displays import clamp_to_monitor, monitor_rects
from modes import MODES, PALETTES
import overlay

BG_FLOOR = 12  # see render(): keeps colour-key transparency actually transparent

LAYERS = ("top", "normal", "desktop")
BOTTOM_REASSERT_FRAMES = 120  # ~2s; cheap insurance against drifting upward

MODE_NAMES = [m.name for m in MODES]
PALETTE_NAMES = [p[0] for p in PALETTES]

HELP_LINES = [
    "1/2/3 or TAB  mode",
    "SPACE         palette",
    "A             auto-gain",
    "+ / -         gain",
    "F / F11       fullscreen",
    "H             hide this",
    "S             screenshot",
]


def shots_dir():
    """Screenshots go to Pictures; the app folder may not be writable once frozen."""
    pictures = os.path.join(os.path.expanduser("~"), "Pictures")
    return pictures if os.path.isdir(pictures) else os.path.expanduser("~")


class Visualizer:
    def __init__(
        self,
        size=(1280, 720),
        mode="rings",
        palette="ember",
        bands=72,
        fps=60,
        fullscreen=False,
        display=0,
        device=None,
        show_hud=True,
        caption="Audio Visualizer",
        escape_label="ESC / Q       quit",
        gadget=False,
        wallpaper=False,
        gadget_size=(460, 260),
        gadget_pos=None,
        opacity=0.9,
        click_through=False,
        topmost=None,
        layer="desktop",
        locked=False,
    ):
        self.size = size
        self.fps = fps
        self.device = device
        self.display = display
        self.fullscreen = fullscreen
        # A gadget with a keyboard-help overlay on it would be silly.
        self.show_hud = show_hud and not (gadget or wallpaper)
        self.caption = caption
        self.escape_label = escape_label

        self.gadget = gadget
        self.wallpaper = wallpaper
        self.gadget_size = gadget_size
        self.gadget_pos = gadget_pos
        self.opacity = opacity
        self.click_through = click_through
        # `topmost` is the old two-state setting, kept so saved configs and
        # scripts still work; `layer` supersedes it.
        if topmost is not None:
            layer = "top" if topmost else "normal"
        self.layer = layer if layer in LAYERS else "desktop"
        self.locked = bool(locked)
        self._attached = False
        self._dragging = False
        self._drag_cursor = None
        self._drag_window = None
        self._bottom_ticks = 0

        self.mode_idx = MODE_NAMES.index(mode) if mode in MODE_NAMES else 0
        self.pal_idx = PALETTE_NAMES.index(palette) if palette in PALETTE_NAMES else 0
        self.mode = MODES[self.mode_idx]()
        self.analyzer = Analyzer(SAMPLERATE, fft_size=FFT_SIZE, bands=bands)

        self.capture = None
        self.screen = None
        self.trail = None
        self.font = None
        self.clock = None
        self.running = True
        self.frames = 0
        self.last_shot = None
        # Called when the user hits ESC or the window's X. The tray app swaps in
        # its own handler so closing hides instead of quitting.
        self.on_close = None
        self._start = time.perf_counter()

    # ------------------------------------------------------------------ audio

    def start_audio(self):
        if self.capture is None:
            self.capture = AudioCapture(device=self.device, samplerate=SAMPLERATE).start()

    def stop_audio(self):
        if self.capture is not None:
            self.capture.stop()
            self.capture = None

    # ----------------------------------------------------------------- window

    @property
    def is_open(self):
        return self.screen is not None

    def open(self):
        if self.is_open:
            return
        if not pygame.get_init():
            pygame.init()
        if not pygame.display.get_init():
            pygame.display.init()
        if not pygame.font.get_init():
            pygame.font.init()
        pygame.display.set_caption(self.caption)
        self.font = pygame.font.SysFont("Consolas,Menlo,monospace", 14)
        self.clock = pygame.time.Clock()
        self._apply_window()
        self.start_audio()

    def close(self):
        self.stop_audio()
        if self.screen is not None:
            was_attached = self._attached
            if was_attached:  # leave Explorer's desktop layer as we found it
                overlay.detach_from_desktop(overlay.hwnd())
                self._attached = False
            self.screen = None
            self.trail = None
            pygame.display.quit()
            if was_attached:
                # Only worth anything once our window is actually gone,
                # otherwise we just repaint underneath ourselves.
                overlay.refresh_desktop()

    def _display_index(self):
        try:
            count = pygame.display.get_num_displays()
        except pygame.error:
            return 0
        return max(0, min(self.display, count - 1))

    def _apply_window(self, move=True):
        """(Re)create the display surface.

        Fullscreen is borderless-at-monitor-bounds rather than an SDL exclusive
        mode: SDL refuses a zero-sized SCALED mode outright, and its fullscreen
        `display=` hint lands on the primary monitor regardless of what we ask
        for. Positioning the window ourselves is the only way to honour
        --display. Any failure drops back to a window instead of raising --
        losing fullscreen is survivable, crashing mid-song is not.
        """
        idx = self._display_index()
        # Creating an SDL window activates it, which would yank focus out of
        # whatever you are typing in every time the gadget appears. The SDL hint
        # prevents it; remembering the foreground window undoes it if the hint
        # is not honoured.
        unobtrusive = self.wallpaper or (self.gadget and self.layer == "desktop")
        previous_focus = overlay.foreground_window() if unobtrusive else None
        if unobtrusive:
            os.environ["SDL_WINDOW_NO_ACTIVATION_WHEN_SHOWN"] = "1"
        else:
            os.environ.pop("SDL_WINDOW_NO_ACTIVATION_WHEN_SHOWN", None)

        try:
            if self.wallpaper:
                self._open_wallpaper(idx)
            elif self.gadget:
                self._open_gadget(idx)
            elif self.fullscreen:
                self._open_fullscreen(idx)
            else:
                self._open_windowed(move, idx)
        except pygame.error as exc:
            print(f"display mode failed: {exc}")
            self.fullscreen = self.gadget = self.wallpaper = False
            os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            self.screen = pygame.display.set_mode(self.size, pygame.RESIZABLE)

        self.trail = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.mouse.set_visible(not self.fullscreen)
        self._apply_styles()
        if previous_focus and overlay.foreground_window() != previous_focus:
            overlay.restore_foreground(previous_focus)

    def _open_fullscreen(self, idx):
        rects = monitor_rects()
        if idx < len(rects):
            x, y, w, h = rects[idx]
            # SDL reads this on window creation; set_window_position fixes up
            # the case where the window already existed.
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
            self.screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
            try:
                pygame.display.set_window_position((x, y))
            except (AttributeError, TypeError, pygame.error):
                pass
        else:  # no Win32 geometry: fall back to SDL's own fullscreen
            sizes = pygame.display.get_desktop_sizes()
            size = sizes[idx] if idx < len(sizes) else self.size
            self.screen = pygame.display.set_mode(size, pygame.FULLSCREEN)

    def _open_windowed(self, move, idx):
        os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
        if move:
            self.screen = pygame.display.set_mode(self.size, pygame.RESIZABLE, display=idx)
        else:
            self.screen = pygame.display.set_mode(self.size, pygame.RESIZABLE)

    def _gadget_origin(self, idx):
        """Remembered spot, else tucked into the monitor's bottom-right corner.

        A remembered spot is re-clamped: the monitor it was saved on may have
        been unplugged or rearranged since, which would otherwise strand the
        gadget somewhere invisible.
        """
        if self.gadget_pos is not None:
            return clamp_to_monitor(tuple(self.gadget_pos), self.gadget_size)
        rects = monitor_rects()
        w, h = self.gadget_size
        if idx < len(rects):
            mx, my, mw, mh = rects[idx]
            margin = 40
            return (mx + mw - w - margin, my + mh - h - margin * 2)
        return (80, 80)

    def _open_gadget(self, idx):
        x, y = self._gadget_origin(idx)
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
        self.screen = pygame.display.set_mode(self.gadget_size, pygame.NOFRAME)
        try:
            pygame.display.set_window_position((x, y))
        except (AttributeError, TypeError, pygame.error):
            pass
        self.gadget_pos = (x, y)

    def _open_wallpaper(self, idx):
        rects = monitor_rects()
        rect = rects[idx] if idx < len(rects) else (0, 0, *self.size)
        x, y, w, h = rect
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
        self.screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
        self._attached = overlay.attach_to_desktop(overlay.hwnd(), rect)
        if not self._attached:
            # Without WorkerW this would be a huge window sitting on top of
            # everything, which is the opposite of what was asked for.
            print("could not reach the desktop layer; falling back to a gadget")
            self.wallpaper = False
            self.gadget = True
            self._open_gadget(idx)

    def _apply_styles(self):
        """Re-assert the Win32 styles -- set_mode() makes a new HWND each time."""
        handle = overlay.hwnd()
        if handle is None:
            return
        if self.wallpaper or self.gadget:
            overlay.set_transparent(handle, self.opacity)
            overlay.set_tool_window(handle, True)
            overlay.set_click_through(handle, self.click_through or self.wallpaper)
            self._apply_layer(handle)
        else:
            overlay.set_opaque(handle)
            overlay.set_click_through(handle, False)
            overlay.set_tool_window(handle, False)
            overlay.set_no_activate(handle, False)
            overlay.set_topmost(handle, False)

    def _apply_layer(self, handle):
        if self.wallpaper:
            return  # the desktop layer does its own z-ordering
        desktop = self.layer == "desktop"
        # No-activate on the desktop layer: clicking the gadget while browsing
        # must not yank focus away from what you are doing.
        overlay.set_no_activate(handle, desktop)
        overlay.set_topmost(handle, self.layer == "top")
        if desktop:
            overlay.set_bottom(handle)
        self._bottom_ticks = 0

    def _reopen(self):
        """Rebuild the window for a new layout, unhooking the desktop first."""
        if self._attached:
            overlay.detach_from_desktop(overlay.hwnd())
            self._attached = False
        if self.is_open:
            self._apply_window()

    def set_gadget(self, value):
        value = bool(value)
        if value == self.gadget:
            return
        self.gadget = value
        if value:
            self.wallpaper = False
            self.fullscreen = False
            self.show_hud = False
        self._reopen()

    def set_wallpaper(self, value):
        value = bool(value)
        if value == self.wallpaper:
            return
        self.wallpaper = value
        if value:
            self.gadget = False
            self.fullscreen = False
            self.show_hud = False
        self._reopen()

    def reattach(self):
        """Re-hook the desktop layer.

        Whether a window parented into Explorer's WorkerW actually gets painted
        depends on the desktop's current state, so this is the escape hatch when
        wallpaper mode comes up blank.
        """
        if not (self.is_open and self.wallpaper):
            return False
        overlay.detach_from_desktop(overlay.hwnd())
        self._attached = False
        overlay.refresh_desktop()
        self._apply_window()
        return self._attached

    def set_opacity(self, value):
        self.opacity = max(0.1, min(1.0, float(value)))
        if self.is_open and (self.gadget or self.wallpaper):
            overlay.set_transparent(overlay.hwnd(), self.opacity)

    def set_click_through(self, value):
        self.click_through = bool(value)
        if self.is_open and self.gadget:
            overlay.set_click_through(overlay.hwnd(), self.click_through)

    def set_layer(self, layer):
        if layer not in LAYERS:
            return
        self.layer = layer
        if self.is_open and self.gadget:
            self._apply_layer(overlay.hwnd())

    @property
    def topmost(self):
        return self.layer == "top"

    def begin_drag(self):
        """Anchor the drag: remember where the cursor and the window both were."""
        if not self.gadget or self.locked:
            return False
        cursor = overlay.cursor_pos()
        if cursor is None:
            return False
        try:
            self._drag_window = tuple(pygame.display.get_window_position())
        except (AttributeError, pygame.error):
            return False
        self._drag_cursor = cursor
        self._dragging = True
        return True

    def end_drag(self):
        self._dragging = False
        self._drag_cursor = self._drag_window = None

    def drag_to(self, cursor):
        """Move so the window keeps the same offset from the cursor it started
        with. Both anchors are fixed at button-down, so there is no feedback."""
        if not (self._dragging and cursor and self._drag_cursor and self._drag_window):
            return
        pos = (
            int(self._drag_window[0] + cursor[0] - self._drag_cursor[0]),
            int(self._drag_window[1] + cursor[1] - self._drag_cursor[1]),
        )
        # Never let it leave the screen. The cursor picks the target monitor,
        # so dragging onto a second display still works -- it just cannot be
        # parked off an outer edge, or in the gap between two monitors.
        pos = clamp_to_monitor(
            pos, self.screen.get_size(), cursor, anchor=self.gadget_pos
        )
        if pos == tuple(self.gadget_pos or ()):
            return
        try:
            pygame.display.set_window_position(pos)
        except (AttributeError, TypeError, pygame.error):
            return
        self.gadget_pos = pos

    def set_locked(self, value):
        self.locked = bool(value)
        if self.locked:
            self.end_drag()

    def scale_gadget(self, factor):
        w, h = self.gadget_size
        ratio = h / w
        w = int(max(200, min(1600, w * factor)))
        self.gadget_size = (w, int(w * ratio))
        if self.gadget_pos is not None:  # growing can push it off the edge
            self.gadget_pos = clamp_to_monitor(self.gadget_pos, self.gadget_size)
        if self.is_open and self.gadget:
            self._apply_window()

    def set_fullscreen(self, value):
        value = bool(value)
        if value == self.fullscreen:
            return
        self.fullscreen = value
        if value:
            self.gadget = False
            self.wallpaper = False
        self._reopen()

    def set_display(self, index):
        self.display = int(index)
        if self.is_open:
            self._apply_window()

    def set_mode_index(self, index):
        self.mode_idx = int(index) % len(MODES)
        self.mode = MODES[self.mode_idx]()

    def set_palette_index(self, index):
        self.pal_idx = int(index) % len(PALETTES)

    def screenshot(self):
        if not self.is_open:
            return None
        path = os.path.join(shots_dir(), time.strftime("viz-%Y%m%d-%H%M%S.png"))
        pygame.image.save(self.screen, path)
        self.last_shot = path
        print("saved", path)
        return path

    def request_close(self):
        if self.on_close is not None:
            self.on_close()
        else:
            self.running = False

    # ------------------------------------------------------------------ loop

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.request_close()
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.size = event.size  # remembered, so leaving fullscreen restores it
                self._apply_window(move=False)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.begin_drag()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.end_drag()
            elif event.type == pygame.MOUSEWHEEL and self.gadget and not self.locked:
                self.scale_gadget(1.0 + 0.08 * event.y)
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
            if not self.is_open:
                return  # the window went away mid-queue; stop touching it

    def _handle_key(self, key):
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.request_close()
        elif key in (pygame.K_f, pygame.K_F11):
            self.set_fullscreen(not self.fullscreen)
        elif key == pygame.K_TAB:
            self.set_mode_index(self.mode_idx + 1)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.set_mode_index(min(key - pygame.K_1, len(MODES) - 1))
        elif key == pygame.K_SPACE:
            self.set_palette_index(self.pal_idx + 1)
        elif key == pygame.K_a:
            self.analyzer.auto_gain = not self.analyzer.auto_gain
        elif key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_UP):
            self.analyzer.nudge_gain(1.15)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_DOWN):
            self.analyzer.nudge_gain(1 / 1.15)
        elif key == pygame.K_h:
            self.show_hud = not self.show_hud
        elif key == pygame.K_s:
            self.screenshot()

    def render(self, dt):
        screen, trail = self.screen, self.trail
        self.analyzer.update(self.capture.latest(self.analyzer.fft_size), dt)

        fade = self.mode.fade
        trail.fill((fade, fade, fade, fade), special_flags=pygame.BLEND_RGBA_SUB)
        transparent = self.gadget or self.wallpaper
        ctx = {
            "palette": PALETTES[self.pal_idx][1],
            "time": time.perf_counter() - self._start,
            "glow": screen,
            "transparent": transparent,
        }

        # Glow goes straight onto the screen (cleared each frame) so it sits
        # behind the trail without accumulating into a white blob.
        screen.fill((0, 0, 0))
        self.mode.draw(trail, self.analyzer, ctx)
        screen.blit(trail, (0, 0))

        if transparent:
            # The colour key only removes EXACT black. Glow haloes and
            # anti-aliased fringes sit a few units above it, which on a
            # wallpaper reads as dark discs behind the visuals. Subtracting a
            # small floor pushes all of that to true black -- and darkening
            # everything else by BG_FLOOR/255 is imperceptible. One blended
            # fill, so it costs nothing next to a per-pixel pass in numpy.
            screen.fill((BG_FLOOR, BG_FLOOR, BG_FLOOR), special_flags=pygame.BLEND_RGB_SUB)

        if self.show_hud:
            self._draw_hud()

        pygame.display.flip()
        self.frames += 1

    def _draw_hud(self):
        an = self.analyzer
        lines = [
            f"{self.mode.name}  |  {PALETTES[self.pal_idx][0]}  |  {self.clock.get_fps():4.0f} fps",
            f"{self.capture.device_name[:46]}  [{self.capture.status}]",
            f"gain {an.gain:.2f}  auto {'on' if an.auto_gain else 'off'}"
            f"   bass {an.bass:.2f} mid {an.mid:.2f} hi {an.treble:.2f}",
        ]
        help_lines = HELP_LINES + [self.escape_label]
        for i, text in enumerate(lines + [""] + help_lines):
            if not text:
                continue
            dim = 150 if i > len(lines) else 225
            self.screen.blit(self.font.render(text, True, (dim, dim, dim)), (14, 12 + i * 17))

    def frame(self):
        """One tick: events, then a rendered frame if the window is still up."""
        dt = self.clock.tick(self.fps) / 1000.0
        self.handle_events()
        if self._dragging:
            if overlay.left_button_down():
                self.drag_to(overlay.cursor_pos())
            else:
                self.end_drag()  # released off-window, so we never saw the event
        if self.is_open and self.running:
            self.render(dt)
            if self.gadget and self.layer == "desktop":
                self._bottom_ticks += 1
                if self._bottom_ticks >= BOTTOM_REASSERT_FRAMES:
                    self._bottom_ticks = 0
                    overlay.set_bottom(overlay.hwnd())

    def run(self):
        self.open()
        while self.running:
            self.frame()
        self.close()
