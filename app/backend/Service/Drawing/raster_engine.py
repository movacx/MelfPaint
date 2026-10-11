from __future__ import annotations

from collections import deque
from typing import Iterable

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from backend.Service.Drawing.drawing_utils import reemplazar_imagen


def draw_line(
    image: QImage,
    start: QPointF,
    end: QPointF,
    color: QColor,
    width: float = 1.0,
    erase: bool = False,
    antialias: bool = True,
) -> None:
    """Dibuja un segmento y conserva correctamente el canal alfa."""

    if image.isNull():
        return
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
        if erase:
            # DestinationOut respeta el alfa del pincel: 50% reduce el alfa a la
            # mitad y 100% borra completamente. CompositionMode_Clear lo ignora.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        pen = QPen(QColor(color))
        pen.setWidthF(max(1.0, float(width)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        # Un clic también debe dejar una marca visible.
        if start == end:
            painter.drawPoint(start)
    finally:
        painter.end()


def _color_rgba(color: QColor) -> np.ndarray:
    return np.array([color.red(), color.green(), color.blue(), color.alpha()], dtype=np.uint8)


def flood_fill(image: QImage, point: QPoint, color: QColor, tolerance: int = 0) -> bool:
    """Rellena una región conectada usando un scanline rápido sobre NumPy."""

    if image.isNull() or not (0 <= point.x() < image.width() and 0 <= point.y() < image.height()):
        return False

    tolerance = max(0, min(255, int(tolerance)))
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    result = rgba.copy()
    height, width = result.height(), result.width()
    bpl = result.bytesPerLine()
    raw = np.frombuffer(result.bits(), dtype=np.uint8, count=result.sizeInBytes())
    pixels = raw.reshape(height, bpl)[:, : width * 4].reshape(height, width, 4)
    target = pixels[point.y(), point.x()].copy()
    replacement = _color_rgba(QColor(color))
    if np.array_equal(target, replacement):
        return False

    # RGB y alfa participan en la tolerancia. Se usa int16 para no desbordar uint8.
    distance = np.max(np.abs(pixels.astype(np.int16) - target.astype(np.int16)), axis=2)
    matches = distance <= tolerance
    painted = np.zeros((height, width), dtype=np.bool_)
    pending: deque[tuple[int, int]] = deque([(point.x(), point.y())])

    while pending:
        x, y = pending.pop()
        available = matches[y] & ~painted[y]
        if not available[x]:
            continue

        # Buscar límites por bloques de NumPy evita recorrer cada píxel en Python.
        blocked_left = np.flatnonzero(~available[:x])
        left = int(blocked_left[-1] + 1) if blocked_left.size else 0
        blocked_right = np.flatnonzero(~available[x + 1 :])
        right = int(x + blocked_right[0]) if blocked_right.size else width - 1
        painted[y, left : right + 1] = True

        for next_y in (y - 1, y + 1):
            if not 0 <= next_y < height:
                continue
            segment = matches[next_y, left : right + 1] & ~painted[next_y, left : right + 1]
            if not segment.any():
                continue
            starts = segment & np.concatenate((np.array([True], dtype=np.bool_), ~segment[:-1]))
            for index in np.flatnonzero(starts):
                pending.append((left + int(index), next_y))

    if not painted.any():
        return False
    pixels[painted] = replacement
    reemplazar_imagen(image, result)
    return True


def clear_masked_region(image: QImage, rect_x: int, rect_y: int, mask: QImage | None = None) -> None:
    """Limpia un rectángulo completo o solo los píxeles cubiertos por una máscara."""

    if image.isNull():
        return
    painter = QPainter(image)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        if mask is None or mask.isNull():
            return
        painter.drawImage(int(rect_x), int(rect_y), mask)
    finally:
        painter.end()


def sample_color(image: QImage, point: QPointF) -> QColor | None:
    if image.isNull():
        return None
    x = round(point.x())
    y = round(point.y())
    if not (0 <= x < image.width() and 0 <= y < image.height()):
        return None
    return QColor(image.pixelColor(x, y))


def interpolate_points(start: QPointF, end: QPointF, spacing: float) -> Iterable[QPointF]:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    distance = float(np.hypot(dx, dy))
    steps = max(1, int(np.ceil(distance / max(0.25, spacing))))
    for index in range(1, steps + 1):
        amount = index / steps
        yield QPointF(start.x() + dx * amount, start.y() + dy * amount)
