"""A system-wide hotkey, so the visualizer can be summoned from anything.

RegisterHotKey delivers WM_HOTKEY to the *thread* that registered it, so the
registration and the message pump have to live on the same thread -- hence a
thread of its own. Polling with PeekMessage rather than blocking in GetMessage
keeps stop() responsive.
"""

import ctypes
import threading
import time
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

HOTKEY_ID = 0xA17


class GlobalHotkey(threading.Thread):
    def __init__(self, callback, mods=MOD_CONTROL | MOD_ALT, vk=ord("V"), label="Ctrl+Alt+V"):
        super().__init__(name="hotkey", daemon=True)
        self.callback = callback
        self.mods = mods
        self.vk = vk
        self.label = label
        self.error = None
        self.registered = False
        self._stop = threading.Event()

    def run(self):
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, HOTKEY_ID, self.mods | MOD_NOREPEAT, self.vk):
            # Almost always means another app already owns the combination.
            self.error = f"{self.label} is already taken by another app"
            return
        self.registered = True
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY:
                        try:
                            self.callback()
                        except Exception as exc:
                            print("hotkey callback failed:", exc)
                time.sleep(0.03)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False

    def stop(self):
        self._stop.set()


if __name__ == "__main__":
    hits = []
    hk = GlobalHotkey(lambda: hits.append(time.time()))
    hk.start()
    time.sleep(0.5)
    print("registered:", hk.registered, "error:", hk.error)
    hk.stop()
