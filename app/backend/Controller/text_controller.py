from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor

from backend.Model.document import Document
from backend.Model.text_format import TextFormat
from backend.Service.history_service import HistoryService
from backend.Service.text_service import TextService


class TextController(QObject):
    """Mantiene el formato temporal y confirma el texto sobre la capa activa."""

    textChanged = Signal()
    historyChanged = Signal()

    def __init__(self, document: Document, history: HistoryService) -> None:
        super().__init__()
        self.document = document
        self.history = history
        self.service = TextService(history)

    def bind(self, document: Document) -> None:
        self.document = document

    def update_format(self, values: dict) -> TextFormat:
        formato = self.document.text_format
        formato.family = str(values.get("familia", formato.family))
        formato.size = max(1, min(512, int(values.get("tamano", formato.size))))
        formato.bold = bool(values.get("negrita", formato.bold))
        formato.italic = bool(values.get("cursiva", formato.italic))
        formato.underline = bool(values.get("subrayado", formato.underline))
        formato.strikeout = bool(values.get("tachado", formato.strikeout))
        formato.opaque_background = values.get("fondo", "transparent") == "opaque"
        formato.alignment = self._alignment(values.get("alineacion", "left"))
        self.textChanged.emit()
        return formato

    def set_colors(self, foreground: QColor | str, background: QColor | str) -> None:
        frente = QColor(foreground)
        fondo = QColor(background)
        if frente.isValid():
            self.document.text_format.text_color = frente
        if fondo.isValid():
            self.document.text_format.background_color = fondo

    def insert_text(self, rect: QRect, text: str, layer_id: str | None = None) -> bool:
        changed = self.service.insert_text(
            self.document,
            rect,
            text,
            self.document.text_format,
            layer_id,
        )
        if changed:
            self.textChanged.emit()
            self.historyChanged.emit()
        return changed

    @staticmethod
    def _alignment(value: object) -> Qt.AlignmentFlag:
        if value == "right":
            return Qt.AlignmentFlag.AlignRight
        if value == "center":
            return Qt.AlignmentFlag.AlignHCenter
        return Qt.AlignmentFlag.AlignLeft
