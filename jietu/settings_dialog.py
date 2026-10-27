"""设置面板。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import app_data_dir, config

QSS = """
QDialog { background: #1E2024; }
QLabel { color: #D5D9DF; font-size: 13px; }
QCheckBox { color: #D5D9DF; font-size: 13px; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #4A5058; background: #2A2E34; }
QCheckBox::indicator:checked { background: #2F6FEB; border: 1px solid #2F6FEB; }
QLineEdit, QComboBox, QSpinBox {
    background: #262A30; color: #E8EAED; border: 1px solid #3A3F46;
    border-radius: 6px; padding: 5px 8px; font-size: 13px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: #262A30; color: #E8EAED;
    selection-background-color: #2F6FEB; border: 1px solid #3A3F46; }
QPushButton { background: #2E333A; color: #E8EAED; border: none;
    border-radius: 6px; padding: 6px 14px; font-size: 13px; }
QPushButton:hover { background: #3A4048; }
QPushButton#primary { background: #2F6FEB; }
QPushButton#primary:hover { background: #3B7BF5; }
QSlider::groove:horizontal { height: 4px; background: #3A3F46; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; background: #2F6FEB; }
QGroupBox { color: #9AA0A6; border: 1px solid #33383F; border-radius: 8px;
    margin-top: 14px; padding-top: 8px; font-size: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
"""


class HotkeyEdit(QLineEdit):
    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setReadOnly(True)
        self.setPlaceholderText("点击后按下快捷键")
        self.setCursor(Qt.PointingHandCursor)

    def keyPressEvent(self, e):
        key = e.key()
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            return
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            self.setText("")
            return
        mods = e.modifiers()
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.AltModifier:
            parts.append("alt")
        if mods & Qt.ShiftModifier:
            parts.append("shift")
        if mods & Qt.MetaModifier:
            parts.append("win")
        if Qt.Key_A <= key <= Qt.Key_Z:
            parts.append(chr(key).lower())
        elif Qt.Key_0 <= key <= Qt.Key_9:
            parts.append(chr(key))
        elif Qt.Key_F1 <= key <= Qt.Key_F24:
            parts.append(f"f{key - Qt.Key_F1 + 1}")
        elif key == Qt.Key_Print:
            parts.append("printscreen")
        elif key == Qt.Key_Space:
            parts.append("space")
        else:
            return
        if len(parts) < 2:
            return
        self.setText("+".join(parts))


def app_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if pyw.exists():
        exe = pyw
    return f'"{exe}" "{main_py}" --tray'


def set_autostart(enable: bool) -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enable:
            winreg.SetValueEx(key, "JietuPro", 0, winreg.REG_SZ, app_command())
        else:
            try:
                winreg.DeleteValue(key, "JietuPro")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def is_autostart() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, "JietuPro")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jietu Pro · 设置")
        self.setMinimumWidth(460)
        self.setStyleSheet(QSS)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        title = QLabel("设置")
        f = QFont("Microsoft YaHei UI", 14)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#FFFFFF;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 保存目录
        dir_row = QWidget()
        dl = QHBoxLayout(dir_row)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        self.dir_edit = QLineEdit(str(config.get("save_dir")))
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        dl.addWidget(self.dir_edit, 1)
        dl.addWidget(browse)
        form.addRow("保存目录", dir_row)

        # 格式
        self.fmt = QComboBox()
        self.fmt.addItems(["PNG（无损）", "JPG（体积小）"])
        self.fmt.setCurrentIndex(0 if config.get("image_format") == "png" else 1)
        form.addRow("图片格式", self.fmt)

        self.quality = QSpinBox()
        self.quality.setRange(50, 100)
        self.quality.setValue(int(config.get("jpg_quality", 95)))
        self.quality.setSuffix(" %")
        form.addRow("JPG 质量", self.quality)

        # 文件名格式
        self.filename = QLineEdit(str(config.get("filename_pattern", "Jietu_{date}_{time}")))
        self.filename.setPlaceholderText("Jietu_{date}_{time}")
        self.filename.setToolTip("可用占位符：{date} 日期、{time} 时间；重名自动加序号")
        form.addRow("文件名格式", self.filename)

        # 遮罩透明度
        self.alpha = QSlider(Qt.Horizontal)
        self.alpha.setRange(0, 90)
        self.alpha.setValue(int(float(config.get("overlay_alpha", 0.45)) * 100))
        self.alpha_lbl = QLabel(f"{self.alpha.value()}%")
        self.alpha_lbl.setFixedWidth(42)
        self.alpha.valueChanged.connect(lambda v: self.alpha_lbl.setText(f"{v}%"))
        ar = QWidget()
        al = QHBoxLayout(ar)
        al.setContentsMargins(0, 0, 0, 0)
        al.addWidget(self.alpha, 1)
        al.addWidget(self.alpha_lbl)
        form.addRow("遮罩深浅", ar)

        # 快捷键
        self.hk_capture = HotkeyEdit(str(config.get("hotkey_capture")))
        form.addRow("框选截图", self.hk_capture)

        self.hk_full = HotkeyEdit(str(config.get("hotkey_fullscreen")))
        form.addRow("全屏截图", self.hk_full)

        root.addLayout(form)

        # 开关
        self.chk_copy = QCheckBox("保存后同时复制到剪贴板")
        self.chk_copy.setChecked(bool(config.get("auto_copy")))
        root.addWidget(self.chk_copy)

        self.chk_mag = QCheckBox("选框时显示放大镜 / 取色")
        self.chk_mag.setChecked(bool(config.get("show_magnifier")))
        root.addWidget(self.chk_mag)

        self.chk_win = QCheckBox("鼠标悬停时自动识别窗口")
        self.chk_win.setChecked(bool(config.get("show_window_detect")))
        root.addWidget(self.chk_win)

        self.chk_ocr_pre = QCheckBox("截图后预热文字识别（更快，但常驻占用内存）")
        self.chk_ocr_pre.setChecked(bool(config.get("ocr_preload", False)))
        self.chk_ocr_pre.setToolTip(
            "开启后每次截图都会启动识别助手进程，首次识别更快；\n"
            "关闭则等到真正点“识别文字”时才启动，空闲 60 秒自动退出。"
        )
        root.addWidget(self.chk_ocr_pre)

        self.chk_hotkey = QCheckBox("启用全局快捷键")
        self.chk_hotkey.setChecked(bool(config.get("enable_hotkey")))
        root.addWidget(self.chk_hotkey)

        hist_row = QHBoxLayout()
        hist_row.setContentsMargins(0, 0, 0, 0)
        self.chk_hist = QCheckBox("保留截图历史记录")
        self.chk_hist.setChecked(bool(config.get("save_history", True)))
        self.hist_limit = QSpinBox()
        self.hist_limit.setRange(5, 500)
        self.hist_limit.setValue(int(config.get("history_limit", 60)))
        self.hist_limit.setSuffix(" 张")
        self.hist_limit.setEnabled(self.chk_hist.isChecked())
        self.chk_hist.toggled.connect(self.hist_limit.setEnabled)
        hist_row.addWidget(self.chk_hist)
        hist_row.addStretch(1)
        hist_row.addWidget(self.hist_limit)
        root.addLayout(hist_row)

        self.chk_boot = QCheckBox("开机自动启动（最小化到托盘）")
        self.chk_boot.setChecked(is_autostart())
        root.addWidget(self.chk_boot)

        btns = QDialogButtonBox()
        ok = QPushButton("保存")
        ok.setObjectName("primary")
        cancel = QPushButton("取消")
        btns.addButton(ok, QDialogButtonBox.AcceptRole)
        btns.addButton(cancel, QDialogButtonBox.RejectRole)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        root.addSpacing(4)
        root.addWidget(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def apply(self) -> None:
        config["save_dir"] = self.dir_edit.text().strip() or str(Path.home())
        config["image_format"] = "png" if self.fmt.currentIndex() == 0 else "jpg"
        config["jpg_quality"] = self.quality.value()
        config["filename_pattern"] = self.filename.text().strip() or "Jietu_{date}_{time}"
        config["overlay_alpha"] = self.alpha.value() / 100.0
        config["hotkey_capture"] = self.hk_capture.text().strip() or "ctrl+alt+a"
        config["hotkey_fullscreen"] = self.hk_full.text().strip() or "ctrl+alt+f"
        config["auto_copy"] = self.chk_copy.isChecked()
        config["show_magnifier"] = self.chk_mag.isChecked()
        config["show_window_detect"] = self.chk_win.isChecked()
        config["ocr_preload"] = self.chk_ocr_pre.isChecked()
        config["enable_hotkey"] = self.chk_hotkey.isChecked()
        config["save_history"] = self.chk_hist.isChecked()
        config["history_limit"] = self.hist_limit.value()
        config.save()

        cur = is_autostart()
        want = self.chk_boot.isChecked()
        if cur != want:
            if not set_autostart(want):
                QMessageBox.warning(self, "提示", "设置开机自启失败，可能被安全软件拦截。")
