from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage


class PointerButton(str, Enum):
    """Botones normalizados para no acoplar el Service con eventos de la View."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


def normalizar_boton(button: Any) -> PointerButton:
    if isinstance(button, PointerButton):
        return button
    if button in {Qt.MouseButton.RightButton, 2, "right", "secondary", "secundario"}:
        return PointerButton.SECONDARY
    return PointerButton.PRIMARY


def color_del_boton(settings: Any, button: Any) -> QColor:
    normalizado = normalizar_boton(button)
    atributo = "secondary_color" if normalizado is PointerButton.SECONDARY else "primary_color"
    color = QColor(getattr(settings, atributo, QColor("black")))
    opacity = getattr(settings, "opacity", 1.0)
    try:
        opacity = float(opacity)
    except (TypeError, ValueError):
        opacity = 1.0
    if opacity > 1.0:
        opacity = opacity / 255.0
    color.setAlpha(round(color.alpha() * max(0.0, min(1.0, opacity))))
    return color


class Tool(ABC):
    """Contrato sencillo para todas las herramientas del lienzo."""

    id = "tool"
    name = "Herramienta"
    cursor = Qt.CursorShape.CrossCursor
    # Modificadores del teclado durante el gesto. La View los informa al
    # controlador y este los copia aquí antes de cada evento del puntero.
    shift = False
    ctrl = False

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        return None

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        return None

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> Any:
        return None

    def preview(self) -> QImage | None:
        return None

    def cancel(self, document: Any | None = None) -> None:
        return None

    # Algunas herramientas (formas) dejan un resultado editable que todavía no
    # forma parte de la capa. Estas operaciones permiten confirmarlo.
    def has_pending(self) -> bool:
        return False

    def commit_pending(self, document: Any) -> Any:
        return None

    def discard_pending(self, document: Any) -> bool:
        return False

    def refresh(self, document: Any, settings: Any) -> None:
        return None

    def overlay(self) -> dict[str, Any] | None:
        """Datos para que la View dibuje el marco y los tiradores del objeto editable."""
        return None

    def cursor_at(self, point: QPointF, settings: Any) -> Any:
        return self.cursor
