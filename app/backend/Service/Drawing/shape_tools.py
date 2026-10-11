from __future__ import annotations

import math
import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from backend.Service.Drawing.base_tool import PointerButton, Tool, color_del_boton, normalizar_boton
from backend.Service.Drawing.commands import LayerImageCommand
from backend.Service.Drawing.drawing_utils import (
    ancho_herramienta,
    buscar_capa,
    crear_imagen_transparente,
    imagenes_iguales,
    invalidar,
    obtener_id_capa,
    opcion_habilitada,
    valor_config,
)
from backend.Service.Drawing.shape_engine import create_shape_preview, draw_shape, shape_path


HANDLE_NAMES = ("top_left", "top", "top_right", "right", "bottom_right", "bottom", "bottom_left", "left")


def handle_points(rect: QRectF) -> dict[str, QPointF]:
    return {
        "top_left": rect.topLeft(),
        "top": QPointF(rect.center().x(), rect.top()),
        "top_right": rect.topRight(),
        "right": QPointF(rect.right(), rect.center().y()),
        "bottom_right": rect.bottomRight(),
        "bottom": QPointF(rect.center().x(), rect.bottom()),
        "bottom_left": rect.bottomLeft(),
        "left": QPointF(rect.left(), rect.center().y()),
    }


def handle_tolerance(settings: Any) -> float:
    """Tolerancia de los tiradores en píxeles del documento (8 px en pantalla)."""

    try:
        zoom = float(valor_config(settings, "zoom", default=1.0))
    except (TypeError, ValueError):
        zoom = 1.0
    return max(1.5, 8.0 / max(0.05, zoom))


def hit_handle(rect: QRectF, point: QPointF, tolerance: float) -> str | None:
    for name, center in handle_points(rect).items():
        if abs(point.x() - center.x()) <= tolerance and abs(point.y() - center.y()) <= tolerance:
            return name
    return None


def resize_rect(rect: QRectF, handle: str, point: QPointF, keep_ratio: bool = False) -> QRectF:
    """Mueve los bordes indicados por el tirador y devuelve el rectángulo nuevo."""

    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
    if "left" in handle:
        left = point.x()
    if "right" in handle:
        right = point.x()
    if handle.startswith("top"):
        top = point.y()
    if handle.startswith("bottom"):
        bottom = point.y()
    result = QRectF(QPointF(min(left, right), min(top, bottom)), QPointF(max(left, right), max(top, bottom)))
    if keep_ratio and rect.width() > 0 and rect.height() > 0 and handle in {"top_left", "top_right", "bottom_left", "bottom_right"}:
        ratio = rect.width() / rect.height()
        width = max(result.width(), result.height() * ratio)
        height = width / ratio
        anchor_x = rect.right() if "left" in handle else rect.left()
        anchor_y = rect.bottom() if handle.startswith("top") else rect.top()
        x = anchor_x - width if "left" in handle else anchor_x
        y = anchor_y - height if handle.startswith("top") else anchor_y
        result = QRectF(x, y, width, height)
    if result.width() < 1.0:
        result.setWidth(1.0)
    if result.height() < 1.0:
        result.setHeight(1.0)
    return result


def cursor_for_handle(name: str | None) -> Qt.CursorShape:
    if name in {"top_left", "bottom_right"}:
        return Qt.CursorShape.SizeFDiagCursor
    if name in {"top_right", "bottom_left"}:
        return Qt.CursorShape.SizeBDiagCursor
    if name in {"left", "right"}:
        return Qt.CursorShape.SizeHorCursor
    if name in {"top", "bottom"}:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.CrossCursor


def _constrain_line(start: QPointF, end: QPointF) -> QPointF:
    """Con Mayús, la línea se ajusta a múltiplos de 45°."""

    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy)
    if length == 0:
        return QPointF(end)
    angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    return QPointF(start.x() + math.cos(angle) * length, start.y() + math.sin(angle) * length)


