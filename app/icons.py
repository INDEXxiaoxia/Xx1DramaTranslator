"""轻量矢量图标：不依赖外部资源文件。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from app.theme import Colors


def _pix(size: int, draw) -> QIcon:
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(dpr, dpr)
    draw(p, size)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def icon_play(color: str | None = None, size: int = 18) -> QIcon:
    col = QColor(color or Colors.ink)

    def draw(p: QPainter, s: int) -> None:
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.22)
        path.lineTo(s * 0.78, s * 0.50)
        path.lineTo(s * 0.32, s * 0.78)
        path.closeSubpath()
        p.drawPath(path)

    return _pix(size, draw)


def icon_pause(color: str | None = None, size: int = 18) -> QIcon:
    col = QColor(color or Colors.ink)

    def draw(p: QPainter, s: int) -> None:
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        w = s * 0.16
        gap = s * 0.12
        x1 = s * 0.30
        x2 = s * 0.30 + w + gap
        y = s * 0.24
        h = s * 0.52
        p.drawRoundedRect(QRectF(x1, y, w, h), 1.5, 1.5)
        p.drawRoundedRect(QRectF(x2, y, w, h), 1.5, 1.5)

    return _pix(size, draw)


def icon_settings(color: str | None = None, size: int = 18) -> QIcon:
    col = QColor(color or Colors.ink)

    def draw(p: QPainter, s: int) -> None:
        cx, cy = s * 0.5, s * 0.5
        pen = QPen(col, max(1.4, s * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # 外圈齿轮简化为六角齿 + 内圆
        r_out = s * 0.34
        r_in = s * 0.18
        teeth = 8
        path = QPainterPath()
        for i in range(teeth * 2):
            ang = (i * 180.0 / teeth) - 90.0
            rad = r_out if i % 2 == 0 else r_out * 0.78
            from math import cos, radians, sin

            x = cx + rad * cos(radians(ang))
            y = cy + rad * sin(radians(ang))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(cx, cy), r_in, r_in)

    return _pix(size, draw)


def icon_plus(color: str | None = None, size: int = 16) -> QIcon:
    col = QColor(color or Colors.accent_deep)

    def draw(p: QPainter, s: int) -> None:
        pen = QPen(col, max(1.8, s * 0.14))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = s * 0.28
        p.drawLine(QPointF(s * 0.5, m), QPointF(s * 0.5, s - m))
        p.drawLine(QPointF(m, s * 0.5), QPointF(s - m, s * 0.5))

    return _pix(size, draw)


def icon_minus(color: str | None = None, size: int = 16) -> QIcon:
    col = QColor(color or Colors.err)

    def draw(p: QPainter, s: int) -> None:
        pen = QPen(col, max(1.8, s * 0.14))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = s * 0.28
        p.drawLine(QPointF(m, s * 0.5), QPointF(s - m, s * 0.5))

    return _pix(size, draw)


def icon_list(color: str | None = None, size: int = 18) -> QIcon:
    col = QColor(color or Colors.ink_muted)

    def draw(p: QPainter, s: int) -> None:
        pen = QPen(col, max(1.6, s * 0.11))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        xs, xe = s * 0.26, s * 0.74
        for y in (0.32, 0.50, 0.68):
            p.drawLine(QPointF(xs, s * y), QPointF(xe, s * y))

    return _pix(size, draw)
