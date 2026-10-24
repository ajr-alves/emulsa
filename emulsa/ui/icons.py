"""Simple line icons drawn in code, so they follow the theme and stay sharp on any display."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme


def _canvas(size: int):
    pm = QPixmap(size * 3, size * 3)
    pm.setDevicePixelRatio(3)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _pen(color: QColor, width: float = 1.5) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def icon(name: str, size: int = 18, color: str = "muted") -> QIcon:
    pm, p = _canvas(size)
    col = theme.qc(color) if color in theme.LIGHT else QColor(color)
    p.setPen(_pen(col))
    p.setBrush(Qt.NoBrush)
    s = size
    m = s * 0.18
    path = QPainterPath()
    if name == "folder":
        path.moveTo(m, s * 0.3); path.lineTo(s * 0.42, s * 0.3); path.lineTo(s * 0.5, s * 0.4)
        path.lineTo(s - m, s * 0.4); path.lineTo(s - m, s - m * 1.2); path.lineTo(m, s - m * 1.2); path.closeSubpath()
        p.drawPath(path)
    elif name == "plus":
        p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m)); p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))
    elif name == "compare":
        r = QRectF(m, m * 1.2, s - 2 * m, s - 2.4 * m)
        p.drawRoundedRect(r, 2, 2)
        p.drawLine(QPointF(s / 2, m * 0.6), QPointF(s / 2, s - m * 0.6))
        p.setBrush(col); p.setPen(Qt.NoPen)
        p.drawRect(QRectF(r.x(), r.y(), r.width() / 2, r.height()))
    elif name == "export":
        p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s * 0.62))
        p.drawLine(QPointF(s * 0.32, s * 0.3), QPointF(s / 2, m)); p.drawLine(QPointF(s * 0.68, s * 0.3), QPointF(s / 2, m))
        path.moveTo(m, s * 0.55); path.lineTo(m, s - m); path.lineTo(s - m, s - m); path.lineTo(s - m, s * 0.55)
        p.drawPath(path)
    elif name == "more":
        p.setBrush(col); p.setPen(Qt.NoPen)
        for x in (0.25, 0.5, 0.75):
            p.drawEllipse(QPointF(s * x, s / 2), s * 0.07, s * 0.07)
    elif name in ("star", "star-filled"):
        import math
        pts = []
        for i in range(10):
            r = (s / 2 - m * 0.6) if i % 2 == 0 else (s / 2 - m * 0.6) * 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(QPointF(s / 2 + r * math.cos(a), s / 2 + 0.5 + r * math.sin(a)))
        path.moveTo(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        path.closeSubpath()
        if name == "star-filled":
            p.setBrush(col)
        p.drawPath(path)
    elif name == "chevron-down":
        path.moveTo(s * 0.3, s * 0.4); path.lineTo(s / 2, s * 0.6); path.lineTo(s * 0.7, s * 0.4); p.drawPath(path)
    elif name == "chevron-right":
        path.moveTo(s * 0.4, s * 0.3); path.lineTo(s * 0.6, s / 2); path.lineTo(s * 0.4, s * 0.7); p.drawPath(path)
    elif name == "close":
        p.drawLine(QPointF(m * 1.4, m * 1.4), QPointF(s - m * 1.4, s - m * 1.4))
        p.drawLine(QPointF(s - m * 1.4, m * 1.4), QPointF(m * 1.4, s - m * 1.4))
    elif name == "settings":
        p.drawEllipse(QPointF(s / 2, s / 2), s * 0.13, s * 0.13)
        p.drawEllipse(QPointF(s / 2, s / 2), s * 0.32, s * 0.32)
        import math
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(s / 2 + s * 0.32 * math.cos(a), s / 2 + s * 0.32 * math.sin(a)),
                       QPointF(s / 2 + s * 0.42 * math.cos(a), s / 2 + s * 0.42 * math.sin(a)))
    elif name == "send":
        p.drawLine(QPointF(s / 2, s - m), QPointF(s / 2, m))
        p.drawLine(QPointF(s * 0.28, s * 0.4), QPointF(s / 2, m)); p.drawLine(QPointF(s * 0.72, s * 0.4), QPointF(s / 2, m))
    elif name == "image":
        p.drawRoundedRect(QRectF(m, m * 1.2, s - 2 * m, s - 2.4 * m), 2, 2)
        path.moveTo(m, s * 0.68); path.lineTo(s * 0.4, s * 0.45); path.lineTo(s * 0.6, s * 0.62)
        path.lineTo(s * 0.7, s * 0.55); path.lineTo(s - m, s * 0.68); p.drawPath(path)
        p.drawEllipse(QPointF(s * 0.66, s * 0.36), s * 0.06, s * 0.06)
    elif name == "sparkle":
        def spark(cx, cy, r):
            sp = QPainterPath()
            sp.moveTo(cx, cy - r); sp.quadTo(cx, cy, cx + r, cy); sp.quadTo(cx, cy, cx, cy + r)
            sp.quadTo(cx, cy, cx - r, cy); sp.quadTo(cx, cy, cx, cy - r)
            return sp
        p.setBrush(col); p.setPen(Qt.NoPen)
        p.drawPath(spark(s * 0.44, s * 0.56, s * 0.34))
        p.drawPath(spark(s * 0.76, s * 0.24, s * 0.14))
    elif name == "undo":
        path.moveTo(s * 0.3, s * 0.42); path.lineTo(s * 0.62, s * 0.42)
        path.arcTo(QRectF(s * 0.45, s * 0.42, s * 0.36, s * 0.36), 90, -180); path.lineTo(s * 0.4, s * 0.78)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.44, s * 0.28)); p.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.44, s * 0.56))
    p.end()
    return QIcon(pm)
