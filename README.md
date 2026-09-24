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
- **Hover to reveal it** — only while *Resize by dragging edges* is on. Move the
  pointer onto the gadget and a faint panel, outline and grab handles appear;
  move away and it goes back to bare visuals. This is not decoration: colour-keyed
  pixels are transparent to *clicks* as well as to light, so without something
  drawn there, a click on an empty part of the panel sails straight through to
  whatever is behind it. With resizing switched off nothing is drawn on hover at
  all, so the gadget never lights up while you are just passing over it -- the
  trade-off being that you can then only grab it where the visuals actually are.
- **Resize by dragging edges** — a tray toggle, on by default. Grab the left or
  right edge for **width**, the top or bottom edge for **height**, or any corner
  for **both at once**. The pointer changes shape as you cross an edge so you can
  see where the grab zone is. Dragging a left or top edge keeps the opposite side
  planted. Minimum size is 180x110, and it cannot be grown past the edge of the
  screen. Turn the toggle off and the edges become draggable like the rest of the
  panel, moving it instead.
- **Mouse wheel** resizes proportionally. Also governed by that toggle.
- **Lock position** pins it where it sits so you cannot nudge it by accident.
  It is independent of resizing: a locked gadget still resizes from its edges, it
  just will not move.
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

**Fullscreen** (tray menu, or `F`) borrows the whole monitor for as long as you
want it, then hands everything back: leaving fullscreen returns the gadget to the
exact size, position and transparency it had, rather than to a plain window.

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
--click-through --locked --no-drag-resize
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

Sound goes in one end and pixels come out the other, through four stages. Each
stage hands the next one a plain data structure, so any of them can be read on
its own.

```
WASAPI loopback -> ring buffer -> FFT + smoothing -> renderer -> layered window
   capture.py       capture.py      analysis.py      modes.py    engine/overlay
```

### 1. Capture (`capture.py`)

A background thread opens the output device as a *loopback* recorder through
`soundcard`, which is what lets it hear what Windows is playing without any
virtual cable. It records in 512-frame blocks and writes them into a one-second
stereo ring buffer behind a lock.

The render loop never waits on audio: it just asks for `latest(4096)`, the most
recent frames, whenever it wants them. If the stream throws -- headphones
unplugged, the device switching format, another app grabbing it exclusively --
the thread closes the recorder, re-resolves the device and starts again, which is
what the `[live]` / `[reconnecting]` label in the overlay reports.

### 2. Analysis (`analysis.py`)

`Analyzer.update(samples, dt)` turns those frames into the numbers the renderers
draw. In order:

- Mix to mono, apply a **Hann window**, and take a **4096-point real FFT**. That
  is ~12 Hz per bin and ~85 ms of audio: fine enough to separate bass notes,
  short enough to still feel immediate.
- Fold the bins into **72 log-spaced bands** from 28 Hz to 16 kHz, taking the
  loudest bin in each band. Log spacing because pitch is logarithmic -- linear
  bands would spend half the display on the top two octaves, where little
  happens.
- Convert to dB and add a **+3 dB/octave tilt**. Music is roughly pink (energy
  falls with frequency), so without the tilt the treble bands would barely move.
  Then normalise between -86 dB and -12 dB.
- **Auto-gain**: track the 92nd percentile of band levels and scale towards a
  target, fast to rise and slow to release, so a quiet track still fills the
  panel without pumping on every note.
- **Smoothing** with separate attack and decay time constants, computed as
  `1 - exp(-dt/tau)` rather than a fixed per-frame factor -- that keeps the feel
  identical at 30, 60 or 144 fps.
- **Peak holds** that fall at a constant rate, the little caps above the bars.
- **Beat detection**: compare current bass energy against a rolling mean and
  standard deviation of the last 48 frames, with a cooldown so one hit does not
  register three times. Drives a `beat` envelope the renderers use for punch.