def _constrain_square(start: QPointF, end: QPointF) -> QPointF:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    side = max(abs(dx), abs(dy))
    return QPointF(start.x() + math.copysign(side, dx or 1.0), start.y() + math.copysign(side, dy or 1.0))


class ShapeTool(Tool):
    """Figura que permanece editable hasta confirmarla.

    Mientras está pendiente se puede mover, cambiar de tamaño con sus
    tiradores y actualizar su color, grosor, contorno y relleno. Se fija en
    la capa al hacer clic fuera, cambiar de herramienta o guardar.
    """

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, shape: str = "rectangle", name: str | None = None) -> None:
        self.shape = str(shape)
        self.id = self.shape
        self.name = name or self.shape.replace("_", " ").title()
        self._button = PointerButton.PRIMARY
        self._layer_id: str | int | None = None
        self._size: tuple[int, int] = (1, 1)
        self._points: list[QPointF] = []
        self._state = "idle"
        self._drag_handle: str | None = None
        self._drag_origin: QPointF | None = None
        self._drag_points: list[QPointF] = []
        self._drag_bounds = QRectF()
        self._preview: QImage | None = None
        self._last_click = 0.0
        self._pending_command: LayerImageCommand | None = None

    # ------------------------------------------------------------------
    # Geometría
    @property
    def _is_line(self) -> bool:
        return self.shape == "line"

    @property
    def _is_curve(self) -> bool:
        return self.shape == "curve"

    @property
    def _is_polygon(self) -> bool:
        return self.shape == "polygon"

    def _bounds(self) -> QRectF:
        if not self._points:
            return QRectF()
        if self._is_curve and len(self._points) >= 2:
            start, end, *controls = self._points
            path = shape_path("curve", start, end, controls or [start, end])
            return path.boundingRect()
        xs = [point.x() for point in self._points]
        ys = [point.y() for point in self._points]
        return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))

    def _point_bounds(self) -> QRectF:
        xs = [point.x() for point in self._points]
        ys = [point.y() for point in self._points]
        return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))

    def _render(self, settings: Any) -> None:
        if len(self._points) < 2 and not (self._is_polygon and self._points):
            self._preview = None
            return
        width, height = self._size
        outline, fill = self._colors(settings)
        stroke = ancho_herramienta(settings)
        outline_style = str(valor_config(settings, "outline_style", "outline_mode", default="solid"))
        fill_style = str(valor_config(settings, "fill_style", "fill_mode", default="solid"))

        if self._is_polygon and self._state in {"polygon", "polygon_drag", "drawing"}:
            # Mientras se construye, el polígono se ve como una línea abierta.
            image = crear_imagen_transparente(width, height)
            painter = QPainter(image)
            try:
                for start, end in zip(self._points, self._points[1:]):
                    draw_shape(painter, "line", start, end, outline or QColor(0, 0, 0), None, stroke, outline_style if outline else "solid")
            finally:
                painter.end()
            self._preview = image
            return

        if self._is_curve:
            start, end, *controls = self._points
            controls = controls or [start, end]
            if len(controls) == 1:
                controls = [controls[0], controls[0]]
            self._preview = create_shape_preview((width, height), "curve", start, end, outline, None, stroke, outline_style, fill_style, controls)
            return
        if self._is_polygon:
            bounds = self._point_bounds()
            self._preview = create_shape_preview(
                (width, height), "polygon", bounds.topLeft(), bounds.bottomRight(), outline, fill, stroke, outline_style, fill_style, list(self._points)
            )
            return
        start, end = self._points[0], self._points[1]
        self._preview = create_shape_preview((width, height), self.shape, start, end, outline, fill, stroke, outline_style, fill_style)

    def _colors(self, settings: Any) -> tuple[QColor | None, QColor | None]:
        primary = color_del_boton(settings, self._button)
        opposite = PointerButton.SECONDARY if self._button is PointerButton.PRIMARY else PointerButton.PRIMARY
        secondary = color_del_boton(settings, opposite)
        outline = primary if opcion_habilitada(settings, "outline_enabled", "outline_mode", True) else None
        fill = secondary if opcion_habilitada(settings, "fill_enabled", "fill_mode", False) else None
        if self.shape in {"line", "curve"} and outline is None:
            # Una línea sin contorno no se vería: siempre se dibuja.
            outline = primary
        return outline, fill

    # ------------------------------------------------------------------
    # Gestos
    def _begin(self, document: Any, point: QPointF, button: Any) -> None:
        self._button = normalizar_boton(button)
        self._layer_id = obtener_id_capa(document.active_layer, document)
        self._size = (int(document.width), int(document.height))
        self._points = [QPointF(point), QPointF(point)]
        self._state = "drawing"

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        point = QPointF(point)
        if self._state in {"curve_wait1", "curve_wait2"}:
            if self._state == "curve_wait1":
                self._points[2:] = [QPointF(point), QPointF(point)]
                self._state = "curve_bend1"
            else:
                self._points[3] = QPointF(point)
                self._state = "curve_bend2"
            self._render(settings)
            return
        if self._state == "polygon":
            self._polygon_click(document, point, settings)
            return
        if self._state == "pending":
            tolerance = handle_tolerance(settings)
            handle = self._hit(point, tolerance)
            if handle is not None:
                self._start_drag("resizing", point, handle)
                return
            if self._bounds().adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(point):
                self._start_drag("moving", point, None)
                return
            self._pending_command = self.commit_pending(document)
        self._begin(document, point, button)
        self._render(settings)

    def _polygon_click(self, document: Any, point: QPointF, settings: Any) -> None:
        tolerance = handle_tolerance(settings)
        now = time.monotonic()
        double_click = now - self._last_click < 0.4 and (point - self._points[-1]).manhattanLength() <= tolerance * 2
        self._last_click = now
        near_start = len(self._points) >= 3 and (point - self._points[0]).manhattanLength() <= tolerance * 2
        if double_click or near_start:
            self._close_polygon(settings)
            return
        self._points.append(QPointF(point))
        self._state = "polygon_drag"
        self._render(settings)

    def _close_polygon(self, settings: Any) -> None:
        # Se descartan vértices repetidos por el doble clic.
        unique: list[QPointF] = []
        for point in self._points:
            if not unique or (point - unique[-1]).manhattanLength() > 0.5:
                unique.append(point)
        self._points = unique
        if len(self._points) < 3:
            self.cancel()
            return
        self._state = "pending"
        self._render(settings)

    def _start_drag(self, state: str, point: QPointF, handle: str | None) -> None:
        self._state = state
        self._drag_handle = handle
        self._drag_origin = QPointF(point)
        self._drag_points = [QPointF(item) for item in self._points]
        self._drag_bounds = self._point_bounds() if not self._is_line else QRectF()

    def _hit(self, point: QPointF, tolerance: float) -> str | None:
        if self._is_line and len(self._points) >= 2:
            for name, center in (("start", self._points[0]), ("end", self._points[1])):
                if abs(point.x() - center.x()) <= tolerance and abs(point.y() - center.y()) <= tolerance:
                    return name
            return None
        return hit_handle(self._point_bounds(), point, tolerance)

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        point = QPointF(point)
        if self._state == "drawing":
            start = self._points[0]
            if self.shift:
                point = _constrain_line(start, point) if self.shape in {"line", "curve", "polygon"} else _constrain_square(start, point)
            self._points[1] = point
        elif self._state == "curve_bend1":
            self._points[2] = QPointF(point)
            self._points[3] = QPointF(point)
        elif self._state == "curve_bend2":
            self._points[3] = QPointF(point)
        elif self._state == "polygon_drag":
            if self.shift and len(self._points) >= 2:
                point = _constrain_line(self._points[-2], point)
            self._points[-1] = point
        elif self._state == "moving" and self._drag_origin is not None:
            delta = point - self._drag_origin
            self._points = [item + delta for item in self._drag_points]
        elif self._state == "resizing" and self._drag_handle is not None:
            self._resize_to(point)
        else:
            return
        self._render(settings)

    def _resize_to(self, point: QPointF) -> None:
        if self._drag_handle in {"start", "end"}:
            index = 0 if self._drag_handle == "start" else 1
            other = self._drag_points[1 - index]
            self._points[index] = _constrain_line(other, point) if self.shift else QPointF(point)
            return
        old = self._drag_bounds
        new = resize_rect(old, self._drag_handle or "bottom_right", point, self.shift)
        sx = new.width() / old.width() if old.width() > 0 else 1.0
        sy = new.height() / old.height() if old.height() > 0 else 1.0
        self._points = [
            QPointF(new.left() + (item.x() - old.left()) * sx, new.top() + (item.y() - old.top()) * sy)
            for item in self._drag_points
        ]

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        command = self._take_command()
        if self._state == "drawing":
            self.pointer_move(document, point, button, settings)
            start, end = self._points[0], self._points[1]
            tiny = max(abs(end.x() - start.x()), abs(end.y() - start.y())) < 2.0
            if self._is_polygon:
                self._points = [start] if tiny else [start, end]
                self._state = "polygon"
                self._last_click = time.monotonic()
            elif tiny:
                self.cancel()
            elif self._is_curve:
                self._points = [start, end, QPointF(start), QPointF(end)]
                self._state = "curve_wait1"
            else:
                self._state = "pending"
        elif self._state == "curve_bend1":
            self._state = "curve_wait2"
        elif self._state == "curve_bend2":
            self._state = "pending"
        elif self._state == "polygon_drag":
            self._state = "polygon"
        elif self._state in {"moving", "resizing"}:
            self._state = "pending"
            self._drag_handle = None
            self._drag_origin = None
        self._render(settings)
        return command

    def _take_command(self) -> LayerImageCommand | None:
        command = self._pending_command
        self._pending_command = None
        return command

    def pop_pending_command(self) -> LayerImageCommand | None:
        return self._take_command()

    # ------------------------------------------------------------------
    # Estado editable
    def has_pending(self) -> bool:
        return self._state not in {"idle"} and bool(self._points)

    def finish_construction(self, settings: Any) -> None:
        """Enter o Esc terminan un polígono o una curva todavía en construcción."""

        if self._state in {"polygon", "polygon_drag"}:
            self._close_polygon(settings)
        elif self._state in {"curve_wait1", "curve_wait2", "curve_bend1", "curve_bend2"}:
            self._state = "pending"
            self._render(settings)

    def commit_pending(self, document: Any) -> LayerImageCommand | None:
        if self._state in {"polygon", "polygon_drag"}:
            self._close_polygon(getattr(document, "tool_settings", None))
        preview = self._preview
        layer = buscar_capa(document, self._layer_id) if self._layer_id is not None else None
        layer_id = self._layer_id
        self.cancel()
        if preview is None or layer is None or preview.size() != layer.image.size():
            return None
        before = layer.image.copy()
        painter = QPainter(layer.image)
        try:
            painter.drawImage(0, 0, preview)
        finally:
            painter.end()
        after = layer.image.copy()
        if imagenes_iguales(before, after):
            return None
        invalidar(document)
        return LayerImageCommand(layer_id=layer_id, before=before, after=after, label=self.name)

    def discard_pending(self, document: Any) -> bool:
        had = self.has_pending()
        self.cancel()
        return had

    def nudge(self, dx: float, dy: float, settings: Any) -> bool:
        if self._state != "pending":
            return False
        delta = QPointF(dx, dy)
        self._points = [point + delta for point in self._points]
        self._render(settings)
        return True

    def refresh(self, document: Any, settings: Any) -> None:
        if self.has_pending():
            self._render(settings)

    def overlay(self) -> dict[str, Any] | None:
        if self._state not in {"pending", "moving", "resizing"} or not self._points:
            return None
        if self._is_line:
            return {"kind": "line", "points": [QPointF(self._points[0]), QPointF(self._points[1])]}
        return {"kind": "box", "rect": self._point_bounds()}

    def cursor_at(self, point: QPointF, settings: Any) -> Any:
        if self._state != "pending":
            return self.cursor
        tolerance = handle_tolerance(settings)
        handle = self._hit(point, tolerance)
        if handle in {"start", "end"}:
            return Qt.CursorShape.SizeAllCursor
        if handle is not None:
            return cursor_for_handle(handle)
        if self._bounds().adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(point):
            return Qt.CursorShape.SizeAllCursor
        return self.cursor

    def bounds(self) -> QRectF:
        return self._bounds() if self._points else QRectF()

    def set_points(self, points: list[QPointF]) -> None:
        """Compatibilidad: permite fijar puntos de control desde código."""

        if len(self._points) >= 2 and self._is_curve:
            self._points = self._points[:2] + [QPointF(point) for point in points[:2]]

    def preview(self) -> QImage | None:
        return self._preview

    def cancel(self, document: Any | None = None) -> None:
        self._points = []
        self._state = "idle"
        self._preview = None
        self._drag_handle = None
        self._drag_origin = None
        self._drag_points = []
        self._layer_id = None


