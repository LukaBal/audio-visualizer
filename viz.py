"""Desktop audio visualizer: reacts to whatever Windows is playing.

    python viz.py                 windowed, default output device
    python viz.py --fullscreen    fullscreen on monitor 0
    python viz.py --list-devices  show capturable outputs

For the tray version that stays resident, run app.py instead.
"""

import argparse
import os
import sys

from capture import list_loopback_devices


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--device", help="partial name of the output device to capture")
    p.add_argument("--list-devices", action="store_true", help="list loopback devices and exit")
    p.add_argument("--mode", default="rings", choices=["rings", "bars", "scope"])
    p.add_argument("--palette", default="ember")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--display", type=int, default=0, help="monitor index for fullscreen")
    p.add_argument("--size", default="1280x720", help="window size, e.g. 1600x900")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--bands", type=int, default=72)
    p.add_argument("--gadget", action="store_true", help="transparent desktop gadget")
    p.add_argument("--wallpaper", action="store_true", help="draw behind the desktop icons")
    p.add_argument("--gadget-size", dest="gadget_size", default="460x260")
    p.add_argument("--pos", help="gadget position, e.g. 1400,760")
    p.add_argument("--opacity", type=float, default=0.9, help="0.1 to 1.0")
    p.add_argument("--click-through", dest="click_through", action="store_true")
    p.add_argument("--locked", action="store_true", help="pin the gadget in place")
    p.add_argument(
        "--no-drag-resize",
        dest="resizable",
        action="store_false",
        help="do not resize when dragging the edges",
    )
    p.add_argument(
        "--layer",
        default="desktop",
        choices=("desktop", "normal", "top"),
        help="desktop = behind every window (default), normal, or top",
    )
    p.add_argument("--no-topmost", dest="layer", action="store_const", const="normal")
    p.add_argument("--selftest", type=int, metavar="FRAMES", help="render headless and exit")
    p.add_argument("--shot", help="where --selftest writes its final frame")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.list_devices:
        for mic in list_loopback_devices():
            print(f"  {mic.name}")
        return 0

    if args.selftest:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    # Imported here: engine pulls in pygame, which reads SDL_VIDEODRIVER at import.
    import numpy as np
    import pygame

    from engine import Visualizer

    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        raise SystemExit(f"--size must look like 1280x720, got {args.size!r}")

    try:
        gw, gh = (int(v) for v in args.gadget_size.lower().split("x"))
    except ValueError:
        raise SystemExit(f"--gadget-size must look like 460x260, got {args.gadget_size!r}")
    pos = None
    if args.pos:
        try:
            px, py = (int(v) for v in args.pos.replace(" ", "").split(","))
            pos = (px, py)
        except ValueError:
            raise SystemExit(f"--pos must look like 1400,760, got {args.pos!r}")

    viz = Visualizer(
        size=(width, height),
        mode=args.mode,
        palette=args.palette,
        bands=args.bands,
        fps=args.fps,
        fullscreen=args.fullscreen,
        display=args.display,
        device=args.device,
        gadget=args.gadget,
        wallpaper=args.wallpaper,
        gadget_size=(gw, gh),
        gadget_pos=pos,
        opacity=args.opacity,
        click_through=args.click_through,
        layer=args.layer,
        locked=args.locked,
        resizable=args.resizable,
    )
    viz.open()

    if args.selftest:
        for _ in range(args.selftest):
            viz.frame()
        out = args.shot or "selftest.png"
        pygame.image.save(viz.screen, out)
        peak = float(np.abs(viz.capture.latest(4096)).max())
        fps = viz.clock.get_fps()
        print(f"selftest: {viz.frames} frames, {fps:.0f} fps, audio peak {peak:.4f} -> {out}")
    else:
        while viz.running:
            viz.frame()

    viz.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
