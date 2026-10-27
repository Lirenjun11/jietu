"""应用主控：托盘、菜单、快捷键、截图调度。"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from .config import APP_TITLE, config
from .hotkey import GlobalHotkeys
from .icons import app_icon, make_icon

# capture / overlay / pin / history / settings 都改成用到时再导入：
# 托盘常驻时只加载必要的模块，空载内存与启动时间都更低。


def trim_working_set() -> None:
    """把工作集里的空闲页还给系统。

    Python + Qt 的常驻内存里有一大块是已加载但当前不用的 DLL 页面，
    调用 SetProcessWorkingSetSize(-1,-1) 后这些页进入备用列表，任务管理器里
    看到的占用会明显下降；下次用到时由系统按需重新映射（都是文件页，很快）。
    """
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetProcessWorkingSetSize.argtypes = [
            wintypes.HANDLE,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        k32.SetProcessWorkingSetSize.restype = wintypes.BOOL
        k32.SetProcessWorkingSetSize(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.c_size_t(-1),
            ctypes.c_size_t(-1),
        )
    except Exception:
        pass


def shiboken_is_valid(obj) -> bool:
    try:
        import shiboken6

        return shiboken6.isValid(obj)
    except Exception:
        return True

MENU_QSS = """
QMenu { background: #23262B; color: #E8EAED; border: 1px solid #3A3F46;
        border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 30px; border-radius: 5px; font-size: 13px; }
