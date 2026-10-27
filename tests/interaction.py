"""交互逻辑测试：模拟鼠标完成 框选 → 标注 → 撤销 → 复制。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from jietu.overlay import MODE_EDIT, MODE_SELECT, CaptureOverlay  # noqa: E402
from jietu.annotations import Annotation  # noqa: E402


class FakeShot:
    def __init__(self, rect):
        self.virtual = rect
        self.img = QImage(rect.size(), QImage.Format_ARGB32)
        self.img.fill(QColor("#3A7BD5"))

    def paint(self, p, target=None):
        p.drawImage(QRectF(self.virtual), self.img)

    def crop(self, r):
        return QPixmap.fromImage(self.img.copy(r.translated(-self.virtual.topLeft())))

    def screen_at(self, pt):
        return None

    def dpr_at(self, pt):
        return 1.0

    def pixel(self, pt):
        return QColor("#3A7BD5")


def ev(kind, x, y, buttons=Qt.NoButton, button=Qt.LeftButton):
    lp = QPointF(x, y)
    gp = QPointF(x, y)
    return QMouseEvent(kind, lp, gp, button, buttons, Qt.NoModifier)


ov = CaptureOverlay(FakeShot(QRect(0, 0, 1200, 800)), "region")
ov.begin()
assert ov.mode == MODE_SELECT
print("[1] overlay created, mode = select")

# 拖拽框选
ov.mousePressEvent(ev(QEvent.MouseButtonPress, 100, 100, Qt.LeftButton))
ov.mouseMoveEvent(ev(QEvent.MouseMove, 300, 260, Qt.LeftButton))
ov.mouseMoveEvent(ev(QEvent.MouseMove, 500, 400, Qt.LeftButton))
ov.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 500, 400))
assert ov.mode == MODE_EDIT, "未进入编辑模式"
assert ov.sel == QRect(100, 100, 400, 300), ov.sel
assert ov.toolbar is not None and ov.toolbar.isVisible()
print("[2] drag select ok, sel =", ov.sel, "toolbar visible =", ov.toolbar.isVisible())

# 绘制矩形
ov.set_tool("rect")
ov.mousePressEvent(ev(QEvent.MouseButtonPress, 150, 150, Qt.LeftButton))
ov.mouseMoveEvent(ev(QEvent.MouseMove, 320, 280, Qt.LeftButton))
ov.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 320, 280))
assert len(ov.annotations) == 1, len(ov.annotations)
a = ov.annotations[0]
assert a.kind == "rect" and abs(a.end.x() - 220) < 1, (a.kind, a.end)
print("[3] draw rect ok, local end =", a.end)

# 画笔
ov.set_tool("pen")
ov.mousePressEvent(ev(QEvent.MouseButtonPress, 200, 300, Qt.LeftButton))
for i in range(10):
    ov.mouseMoveEvent(ev(QEvent.MouseMove, 200 + i * 8, 300 + i * 4, Qt.LeftButton))
ov.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 280, 340))
assert len(ov.annotations) == 2
assert len(ov.annotations[1].points) > 5
print("[4] pen ok, points =", len(ov.annotations[1].points))

# 序号
ov.set_tool("number")
ov.mousePressEvent(ev(QEvent.MouseButtonPress, 400, 200, Qt.LeftButton))
ov.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 400, 200))
assert len(ov.annotations) == 3 and ov.annotations[2].number == 1
print("[5] number badge ok")

# 撤销 / 重做
ov.do_undo()
assert len(ov.annotations) == 2
ov.do_undo()
assert len(ov.annotations) == 1
ov.do_redo()
assert len(ov.annotations) == 2
print("[6] undo/redo ok")

# 输出
pm = ov.render()
assert pm.width() == 400 and pm.height() == 300, pm.size()
print("[8] render ok", pm.size())

# 复制并关闭
ov.do_copy()
assert not app.clipboard().pixmap().isNull()
print("[9] clipboard ok", app.clipboard().pixmap().size())

# 第二次框选（验证窗口可复用新实例）
ov2 = CaptureOverlay(FakeShot(QRect(0, 0, 1200, 800)), "region")
ov2.begin()
ov2.detector = None  # 无窗口可识别时才走“过小选区取消”分支
ov2.mousePressEvent(ev(QEvent.MouseButtonPress, 10, 10, Qt.LeftButton))
ov2.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 15, 15))
assert ov2.mode == MODE_SELECT and not ov2.sel_valid, "过小的选区应被取消"
print("[10] tiny selection cancelled ok")

# 编辑模式下点击选区外：开始重新框选，且不产生新图元
ov2.sel = QRect(100, 100, 400, 300)
ov2.sel_valid = True
ov2._enter_edit()
ov2.annotations.append(Annotation("rect", QPointF(10, 10), "#FF3B30", 3))
ov2.mousePressEvent(ev(QEvent.MouseButtonPress, 1100, 700, Qt.LeftButton))
ov2.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 1100, 700))
assert ov2.mode == MODE_SELECT, ov2.mode
assert not ov2.annotations, "重新框选时应清空上一轮的标注"
print("[10b] click outside starts new selection ok")
ov2.finish()

# 回归：反复截图不得残留窗口 / 位图（曾因 WA_DeleteOnClose=False 每次泄漏整屏截图）
import gc  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

for _ in range(5):
    ov3 = CaptureOverlay(FakeShot(QRect(0, 0, 1200, 800)), "region")
    ov3.begin()
    ov3.sel = QRect(100, 100, 400, 300)
    ov3.sel_valid = True
    ov3._enter_edit()
    ov3.annotations.append(Annotation("rect", QPointF(10, 10), "#FF3B30", 3))
    ov3.render()
    ov3.finish()
    del ov3
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    app.processEvents()

left = [w for w in app.topLevelWidgets() if type(w).__name__ == "CaptureOverlay"]
assert not left, f"残留 {len(left)} 个 CaptureOverlay 窗口（内存泄漏）"
print("[11] no leaked overlay windows ok")

print("INTERACTION TESTS PASSED")
