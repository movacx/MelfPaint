from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from backend.Model.selection_state import SelectionMode
from backend.Service.Drawing.base_tool import Tool
from backend.Service.Drawing.commands import LayerImageCommand
from backend.Service.Drawing.shape_tools import cursor_for_handle, handle_tolerance, hit_handle, resize_rect
from backend.Service.Drawing.drawing_utils import (
    buscar_capa,
    crear_imagen_transparente,
    imagenes_iguales,
    invalidar,
    obtener_id_capa,
    rectangulo_limitado,
    valor_config,
)


def _selection_is_active(selection: Any) -> bool:
    return bool(getattr(selection, "has_selection", getattr(selection, "active", False)))


def _selection_contains(selection: Any, x: int, y: int) -> bool:
    if not _selection_is_active(selection):
        return False
    rect = QRect(selection.current_rect)
    if not rect.contains(x, y):
        return False
    mask = getattr(selection, "mask", None)
    if mask is None or mask.isNull():
        return True
    local_x = x - rect.x()
    local_y = y - rect.y()
    return 0 <= local_x < mask.width() and 0 <= local_y < mask.height() and mask.pixelColor(local_x, local_y).alpha() > 0


def _clear_source(image: QImage, rect: QRect, mask: QImage | None) -> None:
    painter = QPainter(image)
    try:
        if mask is None or mask.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            painter.drawImage(rect.topLeft(), mask)
    finally:
        painter.end()


def _apply_mask(image: QImage, mask: QImage | None) -> QImage:
    if mask is None or mask.isNull():
        return image
    result = image.copy()
    painter = QPainter(result)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, mask)
    finally:
        painter.end()
    return result


def create_floating_selection(
    document: Any,
    rect: QRect,
    settings: Any,
    mask: QImage | None = None,
    supplied_image: QImage | None = None,
    clear_source: bool = True,
) -> bool:
    """Convierte una región o imagen pegada en una selección movible."""

    bounds = QRect(0, 0, int(document.width), int(document.height))
    rect = QRect(rect).normalized()
    if supplied_image is None:
        # Una imagen pegada puede ser más grande que el lienzo o quedar
        # parcialmente fuera; lo que sale del lienzo se recorta al confirmar.
        rect = rect.intersected(bounds)
    if rect.isEmpty():
        return False
    layer = document.active_layer
    before = layer.image.copy()
    floating = supplied_image.copy() if supplied_image is not None else layer.image.copy(rect)
    if floating.size() != rect.size():
        floating = floating.copy(0, 0, rect.width(), rect.height())
    local_mask = None
    if mask is not None and not mask.isNull():
        local_mask = mask.copy(0, 0, rect.width(), rect.height())
        floating = _apply_mask(floating, local_mask)
    if clear_source:
        _clear_source(layer.image, rect, local_mask)

    selection = document.selection
    selection.source_rect = QRect(rect)
    selection.floating_image = floating.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    selection.mask = local_mask
    selection.offset = QPoint(rect.topLeft())
    selection.original_layer_id = obtener_id_capa(layer, document)
    selection.original_layer_before = before
    selection.source_was_cleared = bool(clear_source)
    selection.transformed = supplied_image is not None
    selection.transparent_mode = bool(valor_config(settings, "transparent_selection", default=True))
    selection.background_key_color = QColor(valor_config(settings, "secondary_color", default=QColor("white")))
    selection.state = SelectionMode.FLOATING
    invalidate_cache = getattr(selection, "invalidate_cache", None)
    if callable(invalidate_cache):
        invalidate_cache()
    if hasattr(document, "selection_rect"):
        document.selection_rect = QRect(selection.current_rect)
    invalidar(document, modified=False)
    return True


def display_selection_image(selection: Any) -> QImage | None:
    display = getattr(selection, "display_image", None)
    if callable(display):
        return display()
    floating = getattr(selection, "floating_image", None)
    return floating.copy() if floating is not None else None


