from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QColor, QImage, QPainter


def crear_imagen_transparente(width: int, height: int) -> QImage:
    image = QImage(max(1, int(width)), max(1, int(height)), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    return image


def rectangulo_limitado(a: QPointF, b: QPointF, document: Any) -> QRect:
    ax, ay = round(a.x()), round(a.y())
    bx, by = round(b.x()), round(b.y())
    # Arrastrar de 100 a 300 selecciona 200 píxeles: el punto
    # final es el borde del rectángulo, no un píxel incluido.
    rect = QRect(min(ax, bx), min(ay, by), max(1, abs(bx - ax)), max(1, abs(by - ay)))
    return rect.intersected(QRect(0, 0, int(document.width), int(document.height)))


def obtener_id_capa(layer: Any, document: Any) -> str | int:
    if hasattr(layer, "id"):
        return layer.id
    return list(document.layers).index(layer)


def buscar_capa(document: Any, layer_id: str | int) -> Any | None:
    layers = list(getattr(document, "layers", []))
    if isinstance(layer_id, int) and 0 <= layer_id < len(layers):
        return layers[layer_id]
    for layer in layers:
        if getattr(layer, "id", None) == layer_id:
            return layer
    return None


def invalidar(document: Any, modified: bool = True, rect: QRect | None = None) -> None:
    if rect is not None:
        region = getattr(document, "invalidate_region", None)
        if callable(region):
            region(rect, modified)
            return
    invalidate = getattr(document, "invalidate", None)
    if not callable(invalidate):
        return
    try:
        invalidate(mark_modified=modified)
    except TypeError:
        try:
            invalidate(modified)
        except TypeError:
            invalidate()


def imagenes_iguales(first: QImage | None, second: QImage | None) -> bool:
    if first is None or second is None:
        return first is second
    if first.size() != second.size() or first.format() != second.format():
        first = first.convertToFormat(QImage.Format.Format_RGBA8888)
        second = second.convertToFormat(QImage.Format.Format_RGBA8888)
    if first.sizeInBytes() != second.sizeInBytes():
        return False
    a = np.frombuffer(first.constBits(), dtype=np.uint8, count=first.sizeInBytes())
    b = np.frombuffer(second.constBits(), dtype=np.uint8, count=second.sizeInBytes())
    return bool(np.array_equal(a, b))


def reemplazar_imagen(target: QImage, source: QImage) -> None:
    painter = QPainter(target)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(0, 0, source)
    finally:
        painter.end()


def copiar_qpoint(point: QPoint | QPointF | None) -> QPoint:
    if point is None:
        return QPoint()
    return QPoint(round(point.x()), round(point.y()))


def ancho_herramienta(settings: Any, brush: bool = False) -> float:
    nombres = ("brush_size", "stroke_width", "line_width") if brush else ("stroke_width", "line_width", "brush_size")
    for nombre in nombres:
        if hasattr(settings, nombre):
            try:
                return max(1.0, float(getattr(settings, nombre)))
            except (TypeError, ValueError):
                continue
    return 1.0


def valor_config(settings: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(settings, name):
            return getattr(settings, name)
    return default


def opcion_habilitada(settings: Any, flag: str, mode: str, default: bool) -> bool:
    if hasattr(settings, flag):
        return bool(getattr(settings, flag))
    value = str(getattr(settings, mode, "solid" if default else "none") or "").lower()
    return value not in {"none", "transparent", "sin_relleno", "sin_contorno"}
