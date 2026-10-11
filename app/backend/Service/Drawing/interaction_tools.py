from __future__ import annotations

from collections.abc import Callable
from inspect import signature
from typing import Any

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from backend.Service.Drawing.base_tool import PointerButton, Tool, normalizar_boton
from backend.Service.Drawing.drawing_utils import rectangulo_limitado
from backend.Service.Drawing.raster_engine import sample_color


def _send_color(callback: Callable[..., None], color: QColor, button: PointerButton) -> None:
    try:
        callback_signature = signature(callback)
    except (TypeError, ValueError):
        callback(QColor(color), button)
        return
    try:
        callback_signature.bind(QColor(color), button)
    except TypeError:
        callback(QColor(color))
    else:
        callback(QColor(color), button)


def _composite(document: Any) -> QImage:
    composite = getattr(document, "composite", None)
    if callable(composite):
        return composite()
    result = QImage(document.width, document.height, QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(QColor(0, 0, 0, 0))
    painter = QPainter(result)
    try:
        for layer in getattr(document, "layers", []):
            if not bool(getattr(layer, "visible", True)):
                continue
            painter.setOpacity(max(0.0, min(1.0, float(getattr(layer, "opacity", 1.0)))))
            painter.drawImage(0, 0, layer.image)
    finally:
        painter.end()
    return result


class ColorPickerTool(Tool):
    id = "picker"
    name = "Selector de color"
    cursor = Qt.CursorShape.WhatsThisCursor

    def __init__(self, callback: Callable[..., None] | None = None) -> None:
        self.callback = callback
        self.last_color: QColor | None = None

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        color = sample_color(_composite(document), point)
        if color is None or color.alpha() == 0:
            # Un píxel transparente no es un color con el que se pueda pintar.
            return
        color.setAlpha(255)
        self.last_color = color
        normalized = normalizar_boton(button)
        attr = "secondary_color" if normalized is PointerButton.SECONDARY else "primary_color"
        setattr(settings, attr, QColor(color))
        if self.callback is not None:
            _send_color(self.callback, color, normalized)


# Alias utilizado por algunas versiones de la cinta.
EyedropperTool = ColorPickerTool


class ZoomTool(Tool):
    id = "zoom"
    name = "Lupa"
    cursor = Qt.CursorShape.SizeAllCursor

    def __init__(self, callback: Callable[..., None] | None = None) -> None:
        self.callback = callback

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        normalized = normalizar_boton(button)
        direction = -1 if normalized is PointerButton.SECONDARY else 1
        if self.callback is None:
            current = max(0.01, float(getattr(settings, "zoom", 1.0)))
            settings.zoom = max(0.05, min(64.0, current * (0.8 if direction < 0 else 1.25)))
            return
        self.callback(QPointF(point), normalized)


class TextTool(Tool):
    id = "text"
    name = "Texto"
    cursor = Qt.CursorShape.IBeamCursor

    def __init__(self, callback: Callable[[QRect], None] | None = None) -> None:
        self.callback = callback
        self.start: QPointF | None = None
        self.end: QPointF | None = None
        self.requested_rect: QRect | None = None

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        self.start = QPointF(point)
        self.end = QPointF(point)
        self.requested_rect = QRect(round(point.x()), round(point.y()), 1, 1)

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        if self.start is None:
            return
        self.end = QPointF(point)
        self.requested_rect = rectangulo_limitado(self.start, self.end, document)

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        if self.start is None:
            return None
        rect = rectangulo_limitado(self.start, point, document)
        if rect.width() < 8 or rect.height() < 8:
            rect = QRect(round(self.start.x()), round(self.start.y()), 240, 90)
            rect = rect.intersected(QRect(0, 0, document.width, document.height))
        self.requested_rect = rect
        self.start = None
        self.end = None
        if self.callback is not None:
            self.callback(QRect(rect))
        return None

    def preview_rect(self) -> QRect | None:
        return QRect(self.requested_rect) if self.requested_rect is not None else None

    def consume_requested_rect(self) -> QRect | None:
        rect = self.preview_rect()
        self.requested_rect = None
        return rect

    def cancel(self, document: Any | None = None) -> None:
        self.start = None
        self.end = None
        self.requested_rect = None
