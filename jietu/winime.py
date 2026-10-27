"""Windows 输入法上下文管理。

Qt 窗口一旦获得焦点，TSF 就会把当前输入法 DLL 注入进程
（例如搜狗 SogouPY.ime 约 27MB + SogouTSF.ime 5MB，外加 PicFace/Resource 等）。
截图遮罩和工具条不需要输入法，提前解绑输入上下文可以避免这部分常驻内存；
只有真正弹出文字编辑框时才恢复。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes


def _imm32():
    try:
        lib = ctypes.WinDLL("imm32")
        lib.ImmAssociateContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        lib.ImmAssociateContext.restype = wintypes.HANDLE
        lib.ImmCreateContext.argtypes = []
        lib.ImmCreateContext.restype = wintypes.HANDLE
        return lib
    except Exception:
        return None


def detach(hwnd: int):
    """解绑窗口的输入法上下文，返回原上下文（可能为 None）。"""
    lib = _imm32()
    if lib is None or not hwnd:
        return None
    try:
        return lib.ImmAssociateContext(wintypes.HWND(hwnd), None)
    except Exception:
        return None


def attach(hwnd: int, ctx) -> None:
    """恢复输入法上下文；ctx 为空时新建一个，保证中文输入可用。"""
    lib = _imm32()
    if lib is None or not hwnd:
        return
    try:
        if ctx is None:
            ctx = lib.ImmCreateContext()
        if ctx:
            lib.ImmAssociateContext(wintypes.HWND(hwnd), wintypes.HANDLE(ctx))
    except Exception:
        pass
