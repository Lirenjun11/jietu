"""截图主界面：全屏遮罩 → 框选 → 标注编辑 → 复制/保存/贴图。"""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget

from .annotations import (
    TOOL_DEFS,
    Annotation,
    draw_annotation,
    text_bounds,
)
from .capture import Shot, WindowDetector, phys_to_logical
from .config import config
from .toolbar import ToolBar
from .winime import attach as attach_ime
from .winime import detach as detach_ime

MODE_SELECT = 0
MODE_EDIT = 1

HANDLE = 8
ACCENT = QColor("#2F6FEB")
ACCENT_LIGHT = QColor("#7FB0FF")


class CaptureOverlay(QWidget):
    pinRequested = Signal(QPixmap)
    savedTo = Signal(str)
    copiedToClipboard = Signal(QPixmap)
    closed = Signal()

    def __init__(self, shot: Shot, mode: str = "region", parent=None):
        super().__init__(parent)
        self.shot = shot
        self.virtual = shot.virtual
        self.mode = MODE_SELECT
        self.sel = QRect()
        self.sel_valid = False

        self.annotations: list[Annotation] = []
        self.redo_stack: list[Annotation] = []
        self.active: Annotation | None = None

        self.tool = config.get("last_tool", "rect")
        self.color = config.get("last_color", "#FF3B30")
        self.width = int(config.get("last_width", 3))

        self.dragging = None  # 'new' | 'move' | 'resize' | 'draw'
        self.drag_origin = QPointF()
        self.sel_origin = QRect()
        self.resize_idx = -1
        self.cursor_global = QPointF(self.virtual.center())
        self.inside = False

        self.base_pixmap: QPixmap | None = None
        self.base_image: QImage | None = None
        self.base_phys: QImage | None = None
        self.mosaic_scale = 1.0
        self._base_dirty = True

        self.text_editor = None
        self._text_commit = None
        self._text_cancel = None
        self._text_committed_at = 0.0
        self.number_counter = 0

        self.selected: Annotation | None = None
        self._drag_ann: Annotation | None = None
        self._drag_ann_start = QPointF()
        self._drag_ann_origin = QPointF()

        self.detector = WindowDetector() if config.get("show_window_detect") else None
        self.hover_rect: QRect | None = None
        self.hover_title = ""
        self._last_detect = 0.0

        self.toolbar: ToolBar | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        # 不使用 WA_DeleteOnClose：Qt 会在 close() 内部直接 delete，
        # 与 Python 侧引用计数释放冲突，偶发 double-free 崩溃。
        # 改为 finish() 里显式 deleteLater()。
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._finished = False
        # 遮罩本身不需要输入法；否则一获得焦点就会把第三方输入法 DLL
        # （如 SogouPY.ime，约 30MB）注入进程。文字工具单独启用。
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self._ime_ctx = None
        self._ime_detached = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self.virtual)

        if mode == "fullscreen":
            self.sel = QRect(self.virtual)
            self.sel_valid = True
            QTimer.singleShot(30, self._enter_edit)
        elif mode == "window":
            QTimer.singleShot(30, self._pick_window_under_cursor)

    # ================================================================ 生命周期
    def begin(self):
        # 必须在首次显示/激活前解绑，否则 TSF 会在激活瞬间注入输入法 DLL
        self._detach_ime()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)
        # 立即识别光标下的窗口，用户一进来就能看到高亮窗口
        QTimer.singleShot(0, self._detect_under_cursor)
        QTimer.singleShot(120, self._detect_under_cursor)

    def _detach_ime(self):
        """解绑输入法上下文，避免 TSF 注入第三方输入法 DLL。"""
        if self._ime_detached:
            return
        try:
            hwnd = int(self.winId())
            self._ime_ctx = detach_ime(hwnd)
            self._ime_detached = True
        except Exception:
            pass

    def closeEvent(self, e):
        if not self._finished:
            self.finish(None)
        e.accept()

    # ================================================================ 绘制
    def paintEvent(self, e):
        if self.shot is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.translate(-self.virtual.topLeft())

        self.shot.paint(p, self.virtual)

        if self.mode == MODE_SELECT:
            self._paint_select(p)
        else:
            self._paint_edit(p)

        p.end()

    # ---------------------------------------------------------- 选择阶段
    def _paint_select(self, p: QPainter):
        alpha = float(config.get("overlay_alpha", 0.45))
        path = QPainterPath()
        path.addRect(QRectF(self.virtual))
        if self.sel_valid and not self.sel.isEmpty():
            path.addRect(QRectF(self.sel))
        p.fillPath(path, QColor(0, 0, 0, int(255 * alpha)))

        # 窗口高亮
        if self.hover_rect and not self.dragging and not self.sel_valid:
            self._paint_window_hover(p)

        if self.sel_valid and not self.sel.isEmpty():
            r = QRectF(self.sel)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(ACCENT, 1))
            p.drawRect(r)

            # 四角加粗
            p.setPen(QPen(ACCENT_LIGHT, 2))
            L = 16
            for cx, cy, dx, dy in (
                (r.left(), r.top(), 1, 1),
                (r.right(), r.top(), -1, 1),
                (r.right(), r.bottom(), -1, -1),
                (r.left(), r.bottom(), 1, -1),
            ):
                p.drawLine(QPointF(cx, cy), QPointF(cx + dx * L, cy))
                p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * L))

            # 手柄
            if self.sel.width() > 24 and self.sel.height() > 24:
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.setBrush(ACCENT)
                for h in self._handle_rects():
                    p.drawRect(h)

            self._paint_size_badge(p)

        if not self.sel_valid:
            self._paint_hint(p)

        if self.sel_valid or self.inside:
            self._paint_crosshair(p)

        if config.get("show_magnifier") and (not self.sel_valid or self.inside):
            self._paint_magnifier(p)

    def _paint_window_hover(self, p: QPainter):
        r = QRectF(self.hover_rect)
        p.setBrush(QColor(47, 111, 235, 38))
        p.setPen(QPen(ACCENT, 2))
        p.drawRect(r)
        if self.hover_title:
            f = QFont("Microsoft YaHei UI", 9)
            p.setFont(f)
            fm = QFontMetricsF(f)
            tw = min(fm.horizontalAdvance(self.hover_title) + 18, r.width() - 4)
            th = 22
            tx = r.left() + 4
            ty = r.top() - th - 6
            if ty < self.virtual.top() + 4:
                ty = r.top() + 6
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(35, 38, 43, 235))
            p.drawRoundedRect(QRectF(tx, ty, tw, th), 4, 4)
            p.setPen(QColor("#F2F3F5"))
            p.drawText(
                QRectF(tx + 9, ty, tw - 12, th),
                Qt.AlignVCenter | Qt.AlignLeft,
                fm.elidedText(self.hover_title, Qt.ElideRight, tw - 14),
            )

    def _paint_size_badge(self, p: QPainter):
        text = f"{self.sel.width()} × {self.sel.height()}"
        f = QFont("Microsoft YaHei UI", 10)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text) + 20
        h = 26
        x = self.sel.left()
        y = self.sel.top() - h - 8
        if y < self.virtual.top() + 4:
            y = self.sel.top() + 8
        if x + w > self.virtual.right():
            x = self.virtual.right() - w - 4
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(35, 38, 43, 238))
        p.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
        p.setPen(QColor("#F2F3F5"))
        p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)

    def _paint_hint(self, p: QPainter):
        text = "拖拽鼠标选择区域　·　双击截取全屏　·　右键 / Esc 退出"
        f = QFont("Microsoft YaHei UI", 10)
        p.setFont(f)
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text) + 34
        h = 34
        cx = self.virtual.center().x()
        y = self.virtual.bottom() - 120
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 30, 34, 215))
        p.drawRoundedRect(QRectF(cx - w / 2, y, w, h), 8, 8)
        p.setPen(QColor("#E8EAED"))
        p.drawText(QRectF(cx - w / 2, y, w, h), Qt.AlignCenter, text)

    def _paint_crosshair(self, p: QPainter):
        c = self.cursor_global
        if not self.inside:
            return
        p.setPen(QPen(QColor(255, 255, 255, 70), 1, Qt.DashLine))
        p.drawLine(QPointF(self.virtual.left(), c.y()), QPointF(self.virtual.right(), c.y()))
        p.drawLine(QPointF(c.x(), self.virtual.top()), QPointF(c.x(), self.virtual.bottom()))

    def _paint_magnifier(self, p: QPainter):
        c = self.cursor_global
        ss = self.shot.screen_at(c.toPoint())
        if ss is None:
            return
        src_r = 14  # 采样半径（物理像素）
        x = int((c.x() - ss.geometry.x()) * ss.dpr)
        y = int((c.y() - ss.geometry.y()) * ss.dpr)
        # 只裁 28×28 的小块，不再为了放大镜缓存整屏 QImage
        crop = ss.sample(x - src_r, y - src_r, 2 * src_r, 2 * src_r)

        zoom_w = 150
        zoom_h = 150
        info_h = 26
        total_h = zoom_h + info_h

        mx = c.x() + 22
        my = c.y() + 22
        if mx + zoom_w > self.virtual.right() - 8:
            mx = c.x() - zoom_w - 22
        if my + total_h > self.virtual.bottom() - 8:
            my = c.y() - total_h - 22
        mx = max(mx, self.virtual.left() + 8)
        my = max(my, self.virtual.top() + 8)

        # 面板
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(24, 26, 30, 240))
        p.drawRoundedRect(QRectF(mx - 3, my - 3, zoom_w + 6, total_h + 6), 7, 7)

        # 放大图
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(QRectF(mx, my, zoom_w, zoom_h), crop)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 像素网格
        step = zoom_w / (2 * src_r)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        for i in range(1, 2 * src_r):
            p.drawLine(QPointF(mx + i * step, my), QPointF(mx + i * step, my + zoom_h))
            p.drawLine(QPointF(mx, my + i * step), QPointF(mx + zoom_w, my + i * step))

        # 中心十字与高亮框
        cx, cy = mx + zoom_w / 2, my + zoom_h / 2
        p.setPen(QPen(QColor("#FF3B30"), 1.4))
        p.drawRect(QRectF(cx - step / 2, cy - step / 2, step, step))

        # 信息栏
        col = self.shot.pixel(c.toPoint())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(col.red(), col.green(), col.blue()))
        p.drawRect(QRectF(mx + 8, my + zoom_h + 6, 14, 14))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(mx + 8, my + zoom_h + 6, 14, 14))

        f = QFont("Consolas", 9)
        p.setFont(f)
        p.setPen(QColor("#E8EAED"))
        info = f"{col.name().upper()}   {int(c.x())},{int(c.y())}"
        p.drawText(
            QRectF(mx + 28, my + zoom_h + 4, zoom_w - 32, 18),
            Qt.AlignVCenter | Qt.AlignLeft,
            info,
        )

    # ---------------------------------------------------------- 编辑阶段
    def _paint_edit(self, p: QPainter):
        alpha = float(config.get("overlay_alpha", 0.45))
        path = QPainterPath()
        path.addRect(QRectF(self.virtual))
        path.addRect(QRectF(self.sel))
        p.fillPath(path, QColor(0, 0, 0, int(255 * alpha)))

        # 选区内容直接从整屏抓图绘制，不再额外缓存一份逻辑分辨率底图
        if self.shot is not None:
            if abs(self.shot.dpr_at(self.sel.center()) - 1.0) > 0.01:
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            self.shot.paint(p, self.sel)

        # 标注（拖拽改变选区时底图还没重算，先不画马赛克，避免取错区域）
        src = None if self._base_dirty else self.base_phys
        p.save()
        p.setClipRect(QRectF(self.sel))
        p.translate(self.sel.topLeft())
        for a in self.annotations:
            draw_annotation(p, a, src, self.mosaic_scale)
        if self.active is not None:
            draw_annotation(p, self.active, src, self.mosaic_scale)

        # 选中图元的虚线框
        if self.selected is not None:
            b = self.selected.bounds().adjusted(-4, -4, 4, 4)
            p.setBrush(Qt.NoBrush)
            pen = QPen(QColor("#2F6FEB"), 1, Qt.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.drawRect(b)
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.setBrush(QColor("#2F6FEB"))
            for hx, hy in (
                (b.left(), b.top()),
                (b.right(), b.top()),
                (b.right(), b.bottom()),
                (b.left(), b.bottom()),
            ):
                p.drawRect(QRectF(hx - 3, hy - 3, 6, 6))
        p.restore()

        # 选区边框
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(ACCENT, 1))
        p.drawRect(QRectF(self.sel))

    # ================================================================ 几何
    def _handle_rects(self) -> list[QRectF]:
        r = QRectF(self.sel)
        cx, cy = r.center().x(), r.center().y()
        pts = [
            (r.left(), r.top()),
            (cx, r.top()),
            (r.right(), r.top()),
            (r.right(), cy),
            (r.right(), r.bottom()),
            (cx, r.bottom()),
            (r.left(), r.bottom()),
            (r.left(), cy),
        ]
        h = HANDLE
        return [QRectF(x - h / 2, y - h / 2, h, h) for x, y in pts]

    def _handle_at(self, pos: QPointF) -> int:
        if not self.sel_valid:
            return -1
        for i, h in enumerate(self._handle_rects()):
            if h.adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return -1

    def _update_cursor_shape(self, pos: QPointF):
        idx = self._handle_at(pos)
        shapes = {
            0: Qt.SizeFDiagCursor,
            1: Qt.SizeVerCursor,
            2: Qt.SizeBDiagCursor,
            3: Qt.SizeHorCursor,
            4: Qt.SizeFDiagCursor,
            5: Qt.SizeVerCursor,
            6: Qt.SizeBDiagCursor,
            7: Qt.SizeHorCursor,
        }
        if idx >= 0:
            self.setCursor(shapes[idx])
        elif self.sel_valid and self.sel.contains(pos.toPoint()):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    # ================================================================ 鼠标
    def mousePressEvent(self, e):
        if self.text_editor is not None:
            # 点回遮罩：先把文字提交掉，这次点击只用于结束输入
            cb = self._text_commit
            if cb is not None:
                cb()
            return
        pos = self.mapToGlobal(e.position())
        self.cursor_global = pos

        if e.button() == Qt.RightButton:
            if self.mode == MODE_EDIT:
                self._show_edit_menu(e.globalPosition().toPoint())
            elif self.sel_valid:
                self.sel = QRect()
                self.sel_valid = False
                self.update()
            else:
                self.finish(None)
            return

        if e.button() != Qt.LeftButton:
            return

        if self.mode == MODE_SELECT:
            idx = self._handle_at(pos)
            if idx >= 0:
                self.dragging = "resize"
                self.resize_idx = idx
                self.drag_origin = pos
                self.sel_origin = QRect(self.sel)
                return
            if self.sel_valid and self.sel.contains(pos.toPoint()):
                self.dragging = "move"
                self.drag_origin = pos
                self.sel_origin = QRect(self.sel)
                return
            self.dragging = "new"
            self.drag_origin = pos
            self.sel = QRect(int(pos.x()), int(pos.y()), 1, 1)
            self.sel_valid = True
            self.update()
            return

        if self.mode == MODE_EDIT:
            idx = self._handle_at(pos)
            if idx >= 0:
                self.dragging = "resize_sel"
                self.resize_idx = idx
                self.drag_origin = pos
                self.sel_origin = QRect(self.sel)
                return
            if not self.sel.contains(pos.toPoint()):
                # 点选区外：重新开始框选（保留原有工具栏，重新框完后刷新）
                self.mode = MODE_SELECT
                self.annotations.clear()
                self.selected = None
                self.active = None
                self.hover_rect = None
                self.dragging = "new"
                self.drag_origin = pos
                self.sel = QRect(int(pos.x()), int(pos.y()), 1, 1)
                self.sel_valid = True
                if self.toolbar is not None:
                    self.toolbar.hide()
                self.setCursor(Qt.CrossCursor)
                self.update()
                return
            local = pos - QPointF(self.sel.topLeft())
            if self.tool == "select":
                hit = self._annotation_at(local)
                if hit is None:
                    # 空白处拖动 = 移动整个选区
                    self.selected = None
                    self.dragging = "move_sel"
                    self.drag_origin = pos
                    self.sel_origin = QRect(self.sel)
                    self.setCursor(Qt.SizeAllCursor)
                    self.update()
                    return
                self._pick_annotation(local, pos)
                return
            self.selected = None
            self._start_draw(pos)

    def mouseMoveEvent(self, e):
        pos = self.mapToGlobal(e.position())
        self.cursor_global = pos
        self.inside = self.rect().contains(e.position().toPoint())

        if self.mode == MODE_SELECT:
            if self.dragging == "new":
                self.sel = QRect(
                    int(min(self.drag_origin.x(), pos.x())),
                    int(min(self.drag_origin.y(), pos.y())),
                    int(abs(pos.x() - self.drag_origin.x())),
                    int(abs(pos.y() - self.drag_origin.y())),
                )
                self.sel_valid = True
                self.update()
                return
            if self.dragging == "move":
                d = pos - self.drag_origin
                r = QRect(self.sel_origin)
                r.translate(int(d.x()), int(d.y()))
                self.sel = self._clamp_to_virtual(r)
                self.update()
                return
            if self.dragging == "resize":
                self.sel = self._resize_rect(self.sel_origin, self.resize_idx, pos)
                self.update()
                return

            self._update_cursor_shape(pos)
            self._maybe_detect_window(pos)
            self.update()
            return

        # 编辑模式
        if self.dragging == "move_sel":
            d = pos - self.drag_origin
            r = QRect(self.sel_origin)
            r.translate(int(d.x()), int(d.y()))
            self.sel = self._clamp_to_virtual(r)
            self._base_dirty = True  # 拖动过程中不重裁底图，松手后再算
            self._place_toolbar()
            self.update()
        elif self.dragging == "resize_sel":
            self.sel = self._resize_rect(self.sel_origin, self.resize_idx, pos)
            self._base_dirty = True
            self._place_toolbar()
            self.update()
        elif self.dragging == "draw" and self.active is not None:
            local = pos - QPointF(self.sel.topLeft())
            self.active.end = local
            if self.active.kind == "pen":
                self.active.points.append(local)
            elif self.active.kind in ("number",):
                pass
            self.update()
        elif self.dragging == "move_ann" and self._drag_ann is not None:
            d = pos - self._drag_ann_start
            self._restore_drag_ann()
            self._drag_ann.translate(d.x(), d.y())
            self.update()
        else:
            in_sel = self.sel.contains(pos.toPoint())
            idx = self._handle_at(pos)
            if idx >= 0:
                shapes = {
                    0: Qt.SizeFDiagCursor,
                    1: Qt.SizeVerCursor,
                    2: Qt.SizeBDiagCursor,
                    3: Qt.SizeHorCursor,
                    4: Qt.SizeFDiagCursor,
                    5: Qt.SizeVerCursor,
                    6: Qt.SizeBDiagCursor,
                    7: Qt.SizeHorCursor,
                }
                self.setCursor(shapes[idx])
            elif self.tool == "select" and in_sel:
                local = pos - QPointF(self.sel.topLeft())
                hit = self._annotation_at(local)
                self.setCursor(Qt.SizeAllCursor if hit is not None else Qt.ArrowCursor)
            else:
                self.setCursor(Qt.CrossCursor)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = self.mapToGlobal(e.position())

        if self.mode == MODE_SELECT:
            if self.dragging == "new":
                self.dragging = None
                small = (
                    abs(pos.x() - self.drag_origin.x()) <= 3
                    and abs(pos.y() - self.drag_origin.y()) <= 3
                ) or self.sel.width() <= 3 or self.sel.height() <= 3
                if small:
                    # 单击（几乎未拖动）：若已识别到窗口，直接截取该窗口
                    target = self.hover_rect
                    if not target or target.isEmpty():
                        res = self._window_rect_at(pos)
                        target = res[0] if res else None
                    if target and not target.isEmpty():
                        self.sel = QRect(target)
                        self.sel_valid = True
                        self.hover_rect = None
                        self._enter_edit()
                        return
                    self.sel = QRect()
                    self.sel_valid = False
                    self.update()
                    return
                self.sel = self._clamp_to_virtual(self.sel)
                self._enter_edit()
                return
            self.dragging = None
            self.update()
            return

        if self.dragging in ("move_sel", "resize_sel"):
            self.dragging = None
            self.sel = self._clamp_to_virtual(self.sel)
            self._refresh_base()
            self._place_toolbar()
            self.update()
            self.setCursor(Qt.CrossCursor)
            return

        if self.dragging == "draw":
            self.dragging = None
            a = self.active
            self.active = None
            if a is not None and not a.is_empty():
                self.annotations.append(a)
                self.redo_stack.clear()
            self.update()
            return

        if self.dragging == "move_ann":
            self.dragging = None
            self._drag_ann = None
            self.update()

    def mouseDoubleClickEvent(self, e):
        pos = self.mapToGlobal(e.position())
        if self.mode == MODE_SELECT:
            self.sel = QRect(self.virtual)
            self.sel_valid = True
            self._enter_edit()
        elif self.mode == MODE_EDIT:
            self.do_copy()

    def wheelEvent(self, e):
        if self.mode == MODE_EDIT and (e.modifiers() & Qt.ControlModifier):
            step = 1 if e.angleDelta().y() > 0 else -1
            self.width = max(1, min(20, self.width + step))
            if self.toolbar:
                self.toolbar.set_width(self.width)
            config["last_width"] = self.width
            e.accept()
            return
        e.ignore()

    # ================================================================ 键盘
    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        mods = e.modifiers()

        if k == Qt.Key_Escape:
            self.finish(None)
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.do_copy()
            return
        if k == Qt.Key_F3:
            self.do_pin()
            return
        if k in (Qt.Key_Delete, Qt.Key_Backspace) and self.mode == MODE_EDIT:
            if self.selected is not None:
                self.delete_selected()
                return

        if mods & Qt.ControlModifier:
            if k == Qt.Key_C:
                self.do_copy()
                return
            if k == Qt.Key_S:
                if mods & Qt.ShiftModifier:
                    self.do_save_as()
                else:
                    self.do_save()
                return
            if k == Qt.Key_Z:
                if mods & Qt.ShiftModifier:
                    self.do_redo()
                else:
                    self.do_undo()
                return
            if k == Qt.Key_Y:
                self.do_redo()
                return
            if k == Qt.Key_A:
                if self.mode == MODE_EDIT and self.annotations:
                    self.select_all_annotations()
                else:
                    self.sel = QRect(self.virtual)
                    self.sel_valid = True
                    self._enter_edit()
                return
            if k == Qt.Key_D and self.mode == MODE_EDIT:
                self.duplicate_selected()
                return
            if k == Qt.Key_B:
                self.do_beautify()
                return
            if k == Qt.Key_O and (mods & Qt.ShiftModifier):
                self.do_ocr()
                return
            if k == Qt.Key_L and (mods & Qt.ShiftModifier):
                self.do_scroll()
                return

        if self.mode == MODE_SELECT:
            if self.sel_valid and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                if mods & Qt.ShiftModifier:
                    self.sel = self._resize_by_keys(k, 1)
                else:
                    dx = -1 if k == Qt.Key_Left else 1 if k == Qt.Key_Right else 0
                    dy = -1 if k == Qt.Key_Up else 1 if k == Qt.Key_Down else 0
                    r = QRect(self.sel)
                    r.translate(dx, dy)
                    self.sel = self._clamp_to_virtual(r)
                self.update()
                return
            return

        # 编辑模式：工具快捷键
        if not (mods & Qt.ControlModifier):
            key_text = e.text().upper()
            for tk, _name, sc in TOOL_DEFS:
                if key_text == sc:
                    self.set_tool(tk)
                    return

    # ================================================================ 图元编辑
    def _annotation_at(self, local: QPointF) -> Annotation | None:
        tol = 6.0
        for a in reversed(self.annotations):
            if a.hit(local, tol):
                return a
        return None

    def _pick_annotation(self, local: QPointF, gpos: QPointF):
        hit = self._annotation_at(local)
        self.selected = hit
        if hit is not None:
            self.dragging = "move_ann"
            self._drag_ann = hit
            self._drag_ann_start = gpos
            self._drag_ann_origin = QPointF(hit.start)
            if self.toolbar:
                self.toolbar.set_color(hit.color.name())
                self.toolbar.set_width(hit.width)
            self.color = hit.color.name()
            self.width = hit.width
        self.update()

    def _restore_drag_ann(self) -> None:
        if self._drag_ann is None:
            return
        cur = QPointF(self._drag_ann.start)
        d = cur - self._drag_ann_origin
        self._drag_ann.translate(-d.x(), -d.y())

    def delete_selected(self):
        if self.selected is None:
            return
        try:
            self.annotations.remove(self.selected)
        except ValueError:
            pass
        self.redo_stack.append(self.selected)
        self.selected = None
        self.update()

    def apply_selected_style(self):
        a = self.selected
        if a is None:
            return
        a.color = QColor(self.color)
        a.width = max(1, int(self.width))
        self.update()

    def duplicate_selected(self):
        if self.selected is None:
            return
        c = self.selected.clone()
        c.translate(12, 12)
        self.annotations.append(c)
        self.redo_stack.clear()
        self.selected = c
        self.update()

    def select_all_annotations(self):
        """选中最新（最上层）图元；编辑模式下 Ctrl+A 的快捷键入口。"""
        if not self.annotations:
            return
        top = self.annotations[-1]
        self.selected = top
        self.dragging = None
        self._drag_ann = None
        if self.toolbar:
            self.toolbar.set_color(top.color.name())
            self.toolbar.set_width(top.width)
        self.color = top.color.name()
        self.width = top.width
        self.update()

    # ================================================================ 选区操作
    def _resize_rect(self, base: QRect, idx: int, pos: QPointF) -> QRect:
        r = QRectF(base)
        x, y = pos.x(), pos.y()
        if idx in (0, 1, 2):
            r.setTop(min(y, r.bottom() - 4))
        if idx in (4, 5, 6):
            r.setBottom(max(y, r.top() + 4))
        if idx in (0, 6, 7):
            r.setLeft(min(x, r.right() - 4))
        if idx in (2, 3, 4):
            r.setRight(max(x, r.left() + 4))
        return self._clamp_to_virtual(r.toRect())

    def _resize_by_keys(self, key, step: int) -> QRect:
        r = QRectF(self.sel)
        if key == Qt.Key_Left:
            r.setWidth(max(8, r.width() - step))
        elif key == Qt.Key_Right:
            r.setWidth(r.width() + step)
        elif key == Qt.Key_Up:
            r.setHeight(max(8, r.height() - step))
        elif key == Qt.Key_Down:
            r.setHeight(r.height() + step)
        return self._clamp_to_virtual(r.toRect())

    def _clamp_to_virtual(self, r: QRect) -> QRect:
        v = self.virtual
        r = r.normalized()
        inter = r.intersected(v)
        if inter.isEmpty():
            return r
        return inter

    def _window_rect_at(self, pos: QPointF) -> tuple[QRect, str] | None:
        """返回鼠标位置下的窗口（逻辑坐标，已裁到虚拟桌面范围）。"""
        if self.detector is None:
            return None
        ss = self.shot.screen_at(pos.toPoint())
        dpr = ss.dpr if ss else 1.0
        try:
            res = self.detector.window_at(int(pos.x() * dpr), int(pos.y() * dpr))
        except Exception:
            return None
        if not res:
            return None
        rect = phys_to_logical(res[0], dpr).intersected(self.virtual)
        if rect.isEmpty():
            return None
        return rect, res[1]

    def _maybe_detect_window(self, pos: QPointF):
        if self.detector is None or self.sel_valid:
            return
        now = time.time()
        if now - self._last_detect < 0.04:
            return
        self._last_detect = now
        res = self._window_rect_at(pos)
        if res:
            rect, title = res
            if rect != self.hover_rect:
                self.hover_rect = rect
                self.hover_title = title
                self.update()
        elif self.hover_rect is not None:
            self.hover_rect = None
            self.hover_title = ""
            self.update()

    def _detect_under_cursor(self):
        """截图界面刚出现时立即识别光标下的窗口，无需先移动鼠标。"""
        if self.mode != MODE_SELECT or self.sel_valid or self.detector is None:
            return
        pos = QCursor.pos()
        if not self.virtual.contains(pos):
            return
        self._last_detect = 0.0
        self._maybe_detect_window(QPointF(pos))

    def _pick_window_under_cursor(self):
        pos = QCursor.pos()
        res = self._window_rect_at(QPointF(pos))
        if res:
            self.sel = res[0]
            self.sel_valid = True
            self._enter_edit()
            return
        self.sel = QRect(self.virtual)
        self.sel_valid = True
        self._enter_edit()

    # ================================================================ 进入编辑
    def _enter_edit(self):
        if self.sel.width() < 2 or self.sel.height() < 2:
            return
        self.mode = MODE_EDIT
        self.dragging = None
        self.hover_rect = None

        self._refresh_base()

        if self.toolbar is None:
            self.toolbar = ToolBar(self)
            self.toolbar.toolChanged.connect(self.set_tool)
            self.toolbar.colorChanged.connect(self._on_color)
            self.toolbar.widthChanged.connect(self._on_width)
            self.toolbar.undoRequested.connect(self.do_undo)
            self.toolbar.redoRequested.connect(self.do_redo)
            self.toolbar.copyRequested.connect(self.do_copy)
            self.toolbar.saveRequested.connect(self.do_save)
            self.toolbar.pinRequested.connect(self.do_pin)
            self.toolbar.ocrRequested.connect(self.do_ocr)
            self.toolbar.scrollRequested.connect(self.do_scroll)
            self.toolbar.beautifyRequested.connect(self.do_beautify)
            self.toolbar.closeRequested.connect(lambda: self.finish(None))
            self.toolbar.set_tool(self.tool)
            self.toolbar.set_color(self.color)
            self.toolbar.set_width(self.width)
        self.toolbar.show()
        self._place_toolbar()
        # 进入编辑先给“指针”状态：可直接拖动选区、点选图元；
        # 需要画标注时再点工具（与主流截图工具一致）
        self.tool = "select"
        self.toolbar.set_tool("select")
        self.setCursor(Qt.ArrowCursor)
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def _refresh_base(self):
        """按当前选区重新裁切底图（移动 / 缩放选区后调用）。

        只保留一份物理分辨率 QImage：既用于马赛克取样，也是最终输出源。
        显示时直接复用整屏抓图，省掉 QPixmap + 逻辑分辨率 QImage 两份副本。
        """
        if self.sel.width() < 2 or self.sel.height() < 2 or self.shot is None:
            return
        crop_image = getattr(self.shot, "crop_image", None)
        if crop_image is not None:
            self.base_phys = crop_image(self.sel)
        else:  # 兼容测试桩
            self.base_phys = self.shot.crop(self.sel).toImage()
        self.base_pixmap = None
        self.base_image = None
        self.mosaic_scale = (
            self.base_phys.width() / max(1, self.sel.width())
            if self.base_phys.width()
            else 1.0
        )
        self._base_dirty = False

    def _place_toolbar(self):
        tb = self.toolbar
        if tb is None:
            return
        tb.adjustSize()
        w, h = tb.width(), tb.height()
        v = self.virtual
        x = self.sel.center().x() - w // 2
        y = self.sel.bottom() + 12
        if y + h > v.bottom() - 8:
            y = self.sel.top() - h - 12
        if y < v.top() + 8:
            y = min(self.sel.bottom() - h - 8, v.bottom() - h - 8)
            y = max(y, v.top() + 8)
        x = max(v.left() + 8, min(x, v.right() - w - 8))
        tb.move(x - v.left(), y - v.top())
        tb.raise_()

    # ================================================================ 绘制标注
    def _start_draw(self, pos: QPointF):
        local = pos - QPointF(self.sel.topLeft())
        if self.tool == "text":
            # 刚才那次点击是用来“结束上一段文字”的，别再弹一个新编辑框
            if time.time() - self._text_committed_at < 0.3:
                return
            self._open_text_editor(local)
            return
        a = Annotation(self.tool, local, self.color, self.width)
        if self.tool == "number":
            self.number_counter = sum(
                1 for x in self.annotations if x.kind == "number"
            ) + 1
            a.number = self.number_counter
            a.end = local
            self.annotations.append(a)
            self.redo_stack.clear()
            self.update()
            return
        self.active = a
        self.dragging = "draw"

    def _open_text_editor(self, local: QPointF):
        from PySide6.QtGui import QTextOption
        from PySide6.QtWidgets import QTextEdit

        if self.text_editor is not None:
            return
        # 必须是独立顶层窗口：遮罩在 begin() 里解绑了输入法上下文（省内存），
        # 子控件与遮罩共用同一个 HWND，TSF 输入法会整体失效——中文打不进去。
        # 顶层窗口有自己的 HWND，输入法正常工作。
        ed = QTextEdit()
        ed.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        ed.setAttribute(Qt.WA_InputMethodEnabled, True)
        ed.setAcceptRichText(False)
        ed.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        ed.setStyleSheet(
            "QTextEdit{background:#23262B;color:#FFFFFF;border:1.5px solid #2F6FEB;"
            "border-radius:4px;padding:3px 6px;font-size:14px;}"
        )
        size = max(12, int(self.width * 4.5))
        ed.setFont(QFont("Microsoft YaHei UI", size))
        ed.setMinimumSize(200, 56)
        ed.resize(280, 72)
        # 顶层窗口用屏幕坐标（sel 本身就是全局逻辑坐标）
        ed.move(int(self.sel.x() + local.x()), int(self.sel.y() + local.y()))
        ed.show()
        ed.raise_()
        ed.activateWindow()
        ed.setFocus()
        try:
            attach_ime(int(ed.winId()), None)
        except Exception:
            pass
        self.text_editor = ed
        state = {"done": False}

        def _drop_editor():
            self._text_committed_at = time.time()
            self._text_commit = None
            self._text_cancel = None
            ed.deleteLater()
            self.text_editor = None
            flt = getattr(self, "_text_filter", None)
            if flt is not None:
                try:
                    flt.deleteLater()
                except Exception:
                    pass
                self._text_filter = None

        def commit():
            if state["done"]:
                return
            state["done"] = True
            txt = ed.toPlainText().rstrip()
            if txt.strip():
                a = Annotation("text", local, self.color, self.width)
                a.text = txt
                self.annotations.append(a)
                self.redo_stack.clear()
            _drop_editor()
            self.activateWindow()
            self.setFocus(Qt.OtherFocusReason)
            self.update()

        def cancel():
            if state["done"]:
                return
            state["done"] = True
            _drop_editor()
            self.activateWindow()
            self.setFocus(Qt.OtherFocusReason)
            self.update()

        class _Filter(QObject):
            def eventFilter(self, obj, ev):
                # 注意：不要用 WindowDeactivate 提交——中文输入法弹候选窗时
                # 也可能让编辑框短暂失活，会把正在打的字提前提交掉。
                if ev.type() == QEvent.KeyPress:
                    key = ev.key()
                    if key == Qt.Key_Escape:
                        cancel()
                        return True
                    if key in (Qt.Key_Return, Qt.Key_Enter) and not (
                        ev.modifiers() & Qt.ShiftModifier
                    ):
                        commit()
                        return True
                return False

        self._text_filter = _Filter(self)
        ed.installEventFilter(self._text_filter)
        # 点到别处 / 换工具 / 输出成品前，先把编辑框里的字提交掉
        self._text_commit = commit
        self._text_cancel = cancel

    def set_tool(self, key: str):
        if self.text_editor is not None:
            cb = self._text_commit
            if cb is not None:
                cb()
        self.tool = key
        if self.toolbar:
            self.toolbar.set_tool(key)
        config["last_tool"] = key

    def _on_color(self, c: str):
        self.color = c
        config["last_color"] = c

    def _on_width(self, w: int):
        self.width = w
        config["last_width"] = w

    def do_undo(self):
        if self.annotations:
            a = self.annotations.pop()
            self.redo_stack.append(a)
            self.update()

    def do_redo(self):
        if self.redo_stack:
            a = self.redo_stack.pop()
            self.annotations.append(a)
            self.update()

    # ================================================================ 输出
    def render(self) -> QPixmap:
        """输出物理分辨率成品图"""
        if self.text_editor is not None:
            cb = self._text_commit
            if cb is not None:
                cb()
        if self.mode != MODE_EDIT:
            if self.sel_valid:
                return self.shot.crop(self.sel)
            return QPixmap()
        if self._base_dirty:
            # 拖拽中按了 Enter 之类的场景：先把底图补上再输出
            self._refresh_base()
        if self.base_phys is None:
            return QPixmap()
        out = QPixmap(self.base_phys.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(0, 0, self.base_phys)
        p.scale(self.mosaic_scale, self.mosaic_scale)
        for a in self.annotations:
            draw_annotation(p, a, self.base_phys, self.mosaic_scale)
        p.end()
        out.setDevicePixelRatio(1.0)
        return out

    def do_copy(self):
        pm = self.render()
        if pm.isNull():
            return
        QApplication.clipboard().setPixmap(pm)
        self.copiedToClipboard.emit(pm)
        self.finish(None)

    def do_save(self):
        pm = self.render()
        if pm.isNull():
            return
        path = self._save_path()
        fmt = config.get("image_format", "png")
        if fmt == "jpg":
            ok = pm.save(path, "JPG", int(config.get("jpg_quality", 95)))
        else:
            ok = pm.save(path, "PNG")
        if ok:
            if config.get("auto_copy"):
                QApplication.clipboard().setPixmap(pm)
            self.savedTo.emit(path)
            self.finish(None)
        else:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "保存失败", f"无法写入文件：\n{path}")

    # ------------------------------------------------------------- 图片美化
    def do_beautify(self):
        if not self.sel_valid or self.sel.width() < 4 or self.sel.height() < 4:
            return
        from .beautify import BeautifyDialog

        pm = self.render()
        if pm.isNull():
            return
        if getattr(self, "_beautify_dlg", None) is not None:
            return
        dlg = BeautifyDialog(pm, self)
        dlg.pinRequested.connect(self.pinRequested.emit)
        self._beautify_dlg = dlg

        def _beautify_done(*_):
            self._beautify_dlg = None
            dlg.deleteLater()  # 关闭后立刻释放预览用的全尺寸位图

        dlg.finished.connect(_beautify_done)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ------------------------------------------------------------- 识别文字
    def do_ocr(self):
        if not self.sel_valid or self.sel.width() < 4 or self.sel.height() < 4:
            return
        from . import ocr

        if not ocr.available():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "无法识别",
                "系统未提供 Windows OCR 引擎。\n请在“设置 → 时间和语言 → 语言”中安装语言包。",
            )
            return

        from .panels import OcrDialog, OcrWorker, Toast

        if getattr(self, "_ocr_worker", None) is not None:
            return
        image = self.render().toImage()

        toast = Toast("正在识别文字（约需 3~6 秒）…", self)
        toast.show_centered(0, self.virtual)
        self._ocr_toast = toast

        worker = OcrWorker(image, self)
        self._ocr_worker = worker

        def on_done(ok: bool, text: str, err: str):
            try:
                toast.close()
                toast.deleteLater()
            except Exception:
                pass
            self._ocr_worker = None
            dlg = OcrDialog(text, "" if ok else err, self)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

        worker.done.connect(on_done)
        worker.start()

    # ------------------------------------------------------------- 滚动长截图
    def do_scroll(self):
        if not self.sel_valid or self.sel.width() < 8 or self.sel.height() < 8:
            return
        if self.text_editor is not None:
            cb = self._text_commit
            if cb is not None:
                cb()
        from PySide6.QtCore import QThread, Signal

        from .panels import LongShotPreview, Toast

        rect = QRect(self.sel)

        class _ScrollWorker(QThread):
            finished_ok = Signal(object, str)

            def run(self):
                import ctypes

                from . import longshot

                def esc_down() -> bool:
                    try:
                        return bool(
                            ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000
                        )
                    except Exception:
                        return False

                try:
                    img, info = longshot.capture_scrolling(
                        rect, on_frame=None, should_stop=esc_down
                    )
                    if esc_down() and img is not None and not img.isNull():
                        info = (info + "（已手动结束）").strip()
                except Exception as ex:  # pragma: no cover - 防御
                    img, info = None, f"滚动截图失败：{ex}"
                self.finished_ok.emit(img, info)

        if getattr(self, "_scroll_worker", None) is not None:
            return

        toast = Toast("正在滚动截取…按 Esc 可提前结束", self)
        toast.show_centered(0, self.virtual)
        self._scroll_toast = toast
        self.hide()

        worker = _ScrollWorker(self)
        self._scroll_worker = worker

        def on_done(img, info: str):
            self._scroll_worker = None
            try:
                toast.close()
            except Exception:
                pass
            if img is None or img.isNull() or img.height() <= 0:
                self.show()
                self.raise_()
                self.activateWindow()
                t = Toast(info or "未获取到内容", self)
                t.show_centered(2000, self.virtual)
                self._scroll_toast = t
                return
            pv = LongShotPreview(img, info)
            pv.show()
            pv.raise_()
            pv.activateWindow()
            self._longshot_preview = pv
            self.finish(None)

        worker.finished_ok.connect(on_done)
        worker.start()


    def do_save_as(self):
        from PySide6.QtWidgets import QFileDialog

        pm = self.render()
        if pm.isNull():
            return
        fmt = config.get("image_format", "png")
        ext = ".jpg" if fmt == "jpg" else ".png"
        d = config.get("save_dir")
        default = os.path.join(d, "截图_" + time.strftime("%Y%m%d_%H%M%S") + ext)
        filt = "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        path, _ = QFileDialog.getSaveFileName(self, "另存为", default, filt)
        if not path:
            return
        if path.lower().endswith((".jpg", ".jpeg")):
            ok = pm.save(path, "JPG", int(config.get("jpg_quality", 95)))
        else:
            ok = pm.save(path, "PNG")
        if ok:
            if config.get("auto_copy"):
                QApplication.clipboard().setPixmap(pm)
            self.savedTo.emit(path)
            self.finish(None)

    def _show_edit_menu(self, gpos: QPoint):
        from PySide6.QtWidgets import QMenu

        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#23262B;color:#E8EAED;border:1px solid #3A3F46;"
            "border-radius:7px;padding:5px;}"
            "QMenu::item{padding:6px 24px;border-radius:4px;font-size:13px;}"
            "QMenu::item:selected{background:#2F6FEB;}"
            "QMenu::separator{height:1px;background:#3A3F46;margin:4px 8px;}"
        )
        m.addAction("复制到剪贴板\tEnter", self.do_copy)
        m.addAction("保存\tCtrl+S", self.do_save)
        m.addAction("另存为…\tCtrl+Shift+S", self.do_save_as)
        m.addAction("贴图到屏幕\tF3", self.do_pin)
        m.addSeparator()
        m.addAction("撤销\tCtrl+Z", self.do_undo)
        m.addAction("重做\tCtrl+Y", self.do_redo)
        m.addSeparator()
        m.addAction("取消截图\tEsc", lambda: self.finish(None))
        m.exec(gpos)

    def _save_path(self) -> str:
        d = config.get("save_dir")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            d = os.path.expanduser("~")
        pattern = config.get("filename_pattern", "Jietu_{date}_{time}")
        now = time.localtime()
        try:
            name = pattern.format(
                date=time.strftime("%Y%m%d", now), time=time.strftime("%H%M%S", now)
            )
        except Exception:
            name = "Jietu_" + time.strftime("%Y%m%d_%H%M%S", now)
        if not name.strip():
            name = "Jietu_" + time.strftime("%Y%m%d_%H%M%S", now)
        name = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "Jietu"
        fmt = config.get("image_format", "png")
        ext = "jpg" if fmt == "jpg" else "png"
        path = os.path.join(d, f"{name}.{ext}")
        i = 1
        while os.path.exists(path):
            path = os.path.join(d, f"{name}_{i}.{ext}")
            i += 1
        return path

    def do_pin(self):
        pm = self.render()
        if pm.isNull():
            return
        self.pinRequested.emit(pm)
        self.finish(None)

    def finish(self, _=None):
        if self._finished:
            return
        self._finished = True
        try:
            ed = self.text_editor
            self.text_editor = None
            if ed is not None:
                flt = getattr(self, "_text_filter", None)
                if flt is not None:
                    try:
                        ed.removeEventFilter(flt)
                        flt.deleteLater()
                    except Exception:
                        pass
                    self._text_filter = None
                ed.hide()
                ed.close()
                ed.deleteLater()
        except Exception:
            pass
        try:
            if self.toolbar is not None:
                tb = self.toolbar
                self.toolbar = None
                tb.hide()
                tb.setParent(None)
                tb.deleteLater()
        except Exception:
            pass
        # 释放整屏位图与中间缩放图，避免窗口销毁前继续占用内存
        self.annotations.clear()
        self.redo_stack.clear()
        self.active = None
        self.base_pixmap = None
        self.base_image = None
        self.base_phys = None
        shot, self.shot = self.shot, None
        if shot is not None:
            try:
                shot.release()  # 立即归还各屏整屏位图，不等 GC
            except Exception:
                pass
        self.detector = None
        self.hide()
        try:
            self.closed.emit()
        except Exception:
            pass
        self.deleteLater()
