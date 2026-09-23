# Audio Visualizer

> ### ⚠️ Experimental
>
> Early work in progress, written and tested on exactly **one** machine
> (Windows 10 19045, Python 3.14, two monitors). It has not been tried on any
> other setup, there are no tests beyond a built-in self-check, and some of it
> leans on undocumented Windows behaviour that Microsoft can change at will.
>
> Known rough edges:
> - **Behind desktop icons** (wallpaper mode) is unreliable — see the section
>   below. It can also leave the last frame painted on your desktop if the app
>   is force-killed while it is on.
> - Transparency is a colour key, not real per-pixel alpha, so *nearly* black
>   pixels can survive as a faint haze. Mitigated, not eliminated.
> - Multi-monitor handling assumes the Win32 monitor geometry is sane; only a
>   1920x1080 + 1280x720 layout has actually been exercised.
> - Software rendering: comfortable at 1080p, tight at 4K.
>
> Use it, break it, open an issue. Just do not expect it to be polished yet.

A desktop visualizer that reacts to whatever Windows is playing — Spotify,
YouTube, games, anything hitting your speakers. No routing, no virtual cable: it
captures the output device directly over WASAPI loopback.

By default it runs as a **transparent desktop gadget**: a small frameless panel
with no background, sitting on your desktop, below your other windows and out of
the taskbar.

## Install it

```
python build.py      builds dist\AudioVisualizer.exe
python install.py    copies it to %LOCALAPPDATA%\Programs and makes shortcuts
```

After that it is a normal app: launch it from the **Start Menu**, the **Desktop
icon**, or by searching for "Audio Visualizer". No Python needed to run it, and
no command to type. `python install.py --uninstall` removes the app and its
shortcuts (settings and logs are left alone).

Installing also copies the exe out of `dist/`, which means `python build.py`
keeps working while the app is running -- Windows locks a running .exe.

## The standalone app

```
dist\AudioVisualizer.exe
```

One file, nothing to install, no Python on the machine required. It sits in the
notification area and stays there:

- **Ctrl+Alt+V** toggles the visualizer from anywhere, at any time.
- **Left-click the tray icon** does the same.
- **Right-click** for everything else — mode, palette, monitor, gadget options,
  fullscreen, screenshot, "Start with Windows", Quit.
- Closing the window (X or `ESC`) **hides** it. Only Quit exits.

While hidden it is genuinely off: the window is destroyed and the audio device
released, so it uses no measurable CPU (~7 MB resident, 0% CPU).

Where you put the gadget, how big it is and how it looks are remembered in
`%LOCALAPPDATA%\AudioVisualizer\config.json`, so it comes back where you left it.

## Gadget mode

- **Drag** it anywhere: click and hold anywhere on it and it follows the cursor.
  The whole panel is the grab handle — there is no title bar. It cannot be pushed
  off the screen: it stays fully inside whichever monitor the cursor is on, so
  dragging it to a second monitor works, but dragging it into nothing does not.
  A position saved on a monitor that is later unplugged is pulled back on screen.
- **Lock position** in the tray menu pins it where it is, so you cannot nudge it
  by accident. Unlock to move it again. Wheel-resize is disabled while locked too.
- **Mouse wheel** resizes it.
- **Opacity** — 100 / 85 / 70 / 55 / 40% in the tray menu.
- **Click-through** — clicks pass straight through to whatever is underneath, so
  it cannot get in your way. (You can still move it again by turning
  click-through back off.)
- **Window layer** — three choices:
  - **Stuck to the desktop** (default) — sits above the wallpaper and icons but
    *below every ordinary window*, and never takes focus. Browse, code, watch
    something: it stays out of the way, and comes back when you minimise things.
  - **Normal window** — behaves like any other window.
  - **Always on top** — floats over everything.

Because it sits below other windows and refuses focus, it cannot interrupt what
you are doing — clicking it does not raise it, and it does not grab the keyboard
when it appears.

Transparency is a colour key: pure black is punched out, everything else is drawn
at the chosen opacity. That suits this app because every mode already draws on
black and the trails fade back to black, so what you get is bars and rings
floating on your wallpaper with no panel behind them.

SDL2 has no per-pixel-alpha window on Windows, hence a colour key rather than
true alpha — and a colour key removes only *exact* black. Anything a shade above
it survives as a dark haze, which is what glow gradients are made of. Gadget mode
therefore skips the wide ambient glows and subtracts a small floor from each
finished frame, pushing that haze down to true black. It is a good approximation,
not real alpha: a hard edge can still show where a gradient crosses the floor.

