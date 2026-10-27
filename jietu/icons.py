"""用 QPainter 现画矢量图标，免去图片资源依赖。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

ICON_COLOR = "#E8EAED"


def _glyph(name: str, p: QPainter, color: QColor, w: float = 1.8) -> None:
    pen = QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if name == "rect":
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
    elif name == "select":
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(
            [
                QPointF(6, 3.5),
                QPointF(6, 18.5),
                QPointF(10, 14.8),
                QPointF(12.6, 20.5),
                QPointF(15.2, 19.3),
                QPointF(12.6, 13.8),
                QPointF(17.8, 13.8),
                QPointF(6, 3.5),
            ]
        )
    elif name == "ellipse":
        p.drawEllipse(QRectF(4, 5, 16, 14))
    elif name == "line":
        p.drawLine(QPointF(5, 19), QPointF(19, 5))
    elif name == "arrow":
        p.drawLine(QPointF(4.5, 19.5), QPointF(15.0, 9.0))
        head = QPolygonF([QPointF(19.5, 4.5), QPointF(19.8, 12.9), QPointF(11.1, 4.8)])
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(head)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
    elif name == "pen":
        path = QPainterPath(QPointF(4, 17))
        path.cubicTo(8, 6, 11, 20, 14, 12)
        path.cubicTo(16, 7, 18, 9, 20, 7)
        p.drawPath(path)
        p.setPen(QPen(color, w * 0.85, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))
    elif name == "highlight":
        p.setPen(QPen(color, 7, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(6.5, 16.5), QPointF(15, 8))
        p.setPen(pen)
        p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))
    elif name == "mosaic":
        for i in range(3):
            for j in range(3):
                r = QRectF(4 + i * 5.4, 4 + j * 5.4, 5.4, 5.4)
                p.setPen(QPen(color, 1.2))
                if (i + j) % 2 == 0:
                    p.fillRect(r.adjusted(0.7, 0.7, -0.7, -0.7), color)
    elif name == "ocr":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
        p.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(11, 8.5), QPointF(11, 15.5))
        p.drawLine(QPointF(8.2, 8.5), QPointF(11, 8.5))
        p.drawLine(QPointF(8.2, 12.2), QPointF(10.4, 12.2))
        p.drawLine(QPointF(13, 15.5), QPointF(17, 8.5))
        p.drawLine(QPointF(17, 15.5), QPointF(17, 15.5))
    elif name == "scroll":
        p.drawRoundedRect(QRectF(6, 3.5, 12, 17), 2, 2)
        p.drawLine(QPointF(9, 7.5), QPointF(15, 7.5))
        p.drawLine(QPointF(9, 10.5), QPointF(15, 10.5))
        p.drawLine(QPointF(9, 13.5), QPointF(15, 13.5))
        p.drawPolyline(
            [QPointF(9, 17.2), QPointF(12, 20.2), QPointF(15, 17.2)]
        )
    elif name == "beautify":
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 2.5, 2.5)
        p.setPen(QPen(color, 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(4, 7), QPointF(4, 4))
        p.drawLine(QPointF(4, 4), QPointF(7, 4))
        p.drawLine(QPointF(17, 4), QPointF(20, 4))
        p.drawLine(QPointF(20, 4), QPointF(20, 7))
        p.drawLine(QPointF(4, 17), QPointF(4, 20))
        p.drawLine(QPointF(4, 20), QPointF(7, 20))
        p.drawLine(QPointF(17, 20), QPointF(20, 20))
        p.drawLine(QPointF(20, 20), QPointF(20, 17))
    elif name == "history":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.drawLine(QPointF(12, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(15.5, 14))
    elif name == "text":
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(5, 5.5), QPointF(19, 5.5))
        p.drawLine(QPointF(12, 5.5), QPointF(12, 19))
    elif name == "number":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(12, 8), QPointF(12, 16))
        p.drawLine(QPointF(9.5, 10.2), QPointF(12, 8))
    elif name == "undo":
        path = QPainterPath(QPointF(5, 12))
        path.arcTo(QRectF(4.5, 5, 15, 14), 180, -230)
        p.drawPath(path)
        p.drawLine(QPointF(5, 12), QPointF(5, 6.5))
        p.drawLine(QPointF(5, 12), QPointF(10.5, 12))
    elif name == "redo":
        path = QPainterPath(QPointF(19, 12))
        path.arcTo(QRectF(4.5, 5, 15, 14), 0, 230)
        p.drawPath(path)
        p.drawLine(QPointF(19, 12), QPointF(19, 6.5))
        p.drawLine(QPointF(19, 12), QPointF(13.5, 12))
    elif name == "save":
        p.drawLine(QPointF(12, 4), QPointF(12, 14))
        p.drawPolyline(
            [QPointF(8, 10.5), QPointF(12, 14.5), QPointF(16, 10.5)]
        )
        p.drawPolyline(
            [QPointF(5, 16), QPointF(5, 19.5), QPointF(19, 19.5), QPointF(19, 16)]
        )
    elif name == "copy":
        p.drawRoundedRect(QRectF(4, 4, 12, 12), 1.6, 1.6)
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 1.6, 1.6)
    elif name == "pin":
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(12, 13), QPointF(12, 21))
        head = QPainterPath(QPointF(7, 4.5))
        head.lineTo(17, 4.5)
        head.lineTo(16, 9)
        head.lineTo(17.5, 13)
        head.lineTo(6.5, 13)
        head.lineTo(8, 9)
        head.closeSubpath()
        p.drawPath(head)
    elif name == "close":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "settings":
        p.drawEllipse(QRectF(8.5, 8.5, 7, 7))
        for ang in range(0, 360, 45):
            import math

            a = math.radians(ang)
            x1 = 12 + math.cos(a) * 6.2
            y1 = 12 + math.sin(a) * 6.2
            x2 = 12 + math.cos(a) * 8.6
            y2 = 12 + math.sin(a) * 8.6
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "folder":
        p.drawPolyline(
            [
                QPointF(3.5, 7),
                QPointF(9, 7),
                QPointF(10.5, 9),
                QPointF(20.5, 9),
                QPointF(20.5, 19),
                QPointF(3.5, 19),
                QPointF(3.5, 7),
            ]
        )
    elif name == "fullscreen":
        p.drawLine(QPointF(4, 9.5), QPointF(4, 4))
        p.drawLine(QPointF(4, 4), QPointF(9.5, 4))
        p.drawLine(QPointF(14.5, 4), QPointF(20, 4))
        p.drawLine(QPointF(20, 4), QPointF(20, 9.5))
        p.drawLine(QPointF(20, 14.5), QPointF(20, 20))
        p.drawLine(QPointF(20, 20), QPointF(14.5, 20))
        p.drawLine(QPointF(9.5, 20), QPointF(4, 20))
        p.drawLine(QPointF(4, 20), QPointF(4, 14.5))
    elif name == "window":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2, 2)
        p.drawLine(QPointF(3.5, 9), QPointF(20.5, 9))
    elif name == "delay":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.drawLine(QPointF(12, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(15.5, 14))
    elif name == "crop":
        p.drawLine(QPointF(6, 2.5), QPointF(6, 16))
        p.drawLine(QPointF(6, 16), QPointF(19.5, 16))
        p.drawLine(QPointF(4, 6), QPointF(17.5, 6))
        p.drawLine(QPointF(17.5, 6), QPointF(17.5, 19.5))
    elif name == "eraser":
        path = QPainterPath(QPointF(5, 15))
        path.lineTo(11, 5)
        path.lineTo(19, 10)
        path.lineTo(13, 20)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(8, 17.5), QPointF(16, 17.5))


def make_pixmap(name: str, size: int = 22, color: str = ICON_COLOR, ratio: float = 2.0) -> QPixmap:
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    _glyph(name, p, QColor(color))
    p.end()
    return pm


def make_icon(name: str, size: int = 22, color: str = ICON_COLOR) -> QIcon:
    icon = QIcon()
    icon.addPixmap(make_pixmap(name, size, color, 2.0), QIcon.Normal, QIcon.Off)
    return icon


def color_dot_icon(color: str, size: int = 22) -> QIcon:
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(color)
    p.setPen(QPen(QColor("#FFFFFF"), 1.6))
    p.setBrush(c)
    p.drawEllipse(QRectF(3, 3, size - 6, size - 6))
    p.end()
    return QIcon(pm)


def width_icon(width: int, size: int = 22, color: str = ICON_COLOR) -> QIcon:
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(color), 1.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(4, 6, size - 4, 6)
    p.setPen(QPen(QColor(color), max(1, width), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(4, size / 2, size - 4, size / 2)
    p.setPen(QPen(QColor(color), 1.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(4, size - 6, size - 4, size - 6)
    p.end()
    return QIcon(pm)


def app_icon(size: int = 64) -> QIcon:
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor("#2F6FEB"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.22, size * 0.22)

    p.setPen(QPen(QColor("#FFFFFF"), size * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    s = size
    m = s * 0.26
    p.drawLine(QPointF(m, m + s * 0.10), QPointF(m, m))
    p.drawLine(QPointF(m, m), QPointF(m + s * 0.10, m))
    p.drawLine(QPointF(s - m - s * 0.10, m), QPointF(s - m, m))
    p.drawLine(QPointF(s - m, m), QPointF(s - m, m + s * 0.10))
    p.drawLine(QPointF(s - m, s - m - s * 0.10), QPointF(s - m, s - m))
    p.drawLine(QPointF(s - m, s - m), QPointF(s - m - s * 0.10, s - m))
    p.drawLine(QPointF(m + s * 0.10, s - m), QPointF(m, s - m))
    p.drawLine(QPointF(m, s - m), QPointF(m, s - m - s * 0.10))
    p.end()
    return QIcon(pm)