def commit_floating_selection(document: Any, label: str = "Confirmar selección") -> LayerImageCommand | None:
    selection = document.selection
    if not _selection_is_active(selection):
        return None
    layer_id = selection.original_layer_id
    layer = buscar_capa(document, layer_id)
    if layer is None:
        layer = document.active_layer
        layer_id = obtener_id_capa(layer, document)
    before = selection.original_layer_before.copy() if selection.original_layer_before is not None else layer.image.copy()
    was_modified = bool(getattr(document, "modified", False))
    same_position = QPoint(selection.offset) == selection.source_rect.topLeft()
    untouched = same_position and not bool(getattr(selection, "transformed", False))
    if bool(getattr(selection, "source_was_cleared", False)) and untouched:
        layer.image = before.copy()
        selection.clear()
        if hasattr(document, "selection_rect"):
            document.selection_rect = None
        invalidar(document, modified=False)
        if hasattr(document, "modified"):
            document.modified = was_modified
        return None
    image = display_selection_image(selection)
    if image is not None:
        painter = QPainter(layer.image)
        try:
            painter.drawImage(QPoint(selection.offset), image)
        finally:
            painter.end()
    after = layer.image.copy()
    selection.clear()
    if hasattr(document, "selection_rect"):
        document.selection_rect = None
    if imagenes_iguales(before, after):
        invalidar(document, modified=False)
        if hasattr(document, "modified"):
            document.modified = was_modified
        return None
    invalidar(document)
    return LayerImageCommand(layer_id=layer_id, before=before, after=after, label=label)


def delete_floating_selection(document: Any, label: str = "Eliminar selección") -> LayerImageCommand | None:
    selection = document.selection
    if not _selection_is_active(selection):
        return None
    layer_id = selection.original_layer_id
    layer = buscar_capa(document, layer_id)
    if layer is None:
        layer = document.active_layer
        layer_id = obtener_id_capa(layer, document)
    before = selection.original_layer_before.copy() if selection.original_layer_before is not None else layer.image.copy()
    was_modified = bool(getattr(document, "modified", False))
    after = layer.image.copy()
    selection.clear()
    if hasattr(document, "selection_rect"):
        document.selection_rect = None
    if imagenes_iguales(before, after):
        invalidar(document, modified=False)
        if hasattr(document, "modified"):
            document.modified = was_modified
        return None
    invalidar(document)
    return LayerImageCommand(layer_id=layer_id, before=before, after=after, label=label)


def cancel_floating_selection(document: Any) -> bool:
    selection = document.selection
    if not _selection_is_active(selection):
        return False
    layer = buscar_capa(document, selection.original_layer_id)
    if layer is not None and selection.original_layer_before is not None:
        layer.image = selection.original_layer_before.copy()
    selection.clear()
    if hasattr(document, "selection_rect"):
        document.selection_rect = None
    invalidar(document, modified=False)
    return True


