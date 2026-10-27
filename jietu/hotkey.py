"""Windows 全局热键（RegisterHotKey + Qt 原生事件过滤）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


class GlobalHotkeys(QAbstractNativeEventFilter):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.callbacks: dict[int, callable] = {}
        self._next = 0x4A00
        self.ok = False
        try:
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.RegisterHotKey.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                wintypes.UINT,
                wintypes.UINT,
            ]
            self.user32.RegisterHotKey.restype = wintypes.BOOL
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.UnregisterHotKey.restype = wintypes.BOOL
            self.ok = True
        except Exception:
            self.ok = False
        try:
            app.installNativeEventFilter(self)
        except Exception:
            pass

    # ------------------------------------------------------------------
    @staticmethod
    def parse(seq: str):
        parts = [p.strip().lower() for p in seq.replace(" ", "").split("+") if p.strip()]
        mods = MOD_NOREPEAT
        vk = 0
        for p in parts:
            if p in ("ctrl", "control"):
                mods |= MOD_CONTROL
            elif p == "alt":
                mods |= MOD_ALT
            elif p == "shift":
                mods |= MOD_SHIFT
            elif p in ("win", "meta", "super"):
                mods |= MOD_WIN
            elif len(p) == 1 and p.isalnum():
                vk = ord(p.upper())
            elif p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
                vk = 0x70 + int(p[1:]) - 1
            elif p in ("printscreen", "prtsc", "prtscr"):
                vk = 0x2C
        return mods, vk

    def register(self, seq: str, cb) -> bool:
        if not self.ok:
            return False
        mods, vk = self.parse(seq)
        if not vk:
            return False
        hid = self._next
        self._next += 1
        if not self.user32.RegisterHotKey(None, hid, mods, vk):
            return False
        self.callbacks[hid] = cb
        return True

    def clear(self):
        if not self.ok:
            return
        for hid in list(self.callbacks):
            try:
                self.user32.UnregisterHotKey(None, hid)
            except Exception:
                pass
        self.callbacks.clear()

    # ------------------------------------------------------------------
    def nativeEventFilter(self, eventType, message):
        try:
            et = bytes(eventType) if not isinstance(eventType, str) else eventType.encode()
            if et == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    cb = self.callbacks.get(int(msg.wParam))
                    if cb is not None:
                        cb()
                        return True, 0
        except Exception:
            pass
        return False, 0
