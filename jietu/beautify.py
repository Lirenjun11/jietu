"""图片美化：加内边距、圆角、投影与背景，可预览后复制/保存/贴图。"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from .config import config

QSS = """
QDialog { background: #23262B; }
QLabel { color: #C9CDD3; font-size: 12px; }
QLabel#title { color: #E8EAED; font-size: 14px; font-weight: 600; }
QComboBox, QSpinBox {
    background: #2C3037; color: #D5D9DF; border: 1px solid #3A3F46;
    border-radius: 6px; padding: 4px 8px; font-size: 13px;
}
QCheckBox { color: #D5D9DF; font-size: 13px; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #4A5058; background: #2C3037; }
QCheckBox::indicator:checked { background: #2F6FEB; border: 1px solid #2F6FEB; }
QSlider::groove:horizontal { height: 4px; background: #3A3F46; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -6px 0;
    border-radius: 7px; background: #2F6FEB; }
QPushButton { background: #2C3037; color: #C9CDD3; border: none;
    border-radius: 6px; padding: 6px 14px; font-size: 13px; }
QPushButton:hover { background: #383D45; }
QPushButton#primary { background: #2F6FEB; color: #FFFFFF; }
QPushButton#primary:hover { background: #3B7BF5; }
"""

BACKGROUNDS = [
    ("纯白", ("#FFFFFF", "#FFFFFF")),
    ("浅灰", ("#F2F4F7", "#DDE3EA")),
    ("日落", ("#FF7A45", "#FF3B7B")),
    ("海洋", ("#2E86C1", "#8E44FF")),
    ("森林", ("#34C759", "#0E7C66")),
    ("深色", ("#23262B", "#111318")),
]


def beautify(
    src: QPixmap,
    pad: int = 28,
    radius: int = 14,
    shadow: bool = True,
    background: tuple[str, str] = ("#FFFFFF", "#FFFFFF"),
    bg_scale_max: float = 1.6,
) -> QPixmap:
    """给截图套一层卡片式背景。"""
    if src.isNull():
        return src
    sw, sh = src.width(), src.height()
    out_w = sw + pad * 2
    out_h = sh + pad * 2 + (pad if shadow else 0)

    img = QImage(out_w, out_h, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    card = QRectF(pad, pad, sw, sh)

    if shadow:
        for i in range(pad, 0, -1):
            alpha = int(9 + (pad - i) * 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, min(alpha, 70)))
            p.drawRoundedRect(
                card.adjusted(i, i + 2, -i, -i + 2), radius + i, radius + i
            )

    c1, c2 = background
    if c1 or c2:
        g = QLinearGradient(QPointF(0, 0), QPointF(out_w, out_h))
        g.setColorAt(0, QColor(c1))
        g.setColorAt(1, QColor(c2))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(card.adjusted(-pad + 6, -pad + 6, pad - 6, pad - 6), radius + 8, radius + 8)

    path = QPainterPath()
    path.addRoundedRect(card, radius, radius)
    p.save()
    p.setClipPath(path)
    p.drawPixmap(card.toRect(), src)
    p.restore()
    if radius:
        p.setPen(QColor(0, 0, 0, 26))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.end()
    return QPixmap.fromImage(img)


class BeautifyDialog(QDialog):
    pinRequested = Signal(QPixmap)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.src = pixmap
        # 成品图缓存：只有参数变化才重算，缩放窗口只重新缩放预览，
        # 避免每次 resize / 拖动滑块都生成一张全尺寸大图。
        self._cache: QPixmap | None = None
        self.setWindowTitle("图片美化")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("图片美化")
        title.setObjectName("title")
        root.addWidget(title)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(360, 220)
        self.preview.setStyleSheet(
            "background:#17191D;border:1px solid #3A3F46;border-radius:8px;padding:6px;"
        )
        root.addWidget(self.preview, 1)

        from PySide6.QtWidgets import QFormLayout, QSpinBox

        form = QFormLayout()
        form.setSpacing(8)

        self.bg = QComboBox()
        for name, _ in BACKGROUNDS:
            self.bg.addItem(name)
        form.addRow("背景", self.bg)

        self.pad = QSlider(Qt.Horizontal)
        self.pad.setRange(0, 120)
        self.pad.setValue(28)
        form.addRow("留白", self.pad)

        self.radius = QSlider(Qt.Horizontal)
        self.radius.setRange(0, 48)
        self.radius.setValue(14)
        form.addRow("圆角", self.radius)
        root.addLayout(form)

        self.chk_shadow = QCheckBox("添加投影")
        self.chk_shadow.setChecked(True)
        root.addWidget(self.chk_shadow)

        row = QHBoxLayout()
        row.addStretch(1)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("另存为…")
        save_btn.clicked.connect(self._save_as)
        pin_btn = QPushButton("贴图")
        pin_btn.clicked.connect(self._pin)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        for b in (copy_btn, save_btn, pin_btn, close_btn):
            row.addWidget(b)
        root.addLayout(row)

        for w in (self.pad, self.radius):
            w.valueChanged.connect(self._on_params_changed)
        self.bg.currentIndexChanged.connect(self._on_params_changed)
        self.chk_shadow.toggled.connect(self._on_params_changed)
        self._update_preview()

    def result_pixmap(self) -> QPixmap:
        if self._cache is None:
            c1, c2 = BACKGROUNDS[self.bg.currentIndex()][1]
            self._cache = beautify(
                self.src,
                pad=self.pad.value(),
                radius=self.radius.value(),
                shadow=self.chk_shadow.isChecked(),
                background=(c1, c2),
            )
        return self._cache

    def _on_params_changed(self, *_):
        self._cache = None
        self._update_preview()

    def _update_preview(self):
        pm = self.result_pixmap()
        if pm.isNull():
            return
        self.preview.setPixmap(
            pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def refresh(self):
        self._on_params_changed()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_preview()

    def _copy(self):
        QApplication.clipboard().setPixmap(self.result_pixmap())

    def _save_as(self):
        d = config.get("save_dir")
        name = "beautify_" + time.strftime("%Y%m%d_%H%M%S") + ".png"
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", os.path.join(d, name), "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if not path:
            return
        pm = self.result_pixmap()
        if path.lower().endswith((".jpg", ".jpeg")):
            pm.save(path, "JPG", 95)
        else:
            pm.save(path, "PNG")

    def _pin(self):
        self.pinRequested.emit(self.result_pixmap())