class _SelectionTool(Tool):
    id = "select"
    name = "Selección rectangular"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self) -> None:
        self._start: QPointF | None = None
        self._end: QPointF | None = None
        self._drag_start: QPoint | None = None
        self._offset_start: QPoint | None = None
        self._mode = "idle"
        self._pending_command: LayerImageCommand | None = None
        self._handle: str | None = None
        self._base_rect = QRect()
        self._base_image: QImage | None = None
        self._base_mask: QImage | None = None

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        x, y = round(point.x()), round(point.y())
        selection = document.selection
        if _selection_is_active(selection):
            handle = hit_handle(QRectF(selection.current_rect), point, handle_tolerance(settings))
            if handle is not None:
                self._mode = "resizing"
                self._handle = handle
                self._base_rect = QRect(selection.current_rect)
                self._base_image = selection.floating_image.copy()
                self._base_mask = selection.mask.copy() if selection.mask is not None else None
                selection.state = SelectionMode.MOVING
                return
        if _selection_contains(selection, x, y):
            self._mode = "moving"
            selection.state = SelectionMode.MOVING
            self._drag_start = QPoint(x, y)
            self._offset_start = QPoint(selection.offset)
            if self.ctrl:
                # Ctrl + arrastrar deja una copia en el lugar original.
                self._stamp_copy(document)
            return
        if _selection_is_active(selection):
            self._pending_command = commit_floating_selection(document)
        self._mode = "creating"
        selection.state = SelectionMode.CREATING
        self._start = QPointF(point)
        self._end = QPointF(point)
        if hasattr(document, "selection_rect"):
            document.selection_rect = QRect(x, y, 1, 1)
        invalidar(document, modified=False)

    def _stamp_copy(self, document: Any) -> None:
        selection = document.selection
        layer = buscar_capa(document, selection.original_layer_id) or document.active_layer
        image = display_selection_image(selection)
        if image is None:
            return
        painter = QPainter(layer.image)
        try:
            painter.drawImage(QPoint(selection.offset), image)
        finally:
            painter.end()
        selection.transformed = True
        invalidar(document)

    def _resize_floating(self, document: Any, point: QPointF) -> None:
        selection = document.selection
        if self._base_image is None or self._handle is None:
            return
        rect = resize_rect(QRectF(self._base_rect), self._handle, point, self.shift).toAlignedRect()
        size = QSize(max(1, rect.width()), max(1, rect.height()))
        image = self._base_image.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        selection.floating_image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        if self._base_mask is not None:
            selection.mask = self._base_mask.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        selection.source_rect = QRect(selection.source_rect.topLeft(), image.size())
        selection.offset = QPoint(rect.topLeft())
        selection.transformed = True
        selection.invalidate_cache()
        if hasattr(document, "selection_rect"):
            document.selection_rect = QRect(selection.current_rect)
        invalidar(document, modified=False)

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        selection = document.selection
        if self._mode == "resizing":
            self._resize_floating(document, point)
            return
        if self._mode == "moving" and self._drag_start is not None and self._offset_start is not None:
            delta = QPoint(round(point.x()), round(point.y())) - self._drag_start
            # La selección puede salir del lienzo; lo que quede
            # fuera se descarta al confirmar.
            selection.offset = self._offset_start + delta
            if hasattr(document, "selection_rect"):
                document.selection_rect = QRect(selection.current_rect)
            invalidar(document, modified=False)
            return
        if self._mode == "creating" and self._start is not None:
            self._end = QPointF(point)
            self._update_creating_preview(document)
            invalidar(document, modified=False)

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        if self._mode == "resizing":
            self._resize_floating(document, point)
            document.selection.state = SelectionMode.FLOATING
            self._mode = "idle"
            self._handle = None
            self._base_image = None
            self._base_mask = None
            invalidar(document, modified=False)
            return self._take_pending()
        if self._mode == "moving":
            document.selection.state = SelectionMode.FLOATING
            self._mode = "idle"
            self._drag_start = None
            self._offset_start = None
            invalidar(document, modified=False)
            return self._take_pending()
        if self._mode != "creating" or self._start is None:
            return self._take_pending()
        self._end = QPointF(point)
        created = self._finish_creation(document, settings)
        self._mode = "idle"
        self._start = None
        self._end = None
        if not created:
            document.selection.clear()
            if hasattr(document, "selection_rect"):
                document.selection_rect = None
        invalidar(document, modified=False)
        return self._take_pending()

    def _take_pending(self) -> LayerImageCommand | None:
        command = self._pending_command
        self._pending_command = None
        return command

    def pop_pending_command(self) -> LayerImageCommand | None:
        """Permite registrar de inmediato una selección confirmada al hacer clic fuera."""

        return self._take_pending()

    def _constrained_end(self) -> QPointF | None:
        if self._start is None or self._end is None:
            return self._end
        if not self.shift:
            return self._end
        dx, dy = self._end.x() - self._start.x(), self._end.y() - self._start.y()
        side = max(abs(dx), abs(dy))
        return QPointF(self._start.x() + (side if dx >= 0 else -side), self._start.y() + (side if dy >= 0 else -side))

    def _update_creating_preview(self, document: Any) -> None:
        if self._start is not None and self._end is not None and hasattr(document, "selection_rect"):
            document.selection_rect = rectangulo_limitado(self._start, self._constrained_end(), document)

    def cursor_at(self, point: QPointF, settings: Any) -> Any:
        return self.cursor

    def selection_cursor(self, document: Any, point: QPointF, settings: Any) -> Any | None:
        selection = document.selection
        if not _selection_is_active(selection):
            return None
        handle = hit_handle(QRectF(selection.current_rect), point, handle_tolerance(settings))
        if handle is not None:
            return cursor_for_handle(handle)
        if _selection_contains(selection, round(point.x()), round(point.y())):
            return Qt.CursorShape.SizeAllCursor
        return None

    def _finish_creation(self, document: Any, settings: Any) -> bool:
        raise NotImplementedError

    def move_by(self, document: Any, dx: int, dy: int) -> bool:
        selection = document.selection
        if not _selection_is_active(selection):
            return False
        offset = QPoint(selection.offset.x() + int(dx), selection.offset.y() + int(dy))
        if offset == selection.offset:
            return False
        selection.offset = offset
        if hasattr(document, "selection_rect"):
            document.selection_rect = QRect(selection.current_rect)
        invalidar(document, modified=False)
        return True

    def commit(self, document: Any) -> LayerImageCommand | None:
        return commit_floating_selection(document)

    def delete(self, document: Any) -> LayerImageCommand | None:
        return delete_floating_selection(document)

    def cancel_selection(self, document: Any) -> bool:
        restored = cancel_floating_selection(document)
        self.cancel()
        return restored

    def cancel(self, document: Any | None = None) -> None:
        if document is not None and self._mode == "moving" and self._offset_start is not None:
            document.selection.offset = QPoint(self._offset_start)
            document.selection.state = SelectionMode.FLOATING
            if hasattr(document, "selection_rect"):
                document.selection_rect = QRect(document.selection.current_rect)
            invalidar(document, modified=False)
        elif document is not None and self._mode == "resizing" and self._base_image is not None:
            selection = document.selection
            selection.floating_image = self._base_image
            selection.mask = self._base_mask
            selection.source_rect = QRect(selection.source_rect.topLeft(), self._base_image.size())
            selection.offset = QPoint(self._base_rect.topLeft())
            selection.state = SelectionMode.FLOATING
            selection.invalidate_cache()
            invalidar(document, modified=False)
        elif document is not None and self._mode == "creating":
            document.selection.clear()
            if hasattr(document, "selection_rect"):
                document.selection_rect = None
            invalidar(document, modified=False)
        self._start = None
        self._end = None
        self._drag_start = None
        self._offset_start = None
        self._mode = "idle"
        self._pending_command = None
        self._handle = None
        self._base_image = None
        self._base_mask = None


