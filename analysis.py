"""FFT -> log-spaced bands -> smoothed levels, plus bass/beat detection."""

from collections import deque

import numpy as np

FFT_SIZE = 4096
BANDS = 72
FMIN = 28.0
FMAX = 16000.0

DB_FLOOR = -86.0
DB_CEIL = -12.0
TILT_DB_PER_OCTAVE = 3.0  # music is pink; lift the highs so they stay visible

ATTACK_TAU = 0.025
DECAY_TAU = 0.20
PEAK_FALL = 0.55  # units per second


def _tau_coeff(tau, dt):
    """Frame-rate independent smoothing factor."""
    return 1.0 - np.exp(-dt / max(tau, 1e-6))


class Analyzer:
    def __init__(self, samplerate, fft_size=FFT_SIZE, bands=BANDS, fmin=FMIN, fmax=FMAX):
        self.samplerate = samplerate
        self.fft_size = fft_size
        self.bands = bands
        self.window = np.hanning(fft_size).astype(np.float32)
        self.window_gain = self.window.sum() / 2.0

        freqs = np.fft.rfftfreq(fft_size, 1.0 / samplerate)
        self.freqs = freqs
        edges = np.geomspace(fmin, fmax, bands + 1)
        self.band_centers = np.sqrt(edges[:-1] * edges[1:])
        self._slices = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            idx = np.where((freqs >= lo) & (freqs < hi))[0]
            if idx.size == 0:  # band narrower than one bin: snap to nearest
                idx = np.array([int(np.argmin(np.abs(freqs - np.sqrt(lo * hi))))])
            self._slices.append((idx[0], idx[-1] + 1))

        octaves = np.log2(self.band_centers / fmin)
        self.tilt = (octaves * TILT_DB_PER_OCTAVE).astype(np.float32)

        self.levels = np.zeros(bands, dtype=np.float32)
        self.peaks = np.zeros(bands, dtype=np.float32)
        self.raw = np.zeros(bands, dtype=np.float32)
        self.waveform = np.zeros((512, 2), dtype=np.float32)

        self.bass = 0.0
        self.mid = 0.0
        self.treble = 0.0
        self.energy = 0.0
        self.beat = 0.0  # 0..1 envelope, spikes on a detected hit
        self.gain = 1.0
        self.auto_gain = True
        self.wave_scale = 1.0
        self._wave_peak = 0.05

        self._bass_bands = self.band_centers < 160.0
        self._mid_bands = (self.band_centers >= 160.0) & (self.band_centers < 2500.0)
        self._treble_bands = self.band_centers >= 2500.0
        self._history = deque(maxlen=48)
        self._beat_cooldown = 0.0
        self._agc = 1.0

    def update(self, samples, dt):
        dt = float(np.clip(dt, 1e-4, 0.1))
        mono = samples.mean(axis=1)
        if len(mono) < self.fft_size:
            mono = np.pad(mono, (self.fft_size - len(mono), 0))

        spectrum = np.abs(np.fft.rfft(mono * self.window)) / self.window_gain
        band_mag = np.array(
            [spectrum[lo:hi].max() for lo, hi in self._slices], dtype=np.float32
        )

        db = 20.0 * np.log10(band_mag + 1e-10) + self.tilt
        norm = np.clip((db - DB_FLOOR) / (DB_CEIL - DB_FLOOR), 0.0, 1.0)

        if self.auto_gain:
            loud = float(np.percentile(norm, 92))
            target = 0.80 / max(loud, 0.04) if loud > 0.02 else self._agc
            target = float(np.clip(target, 0.6, 6.0))
            self._agc += (target - self._agc) * _tau_coeff(1.8 if target < self._agc else 0.6, dt)
        else:
            self._agc = 1.0
        norm = np.clip(norm * self._agc * self.gain, 0.0, 1.0)
        self.raw = norm

        rising = norm > self.levels
        coeff = np.where(rising, _tau_coeff(ATTACK_TAU, dt), _tau_coeff(DECAY_TAU, dt))
        self.levels += (norm - self.levels) * coeff

        self.peaks = np.maximum(self.peaks - PEAK_FALL * dt, self.levels)

        self.bass = float(self.levels[self._bass_bands].mean())
        self.mid = float(self.levels[self._mid_bands].mean())
        self.treble = float(self.levels[self._treble_bands].mean())
        self.energy = float(self.levels.mean())

        self._update_waveform(samples, dt)

        self._detect_beat(dt)
        return self

    def _update_waveform(self, samples, dt):
        """Grab a contiguous slice aligned to a rising zero crossing.

        Decimating the FFT window instead would alias the waveform into noise,
        and without the trigger the wave slides sideways every frame.
        """
        span = len(self.waveform)
        tail = samples[-span * 3:]
        if len(tail) < span * 2:
            return
        mono = tail.mean(axis=1)
        search = mono[: len(tail) - span]
        crossings = np.where((search[:-1] <= 0.0) & (search[1:] > 0.0))[0]
        start = int(crossings[len(crossings) // 2]) if len(crossings) else 0
        self.waveform = tail[start : start + span]

        # Amplitude envelope so quiet tracks still fill the screen: fast to
        # follow a rise, slow to release so it does not pump on every note.
        peak = float(np.abs(tail).max())
        tau = 0.05 if peak > self._wave_peak else 0.6
        self._wave_peak += (max(peak, 0.01) - self._wave_peak) * _tau_coeff(tau, dt)
        self.wave_scale = float(np.clip(0.45 / max(self._wave_peak, 1e-3), 0.5, 14.0))

    def _detect_beat(self, dt):
        band_energy = float(self.raw[self._bass_bands].mean())
        self._history.append(band_energy)
        self.beat = max(0.0, self.beat - dt / 0.28)
        self._beat_cooldown = max(0.0, self._beat_cooldown - dt)
        if len(self._history) < self._history.maxlen or self._beat_cooldown > 0:
            return
        hist = np.fromiter(self._history, dtype=np.float32)
        mean, std = float(hist.mean()), float(hist.std())
        if band_energy > mean * 1.35 + std * 0.6 and band_energy > 0.12:
            self.beat = 1.0
            self._beat_cooldown = 0.13

    def nudge_gain(self, factor):
        self.gain = float(np.clip(self.gain * factor, 0.1, 8.0))
