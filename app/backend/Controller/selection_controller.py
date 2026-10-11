from __future__ import annotations

from math import isfinite, radians, tan
from typing import Any

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QTransform

from backend.Service.Drawing.drawing_utils import invalidar
from backend.Service.Drawing.selection_tools import (
    cancel_floating_selection,
    commit_floating_selection,
    create_floating_selection,
    delete_floating_selection,
    display_selection_image,
)


class SelectionController:
    """Coordina selección, portapapeles y el historial sin lógica de widgets."""

    def __init__(self, document: Any, history: Any, tools: Any | None = None, settings: Any | None = None) -> None:
        self.document = document
        self.history = history
        self.tools = tools
        self.settings = settings or getattr(document, "tool_settings", None)
        self._local_clipboard: QImage | None = None

    def bind(self, document: Any) -> None:
        self.document = document
        if self.settings is None:
            self.settings = getattr(document, "tool_settings", None)

    def selection_rect(self) -> QRect:
        selection = self.document.selection
        if bool(getattr(selection, "has_selection", False)):
            rect = QRect(selection.current_rect)
        else:
            rect = QRect(getattr(self.document, "selection_rect", QRect()) or QRect())
        return rect.intersected(QRect(0, 0, self.document.width, self.document.height))

    def has_selection(self) -> bool:
        return bool(getattr(self.document.selection, "has_selection", False))

    def _tool(self) -> Any | None:
        if self.tools is None:
            return None
        registry = getattr(self.tools, "tools", {})
        active_id = getattr(self.tools, "active_tool_id", None)
        return registry.get(active_id) or registry.get("select")

    def _push(self, command: Any | None) -> Any | None:
        if command is not None:
            self.history.push(command)
        return command

    def make_floating_from_rect(self, rect: QRect) -> bool:
        if self.settings is None:
            raise RuntimeError("La selección necesita ToolSettings")
        return create_floating_selection(self.document, rect, self.settings)

    def select_all(self) -> bool:
        self.commit(push_history=True)
        if self.tools is not None:
            try:
                self.tools.set_tool("select")
            except (KeyError, ValueError):
                pass
        return self.make_floating_from_rect(QRect(0, 0, self.document.width, self.document.height))

    def commit(self, push_history: bool = True) -> Any | None:
        tool = self._tool()
        command = tool.commit(self.document) if tool is not None and hasattr(tool, "commit") else commit_floating_selection(self.document)
        if push_history:
            self._push(command)
        return command

    def deselect(self) -> None:
        self.commit(push_history=True)

    def _set_clipboard_image(self, image: QImage) -> None:
        self._local_clipboard = image.copy()
        app = QGuiApplication.instance()
        if app is not None:
            QGuiApplication.clipboard().setImage(image)

    def _get_clipboard_image(self) -> QImage:
        app = QGuiApplication.instance()
        if app is not None:
            image = QGuiApplication.clipboard().image()
            if not image.isNull():
                return image
        return self._local_clipboard.copy() if self._local_clipboard is not None else QImage()

    def copy(self) -> bool:
        if not self.has_selection():
            return False
        image = display_selection_image(self.document.selection)
        if image is None or image.isNull():
            return False
        self._set_clipboard_image(image)
        return True

    def cut(self) -> bool:
        if not self.copy():
            return False
        self.delete()
        return True

    def clipboard_image(self) -> QImage:
        return self._get_clipboard_image()

    def paste(self, image: QImage | None = None, position: QPoint | None = None) -> bool:
        """Pega una imagen como selección flotante en ``position`` (por defecto 0, 0).

        La imagen se conserva completa aunque sea más grande que el lienzo: lo
        que quede fuera se recorta al confirmar.
        """

        floating = image.copy() if image is not None else self._get_clipboard_image()
        if floating.isNull():
            return False
        self.commit(push_history=True)
        if self.tools is not None:
            try:
                self.tools.set_tool("select")
            except (KeyError, ValueError):
                pass
        origin = QPoint(position) if position is not None else QPoint(0, 0)
        rect = QRect(origin, floating.size())
        return create_floating_selection(
            self.document,
            rect,
            self.settings or self.document.tool_settings,
            supplied_image=floating.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied),
            clear_source=False,
        )

    def invert(self) -> bool:
        """Selecciona todo lo que no estaba seleccionado."""

        selection = self.document.selection
        bounds = QRect(0, 0, self.document.width, self.document.height)
        if not self.has_selection():
            return self.select_all()
        rect = QRect(selection.current_rect)
        mask = selection.mask.copy() if selection.mask is not None else None
        self.commit(push_history=True)
        inverse = QImage(bounds.size(), QImage.Format.Format_ARGB32_Premultiplied)
        inverse.fill(QColor(255, 255, 255, 255))
        painter = QPainter(inverse)
        try:
            if mask is None or mask.isNull():
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(rect, QColor(0, 0, 0, 0))
            else:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                painter.drawImage(rect.topLeft(), mask)
        finally:
            painter.end()
        if self.tools is not None:
            try:
                self.tools.set_tool("select")
            except (KeyError, ValueError):
                pass
        return create_floating_selection(self.document, bounds, self.settings, mask=inverse)

    def delete(self) -> Any | None:
        tool = self._tool()
        command = tool.delete(self.document) if tool is not None and hasattr(tool, "delete") else delete_floating_selection(self.document)
        return self._push(command)

    def move_by(self, dx: int, dy: int) -> bool:
        tool = self._tool()
        if tool is not None and hasattr(tool, "move_by"):
            return bool(tool.move_by(self.document, dx, dy))
        selection = self.document.selection
        if not self.has_selection():
            return False
        offset = QPoint(selection.offset.x() + int(dx), selection.offset.y() + int(dy))
        if offset == selection.offset:
            return False
        selection.offset = offset
        self.document.selection_rect = QRect(selection.current_rect)
        invalidar(self.document, modified=False)
        return True

    def rotate(self, degrees: float) -> bool:
        selection = self.document.selection
        if not self.has_selection():
            return False
        angle = float(degrees)
        if not -360_000.0 < angle < 360_000.0:
            raise ValueError("El ángulo de la selección no es válido")
        if abs(angle % 360.0) < 0.000001:
            return False
        transform = QTransform().rotate(angle)
        image = selection.floating_image.transformed(
            transform,
            Qt.TransformationMode.SmoothTransformation,
        )
        if image.isNull():
            return False
        mask = None
        if selection.mask is not None:
            mask = selection.mask.transformed(
                transform,
                Qt.TransformationMode.SmoothTransformation,
            )
        return self._replace_floating_image(image, mask)

    def resize_and_skew(
        self,
        width: int,
        height: int,
        keep_aspect: bool = False,
        horizontal_skew: float = 0.0,
        vertical_skew: float = 0.0,
    ) -> bool:
        selection = self.document.selection
        if not self.has_selection():
            return False
        width = int(width)
        height = int(height)
        horizontal = float(horizontal_skew)
        vertical = float(vertical_skew)
        if width < 1 or height < 1 or width > 32768 or height > 32768:
            raise ValueError("El tamaño de la selección no es válido")
        if width * height > 100_000_000:
            raise ValueError("La selección supera el límite de píxeles")
        if not isfinite(horizontal) or not isfinite(vertical):
            raise ValueError("El sesgo de la selección no es válido")
        if abs(horizontal) >= 89.0 or abs(vertical) >= 89.0:
            raise ValueError("El sesgo debe estar entre -89 y 89 grados")

        mode = (
            Qt.AspectRatioMode.KeepAspectRatio
            if keep_aspect
            else Qt.AspectRatioMode.IgnoreAspectRatio
        )
        target = QSize(width, height)
        image = selection.floating_image.scaled(
            target,
            mode,
            Qt.TransformationMode.SmoothTransformation,
        )
        mask = None
        if selection.mask is not None:
            mask = selection.mask.scaled(
                target,
                mode,
                Qt.TransformationMode.SmoothTransformation,
            )

        if horizontal or vertical:
            transform = QTransform().shear(tan(radians(horizontal)), tan(radians(vertical)))
            image = image.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            if mask is not None:
                mask = mask.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        if image.isNull() or image.width() * image.height() > 100_000_000:
            raise ValueError("La transformación de la selección es demasiado grande")
        if (
            horizontal == 0.0
            and vertical == 0.0
            and image.size() == selection.floating_image.size()
            and image == selection.floating_image
        ):
            return False
        return self._replace_floating_image(image, mask)

    def flip(self, horizontal: bool) -> bool:
        selection = self.document.selection
        if not self.has_selection():
            return False
        image = self._flipped(selection.floating_image, horizontal)
        mask = None
        if selection.mask is not None:
            mask = self._flipped(selection.mask, horizontal)
        return self._replace_floating_image(image, mask)

    @staticmethod
    def _flipped(image: QImage, horizontal: bool) -> QImage:
        method = getattr(image, "flipped", None)
        if callable(method):
            orientation = Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical
            return method(orientation)
        return image.mirrored(horizontal, not horizontal)

    def _replace_floating_image(self, image: QImage, mask: QImage | None) -> bool:
        selection = self.document.selection
        current = selection.current_rect
        center = current.center()
        width = image.width()
        height = image.height()
        x = center.x() - width // 2
        y = center.y() - height // 2
        x = max(0, min(max(0, self.document.width - width), x))
        y = max(0, min(max(0, self.document.height - height), y))
        selection.floating_image = image
        selection.mask = mask
        selection.source_rect = QRect(0, 0, width, height)
        selection.offset = QPoint(x, y)
        selection.transformed = True
        selection.invalidate_cache()
        self.document.selection_rect = QRect(selection.current_rect)
        invalidar(self.document, modified=False)
        return True

    def apply_filter(self, name: str) -> bool:
        """Aplica un efecto solo a la selección flotante."""

        from backend.Service.document_service import DocumentService

        selection = self.document.selection
        if not self.has_selection():
            return False
        imagen, pixeles = DocumentService._rgba(selection.floating_image)
        DocumentService._filter_pixels(pixeles, name)
        resultado = imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        if selection.mask is not None:
            painter = QPainter(resultado)
            try:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                painter.drawImage(0, 0, selection.mask)
            finally:
                painter.end()
        selection.floating_image = resultado
        selection.transformed = True
        selection.invalidate_cache()
        invalidar(self.document, modified=True)
        return True

    def cancel(self) -> bool:
        tool = self._tool()
        if tool is not None and hasattr(tool, "cancel_selection"):
            return bool(tool.cancel_selection(self.document))
        return cancel_floating_selection(self.document)

    def set_transparent(self, enabled: bool) -> None:
        if self.settings is not None and hasattr(self.settings, "transparent_selection"):
            self.settings.transparent_selection = bool(enabled)
        selection = self.document.selection
        selection.transparent_mode = bool(enabled)
        if self.settings is not None:
            selection.background_key_color = QColor(getattr(self.settings, "secondary_color", QColor("white")))
        invalidate_cache = getattr(selection, "invalidate_cache", None)
        if callable(invalidate_cache):
            invalidate_cache()
        invalidar(self.document, modified=False)
