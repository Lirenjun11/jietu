"""识别结果对话框、长截图预览窗与轻量提示条。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

PANEL_QSS = """
QDialog, QWidget#Panel { background: #23262B; }
QLabel#title { color: #E8EAED; font-size: 13px; font-weight: 600; }
QLabel#info { color: #9AA0A6; font-size: 12px; }
QPlainTextEdit {
    background: #1B1E22; color: #E8EAED; border: 1px solid #3A3F46;
    border-radius: 6px; font-size: 13px; padding: 6px;
    selection-background-color: #2F6FEB;
}
QPushButton {
    background: #2F6FEB; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 6px 14px; font-size: 13px;
}
QPushButton:hover { background: #3B7BF5; }
QPushButton#ghost { background: #2C3037; color: #C9CDD3; }
QPushButton#ghost:hover { background: #383D45; }
QScrollArea { border: 1px solid #3A3F46; border-radius: 6px; background: #1B1E22; }
"""


class OcrWorker(QThread):
    """在后台线程跑 OCR（PowerShell 约 1 秒），避免卡住界面。"""

    done = Signal(bool, str, str)

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        # 不再 image.copy()：调用方传进来的已是独立副本，多存一份等于整图翻倍
        self._image = image

    def run(self):
        try:
            from . import ocr

            res = ocr.recognize(self._image)
            self.done.emit(res.ok, res.text, res.error)
        except Exception as ex:  # pragma: no cover - 防御
            self.done.emit(False, "", str(ex))
        finally:
            self._image = QImage()


class OcrDialog(QDialog):
    def __init__(self, text: str, error: str = "", parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("识别文字")
        self.setStyleSheet(PANEL_QSS)
        self.setMinimumSize(460, 320)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        title = QLabel("识别结果" if not error else "识别失败")
        title.setObjectName("title")
        lay.addWidget(title)

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text if not error else error)
        self.edit.setReadOnly(bool(error))
        lay.addWidget(self.edit, 1)

        self.info = QLabel("")
        self.info.setObjectName("info")
        lay.addWidget(self.info)

        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_btn = QPushButton("复制文本")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = QPushButton("保存为 TXT")
        self.save_btn.setObjectName("ghost")
        self.save_btn.clicked.connect(self._save)
        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("ghost")
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.copy_btn)
        row.addWidget(self.save_btn)
        row.addWidget(self.close_btn)
        lay.addLayout(row)

        if error:
            self.copy_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
        else:
            n = len([ln for ln in text.splitlines() if ln.strip()])
            self.info.setText(f"{n} 行，{len(text)} 字符")

    def _copy(self):
        QApplication.clipboard().setText(self.edit.toPlainText())
        self.info.setText("已复制到剪贴板")

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存文本", "识别结果.txt", "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(self.edit.toPlainText())
            self.info.setText(f"已保存：{path}")
        except Exception as ex:
            self.info.setText(f"保存失败：{ex}")


class Toast(QWidget):
    """屏幕中上方的小提示，自动消失。"""

    def __init__(self, text: str, parent=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(PANEL_QSS)
        self.setObjectName("Panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        self.label = QLabel(text)
        self.label.setObjectName("title")
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)
        self.adjustSize()

    def show_centered(self, timeout_ms: int = 1500, parent_rect=None):
        g = parent_rect or QGuiApplication.primaryScreen().geometry()
        self.move(g.center().x() - self.width() // 2, g.top() + 60)
        self.show()
        if timeout_ms > 0:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(timeout_ms, self._auto_close)

    def _auto_close(self):
        """自动消失后立刻销毁，否则每次提示都会留下一个隐藏窗口。"""
        try:
            self.close()
            self.deleteLater()
        except Exception:
            pass

    def set_text(self, text: str):
        self.label.setText(text)
        self.adjustSize()


class LongShotPreview(QWidget):
    """长截图预览窗，带保存/复制。"""

    def __init__(self, image: QImage, info: str = "", parent=None):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("长截图预览")
        self.setStyleSheet(PANEL_QSS)
        self.resize(760, 620)
        self._image = image

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        title = QLabel(f"长截图：{image.width()} × {image.height()} 像素  {info}")
        title.setObjectName("title")
        lay.addWidget(title)

        area = QScrollArea()
        area.setWidgetResizable(True)
        holder = QLabel()
        holder.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        holder.setPixmap(QPixmap.fromImage(image))
        self._holder = holder
        area.setWidget(holder)
        lay.addWidget(area, 1)

        row = QHBoxLayout()
        self.info = QLabel("")
        self.info.setObjectName("info")
        row.addWidget(self.info)
        row.addStretch(1)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self.close)
        row.addWidget(copy_btn)
        row.addWidget(save_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)

    def closeEvent(self, e):
        # 长截图动辄上万像素高，关闭时立刻松手，别等 GC
        self._holder.setPixmap(QPixmap())
        self._image = QImage()
        super().closeEvent(e)

    def _copy(self):
        QApplication.clipboard().setImage(self._image)
        self.info.setText("已复制到剪贴板")

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存长截图", "长截图.png", "PNG 图片 (*.png);;JPEG 图片 (*.jpg)"
        )
        if not path:
            return
        ok = self._image.save(path)
        self.info.setText(f"已保存：{path}" if ok else "保存失败")
