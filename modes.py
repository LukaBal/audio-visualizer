"""Render modes. Each draw() paints onto a per-pixel-alpha trail surface."""

import math

import numpy as np
import pygame

PALETTES = [
    ("ember", [(14, 8, 40), (140, 20, 120), (240, 70, 60), (255, 170, 60), (255, 244, 214)]),
    ("cyan", [(6, 14, 46), (20, 90, 190), (0, 200, 220), (120, 245, 235), (240, 255, 255)]),
    ("acid", [(8, 30, 16), (30, 140, 60), (120, 220, 60), (210, 250, 110), (250, 255, 230)]),
    ("violet", [(12, 6, 36), (70, 30, 170), (160, 60, 230), (240, 120, 200), (255, 230, 250)]),
    ("mono", [(10, 10, 12), (70, 70, 78), (150, 150, 160), (215, 215, 225), (255, 255, 255)]),
]

_GLOW_CACHE = {}


def sample(palette, t, brightness=1.0):
    """Linear sample of a palette at t in 0..1, scaled by brightness."""
    t = min(max(t, 0.0), 1.0) * (len(palette) - 1)
    i = int(t)
    j = min(i + 1, len(palette) - 1)
    f = t - i
    c = [palette[i][k] + (palette[j][k] - palette[i][k]) * f for k in range(3)]
    return tuple(int(min(255, max(0, v * brightness))) for v in c)


GLOW_BASE = 224  # base sprites are built once at this size, then scaled per frame
_COLOR_STEP = 12  # quantize colors so a fading glow keeps hitting the cache


