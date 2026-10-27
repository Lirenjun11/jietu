"""标注图元：定义、绘制、命中测试、包围盒与变换。坐标均为选区局部逻辑坐标。"""
from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

FONT_FAMILY = "Microsoft YaHei UI"


class Annotation:
    __slots__ = (
        "kind",
        "start",
        "end",
        "points",
        "color",
        "width",
        "text",
        "number",
        "filled",
        "alpha",
        "uid",
    )

    def __init__(self, kind: str, start: QPointF, color: str | QColor, width: int = 3):
        self.kind = kind
        self.start = QPointF(start)
        self.end = QPointF(start)
        self.points: list[QPointF] = [QPointF(start)]
        self.color = QColor(color)
        self.width = max(1, int(width))
        self.text = ""
        self.number = 0
        self.filled = False
        self.alpha = 255
        self.uid = uuid.uuid4().hex

    # 矩形范围
    def bounds(self) -> QRectF:
        if self.kind == "pen":
            xs = [p.x() for p in self.points] or [self.start.x()]
            ys = [p.y() for p in self.points] or [self.start.y()]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if self.kind == "text":
            return text_bounds(self)
        if self.kind == "number":
            r = max(11.0, 8 + self.width * 2.2)
            return QRectF(self.start.x(), self.start.y(), r * 2, r * 2)
        return QRectF(self.start, self.end).normalized()

    def is_empty(self) -> bool:
        if self.kind in ("text", "number"):
            return False
        b = self.bounds()
        return b.width() < 2 and b.height() < 2

    def clone(self) -> "Annotation":
        a = Annotation(self.kind, self.start, self.color, self.width)
        a.end = QPointF(self.end)
        a.points = [QPointF(p) for p in self.points]
        a.text = self.text
        a.number = self.number
        a.filled = self.filled
        a.alpha = self.alpha
        return a

    # ---------------------------------------------------------- 变换
    def translate(self, dx: float, dy: float) -> None:
        d = QPointF(dx, dy)
        self.start += d
        self.end += d
        self.points = [p + d for p in self.points]

    def scale_by(self, sx: float, sy: float) -> None:
        def sp(p: QPointF) -> QPointF:
            return QPointF(p.x() * sx, p.y() * sy)

        self.start = sp(self.start)
        self.end = sp(self.end)
        self.points = [sp(p) for p in self.points]
        self.width = max(1, int(round(self.width * min(sx, sy))))

    def hit(self, pt: QPointF, tol: float = 6.0) -> bool:
        """判断点是否命中图元（用于选中）。"""
        b = self.bounds()
        if self.kind in ("rect", "ellipse", "mosaic"):
            return b.adjusted(-tol, -tol, tol, tol).contains(pt)
        if self.kind in ("line", "arrow", "highlight"):
            return _dist_to_segment(pt, self.start, self.end) <= max(tol, self.width)
        if self.kind == "pen":
            pts = self.points
            if len(pts) == 1:
                return _dist(pt, pts[0]) <= max(tol, self.width)
            for i in range(1, len(pts)):
                if _dist_to_segment(pt, pts[i - 1], pts[i]) <= max(tol, self.width):
                    return True
            return False
        return b.adjusted(-tol, -tol, tol, tol).contains(pt)


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay, bx, by, px, py = a.x(), a.y(), b.x(), b.y(), p.x(), p.y()
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ------------------------------------------------------------------ 绘制
def _pen(color: QColor, width: float, alpha: int = 255) -> QPen:
    c = QColor(color)
    c.setAlpha(alpha)
    p = QPen(c, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    return p


def _draw_arrow(p: QPainter, a: Annotation) -> None:
    s, e = a.start, a.end
    dx, dy = e.x() - s.x(), e.y() - s.y()
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    head_len = min(max(a.width * 4.2, 12), length * 0.55)
    head_w = head_len * 0.62

    tip = QPointF(e)
    base = QPointF(e.x() - ux * head_len, e.y() - uy * head_len)
    left = QPointF(base.x() - uy * head_w / 2, base.y() + ux * head_w / 2)
    right = QPointF(base.x() + uy * head_w / 2, base.y() - ux * head_w / 2)

    p.setPen(_pen(a.color, a.width, a.alpha))
    p.setBrush(Qt.NoBrush)
    p.drawLine(s, QPointF(base.x() + ux * head_len * 0.25, base.y() + uy * head_len * 0.25))

    p.setPen(Qt.NoPen)
    c = QColor(a.color)
    c.setAlpha(a.alpha)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([tip, left, right]))


def _draw_number(p: QPainter, a: Annotation) -> None:
    r = max(11.0, 8 + a.width * 2.2)
    center = QPointF(a.start.x() + r, a.start.y() + r)
    c = QColor(a.color)
    c.setAlpha(a.alpha)
    p.setPen(QPen(QColor(255, 255, 255, 210), max(1.5, a.width * 0.5)))
    p.setBrush(c)
    p.drawEllipse(center, r, r)

    f = QFont(FONT_FAMILY, int(r * 1.15))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(
        QRectF(center.x() - r, center.y() - r, r * 2, r * 2),
        Qt.AlignCenter,
        str(a.number),
    )


