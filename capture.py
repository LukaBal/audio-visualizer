"""WASAPI loopback capture: pulls whatever Windows is playing into a ring buffer."""

import threading
import time
import warnings

import numpy as np
import soundcard as sc

# Loopback streams hiccup whenever Windows reroutes audio; the recorder recovers
# on its own, so keep the warning out of the console.
warnings.filterwarnings("ignore", message="data discontinuity in recording")

SAMPLERATE = 48000
BLOCKSIZE = 512


def list_loopback_devices():
    """Every device we can record system audio from, default speaker first."""
    mics = sc.all_microphones(include_loopback=True)
    loopbacks = [m for m in mics if getattr(m, "isloopback", False)]
    try:
        default = sc.default_speaker().name
    except Exception:
        default = None
    loopbacks.sort(key=lambda m: (default is None or default not in m.name))
    return loopbacks


def resolve_device(name=None):
    """Find a loopback mic by (partial, case-insensitive) name, else the default speaker."""
    if name:
        needle = name.lower()
        for mic in list_loopback_devices():
            if needle in mic.name.lower():
                return mic
        raise SystemExit(f"No loopback device matching {name!r}. Try --list-devices.")
    speaker = sc.default_speaker()
    return sc.get_microphone(id=str(speaker.name), include_loopback=True)


class AudioCapture:
    """Background thread writing stereo frames into a lock-protected ring buffer.

    Reopens the stream on failure so unplugging headphones doesn't kill the app.
    """

    def __init__(self, device=None, samplerate=SAMPLERATE, seconds=1.0):
        self.samplerate = samplerate
        self._device_name = device
        self._mic = resolve_device(device)
        self._size = int(samplerate * seconds)
        self._buf = np.zeros((self._size, 2), dtype=np.float32)
        self._idx = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.status = "starting"

    @property
    def device_name(self):
        return self._mic.name

    def start(self):
        self._thread = threading.Thread(target=self._run, name="audio-capture", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self):
        while not self._stop.is_set():
            try:
                with self._mic.recorder(
                    samplerate=self.samplerate, channels=2, blocksize=BLOCKSIZE
                ) as rec:
                    self.status = "live"
                    while not self._stop.is_set():
                        self._write(rec.record(numframes=BLOCKSIZE))
            except Exception as exc:  # device yanked, format change, exclusive-mode grab
                self.status = f"reconnecting ({type(exc).__name__})"
                time.sleep(0.7)
                try:
                    self._mic = resolve_device(self._device_name)
                except Exception:
                    pass

    def _write(self, data):
        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 1:
            data = np.column_stack((data, data))
        n = len(data)
        if n == 0:
            return
        if n >= self._size:
            data, n = data[-self._size:], self._size
        with self._lock:
            end = self._idx + n
            if end <= self._size:
                self._buf[self._idx:end] = data
            else:
                split = self._size - self._idx
                self._buf[self._idx:] = data[:split]
                self._buf[: n - split] = data[split:]
            self._idx = end % self._size

    def latest(self, n):
        """The most recent n stereo frames, oldest first."""
        n = min(n, self._size)
        out = np.empty((n, 2), dtype=np.float32)
        with self._lock:
            start = self._idx - n
            if start >= 0:
                out[:] = self._buf[start:self._idx]
            else:
                head = -start
                out[:head] = self._buf[self._size - head:]
                out[head:] = self._buf[: self._idx]
        return out
