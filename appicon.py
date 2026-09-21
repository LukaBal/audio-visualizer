"""The app/tray icon, drawn at runtime so there is no binary asset to ship."""

from PIL import Image, ImageDraw

# (height fraction, colour) -- a little spectrum, ember palette.
BARS = [
    (0.42, (196, 40, 120)),
    (0.66, (240, 70, 60)),
    (0.92, (255, 150, 60)),
    (0.58, (255, 196, 90)),
    (0.34, (255, 238, 200)),
]

BACKDROP = (16, 10, 26, 255)


def make_image(size=256):
    """Square RGBA icon. Kept legible down to 16px: few bars, high contrast."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(2, int(size * 0.22))
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BACKDROP)

    pad = size * 0.16
    inner = size - pad * 2
    slot = inner / len(BARS)
    width = slot * 0.62
    bottom = size - pad
    bar_radius = max(1, int(width * 0.35))

    for i, (height, color) in enumerate(BARS):
        x = pad + i * slot + (slot - width) * 0.5
        top = bottom - inner * height
        draw.rounded_rectangle(
            [x, top, x + width, bottom], radius=bar_radius, fill=color + (255,)
        )
    return img


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    img = make_image(256)
    img.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path


if __name__ == "__main__":
    import os
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "assets/icon.ico"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    print("wrote", save_ico(out))
