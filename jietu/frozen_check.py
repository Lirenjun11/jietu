"""打包版自检：验证 frozen 环境下的抓屏、裁剪、标注、图片编码。

因为 exe 是无控制台程序，结果写到 %TEMP%\\jietu_exe_check.txt。
"""
from __future__ import annotations

import os
import tempfile
import time

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

OUT_TXT = os.path.join(tempfile.gettempdir(), "jietu_exe_check.txt")


def run_check(app) -> int:
    lines: list[str] = []
    ok = True
    try:
        from .capture import Shot
        from .annotations import Annotation, draw_annotation
        from .config import app_data_dir

        lines.append(f"time={time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"config_dir={app_data_dir()}")

        shot = Shot()
        lines.append(f"screens={len(shot.parts)} virtual={shot.virtual}")
        for p in shot.parts:
            lines.append(f"  screen={p.name} dpr={p.dpr} pixmap={p.pixmap.width()}x{p.pixmap.height()}")
            if p.pixmap.isNull():
                ok = False
                lines.append("  ERROR: null pixmap")

        pm = shot.crop(shot.virtual)
        if pm.isNull() or pm.width() < 100:
            ok = False
            lines.append("ERROR: crop failed")
        png = os.path.join(tempfile.gettempdir(), "jietu_exe_check.png")
        saved_png = pm.save(png, "PNG")
        lines.append(f"png save={saved_png} size={pm.width()}x{pm.height()} bytes={os.path.getsize(png) if saved_png else 0}")

        jpg = os.path.join(tempfile.gettempdir(), "jietu_exe_check.jpg")
        saved_jpg = pm.save(jpg, "JPG", 92)
        lines.append(f"jpg save={saved_jpg} bytes={os.path.getsize(jpg) if saved_jpg else 0}")
        if not (saved_png and saved_jpg):
            ok = False

        # 标注渲染
        img = QImage(300, 200, QImage.Format_ARGB32)
        img.fill(QColor("#334455"))
        painter = QPainter(img)
        for i, kind in enumerate(("rect", "ellipse", "arrow", "pen", "text", "number", "mosaic", "highlight", "line")):
            a = Annotation(kind, QPointF(10 + i * 5, 10), "#FF3B30", 3)
            a.end = QPointF(80 + i * 5, 90)
            a.points = [QPointF(10, 120), QPointF(40, 140), QPointF(70, 125)]
            a.text = "OK"
            a.number = 1
            draw_annotation(painter, a, img, 1.0)
        painter.end()
        changed = sum(
            1 for y in range(0, 200, 4) for x in range(0, 300, 4)
            if img.pixelColor(x, y) != QColor("#334455")
        )
        lines.append(f"annotations changed_pixels={changed}")
        if changed < 50:
            ok = False

        # 剪贴板
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setPixmap(pm)
        clip = QApplication.clipboard().pixmap()
        lines.append(f"clipboard={clip.width()}x{clip.height()}")
        if clip.isNull():
            ok = False

    except Exception as ex:  # noqa: BLE001
        ok = False
        import traceback

        lines.append("EXCEPTION:\n" + traceback.format_exc())

    lines.insert(0, "RESULT=" + ("PASS" if ok else "FAIL"))
    try:
        with open(OUT_TXT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
    return 0 if ok else 2