PAINT_SHAPES: dict[str, str] = {
    "line": "Línea",
    "curve": "Curva",
    "ellipse": "Óvalo",
    "rectangle": "Rectángulo",
    "rounded_rectangle": "Rectángulo redondeado",
    "polygon": "Polígono",
    "triangle": "Triángulo",
    "right_triangle": "Triángulo rectángulo",
    "diamond": "Diamante",
    "pentagon": "Pentágono",
    "hexagon": "Hexágono",
    "right_arrow": "Flecha derecha",
    "left_arrow": "Flecha izquierda",
    "up_arrow": "Flecha arriba",
    "down_arrow": "Flecha abajo",
    "star_4": "Estrella de cuatro puntas",
    "star_5": "Estrella de cinco puntas",
    "star_6": "Estrella de seis puntas",
    "speech_callout": "Llamada rectangular redondeada",
    "oval_callout": "Llamada ovalada",
    "thought_callout": "Llamada de nube",
    "heart": "Corazón",
    "lightning": "Rayo",
    # Formas de versiones anteriores de MelfPaint que se conservan por compatibilidad.
    "rectangular_callout": "Llamada rectangular",
    "cloud": "Nube",
}

# Orden de la galería de formas.
PAINT_SHAPE_ORDER: tuple[str, ...] = (
    "line",
    "curve",
    "ellipse",
    "rectangle",
    "rounded_rectangle",
    "polygon",
    "triangle",
    "right_triangle",
    "diamond",
    "pentagon",
    "hexagon",
    "right_arrow",
    "left_arrow",
    "up_arrow",
    "down_arrow",
    "star_4",
    "star_5",
    "star_6",
    "speech_callout",
    "oval_callout",
    "thought_callout",
    "heart",
    "lightning",
)


def shape_outline_path(shape: str, rect: QRectF) -> QPainterPath:
    """Trazado de una forma dentro de ``rect``; útil para los iconos de la galería."""

    if shape == "curve":
        return shape_path("curve", rect.bottomLeft(), rect.topRight(), [QPointF(rect.left() + rect.width() * 0.2, rect.top() - rect.height() * 0.2), QPointF(rect.right() - rect.width() * 0.2, rect.bottom() + rect.height() * 0.2)])
    if shape == "line":
        return shape_path("line", rect.bottomLeft(), rect.topRight())
    return shape_path(shape, rect.topLeft(), rect.bottomRight())
