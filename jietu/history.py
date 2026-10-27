"""截图历史记录：保存缩略图索引并提供浏览/复制/贴图/删除。"""
from __future__ import annotations

import os
import shutil
import time

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from . import config as config_mod
from .config import config

PANEL_QSS = """
QDialog { background: #23262B; }
QLabel#title { color: #E8EAED; font-size: 14px; font-weight: 600; }
QLabel#info { color: #9AA0A6; font-size: 12px; }
QListWidget {
    background: #1B1E22; border: 1px solid #3A3F46; border-radius: 8px;
    color: #C9CDD3; font-size: 12px;
}
QListWidget::item { margin: 4px; border-radius: 6px; }
QListWidget::item:selected { background: #2F6FEB; color: #FFFFFF; }
QPushButton {
    background: #2C3037; color: #C9CDD3; border: none; border-radius: 6px;
    padding: 6px 14px; font-size: 13px;
}
QPushButton:hover { background: #383D45; }
QPushButton#primary { background: #2F6FEB; color: #FFFFFF; }
QPushButton#primary:hover { background: #3B7BF5; }
"""


class HistoryStore:
    """把截图写入历史目录，并在超过上限时清理旧文件。"""

    def __init__(self, root: str | None = None):
        self.root = root or str(config_mod.app_data_dir() / "history")
        os.makedirs(self.root, exist_ok=True)

    def add(self, pixmap: QPixmap, source_path: str | None = None) -> str | None:
        if pixmap.isNull():
            return None
        try:
            name = "shot_" + time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time()*1000)%1000:03d}.png"
            path = os.path.join(self.root, name)
            if not pixmap.save(path, "PNG"):
                return None
            self.prune()
            return path
        except Exception:
            return None

    def add_file(self, path: str) -> str | None:
        """直接复制文件进历史目录。

        旧实现先 QPixmap(path) 解码整图再重新编码 PNG，一张 4K 截图就要多占
        30MB 以上峰值内存，这里改成文件级复制。
        """
        try:
            if not os.path.isfile(path):
                return None
            ext = os.path.splitext(path)[1].lower() or ".png"
            name = (
                "shot_"
                + time.strftime("%Y%m%d_%H%M%S")
                + f"_{int(time.time() * 1000) % 1000:03d}{ext}"
            )
            target = os.path.join(self.root, name)
            shutil.copyfile(path, target)
            self.prune()
            return target
        except Exception:
            return None

    def files(self) -> list[str]:
        try:
            items = [
                os.path.join(self.root, f)
                for f in os.listdir(self.root)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))
            ]
        except Exception:
            return []
        items.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return items

    def prune(self) -> None:
        limit = int(config.get("history_limit", 60))
        if limit <= 0:
            return
        for path in self.files()[limit:]:
            try:
                os.remove(path)
            except Exception:
                pass


class HistoryDialog(QDialog):
    pinRequested = Signal(QPixmap)

    def __init__(self, store: HistoryStore, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.store = store
        self.setWindowTitle("历史记录")
        self.setStyleSheet(PANEL_QSS)
        self.resize(720, 560)
        self._thumb = QSize(168, 110)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        self.title = QLabel("历史记录")
        self.title.setObjectName("title")
        lay.addWidget(self.title)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(self._thumb)
        self.list.setGridSize(QSize(190, 150))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda _i: self._copy())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.info = QLabel("")
        self.info.setObjectName("info")
        row.addWidget(self.info)
        row.addStretch(1)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(self._copy)
        pin_btn = QPushButton("贴图")
        pin_btn.clicked.connect(self._pin)
        save_btn = QPushButton("另存为")
        save_btn.clicked.connect(self._save_as)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._delete)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        for b in (copy_btn, pin_btn, save_btn, del_btn, close_btn):
            row.addWidget(b)
        lay.addLayout(row)

        self.reload()

    def reload(self):
        self.list.clear()
        files = self.store.files()
        # 缩略图按解码尺寸直接读，避免把每张原图整幅加载进内存
        dpr = max(1.0, float(self.devicePixelRatioF()))
        thumb = QSize(
            int(self._thumb.width() * dpr), int(self._thumb.height() * dpr)
        )
        for path in files:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            src = reader.size()
            if src.isValid() and not src.isEmpty():
                reader.setScaledSize(src.scaled(thumb, Qt.KeepAspectRatio))
                w, h = src.width(), src.height()
            else:
                w = h = 0
            img = reader.read()
            if img.isNull():
                continue
            item = QListWidgetItem(
                QIcon(QPixmap.fromImage(img)),
                f"{time.strftime('%m-%d %H:%M:%S', time.localtime(os.path.getmtime(path)))}  "
                f"{w}×{h}",
            )
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
        self.info.setText(f"共 {self.list.count()} 张" + ("" if files else "，还没有历史截图"))
        if self.list.count():
            self.list.setCurrentRow(0)

    def _current_path(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _copy(self):
        path = self._current_path()
        if not path:
            return
        pm = QPixmap(path)
        if not pm.isNull():
            QApplication.clipboard().setPixmap(pm)
            self.info.setText("已复制到剪贴板")

    def _pin(self):
        path = self._current_path()
        if not path:
            return
        pm = QPixmap(path)
        if not pm.isNull():
            self.pinRequested.emit(pm)

    def _save_as(self):
        path = self._current_path()
        if not path:
            return
        ext = os.path.splitext(path)[1] or ".png"
        target, _ = QFileDialog.getSaveFileName(
            self, "另存为", os.path.basename(path), f"图片 (*{ext})"
        )
        if not target:
            return
        try:
            with open(path, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())
            self.info.setText(f"已保存：{target}")
        except Exception as ex:
            self.info.setText(f"保存失败：{ex}")

    def _delete(self):
        path = self._current_path()
        if not path:
            return
        if (
            QMessageBox.question(self, "删除", "确定删除这张历史截图？")
            != QMessageBox.Yes
        ):
            return
        try:
            os.remove(path)
        except Exception:
            pass
        self.reload()

    def _menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        m = QMenu(self)
        m.setStyleSheet(PANEL_QSS)
        m.addAction("复制", self._copy)
        m.addAction("贴图", self._pin)
        m.addAction("另存为…", self._save_as)
        m.addSeparator()
        m.addAction("打开所在目录", self._open_dir)
        m.addAction("删除", self._delete)
        m.exec(self.list.mapToGlobal(pos))

    def _open_dir(self):
        try:
            os.startfile(self.store.root)
        except Exception:
            pass