QMenu::item:selected { background: #2F6FEB; }
QMenu::item:disabled { color: #6B7178; }
QMenu::separator { height: 1px; background: #3A3F46; margin: 5px 10px; }
QMenu::icon { padding-left: 8px; }
"""


class JietuApp(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.overlay = None  # CaptureOverlay | None
        self._retiring: list = []  # 已 finish、等 Qt 销毁的 overlay
        self.pins: list = []
        self._busy = False
        from .history import HistoryStore

        self.history = HistoryStore()
        self._history_dlg = None
        self._last_history_at = 0.0

        self.hotkeys = GlobalHotkeys(qapp)

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_TITLE)
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()
        self.tray.show()

        self.register_hotkeys()

        # OCR 助手空闲 60 秒后释放（子进程连同模型一起退出），下次识别自动重启
        self._ocr_sweep = QTimer(self)
        self._ocr_sweep.setInterval(30_000)
        self._ocr_sweep.timeout.connect(self._release_idle_ocr)
        self._ocr_sweep.start()

        # 空闲 20 秒后把用不到的内存页交还系统（连续截图时不会触发，
        # 避免下次截图还要重新映射页面）
        self._trim_timer = QTimer(self)
        self._trim_timer.setSingleShot(True)
        self._trim_timer.setInterval(20_000)
        self._trim_timer.timeout.connect(trim_working_set)
        self._trim_timer.start()

        QTimer.singleShot(
            900,
            lambda: self.notify(
                "Jietu Pro 已启动",
                f"按 {config.get('hotkey_capture').replace('+', ' + ').upper()} 框选截图",
            ),
        )

    # ================================================================ 菜单
    def _build_menu(self):
        m = QMenu()
        m.setStyleSheet(MENU_QSS)

        a = m.addAction(make_icon("crop", 18), "框选截图")
        a.setShortcut("Ctrl+Shift+A")
        a.triggered.connect(lambda: self.start_capture("region"))

        a = m.addAction(make_icon("fullscreen", 18), "全屏截图")
        a.setShortcut("Ctrl+Shift+F")
        a.triggered.connect(lambda: self.start_capture("fullscreen"))

        a = m.addAction(make_icon("window", 18), "窗口截图")
        a.triggered.connect(lambda: self.start_capture("window"))

        sub = m.addMenu("延迟截图")
        sub.setStyleSheet(MENU_QSS)
        for sec in (3, 5, 10):
            act = sub.addAction(f"{sec} 秒后截图")
            act.triggered.connect(lambda _=False, s=sec: self.start_capture("region", delay=s))

        m.addSeparator()

        a = m.addAction(make_icon("folder", 18), "打开保存目录")
        a.triggered.connect(self.open_save_dir)

        a = m.addAction(make_icon("history", 18), "历史记录…")
        a.triggered.connect(self.open_history)

        a = m.addAction(make_icon("settings", 18), "设置…")
        a.triggered.connect(self.open_settings)

        m.addSeparator()

        a = m.addAction(make_icon("close", 18), "退出")
        a.triggered.connect(self.quit)

        self.menu = m
        self.tray.setContextMenu(m)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.start_capture("region")

    # ================================================================ 截图
    def start_capture(self, mode: str = "region", delay: int = 0):
        if self._busy:
            return
        if self.overlay is not None:
            try:
                self.overlay.finish(None)
            except Exception:
                pass
            self.overlay = None

        if delay > 0:
            self.notify("准备截图", f"{delay} 秒后开始…")
            QTimer.singleShot(delay * 1000, lambda: self._do_capture(mode))
        else:
            QTimer.singleShot(160, lambda: self._do_capture(mode))

    def _do_capture(self, mode: str):
        if self._busy:
            return
        self._busy = True
        self._trim_timer.stop()
        try:
            self._warm_ocr()
            from .capture import Shot
            from .overlay import CaptureOverlay

            shot = Shot()
            overlay = CaptureOverlay(shot, mode)
            overlay.pinRequested.connect(self.create_pin)
            overlay.savedTo.connect(self._on_saved)
            overlay.copiedToClipboard.connect(self._on_copied)
            overlay.closed.connect(self._on_overlay_closed)
            overlay.destroyed.connect(lambda *_: self._forget_retired())
            self.overlay = overlay
            overlay.begin()
        except Exception as ex:
            self._busy = False
            self.notify("截图失败", str(ex))
            import traceback

            traceback.print_exc()

    def _forget_retired(self):
        self._retiring = [w for w in self._retiring if shiboken_is_valid(w)]

    def _retire(self, overlay):
        """窗口已 finish() 但尚未被 Qt 销毁时保留 Python 引用，
        避免 C++ 对象销毁与 Python 引用释放竞争导致崩溃。"""
        self._forget_retired()
        if overlay is not None and overlay not in self._retiring:
            self._retiring.append(overlay)

    def _on_overlay_closed(self):
        self._retire(self.overlay)
        self.overlay = None
        self._busy = False
        # 整屏位图已释放；空闲一会儿再收缩工作集，任务管理器里回落
        self._trim_timer.start()

    # ================================================================ 结果
    def create_pin(self, pixmap: QPixmap):
        from .pin import PinWindow

        w = PinWindow(pixmap)
        w.closed.connect(self._remove_pin)
        w.show()
        w.raise_()
        self.pins.append(w)

    def _remove_pin(self, w):
        if w in self.pins:
            self.pins.remove(w)

    def _on_saved(self, path: str):
        self.notify("已保存", os.path.basename(path))
        self._record_history(path)
        if config.get("copy_path_after_save"):
            QApplication.clipboard().setText(path)

    def _on_copied(self, pixmap: QPixmap | None = None):
        self.notify("已复制到剪贴板", "可直接粘贴到聊天窗口或文档")
        self._record_history(pixmap=pixmap)

    def _warm_ocr(self):
        """后台预热识别助手，首次点「识别文字」时不用等模型加载。

        预热会拉起一个常驻子进程（numpy/opencv/onnxruntime + 模型，数百 MB），
        默认关闭，避免每次截图后都多背一个重进程；需要更快的首次识别可在
        设置里打开。
        """
        if not config.get("ocr_preload", False):
            return
        try:
            from . import ocr

            ocr.warm()
        except Exception:
            pass

    def _release_idle_ocr(self):
        from . import ocr

        ocr.release_if_idle()

    def _record_history(self, path: str | None = None, pixmap: QPixmap | None = None):
        if not config.get("save_history", True):
            return
        now = time.time()
        if now - self._last_history_at < 1.5:
            return
        try:
            if path and os.path.exists(path):
                ok = self.history.add_file(path)
            elif pixmap is not None and not pixmap.isNull():
                # 直接用刚渲染好的图，不再从剪贴板回读一份等大位图
                ok = self.history.add(pixmap)
            else:
                pm = QApplication.clipboard().pixmap()
                ok = self.history.add(pm) if not pm.isNull() else None
            if ok:
                self._last_history_at = now
        except Exception:
            pass

    def open_history(self):
        try:
            from .history import HistoryDialog

            dlg = HistoryDialog(self.history)
            dlg.pinRequested.connect(self.create_pin)
            dlg.exec()
            dlg.deleteLater()  # 关掉后立刻释放缩略图等资源
        except Exception as ex:
            self.notify("无法打开历史记录", str(ex))
        self._trim_timer.start()

    def notify(self, title: str, body: str = ""):
        try:
            if QSystemTrayIcon.supportsMessages():
                self.tray.showMessage(title, body, app_icon(), 1800)
        except Exception:
            pass

    def open_save_dir(self):
        d = config.get("save_dir")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            d = os.path.expanduser("~")
        try:
            os.startfile(d)  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", d])

    # ================================================================ 设置
    def open_settings(self):
        from .settings_dialog import SettingsDialog

        dlg = SettingsDialog()
        if dlg.exec() == QDialog.Accepted:
            dlg.apply()
        dlg.deleteLater()
        self.register_hotkeys()
        self.notify("设置已保存", "新的快捷键立即生效")
        self._trim_timer.start()

    def register_hotkeys(self):
        self.hotkeys.clear()
        if not config.get("enable_hotkey"):
            return

        cap = config.get("hotkey_capture")
        full = config.get("hotkey_fullscreen")

        ok1 = self.hotkeys.register(cap, lambda: self.start_capture("region"))
        if not ok1:
            # 被其他软件占用时，自动换一个可用组合
            for alt in ("ctrl+shift+a", "ctrl+shift+x", "f1"):
                if alt == full:
                    continue
                if self.hotkeys.register(alt, lambda: self.start_capture("region")):
                    config["hotkey_capture"] = alt
                    config.save()
                    ok1 = True
                    QTimer.singleShot(
                        1500,
                        lambda a=alt, c=cap: self.notify(
                            "快捷键已自动调整", f"{c} 被占用，改用 {a}"
                        ),
                    )
                    break

        ok2 = self.hotkeys.register(full, lambda: self.start_capture("fullscreen"))
        if not ok2:
            for alt in ("ctrl+shift+f", "ctrl+shift+z", "f2"):
                if alt == config.get("hotkey_capture"):
                    continue
                if self.hotkeys.register(alt, lambda: self.start_capture("fullscreen")):
                    config["hotkey_fullscreen"] = alt
                    config.save()
                    ok2 = True
                    break

        if not ok1:
            self.notify("快捷键注册失败", "框选快捷键被占用，请在设置中更换")

    # ================================================================ 退出
    def quit(self):
        try:
            self.hotkeys.clear()
        except Exception:
            pass
        for p in list(self.pins):
            try:
                p.close()
            except Exception:
                pass
        self.tray.hide()
        self.qapp.quit()
