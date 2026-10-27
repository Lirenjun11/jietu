"""贴图窗口：把截图钉在屏幕上，可拖动、缩放、调透明度。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QWidget

from .config import config

PAD = 10


class PinWindow(QWidget):
    closed = Signal(object)

    def __init__(self, pixmap: QPixmap, pos: QPoint | None = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("拖动移动 · 滚轮缩放 · 双击关闭 · 右键更多")

        self.pm = pixmap
        scr0 = QGuiApplication.screenAt(pos or QCursor.pos()) or QGuiApplication.primaryScreen()
        self.dpr = float(scr0.devicePixelRatio()) or 1.0
        self.base = QSize(pixmap.width(), pixmap.height())
        self.scale = 1.0 / self.dpr
        self.opacity_level = 1.0
        self.card = False
        self.radius = 12
        self._drag_off: QPoint | None = None
        self._resize_edge = ""
        self._resize_start: tuple[QPoint, float] | None = None

        scr = QGuiApplication.screenAt(pos or QCursor.pos()) or QGuiApplication.primaryScreen()
        avail = scr.availableGeometry()
        self._apply_size()
        w, h = self.width(), self.height()
        if pos is None:
            pos = QPoint(
                avail.center().x() - w // 2 + 30,
                avail.center().y() - h // 2 + 30,
            )
        self.move(pos)
        self._avail = avail

    # ------------------------------------------------------------------
    def _apply_size(self):
        w = max(20, int(self.base.width() * self.scale))
        h = max(20, int(self.base.height() * self.scale))
        if self.card:
            w += PAD * 2
            h += PAD * 2
        self.setFixedSize(w, h)

    def _image_rect(self) -> QRect:
        return self.rect().adjusted(PAD, PAD, -PAD, -PAD) if self.card else self.rect()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        target = self._image_rect()
        if self.card:
            for i in range(PAD, 0, -1):
                alpha = int(10 + (PAD - i) * 5)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, alpha))
                p.drawRoundedRect(
                    QRectF(self.rect()).adjusted(i, i, -i + 1, -i + 1),
                    self.radius + i,
                    self.radius + i,
                )
            path = QPainterPath()
            path.addRoundedRect(QRectF(target), self.radius, self.radius)
            p.save()
            p.setClipPath(path)
            p.drawPixmap(target, self.pm)
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(target).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)
        else:
            p.drawPixmap(target, self.pm)
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # ------------------------------------------------------------------
    def _edge_at(self, pos: QPoint) -> str:
        m = 9
        r = self.rect()
        edge = ""
        if pos.x() <= m:
            edge += "l"
        elif pos.x() >= r.width() - m:
            edge += "r"
        if pos.y() <= m:
            edge += "t"
        elif pos.y() >= r.height() - m:
            edge += "b"
        return edge

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edge = self._edge_at(e.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start = (e.globalPosition().toPoint(), self.scale)
                self.setCursor(
                    Qt.SizeFDiagCursor
                    if edge in ("tl", "br")
                    else Qt.SizeBDiagCursor
                    if edge in ("tr", "bl")
                    else Qt.SizeHorCursor
                    if edge in ("l", "r")
                    else Qt.SizeVerCursor
                )
                e.accept()
                return
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._resize_start is not None and e.buttons() & Qt.LeftButton:
            start, base_scale = self._resize_start
            delta = e.globalPosition().toPoint() - start
            dx = delta.x() if "r" in self._resize_edge else -delta.x() if "l" in self._resize_edge else 0
            dy = delta.y() if "b" in self._resize_edge else -delta.y() if "t" in self._resize_edge else 0
            ref = max(self.base.width(), self.base.height()) or 1
            factor = base_scale * (1.0 + (dx + dy) / (ref * 1.6))
            new = max(0.05, min(8.0, factor))
            if not (e.modifiers() & Qt.ShiftModifier):
                self.scale = new
            self._apply_size()
            e.accept()
            return
        if self._drag_off is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_off)
            e.accept()
            return
        edge = self._edge_at(pos)
        if edge:
            self.setCursor(
                Qt.SizeFDiagCursor
                if edge in ("tl", "br")
                else Qt.SizeBDiagCursor
                if edge in ("tr", "bl")
                else Qt.SizeHorCursor
                if edge in ("l", "r")
                else Qt.SizeVerCursor
            )
        else:
            self.setCursor(Qt.OpenHandCursor)

    def mouseReleaseEvent(self, e):
        self._drag_off = None
        self._resize_edge = ""
        self._resize_start = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.close()

    def wheelEvent(self, e):
        step = 1.12 if e.angleDelta().y() > 0 else 1 / 1.12
        new = self.scale * step
        if 0.05 <= new <= 8.0:
            self.scale = new
            self._apply_size()
        e.accept()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#23262B;color:#E8EAED;border:1px solid #3A3F46;"
            "border-radius:6px;padding:4px;}"
            "QMenu::item{padding:6px 22px;border-radius:4px;}"
            "QMenu::item:selected{background:#2F6FEB;}"
            "QMenu::separator{height:1px;background:#3A3F46;margin:4px 8px;}"
        )
        m.addAction("复制到剪贴板", self._copy)
        m.addAction("另存为…", self._save_as)
        m.addSeparator()
        card = m.addAction("圆角阴影边框")
        card.setCheckable(True)
        card.setChecked(self.card)
        card.triggered.connect(self._toggle_card)
        sub = m.addMenu("不透明度")
        for label, v in (("100%", 1.0), ("80%", 0.8), ("60%", 0.6), ("40%", 0.4)):
            a = sub.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(self.opacity_level - v) < 0.01)
            a.triggered.connect(lambda _=False, vv=v: self._set_opacity(vv))
        sub2 = m.addMenu("缩放")
        for label, f in (("原始大小", 1.0), ("50%", 0.5), ("200%", 2.0), ("适应屏幕", -1)):
            a = sub2.addAction(label)
            a.triggered.connect(lambda _=False, ff=f: self._zoom_to(ff))
        m.addSeparator()
        act_top = m.addAction("始终置顶")
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        act_top.triggered.connect(self._toggle_top)
        m.addAction("关闭", self.close)
        m.exec(e.globalPos())

    # ------------------------------------------------------------------
    def _copy(self):
        QApplication.clipboard().setPixmap(self.pm)

    def _save_as(self):
        d = config.get("save_dir")
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", d + "/pin.png", "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if path:
            if path.lower().endswith((".jpg", ".jpeg")):
                self.pm.save(path, "JPG", 95)
            else:
                self.pm.save(path, "PNG")

    def _set_opacity(self, v: float):
        self.opacity_level = v
        self.setWindowOpacity(v)

    def _toggle_card(self):
        self.card = not self.card
        self._apply_size()
        self.update()

    def _zoom_to(self, f: float):
        if f < 0:
            scr = QGuiApplication.screenAt(self.frameGeometry().center())
            avail = (scr or QGuiApplication.primaryScreen()).availableGeometry()
            f = min(
                (avail.width() * 0.85) / max(1, self.base.width()),
                (avail.height() * 0.85) / max(1, self.base.height()),
            )
        self.scale = f
        self._apply_size()

    def _toggle_top(self):
        flags = self.windowFlags()
        if flags & Qt.WindowStaysOnTopHint:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        self.show()

    def closeEvent(self, e):
        self.closed.emit(self)
        # 贴图窗口关闭后立刻释放原图，避免多张贴图把内存堆高
        self.pm = QPixmap()
        super().closeEvent(e)