### Behind the desktop icons (experimental)

The tray menu also has **Behind desktop icons**, which parents the window into
Explorer's `WorkerW` — the layer wallpapers live in — so the visualizer becomes
the desktop background, underneath your icons.

**This one is genuinely flaky, and not because of a bug I can fix from here.**
Whether Explorer actually paints a window parented into that layer depends on the
desktop's current state: the exact same code renders at 60 fps one minute and
shows nothing the next. When it comes up blank, use **Re-attach to desktop** in
the tray menu, or switch it off and back on. If you want this to work reliably
and always, Wallpaper Engine is the tool that has solved it properly.

Turning it off, or quitting normally, repaints the desktop and leaves no trace.
If the app is force-killed while in this mode, the last frame can stay burnt onto
the desktop until something repaints it.

## The CLI

```
python app.py        tray app from source
python viz.py        plain single window, no tray
run.bat              same as viz.py, double-clickable
```

## Controls

| Key | What it does |
| --- | --- |
| `1` `2` `3` / `TAB` | switch mode — rings, bars, scope |
| `SPACE` | next palette (ember, cyan, acid, violet, mono) |
| `A` | toggle auto-gain |
| `+` / `-` (or arrows) | manual gain |
| `F` / `F11` | fullscreen |
| `H` | hide the overlay |
| `S` | save a PNG to your Pictures folder |
| `ESC` / `Q` | quit (tray app: hide) |

## Flags

```
--gadget --opacity 0.7 --gadget-size 520x300 --pos 1400,760
--layer desktop|normal|top   where it sits in the window stack
--click-through --locked
--wallpaper                  behind the desktop icons (experimental)
--fullscreen --display 1     fullscreen on your second monitor
--mode bars --palette cyan
--size 1920x1080 --bands 96 --fps 144
--device "Realtek"           partial name match
--list-devices               (viz.py only)
--hidden / --reset           (app.py only) start in the tray / ignore saved settings
```

By default it follows the Windows default playback device. If you switch outputs
mid-song the capture thread reconnects on its own.

### Building the .exe

```
python build.py            one .exe  (~38 MB, ~70s to build)
python build.py --onedir   a folder instead, starts faster
python build.py --console  keep a console window, for debugging
```

The packaged app is windowed and has nowhere to print, so it logs to
`%LOCALAPPDATA%\AudioVisualizer\log.txt`.

## How it works

- `capture.py` — background thread, WASAPI loopback via `soundcard`, writing into
  a ring buffer so the render loop never blocks on audio.
- `analysis.py` — Hann-windowed 4096-point FFT, 72 log-spaced bands from 28 Hz to
  16 kHz, a +3 dB/octave tilt so the highs stay visible against pink-ish music,
  attack/decay smoothing that is frame-rate independent, falling peak holds, and
  bass-band beat detection against a rolling mean. The scope waveform is a
  contiguous slice aligned to a rising zero crossing, so it does not slide or alias.
- `modes.py` — the three renderers. Geometry is drawn onto a trail surface that
  fades each frame (the afterglow); glow is drawn onto the screen instead,
  because additive light on the trail accumulates and blows out to white.
- `overlay.py` — the Win32 side of gadget mode: layered colour-key transparency,
  click-through, tool-window, always-on-top, and the WorkerW parenting. Every
  style has to be re-applied after each `set_mode()`, which builds a fresh HWND.
- `displays.py` — monitor origins via Win32. SDL only reports desktop *sizes*, and
  its fullscreen `display=` hint silently lands on the primary monitor, so
  fullscreen is a borderless window positioned at the target monitor's bounds.
- `engine.py` — window, input and render loop, able to open and close the window
  and the audio device at runtime. Shared by the CLI and the tray app.
- `app.py` — the tray shell. pygame owns the main thread, so the tray icon
  (`pystray`) and the hotkey (`RegisterHotKey`) run on their own threads and hand
  work back through a queue.
- `settings.py` — the remembered gadget position, size and look.

## Notes

- Requires Python 3.9+ to run from source: `pip install -r requirements.txt`.
- Tested on Python 3.14 with pygame-ce 2.5.8; 60 fps at 1920x1080 with 96 bands.
- `python viz.py --selftest 150 --shot out.png` renders headless and saves a
  frame — useful for checking changes without opening a window.
- `python displays.py` prints the monitor layout; `python overlay.py` prints
  whether the desktop layer can be found.
- Software rendering: fine at 1080p, tight at 4K with high band counts.