class RectangularSelectionTool(_SelectionTool):
    id = "select"
    name = "Selección rectangular"

    def _finish_creation(self, document: Any, settings: Any) -> bool:
        if self._start is None or self._end is None:
            return False
        rect = rectangulo_limitado(self._start, self._constrained_end(), document)
        return create_floating_selection(document, rect, settings) if not rect.isEmpty() else False


class FreeformSelectionTool(_SelectionTool):
    id = "freeform_select"
    name = "Selección libre"

    def __init__(self) -> None:
        super().__init__()
        self._points: list[QPointF] = []
        self._preview: QImage | None = None

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        was_inside = _selection_contains(document.selection, round(point.x()), round(point.y()))
        super().pointer_down(document, point, button, settings)
        self._points = [] if was_inside else [QPointF(point)]

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        if self._mode == "creating":
            if not self._points or (self._points[-1] - point).manhattanLength() >= 2.0:
                self._points.append(QPointF(point))
            self._end = QPointF(point)
            self._update_creating_preview(document)
            invalidar(document, modified=False)
            return
        super().pointer_move(document, point, button, settings)

    def _update_creating_preview(self, document: Any) -> None:
        if len(self._points) < 2:
            return
        self._preview = crear_imagen_transparente(document.width, document.height)
        painter = QPainter(self._preview)
        try:
            pen = QPen(QColor(30, 105, 210), 1.0, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QPolygonF(self._points))
        finally:
            painter.end()
        bounds = QPolygonF(self._points).boundingRect().toAlignedRect().intersected(QRect(0, 0, document.width, document.height))
        if hasattr(document, "selection_rect"):
            document.selection_rect = bounds

    def _finish_creation(self, document: Any, settings: Any) -> bool:
        if self._end is not None:
            self._points.append(QPointF(self._end))
        if len(self._points) < 3:
            self._preview = None
            return False
        polygon = QPolygonF(self._points)
        rect = polygon.boundingRect().toAlignedRect().intersected(QRect(0, 0, document.width, document.height))
        if rect.isEmpty():
            self._preview = None
            return False
        local_points = [QPointF(point.x() - rect.x(), point.y() - rect.y()) for point in self._points]
        mask = crear_imagen_transparente(rect.width(), rect.height())
        painter = QPainter(mask)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 255))
            painter.drawPolygon(QPolygonF(local_points))
        finally:
            painter.end()
        self._preview = None
        return create_floating_selection(document, rect, settings, mask=mask)

    def preview(self) -> QImage | None:
        return self._preview

    def cancel(self, document: Any | None = None) -> None:
        super().cancel(document)
        self._points = []
        self._preview = None
