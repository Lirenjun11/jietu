"""可视化检查：真实抓屏后渲染选择态/编辑态，保存 PNG 供人工核对。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jietu.annotations import Annotation  # noqa: E402
from jietu.capture import Shot  # noqa: E402
from jietu.overlay import CaptureOverlay  # noqa: E402

OUT_DIR = os.path.join(ROOT, "tests", "shots")
os.makedirs(OUT_DIR, exist_ok=True)

app = QApplication(sys.argv)
shot = Shot()
ov = CaptureOverlay(shot, "region")
ov.begin()


def step_select():
    ov.sel = QRect(360, 240, 820, 500)
    ov.sel_valid = True
    ov.cursor_global = QPointF(720, 520)
    ov.inside = True
    ov.update()
    QTimer.singleShot(350, shot_select)


def shot_select():
    pm = ov.grab()
    pm.save(os.path.join(OUT_DIR, "1_select.png"), "PNG")
    print("select:", pm.width(), pm.height())
    ov.sel = QRect(360, 240, 820, 500)
    ov._enter_edit()
    QTimer.singleShot(400, step_edit)


def step_edit():
    a = Annotation("rect", QPointF(60, 70), "#FF3B30", 4)
    a.end = QPointF(330, 230)
    ov.annotations.append(a)

    b = Annotation("arrow", QPointF(380, 300), "#FFCC00", 4)
    b.end = QPointF(600, 190)
    ov.annotations.append(b)

    t = Annotation("text", QPointF(70, 280), "#FFFFFF", 4)
    t.text = "这里是重点说明"
    ov.annotations.append(t)

    m = Annotation("mosaic", QPointF(620, 330), "#FF3B30", 4)
    m.end = QPointF(770, 430)
    ov.annotations.append(m)

    n = Annotation("number", QPointF(100, 400), "#007AFF", 4)
    n.number = 1
    ov.annotations.append(n)

    h = Annotation("highlight", QPointF(430, 420), "#FFCC00", 3)
    h.end = QPointF(700, 420)
    ov.annotations.append(h)
    ov.update()
    QTimer.singleShot(450, shot_edit)


def shot_edit():
    pm = ov.grab()
    pm.save(os.path.join(OUT_DIR, "2_edit.png"), "PNG")
    print("edit:", pm.width(), pm.height())
    out = ov.render()
    out.save(os.path.join(OUT_DIR, "3_result.png"), "PNG")
    print("result:", out.width(), out.height())
    ov.finish()
    QTimer.singleShot(100, app.quit)


QTimer.singleShot(500, step_select)
app.exec()
print("done")
