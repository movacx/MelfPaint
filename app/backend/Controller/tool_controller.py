from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, Signal

from backend.Model.document import Document
from backend.Model.tool_settings import ToolSettings
from backend.Service.Drawing.base_tool import PointerButton, Tool, normalizar_boton
from backend.Service.Drawing.interaction_tools import ColorPickerTool, TextTool, ZoomTool
from backend.Service.Drawing.raster_tools import BrushTool, EraserTool, FillTool, PencilTool
from backend.Service.Drawing.selection_tools import (
    FreeformSelectionTool,
    RectangularSelectionTool,
    commit_floating_selection,
)
from backend.Service.Drawing.shape_tools import PAINT_SHAPES, ShapeTool
from backend.Service.history_service import HistoryService


PICKER_IDS = {"picker", "eyedropper", "color_picker"}


def _point(value: QPointF | QPoint | tuple[float, float]) -> QPointF:
    if isinstance(value, (QPointF, QPoint)):
        return QPointF(value)
    if isinstance(value, tuple) and len(value) == 2:
        return QPointF(float(value[0]), float(value[1]))
    raise TypeError("El punto debe ser QPoint, QPointF o una pareja (x, y)")


class ToolController(QObject):
    """Recibe gestos de la View y los convierte en operaciones con historial."""

    changed = Signal()
    tool_changed = Signal(str)
    preview_changed = Signal()
    text_rect_requested = Signal(QRect)
    command_created = Signal(object)
    aviso = Signal(str)

    # Herramientas que modifican píxeles de la capa activa.
    PAINTING_TOOLS = {"pencil", "brush", "eraser", "fill", "bucket", "text", "text_box"}

    def __init__(
        self,
        document: Document,
        history: HistoryService,
        settings: ToolSettings | None = None,
        color_callback: Callable[..., None] | None = None,
        zoom_callback: Callable[..., None] | None = None,
        text_callback: Callable[[QRect], None] | None = None,
        register_defaults: bool = True,
    ) -> None:
        super().__init__()
        self.document = document
        self.history = history
        self.settings = settings or document.tool_settings
        self.tools: dict[str, Tool] = {}
        self.active_tool: Tool | None = None
        self.active_tool_id = ""
        self.active_button = PointerButton.PRIMARY
        self.previous_tool_id = "pencil"
        self._external_text_callback = text_callback
        if register_defaults:
            self.register_default_tools(color_callback, zoom_callback)
        if self.tools:
            requested = str(getattr(self.settings, "active_tool", "pencil"))
            self.set_tool(requested if requested in self.tools else "pencil", commit_selection=False)

    def register(self, tool: Tool, *aliases: str) -> None:
        ids = (tool.id, *aliases)
        for tool_id in ids:
            if not tool_id:
                continue
            self.tools[str(tool_id)] = tool
        if self.active_tool is None:
            self.active_tool = tool
            self.active_tool_id = str(tool.id)

    def register_default_tools(
        self,
        color_callback: Callable[..., None] | None = None,
        zoom_callback: Callable[..., None] | None = None,
    ) -> None:
        self.register(PencilTool())
        self.register(BrushTool())
        self.register(EraserTool())
        self.register(FillTool(), "bucket")
        self.register(ColorPickerTool(color_callback), "eyedropper", "color_picker")
        self.register(ZoomTool(zoom_callback), "magnifier")
        self.register(TextTool(self._request_text), "text_box")
        self.register(RectangularSelectionTool(), "rectangular_select", "select_rectangular")
        self.register(FreeformSelectionTool(), "free_select", "select_freeform")
        for shape_id, name in PAINT_SHAPES.items():
            self.register(ShapeTool(shape_id, name), f"shape_{shape_id}")
        shape_aliases = {
            "rect": "rectangle",
            "rounded_rect": "rounded_rectangle",
            "oval": "ellipse",
            "arrow": "right_arrow",
            "star": "star_5",
            "spark": "star_4",
            "callout": "speech_callout",
            "rounded_rectangular_callout": "speech_callout",
            "bubble": "thought_callout",
            "cloud_callout": "thought_callout",
            "bolt": "lightning",
        }
        for alias, canonical in shape_aliases.items():
            self.tools[alias] = self.tools[canonical]

    def _request_text(self, rect: QRect) -> None:
        requested = QRect(rect)
        self.text_rect_requested.emit(requested)
        if self._external_text_callback is not None:
            self._external_text_callback(requested)

    def bind(self, document: Document, settings: ToolSettings | None = None) -> None:
        if self.active_tool is not None:
            self.active_tool.cancel(self.document)
        self.document = document
        self.settings = settings or document.tool_settings
        self.changed.emit()

    bind_document = bind

    def set_tool(self, tool_id: str, commit_selection: bool = True) -> None:
        tool_id = str(tool_id)
        if tool_id not in self.tools:
            raise ValueError(f"Herramienta desconocida: {tool_id}")
        if self.active_tool is self.tools[tool_id] and self.active_tool_id == tool_id:
            return

        if self.active_tool is not None:
            if commit_selection:
                self.commit_pending()
            self.active_tool.cancel(self.document)
            if self.active_tool_id not in PICKER_IDS:
                self.previous_tool_id = self.active_tool_id
        self.active_tool = self.tools[tool_id]
        self.active_tool_id = tool_id
        if hasattr(self.settings, "active_tool"):
            self.settings.active_tool = tool_id
        self.tool_changed.emit(tool_id)
        self.changed.emit()

    def _push(self, command: Any | None) -> Any | None:
        if command is not None:
            self.history.push(command)
            self.command_created.emit(command)
        return command

    def has_pending(self) -> bool:
        """Hay una forma editable o una selección flotante sin confirmar."""

        tool_pending = bool(self.active_tool is not None and self.active_tool.has_pending())
        return tool_pending or bool(getattr(self.document.selection, "has_selection", False))

    def has_pending_shape(self) -> bool:
        return bool(self.active_tool is not None and self.active_tool.has_pending())

    def commit_pending(self) -> bool:
        """Fija en la capa la forma editable y la selección flotante."""

        committed = False
        if self.active_tool is not None and self.active_tool.has_pending():
            committed = self._push(self.active_tool.commit_pending(self.document)) is not None or committed
        if bool(getattr(self.document.selection, "has_selection", False)):
            command = (
                self.active_tool.commit(self.document)
                if self.active_tool is not None and hasattr(self.active_tool, "commit")
                else commit_floating_selection(self.document)
            )
            committed = self._push(command) is not None or committed
        if committed:
            self.changed.emit()
            self.preview_changed.emit()
        return committed

    def discard_pending_shape(self) -> bool:
        if self.active_tool is None or not self.active_tool.has_pending():
            return False
        self.active_tool.discard_pending(self.document)
        self.changed.emit()
        self.preview_changed.emit()
        return True

    def finish_construction(self) -> None:
        method = getattr(self.active_tool, "finish_construction", None)
        if callable(method):
            method(self.settings)
            self.changed.emit()
            self.preview_changed.emit()

    def nudge_pending(self, dx: int, dy: int) -> bool:
        method = getattr(self.active_tool, "nudge", None)
        if not callable(method) or not method(dx, dy, self.settings):
            return False
        self.changed.emit()
        self.preview_changed.emit()
        return True

    def refresh_preview(self) -> None:
        """Vuelve a dibujar la forma editable tras cambiar color, grosor o estilo."""

        if self.active_tool is not None and self.active_tool.has_pending():
            self.active_tool.refresh(self.document, self.settings)
            self.changed.emit()
            self.preview_changed.emit()

    def overlay(self) -> dict[str, Any] | None:
        return self.active_tool.overlay() if self.active_tool is not None else None

    def cursor_at(self, point: QPointF | QPoint | tuple[float, float]) -> Any:
        if self.active_tool is None:
            return None
        punto = _point(point)
        selection_cursor = getattr(self.active_tool, "selection_cursor", None)
        if callable(selection_cursor):
            cursor = selection_cursor(self.document, punto, self.settings)
            if cursor is not None:
                return cursor
        return self.active_tool.cursor_at(punto, self.settings)

    def set_modifiers(self, shift: bool = False, ctrl: bool = False) -> None:
        if self.active_tool is not None:
            self.active_tool.shift = bool(shift)
            self.active_tool.ctrl = bool(ctrl)

    def _paints(self) -> bool:
        return self.active_tool_id in self.PAINTING_TOOLS or isinstance(self.active_tool, ShapeTool)

    def pointer_down(self, point: QPointF | QPoint | tuple[float, float], button: Any = PointerButton.PRIMARY) -> None:
        if self.active_tool is None:
            return
        self._bloqueado = False
        if self._paints() and not bool(getattr(self.document.active_layer, "visible", True)) and not self.has_pending_shape():
            # No se dibuja a ciegas sobre una capa oculta.
            self._bloqueado = True
            self.aviso.emit("La capa seleccionada está oculta. Muéstrela para dibujar en ella.")
            return
        if self._paints() and bool(getattr(self.document.active_layer, "locked", False)) and not self.has_pending_shape():
            self._bloqueado = True
            self.aviso.emit("La capa seleccionada está bloqueada. Desbloquéela para dibujar en ella.")
            return
        self.active_button = normalizar_boton(button)
        self.active_tool.pointer_down(self.document, _point(point), self.active_button, self.settings)
        pop_pending = getattr(self.active_tool, "pop_pending_command", None)
        if callable(pop_pending):
            command = pop_pending()
            if command is not None:
                self.history.push(command)
                self.command_created.emit(command)
        self.changed.emit()
        self.preview_changed.emit()

    def pointer_move(
        self,
        point: QPointF | QPoint | tuple[float, float],
        button: Any | None = None,
    ) -> None:
        if self.active_tool is None or getattr(self, "_bloqueado", False):
            return
        if button is not None:
            self.active_button = normalizar_boton(button)
        self.active_tool.pointer_move(self.document, _point(point), self.active_button, self.settings)
        self.changed.emit()
        self.preview_changed.emit()

    def pointer_up(
        self,
        point: QPointF | QPoint | tuple[float, float],
        button: Any | None = None,
    ) -> Any | None:
        if self.active_tool is None:
            return None
        if getattr(self, "_bloqueado", False):
            self._bloqueado = False
            return None
        if button is not None:
            self.active_button = normalizar_boton(button)
        command = self.active_tool.pointer_up(self.document, _point(point), self.active_button, self.settings)
        if command is not None:
            self.history.push(command)
            self.command_created.emit(command)
        self.changed.emit()
        self.preview_changed.emit()
        if self.active_tool_id in PICKER_IDS and self.previous_tool_id in self.tools:
            # Tras tomar un color se vuelve a la herramienta anterior.
            self.set_tool(self.previous_tool_id, commit_selection=False)
        return command

    def cancel_gesture(self) -> None:
        if self.active_tool is not None:
            self.active_tool.cancel(self.document)
        self.changed.emit()
        self.preview_changed.emit()

    def preview(self) -> Any | None:
        return self.active_tool.preview() if self.active_tool is not None else None

    @property
    def cursor(self) -> Any:
        return getattr(self.active_tool, "cursor", None)