def _draw_text(p: QPainter, a: Annotation) -> None:
    size = max(12, int(a.width * 4.5))
    f = QFont(FONT_FAMILY, size)
    p.setFont(f)
    fm = QFontMetricsF(f)
    lines = a.text.split("\n")
    lh = fm.lineSpacing()
    x, y = a.start.x(), a.start.y() + fm.ascent()

    # 文字阴影提高可读性
    p.setPen(QColor(0, 0, 0, 110))
    for i, line in enumerate(lines):
        p.drawText(QPointF(x + 1.2, y + i * lh + 1.2), line)
    c = QColor(a.color)
    c.setAlpha(a.alpha)
    p.setPen(c)
    for i, line in enumerate(lines):
        p.drawText(QPointF(x, y + i * lh), line)


def _draw_pen(p: QPainter, a: Annotation) -> None:
    if len(a.points) < 2:
        return
    path = QPainterPath(a.points[0])
    pts = a.points
    for i in range(1, len(pts) - 1):
        mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
        path.quadTo(pts[i], mid)
    path.lineTo(pts[-1])
    p.setPen(_pen(a.color, a.width, a.alpha))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _draw_highlight(p: QPainter, a: Annotation) -> None:
    pen = _pen(a.color, a.width * 4.5, min(110, a.alpha))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(a.start, a.end)


def _draw_mosaic(p: QPainter, a: Annotation, source: QImage | None, scale: float = 1.0) -> None:
    r = QRectF(a.start, a.end).normalized()
    if r.width() < 2 or r.height() < 2 or source is None or source.isNull():
        return
    sx, sy = r.x() * scale, r.y() * scale
    sw, sh = r.width() * scale, r.height() * scale
    pr = QRectF(sx, sy, sw, sh).toRect().intersected(source.rect())
    if pr.isEmpty():
        return
    sub = source.copy(pr)
    block = max(2, int(9 * scale))
    small = sub.scaled(
        max(1, sub.width() // block),
        max(1, sub.height() // block),
        Qt.IgnoreAspectRatio,
        Qt.FastTransformation,
    )
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    p.setClipRect(r)
    # 用缩放后的采样图铺满目标区域
    p.drawImage(r, small)
    p.restore()


def draw_annotation(
    p: QPainter,
    a: Annotation,
    mosaic_source: QImage | None = None,
    mosaic_scale: float = 1.0,
) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)

    if a.kind == "rect":
        r = QRectF(a.start, a.end).normalized()
        p.setPen(_pen(a.color, a.width, a.alpha))
        p.setBrush(QColor(a.color).lighter(160) if a.filled else Qt.NoBrush)
        if a.filled:
            c = QColor(a.color)
            c.setAlpha(60)
            p.setBrush(c)
        p.drawRect(r)
    elif a.kind == "ellipse":
        r = QRectF(a.start, a.end).normalized()
        p.setPen(_pen(a.color, a.width, a.alpha))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
    elif a.kind == "line":
        p.setPen(_pen(a.color, a.width, a.alpha))
        p.setBrush(Qt.NoBrush)
        p.drawLine(a.start, a.end)
    elif a.kind == "arrow":
        _draw_arrow(p, a)
    elif a.kind == "pen":
        _draw_pen(p, a)
    elif a.kind == "highlight":
        _draw_highlight(p, a)
    elif a.kind == "mosaic":
        _draw_mosaic(p, a, mosaic_source, mosaic_scale)
    elif a.kind == "text":
        _draw_text(p, a)
    elif a.kind == "number":
        _draw_number(p, a)

    p.restore()


def text_bounds(a: Annotation) -> QRectF:
    size = max(12, int(a.width * 4.5))
    f = QFont(FONT_FAMILY, size)
    fm = QFontMetricsF(f)
    lines = a.text.split("\n") or [""]
    w = max(fm.horizontalAdvance(l) for l in lines) + 6
    h = fm.lineSpacing() * len(lines) + 6
    return QRectF(a.start.x(), a.start.y(), w, h)


# ------------------------------------------------------------------ 工具定义
TOOL_DEFS = [
    ("select", "选择/移动", "V"),
    ("rect", "矩形", "R"),
    ("ellipse", "椭圆", "E"),
    ("arrow", "箭头", "A"),
    ("line", "直线", "L"),
    ("pen", "画笔", "P"),
    ("highlight", "高亮", "H"),
    ("mosaic", "马赛克", "M"),
    ("text", "文字", "T"),
    ("number", "序号", "N"),
]

TOOL_NAMES = {k: n for k, n, _ in TOOL_DEFS}