- **Waveform** for the scope: a contiguous slice aligned to a rising zero
  crossing. Contiguous because decimating the FFT window aliases a waveform into
  noise; zero-crossing aligned so the trace does not slide sideways every frame.

### 3. Rendering (`modes.py`)

Three renderers -- `Rings`, `Bars`, `Scope` -- share one contract: draw geometry
onto the **trail surface**, draw glow onto the **screen**. Both distinctions
matter:

- The trail is a per-pixel-alpha surface that is *faded* each frame by
  subtracting a constant (`BLEND_RGBA_SUB`) rather than cleared. That is the
  afterglow. Subtracting reaches exactly zero, where a translucent black overlay
  would leave permanent residue.
- Glow must **not** go on the trail. Additive light on a surface that is only
  partly faded accumulates frame after frame and saturates to a white blob. It
  goes on the screen layer, which is cleared every frame.
- Glow sprites are cached **per quantised colour** and scaled per blit. Keying
  the cache on radius or on an exact colour means rebuilding a full-screen
  gradient every frame, which cost about a third of the frame budget.

### 4. The window (`engine.py`, `overlay.py`, `displays.py`)

`engine.py` owns the window, the input and the frame loop, and can open and close
both the window and the audio device at runtime -- that is what lets the tray app
switch the whole thing off without exiting. One frame, in order:

1. Clear the screen; if hovered, lay down the faint grab-me wash.
2. Fade the trail; let the mode draw (geometry to trail, glow to screen).
3. Blit the trail over the screen.
4. In gadget mode, subtract `BG_FLOOR` from the whole frame.
5. Draw the hover chrome, then the overlay text, then flip.

`overlay.py` is the Win32 half. The window is **layered with a colour key**: pure
black is punched out. Everything awkward about gadget mode follows from one fact
-- *a colour-keyed pixel is transparent to mouse clicks as well as to light*:

- Step 4 exists because a colour key removes only **exact** black, and glow
  gradients fade through near-black. Those pixels would otherwise show as a dark
  haze on your wallpaper.
- The hover chrome exists because 60% of the panel is transparent, so clicks on
  the empty parts land on whatever is behind. Drawing something there is what
  makes the edges grabbable at all.
- Hover is **polled** from the cursor position rather than read from mouse
  events, because no mouse events arrive over transparent pixels in the first
  place.

`displays.py` supplies monitor geometry from Win32, because SDL reports desktop
*sizes* but not where each monitor sits, and its fullscreen `display=` hint lands
on the primary monitor whatever you ask for. Monitors also need not tile the
virtual desktop -- on the machine this was built on they sit 640 px apart -- so
positions are clamped inside a single monitor rather than a bounding box.

Dragging and resizing both anchor on the **absolute cursor position** captured at
button-down. Using relative mouse motion feeds back on itself: moving the window
changes the pointer's position inside it, which changes the next reading.

### 5. The shell (`app.py`)

pygame must own the main thread, so the tray icon (`pystray`) and the global
hotkey (`RegisterHotKey`, which delivers to the thread that registered it) each
run on their own thread and post commands into a queue. The main loop drains that
queue between frames, so nothing but the main thread ever touches the window.

`settings.py` persists the gadget's geometry and look to
`%LOCALAPPDATA%\AudioVisualizer\config.json`; `autostart.py` writes a single
optional value to the per-user `Run` key; `appicon.py` draws the icon at runtime
so there is no binary asset; `build.py` and `install.py` package and install it.

## Notes

- Requires Python 3.9+ to run from source: `pip install -r requirements.txt`.
- Tested on Python 3.14 with pygame-ce 2.5.8; 60 fps at 1920x1080 with 96 bands.
- `python viz.py --selftest 150 --shot out.png` renders headless and saves a
  frame — useful for checking changes without opening a window.
- `python displays.py` prints the monitor layout; `python overlay.py` prints
  whether the desktop layer can be found.
- Software rendering: fine at 1080p, tight at 4K with high band counts.
