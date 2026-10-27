"""Jietu Pro 启动入口。"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from jietu.config import APP_TITLE

SINGLE_KEY = "JietuPro-SingleInstance-7f3a"


def _ensure_streams() -> None:
    """windowed 模式下 sys.stdout/stderr 为 None，任何 print/traceback 都会二次报错，
    这里统一重定向到日志文件。"""
    from jietu.config import app_data_dir

    if sys.stderr is None or sys.stdout is None:
        try:
            f = open(
                app_data_dir() / "runtime.log",
                "a",
                buffering=1,
                encoding="utf-8",
                errors="replace",
            )
            sys.stderr = f
            if sys.stdout is None:
                sys.stdout = f
        except Exception:
            pass


def _install_error_log() -> None:
    """把未捕获异常写入日志，避免无控制台模式下静默退出。"""
    import time
    import traceback

    from jietu.config import app_data_dir

    log_path = app_data_dir() / "error.log"

    def hook(etype, value, tb):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                f.write("".join(traceback.format_exception(etype, value, tb)))
        except Exception:
            pass

    sys.excepthook = hook


def _try_activate_existing() -> bool:
    """已有实例则把截图请求转发过去，返回 True 表示应当退出。"""
    try:
        from PySide6.QtNetwork import QLocalSocket

        sock = QLocalSocket()
        sock.connectToServer(SINGLE_KEY)
        if sock.waitForConnected(350):
            sock.write(b"capture")
            sock.flush()
            sock.waitForBytesWritten(350)
            sock.disconnectFromServer()
            return True
    except Exception:
        pass
    return False


def _log(msg: str) -> None:
    import time

    from jietu.config import app_data_dir

    try:
        with open(app_data_dir() / "ipc.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _start_ipc_server(app: JietuApp):
    import traceback

    try:
        from PySide6.QtNetwork import QLocalServer

        QLocalServer.removeServer(SINGLE_KEY)
        server = QLocalServer()
        if not server.listen(SINGLE_KEY):
            _log(f"listen failed: {server.errorString()}")
            return None
        _log("listening")

        def trigger():
            try:
                _log("trigger capture")
                app.start_capture("region")
            except Exception:
                _log("trigger error:\n" + traceback.format_exc())

        def on_new():
            try:
                conn = server.nextPendingConnection()
                if conn is None:
                    _log("on_new: no pending connection")
                    return
                _log("new connection")

                def read():
                    try:
                        data = bytes(conn.readAll())
                        _log(f"read {data!r}")
                        if b"capture" in data:
                            QTimer.singleShot(60, trigger)
                    except Exception:
                        _log("read error:\n" + traceback.format_exc())

                conn.readyRead.connect(read)
                conn.disconnected.connect(conn.deleteLater)
            except Exception:
                _log("on_new error:\n" + traceback.format_exc())

        server.newConnection.connect(on_new)
        return server
    except Exception:
        _log("server setup error:\n" + traceback.format_exc())
        return None


def _run_ocr_headless(src: str, dst: str = "") -> int:
    """命令行 OCR（由主程序以子进程方式调用）：识别完即退出，内存全部归还。"""
    from jietu import ocr

    if not os.path.exists(src):
        print("无法读取图片:", src)
        return 2
    res = ocr.recognize_file(src)
    text = res.text if res.ok else f"ERR:{res.error}"
    print(text)
    if dst:
        try:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as ex:
            print("写入失败:", ex)
            return 3
    return 0 if res.ok else 1


def main() -> int:
    _ensure_streams()

    args = [a.lower() for a in sys.argv[1:]]

    if "--ocr-server" in args:
        # 常驻识别助手：由 jietu.ocr 启动，识别请求走临时目录交换文件
        from jietu import ocr

        paths = [a for a in sys.argv[1:] if not a.startswith("--")]
        return ocr.serve(paths[0] if paths else "")

    if "--ocr" in args:
        # 用法：JietuPro.exe --ocr <图片路径> [输出txt路径]
        paths = [a for a in sys.argv[1:] if not a.startswith("--")]
        return _run_ocr_headless(
            paths[0] if paths else "",
            paths[1] if len(paths) > 1 else "",
        )

    from jietu.icons import app_icon

    app = QApplication(sys.argv)
    _install_error_log()
    app.setApplicationName("Jietu Pro")
    app.setApplicationDisplayName(APP_TITLE)
    app.setOrganizationName("JietuPro")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    app.setFont(QFont("Microsoft YaHei UI", 9))

    if "--selftest" in args:
        from jietu.frozen_check import run_check

        return run_check(app)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_TITLE, "当前系统不支持托盘，程序无法运行。")
        return 1

    if _try_activate_existing():
        return 0

    from jietu.app import JietuApp

    controller = JietuApp(app)
    server = _start_ipc_server(controller)  # noqa: F841

    if "--fullscreen" in args:
        QTimer.singleShot(400, lambda: controller.start_capture("fullscreen"))
    elif "--capture" in args:
        QTimer.singleShot(400, lambda: controller.start_capture("region"))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