def glow_sprite(color):
    """Radial-gradient sprite in `color`, cached per quantized color.

    Building these is expensive (a full numpy gradient), so never key the cache
    on radius or on an unquantized colour -- both change every single frame.
    """
    key = tuple(min(255, (c // _COLOR_STEP) * _COLOR_STEP) for c in color)
    surf = _GLOW_CACHE.get(key)
    if surf is None:
        axis = np.linspace(-1.0, 1.0, GLOW_BASE, dtype=np.float32)
        dist = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2)
        falloff = np.clip(1.0 - dist, 0.0, 1.0) ** 2.6
        surf = pygame.Surface((GLOW_BASE, GLOW_BASE), pygame.SRCALPHA)
        rgb = pygame.surfarray.pixels3d(surf)
        rgb[:] = (falloff[:, :, None] * np.array(key, dtype=np.float32)).astype(np.uint8)
        del rgb
        alpha = pygame.surfarray.pixels_alpha(surf)
        alpha[:] = (falloff * 255).astype(np.uint8)
        del alpha
        if len(_GLOW_CACHE) > 96:
            _GLOW_CACHE.clear()
        _GLOW_CACHE[key] = surf
    return surf


def blit_glow(surf, center, radius, color):
    """Add a soft radial glow. The gradient is smooth, so plain (nearest) scaling
    is invisible here and far cheaper than smoothscale at full-screen sizes."""
    size = max(8, int(radius) * 2)
    sprite = glow_sprite(color)
    if size != GLOW_BASE:
        sprite = pygame.transform.scale(sprite, (size, size))
    half = size // 2
    surf.blit(
        sprite,
        (int(center[0]) - half, int(center[1]) - half),
        special_flags=pygame.BLEND_RGBA_ADD,
    )


class Mode:
    """draw() paints geometry onto `surf` (the trail, which keeps an afterglow)
    and any glow onto ctx["glow"], a layer cleared every frame. Glow must never
    go on the trail: additive light accumulates there and saturates to white."""

    name = "mode"
    fade = 26  # how fast the afterglow trail decays

    def draw(self, surf, an, ctx):
        raise NotImplementedError


class Rings(Mode):
    """Mirrored radial spectrum with a waveform ring and a bass-driven core."""

    name = "rings"
    fade = 20

    def draw(self, surf, an, ctx):
        w, h = surf.get_size()
        cx, cy = w * 0.5, h * 0.5
        base = min(w, h)
        pal = ctx["palette"]
        beat = an.beat

        levels = an.levels
        n = len(levels)
        seg = n * 2
        mirrored = np.concatenate((levels[::-1], levels))

        r0 = base * (0.135 + 0.030 * an.bass + 0.022 * beat)
        amp = base * 0.32
        span = 2.0 * math.pi / seg
        hw = span * 0.40
        spin = ctx["time"] * 0.06

        # A wide, faint glow is atmosphere against black and a grey smudge on a
        # wallpaper, so the gadget does without it.
        if not ctx.get("transparent"):
            blit_glow(
                ctx["glow"],
                (cx, cy),
                r0 * (2.1 + 0.9 * an.bass + 0.6 * beat),
                sample(pal, 0.42 + 0.35 * an.bass, 0.30 + 0.55 * an.bass + 0.35 * beat),
            )

        tip_color = sample(pal, 0.97, 1.0)
        tip_w = max(1, int(base * 0.0035))
        for i in range(seg):
            lvl = float(mirrored[i])
            if lvl < 0.004:
                continue
            a = -math.pi / 2 + (i + 0.5) * span + spin
            ri, ro = r0, r0 + lvl * amp
            band_t = abs(i - seg / 2) / (seg / 2)
            color = sample(pal, 0.30 + band_t * 0.70, 0.60 + 0.70 * lvl)
            ca, sa = math.cos(a - hw), math.sin(a - hw)
            cb, sb = math.cos(a + hw), math.sin(a + hw)
            quad = (
                (cx + ca * ri, cy + sa * ri),
                (cx + cb * ri, cy + sb * ri),
                (cx + cb * ro, cy + sb * ro),
                (cx + ca * ro, cy + sa * ro),
            )
            pygame.draw.polygon(surf, color, quad)
            if lvl > 0.62:
                pygame.draw.line(surf, tip_color, quad[3], quad[2], tip_w)

        wave = an.waveform.mean(axis=1)
        wave_amp = base * 0.075 * min(an.wave_scale, 5.0)
        pts = []
        wr = r0 * 0.82
        for i in range(seg):
            a = -math.pi / 2 + i * span + spin
            k = int(i / seg * len(wave))
            r = wr + float(wave[k]) * wave_amp * (1.0 + beat)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        if len(pts) > 2:
            pygame.draw.aalines(surf, sample(pal, 0.80, 0.55 + 0.45 * beat), True, pts)

        core = base * (0.020 + 0.045 * an.bass + 0.030 * beat)
        blit_glow(
            ctx["glow"],
            (cx, cy),
            core * (1.5 if ctx.get("transparent") else 2.4),
            sample(pal, 0.90, 0.45 + 0.55 * an.bass),
        )


class Bars(Mode):
    """Classic spectrum bars with peak caps and a reflection."""

    name = "bars"
    fade = 40

    def draw(self, surf, an, ctx):
        w, h = surf.get_size()
        pal = ctx["palette"]
        n = len(an.levels)
        baseline = h * 0.70
        amp = h * 0.60
        slot = w / n
        bw = max(1.0, slot * 0.72)

        if not ctx.get("transparent"):
            blit_glow(
                ctx["glow"],
                (w * 0.5, baseline),
                w * (0.30 + 0.12 * an.energy),
                sample(pal, 0.45, 0.14 + 0.40 * an.energy + 0.25 * an.beat),
            )

        cap_color = sample(pal, 0.95, 0.9)
        for i, lvl in enumerate(an.levels):
            x = i * slot + (slot - bw) * 0.5
            bh = float(lvl) * amp
            t = i / max(1, n - 1)
            if bh >= 1.0:
                color = sample(pal, 0.30 + t * 0.70, 0.60 + 0.60 * float(lvl))
                pygame.draw.rect(surf, color, (x, baseline - bh, bw, bh))
                refl = sample(pal, 0.30 + t * 0.70, 0.28)
                pygame.draw.rect(surf, (*refl, 80), (x, baseline + 2, bw, bh * 0.42))
            pk = float(an.peaks[i]) * amp
            if pk > 2:
                pygame.draw.rect(surf, cap_color, (x, baseline - pk - 2, bw, 2))

        pygame.draw.line(
            surf, sample(pal, 0.5, 0.35 + 0.5 * an.beat), (0, baseline), (w, baseline), 1
        )


class Scope(Mode):
    """Stereo oscilloscope with a Lissajous phase figure behind it."""

    name = "scope"
    fade = 28

    def draw(self, surf, an, ctx):
        w, h = surf.get_size()
        pal = ctx["palette"]
        wave = an.waveform
        gain = an.gain * (an.wave_scale if an.auto_gain else 2.5)
        gain = min(gain, 12.0)
        cx, cy = w * 0.5, h * 0.5
        base = min(w, h)

        if not ctx.get("transparent"):
            blit_glow(
                ctx["glow"],
                (cx, cy),
                base * (0.16 + 0.14 * an.energy + 0.08 * an.beat),
                sample(pal, 0.55, 0.16 + 0.45 * an.energy),
            )

        # Lissajous: rotated 45 deg so mono content reads as a vertical line.
        k = base * 0.26 * gain
        pts = []
        for lft, rgt in wave[::2]:
            x = (float(lft) - float(rgt)) * 0.7071
            y = (float(lft) + float(rgt)) * 0.7071
            pts.append((cx + x * k, cy - y * k))
        if len(pts) > 2:
            pygame.draw.aalines(surf, sample(pal, 0.55, 0.65), False, pts)

        for ch, yc, tone in ((0, h * 0.22, 0.42), (1, h * 0.78, 0.85)):
            line = []
            step = max(1, len(wave) // 480)
            samples = wave[::step, ch]
            for i, v in enumerate(samples):
                x = i / max(1, len(samples) - 1) * w
                line.append((x, yc - float(v) * h * 0.18 * gain))
            if len(line) > 2:
                color = sample(pal, tone, 0.75 + 0.55 * an.energy)
                pygame.draw.aalines(surf, color, False, line)

        r = int(base * (0.02 + 0.06 * an.bass + 0.04 * an.beat))
        if r > 1:
            pygame.draw.circle(
                surf, sample(pal, 0.95, 0.5 + 0.5 * an.beat), (int(cx), int(cy)), r, 1
            )


MODES = [Rings, Bars, Scope]
