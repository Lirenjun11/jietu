"""无头自检：验证导入、标注渲染、输出尺寸。运行：python tests/selftest.py"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from jietu.annotations import Annotation, draw_annotation  # noqa: E402
from jietu.capture import Shot, WindowDetector  # noqa: E402
from jietu.icons import app_icon, color_dot_icon, make_icon, width_icon  # noqa: E402
from jietu.overlay import CaptureOverlay  # noqa: E402
from jietu.pin import PinWindow  # noqa: E402
from jietu.settings_dialog import SettingsDialog  # noqa: E402
from jietu.toolbar import ColorPopup, ToolBar, WidthPopup  # noqa: E402

print("[1] imports ok")


class FakeShot:
    """合成截图，便于无头验证"""

    def __init__(self, rect: QRect):
        self.virtual = rect
        self.img = QImage(rect.size(), QImage.Format_ARGB32)
        self.img.fill(QColor("#3A7BD5"))

    def paint(self, p: QPainter, target=None):
        p.drawImage(QRectF(self.virtual), self.img)

    def crop(self, r: QRect) -> QPixmap:
        sub = self.img.copy(r.translated(-self.virtual.topLeft()))
        pm = QPixmap.fromImage(sub)
        return pm

    def screen_at(self, pt):
        return None

    def dpr_at(self, pt) -> float:
        return 1.0

    def pixel(self, pt) -> QColor:
        return QColor("#3A7BD5")


# --- 图标
for name in ("rect", "ellipse", "arrow", "line", "pen", "highlight", "mosaic",
             "text", "number", "undo", "redo", "save", "copy", "pin", "close",
             "settings", "folder", "fullscreen", "window", "delay", "crop"):
    assert not make_icon(name, 22).isNull(), name
assert not app_icon().isNull()
assert not color_dot_icon("#FF3B30").isNull()
assert not width_icon(3).isNull()
print("[2] icons ok")

# --- 各类型标注渲染
kinds = ["rect", "ellipse", "arrow", "line", "pen", "highlight", "mosaic", "text", "number"]
img = QImage(400, 300, QImage.Format_ARGB32)
img.fill(QColor("#204060"))
base = QImage(400, 300, QImage.Format_ARGB32)
base.fill(QColor("#808080"))
p = QPainter(img)
for i, k in enumerate(kinds):
    a = Annotation(k, QPointF(20 + i * 8, 30), "#FF3B30", 3)
    a.end = QPointF(90 + i * 8, 120)
    a.points = [QPointF(20, 200), QPointF(40, 180), QPointF(60, 210), QPointF(80, 190)]
    a.text = "测试"
    a.number = i + 1
    draw_annotation(p, a, base, 1.0)
p.end()
assert img.pixelColor(5, 5).name() == "#204060"
bg = QColor("#204060")
changed = sum(
    1
    for y in range(0, 300, 3)
    for x in range(0, 400, 3)
    if img.pixelColor(x, y) != bg
)
assert changed > 300, f"标注未绘制，仅 {changed} 个像素变化"
print("[3] annotations ok")

# --- Overlay 全链路
shot = FakeShot(QRect(0, 0, 1200, 800))
ov = CaptureOverlay(shot, "region")
ov.sel = QRect(100, 100, 400, 300)
ov.sel_valid = True
ov._enter_edit()
assert ov.mode == 1
assert ov.base_phys.width() == 400 and ov.base_phys.height() == 300, ov.base_phys.size()

ov.annotations.append(Annotation("rect", QPointF(20, 20), "#FF3B30", 4))
ov.annotations[-1].end = QPointF(200, 160)
ov.annotations.append(Annotation("arrow", QPointF(30, 250), "#FFCC00", 4))
ov.annotations[-1].end = QPointF(300, 180)
t = Annotation("text", QPointF(50, 60), "#FFFFFF", 4)
t.text = "Hello 截图"
ov.annotations.append(t)
m = Annotation("mosaic", QPointF(250, 30), "#FF3B30", 4)
m.end = QPointF(360, 120)
ov.annotations.append(m)
n = Annotation("number", QPointF(320, 200), "#007AFF", 4)
n.number = 1
ov.annotations.append(n)

out = ov.render()
assert out.width() == 400 and out.height() == 300, out.size()
img2 = out.toImage()
assert img2.pixelColor(10, 10).name() == "#3a7bd5", img2.pixelColor(10, 10).name()
assert img2.pixelColor(30, 20) != QColor("#3a7bd5"), "矩形未渲染"
print("[4] overlay render ok ->", out.size())

tmp = os.path.join(tempfile.gettempdir(), "jietu_selftest.png")
assert out.save(tmp, "PNG"), "保存失败"
print("[5] save ok ->", tmp, os.path.getsize(tmp), "bytes")

# --- 工具条 / 弹层 / 设置 / 贴图 / 窗口检测
tb = ToolBar()
assert tb.width() > 300
tb.set_tool("arrow")
assert tb.current_tool == "arrow"
tb.set_color("#00C7BE")
tb.set_width(5)
ColorPopup("#FF3B30")
WidthPopup(3)
print("[6] toolbar ok, width =", tb.width())

dlg = SettingsDialog()
dlg.apply()
print("[7] settings ok")

pin = PinWindow(QPixmap.fromImage(img2))
pin._set_opacity(0.8)
pin._zoom_to(2.0)
assert pin.width() == 800, pin.width()
pin.close()
print("[8] pin ok")

det = WindowDetector()
if det.ok:
    r = det.window_at(10, 10)
    print("[9] window detect ok:", "hit" if r else "none")
else:
    print("[9] window detect unavailable")

print("ALL CHECKS PASSED")
