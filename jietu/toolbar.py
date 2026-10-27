"""浮动工具条与颜色/线宽弹出面板。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .annotations import TOOL_DEFS

PRESET_COLORS = [
    "#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#00C7BE",
    "#007AFF", "#AF52DE", "#FF2D55", "#FFFFFF", "#000000",
]

QSS = """
QWidget#Bar {
    background: #23262B;
    border: 1px solid #3A3F46;
    border-radius: 9px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
    margin: 0px;
}
QToolButton:hover { background: #34383F; }
QToolButton:pressed { background: #2A2E34; }
QToolButton:checked { background: #2F6FEB; }
QToolButton:checked:hover { background: #3B7BF5; }
QFrame#sep { background: #3A3F46; max-width: 1px; min-width: 1px; }
QLabel#hint { color: #9AA0A6; }
"""

BTN = 32
BAR_H = 40


class _Popup(QWidget):
    """通用弹出面板（无边框、置顶、点外部关闭）"""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(
            "QWidget#Pop { background: #23262B; border: 1px solid #3A3F46; border-radius: 8px; }"
        )
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        self.body.setObjectName("Pop")
        self.outer.addWidget(self.body)


class ColorPopup(_Popup):
    picked = Signal(str)

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self.body)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(6)
        for i, c in enumerate(PRESET_COLORS):
            b = QToolButton()
            b.setFixedSize(24, 24)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton{{background:{c};border-radius:5px;"
                f"border:2px solid {'#2F6FEB' if c.lower()==current.lower() else '#00000000'};}}"
                f"QToolButton:hover{{border:2px solid #FFFFFF;}}"
            )
            b.clicked.connect(lambda _=False, col=c: self._pick(col))
            grid.addWidget(b, i // 5, i % 5)

        more = QToolButton()
        more.setText("自定义…")
        more.setCursor(Qt.PointingHandCursor)
        more.setStyleSheet(
            "QToolButton{color:#C9CDD3;background:#2C3037;border:none;border-radius:5px;"
            "padding:5px 8px;font-size:12px;}QToolButton:hover{background:#383D45;}"
        )
        more.clicked.connect(self._custom)
        grid.addWidget(more, 2, 0, 1, 5)

    def _pick(self, c: str):
        self.picked.emit(c)
        self.close()

    def _custom(self):
        c = QColorDialog.getColor(QColor(PRESET_COLORS[0]), self, "选择颜色")
        if c.isValid():
            self.picked.emit(c.name())
        self.close()


class WidthPopup(_Popup):
    picked = Signal(int)

    def __init__(self, current: int, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self.body)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        for w in (2, 3, 5, 8):
            b = QToolButton()
            b.setFixedSize(38, 34)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(icons.width_icon(w, 24, "#E8EAED"))
            b.setIconSize(QSize(24, 24))
            active = w == current
            b.setStyleSheet(
                "QToolButton{background:%s;border:none;border-radius:6px;}"
                "QToolButton:hover{background:#383D45;}" % ("#2F6FEB" if active else "transparent")
            )
            b.clicked.connect(lambda _=False, ww=w: self._pick(ww))
            lay.addWidget(b)

    def _pick(self, w: int):
        self.picked.emit(w)
        self.close()


class ToolBar(QWidget):
    toolChanged = Signal(str)
    colorChanged = Signal(str)
    widthChanged = Signal(int)
    undoRequested = Signal()
    redoRequested = Signal()
    saveRequested = Signal()
    copyRequested = Signal()
    pinRequested = Signal()
    closeRequested = Signal()
    ocrRequested = Signal()
    scrollRequested = Signal()
    beautifyRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Bar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(QSS)
        self.setFixedHeight(BAR_H)
        self.setCursor(Qt.ArrowCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(1)

        self.tool_buttons: dict[str, QToolButton] = {}
        for key, name, _sc in TOOL_DEFS:
            b = self._btn(icons.make_icon(key), f"{name}", checkable=True)
            b.clicked.connect(lambda _=False, k=key: self._select_tool(k))
            lay.addWidget(b)
            self.tool_buttons[key] = b

        lay.addWidget(self._sep())

        self.color_btn = self._btn(icons.color_dot_icon("#FF3B30"), "颜色")
        self.color_btn.clicked.connect(self._open_color)
        lay.addWidget(self.color_btn)

        self.width_btn = self._btn(icons.width_icon(3), "粗细")
        self.width_btn.clicked.connect(self._open_width)
        lay.addWidget(self.width_btn)

        lay.addWidget(self._sep())

        self.undo_btn = self._btn(icons.make_icon("undo"), "撤销 (Ctrl+Z)")
        self.undo_btn.clicked.connect(self.undoRequested.emit)
        lay.addWidget(self.undo_btn)

        self.redo_btn = self._btn(icons.make_icon("redo"), "重做 (Ctrl+Y)")
        self.redo_btn.clicked.connect(self.redoRequested.emit)
        lay.addWidget(self.redo_btn)

        lay.addWidget(self._sep())

        self.pin_btn = self._btn(icons.make_icon("pin"), "贴图到屏幕 (F3)")
        self.pin_btn.clicked.connect(self.pinRequested.emit)
        lay.addWidget(self.pin_btn)

        self.ocr_btn = self._btn(icons.make_icon("ocr"), "识别文字 (Ctrl+Shift+O)")
        self.ocr_btn.clicked.connect(self.ocrRequested.emit)
        lay.addWidget(self.ocr_btn)

        self.scroll_btn = self._btn(icons.make_icon("scroll"), "滚动长截图 (Ctrl+Shift+L)")
        self.scroll_btn.clicked.connect(self.scrollRequested.emit)
        lay.addWidget(self.scroll_btn)

        self.beautify_btn = self._btn(icons.make_icon("beautify"), "图片美化 (Ctrl+B)")
        self.beautify_btn.clicked.connect(self.beautifyRequested.emit)
        lay.addWidget(self.beautify_btn)

        lay.addWidget(self._sep())

        self.save_btn = self._btn(icons.make_icon("save"), "保存 (Ctrl+S)")
        self.save_btn.clicked.connect(self.saveRequested.emit)
        lay.addWidget(self.save_btn)

        self.copy_btn = self._btn(icons.make_icon("copy"), "复制到剪贴板 (Ctrl+C / Enter)")
        self.copy_btn.clicked.connect(self.copyRequested.emit)
        lay.addWidget(self.copy_btn)

        self.close_btn = self._btn(icons.make_icon("close"), "取消 (Esc)")
        self.close_btn.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self.close_btn)

        self.current_tool = "rect"
        self.current_color = "#FF3B30"
        self.current_width = 3
        self.set_tool("rect")
        self.set_color("#FF3B30")
        self.set_width(3)
        self.adjustSize()
        self.setFixedHeight(BAR_H)

    # ------------------------------------------------------------------
    def _btn(self, icon, tip: str, checkable: bool = False) -> QToolButton:
        b = QToolButton(self)
        b.setIcon(icon)
        b.setIconSize(QSize(21, 21))
        b.setFixedSize(BTN, BTN)
        b.setCheckable(checkable)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setObjectName("sep")
        f.setFixedSize(1, 22)
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("background:#3A3F46;border:none;")
        return f

    def _select_tool(self, key: str):
        self.set_tool(key)
        self.toolChanged.emit(key)

    def set_tool(self, key: str):
        self.current_tool = key
        for k, b in self.tool_buttons.items():
            b.setChecked(k == key)

    def set_color(self, color: str):
        self.current_color = color
        self.color_btn.setIcon(icons.color_dot_icon(color))
        self.color_btn.setToolTip(f"颜色 {color}")

    def set_width(self, w: int):
        self.current_width = w
        self.width_btn.setIcon(icons.width_icon(w))
        self.width_btn.setToolTip(f"粗细 {w}px")

    def set_undo_enabled(self, on: bool):
        self.undo_btn.setEnabled(on)
        self.undo_btn.setStyleSheet("" if on else "opacity:0.35;")

    def set_redo_enabled(self, on: bool):
        self.redo_btn.setEnabled(on)

    # ------------------------------------------------------------------
    def _open_color(self):
        pop = ColorPopup(self.current_color, self)
        pop.picked.connect(self._on_color)
        pos = self.color_btn.mapToGlobal(QPoint(0, 0))
        pop.adjustSize()
        y = pos.y() - pop.height() - 6
        if y < 0:
            y = pos.y() + self.color_btn.height() + 6
        pop.move(pos.x() - 20, y)
        pop.show()

    def _on_color(self, c: str):
        self.set_color(c)
        self.colorChanged.emit(c)

    def _open_width(self):
        pop = WidthPopup(self.current_width, self)
        pop.picked.connect(self._on_width)
        pos = self.width_btn.mapToGlobal(QPoint(0, 0))
        pop.adjustSize()
        y = pos.y() - pop.height() - 6
        if y < 0:
            y = pos.y() + self.width_btn.height() + 6
        pop.move(pos.x() - 20, y)
        pop.show()

    def _on_width(self, w: int):
        self.set_width(w)
        self.widthChanged.emit(w)
