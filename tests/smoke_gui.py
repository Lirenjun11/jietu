"""真实桌面冒烟测试：抓屏 / 托盘 / 热键 / 输出保存。约 2 秒后自动退出。"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jietu.app import JietuApp  # noqa: E402
from jietu.capture import Shot  # noqa: E402

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

ctrl = JietuApp(app)
print("tray visible:", ctrl.tray.isVisible())

shot = Shot()
print("virtual desktop:", shot.virtual)
for p in shot.parts:
    print(f"  screen {p.name}: geom={p.geometry} dpr={p.dpr} pixmap={p.pixmap.width()}x{p.pixmap.height()}")
    assert not p.pixmap.isNull(), "抓屏失败"

full = shot.crop(shot.virtual)
print("full crop:", full.width(), "x", full.height())
assert not full.isNull() and full.width() > 100

# 中间区域裁剪
r = QRect(
    shot.virtual.x() + shot.virtual.width() // 4,
    shot.virtual.y() + shot.virtual.height() // 4,
    shot.virtual.width() // 2,
    shot.virtual.height() // 2,
)
part = shot.crop(r)
tmp = os.path.join(tempfile.gettempdir(), "jietu_smoke_crop.png")
assert part.save(tmp, "PNG")
print("region crop:", part.width(), "x", part.height(), "->", os.path.getsize(tmp), "bytes")

px = shot.pixel(shot.virtual.center())
print("pixel at center:", px.name())

print("hotkeys registered:", list(ctrl.hotkeys.callbacks.keys()))
QTimer.singleShot(1200, ctrl.quit)
code = app.exec()
print("exit", code)
