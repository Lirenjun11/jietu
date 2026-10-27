"""屏幕抓取（支持多屏、高 DPI）与窗口检测。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap


class ScreenShot:
    """单个屏幕的抓取结果

    只保留一份 QPixmap。早期版本会缓存一份等大的 QImage（放大镜取色用），
    在 4K/多屏下等于把整屏内存翻倍；现在改为按需裁出几像素的小块。
    """

    __slots__ = ("geometry", "dpr", "pixmap", "name")

    def __init__(self, screen) -> None:
        self.geometry: QRect = screen.geometry()
        self.dpr: float = float(screen.devicePixelRatio()) or 1.0
        self.name: str = screen.name()
        pm = screen.grabWindow(0)
        if pm.isNull() or pm.width() == 0:
            # 兜底：从主屏抓
            pm = QGuiApplication.primaryScreen().grabWindow(0)
        pm.setDevicePixelRatio(1.0)
        self.pixmap: QPixmap = pm

    def sample(self, x: int, y: int, w: int, h: int) -> QImage:
        """从整屏位图里裁一小块（物理像素），不会保留整屏 QImage。"""
        pw, ph = self.pixmap.width(), self.pixmap.height()
        if pw <= 0 or ph <= 0:
            return QImage()
        x = max(0, min(int(x), pw - 1))
        y = max(0, min(int(y), ph - 1))
        w = max(1, min(int(w), pw - x))
        h = max(1, min(int(h), ph - y))
        return self.pixmap.copy(x, y, w, h).toImage()

    def pixel_color(self, x: int, y: int) -> QColor:
        pw, ph = self.pixmap.width(), self.pixmap.height()
        if not (0 <= x < pw and 0 <= y < ph):
            return QColor(0, 0, 0)
        return self.pixmap.copy(int(x), int(y), 1, 1).toImage().pixelColor(0, 0)

    def release(self) -> None:
        self.pixmap = QPixmap()

    @property
    def phys_geometry(self) -> QRectF:
        return QRectF(
            self.geometry.x() * self.dpr,
            self.geometry.y() * self.dpr,
            self.geometry.width() * self.dpr,
            self.geometry.height() * self.dpr,
        )


class Shot:
    """虚拟桌面拼接图"""

    def __init__(self) -> None:
        self.parts: list[ScreenShot] = [
            ScreenShot(s) for s in QGuiApplication.screens()
        ]
        self.virtual: QRect = QRect()
        for p in self.parts:
            self.virtual = self.virtual.united(p.geometry)
        if self.virtual.isEmpty():
            self.virtual = QGuiApplication.primaryScreen().geometry()

    # ---------- 绘制 ----------
    def paint(self, painter: QPainter, target: QRect | None = None) -> None:
        """把整张桌面画到 painter（逻辑坐标）"""
        target = target or self.virtual
        for p in self.parts:
            r = p.geometry.intersected(target)
            if r.isEmpty():
                continue
            src = QRectF(
                (r.x() - p.geometry.x()) * p.dpr,
                (r.y() - p.geometry.y()) * p.dpr,
                r.width() * p.dpr,
                r.height() * p.dpr,
            )
            painter.drawPixmap(QRectF(r), p.pixmap, src)

    def paint_region(self, painter: QPainter, rect: QRect) -> None:
        self.paint(painter, rect)

    # ---------- 取像素 ----------
    def pixel(self, pt: QPoint) -> QColor:
        for p in self.parts:
            if p.geometry.contains(pt):
                x = int((pt.x() - p.geometry.x()) * p.dpr)
                y = int((pt.y() - p.geometry.y()) * p.dpr)
                return p.pixel_color(x, y)
        return QColor(0, 0, 0)

    # ---------- 裁剪输出 ----------
    def crop_image(self, rect: QRect) -> QImage:
        """按逻辑矩形裁剪，输出原始物理分辨率（高清）的 QImage。"""
        rect = rect.normalized()
        if rect.isEmpty():
            return QImage()

        out_dpr = self.dpr_at(rect.center())
        out = QImage(
            max(1, int(round(rect.width() * out_dpr))),
            max(1, int(round(rect.height() * out_dpr))),
            QImage.Format_ARGB32_Premultiplied,
        )
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(out_dpr, out_dpr)
        p.setClipRect(QRectF(0, 0, rect.width(), rect.height()))

        for ss in self.parts:
            inter = ss.geometry.intersected(rect)
            if inter.isEmpty():
                continue
            src = QRectF(
                (inter.x() - ss.geometry.x()) * ss.dpr,
                (inter.y() - ss.geometry.y()) * ss.dpr,
                inter.width() * ss.dpr,
                inter.height() * ss.dpr,
            )
            dst = QRectF(
                inter.x() - rect.x(),
                inter.y() - rect.y(),
                inter.width(),
                inter.height(),
            )
            p.drawPixmap(dst, ss.pixmap, src)
        p.end()
        return out

    def crop(self, rect: QRect) -> QPixmap:
        """按逻辑矩形裁剪，输出原始物理分辨率（高清）"""
        img = self.crop_image(rect)
        if img.isNull():
            return QPixmap()
        return QPixmap.fromImage(img)

    # ---------- 释放 ----------
    def release(self) -> None:
        """立刻归还整屏位图（不等 GC），截图结束后调用。"""
        for p in self.parts:
            p.release()
        self.parts.clear()

    def dpr_at(self, pt: QPoint) -> float:
        for p in self.parts:
            if p.geometry.contains(pt):
                return p.dpr
        return self.parts[0].dpr if self.parts else 1.0

    def screen_at(self, pt: QPoint):
        for p in self.parts:
            if p.geometry.contains(pt):
                return p
        return self.parts[0] if self.parts else None


# ---------------------------------------------------------------- 窗口检测
class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _init_user32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.EnumWindows.restype = wintypes.BOOL
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsIconic.restype = wintypes.BOOL
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    u.GetWindowRect.restype = wintypes.BOOL
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetWindowLongW.restype = ctypes.c_long
    u.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetClassNameW.restype = ctypes.c_int
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextLengthW.restype = ctypes.c_int
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowTextW.restype = ctypes.c_int
    return u


class WindowDetector:
    """找到鼠标下最上层的可见窗口（物理像素坐标）"""

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000

    def __init__(self) -> None:
        self.ok = False
        try:
            self.user32 = _init_user32()
            self.dwmapi = ctypes.WinDLL("dwmapi")
            self.own_pid = ctypes.windll.kernel32.GetCurrentProcessId()
            self.ok = True
        except Exception:
            self.ok = False
        self._skip_classes = {
            "Progman",
            "WorkerW",
            "Shell_TrayWnd",
            "Shell_SecondaryTrayWnd",
            "Windows.UI.Core.CoreWindow",
            "ApplicationFrameWindow_Hidden",
        }

    def _frame_bounds(self, hwnd) -> _RECT | None:
        rect = _RECT()
        try:
            hr = self.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                9,  # DWMWA_EXTENDED_FRAME_BOUNDS
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
                return rect
        except Exception:
            pass
        rect = _RECT()
        if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect
        return None

    def window_at(self, phys_x: int, phys_y: int, exclude_hwnd: int = 0):
        """返回 (QRect 物理坐标, 标题) 或 None"""
        if not self.ok:
            return None
        pt = _POINT(phys_x, phys_y)
        found: list = []

        EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lparam):
            if exclude_hwnd and hwnd == exclude_hwnd:
                return True
            if not self.user32.IsWindowVisible(hwnd):
                return True
            if self.user32.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.own_pid:
                return True
            ex = self.user32.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
            if ex & self.WS_EX_TRANSPARENT:
                return True
            buf = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in self._skip_classes:
                return True
            r = self._frame_bounds(hwnd)
            if not r:
                return True
            if not (r.left <= pt.x < r.right and r.top <= pt.y < r.bottom):
                return True
            if r.right - r.left < 8 or r.bottom - r.top < 8:
                return True
            title_len = self.user32.GetWindowTextLengthW(hwnd)
            title = ""
            if title_len > 0:
                tbuf = ctypes.create_unicode_buffer(title_len + 2)
                self.user32.GetWindowTextW(hwnd, tbuf, title_len + 2)
                title = tbuf.value
            found.append(
                (
                    QRect(r.left, r.top, r.right - r.left, r.bottom - r.top),
                    title,
                    buf.value,
                )
            )
            return False  # 找到最上层即停

        try:
            self.user32.EnumWindows(EnumProc(cb), 0)
        except Exception:
            return None
        return found[0] if found else None


def phys_to_logical(rect_phys: QRect, dpr: float) -> QRect:
    return QRect(
        int(round(rect_phys.x() / dpr)),
        int(round(rect_phys.y() / dpr)),
        int(round(rect_phys.width() / dpr)),
        int(round(rect_phys.height() / dpr)),
    )
