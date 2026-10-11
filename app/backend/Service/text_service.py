from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QPainter, QTextCharFormat, QTextCursor, QTextDocument, QTextOption

from backend.Model.document import Document
from backend.Model.text_format import TextFormat
from backend.Service.history_service import HistoryService, LayerImageCommand


class TextService:
    """Convierte el texto confirmado por la View en pixeles editables por historial."""

    def __init__(self, history: HistoryService) -> None:
        self.history = history

    def insert_text(
        self,
        document: Document,
        rect: QRect,
        text: str,
        text_format: TextFormat | None = None,
        layer_id: str | None = None,
    ) -> bool:
        contenido = str(text)
        if not contenido:
            return False

        area = QRect(rect).normalized().intersected(QRect(0, 0, document.width, document.height))
        if area.isEmpty():
            return False

        formato = (text_format or document.text_format).clone()
        # El editor de texto puede permanecer abierto mientras otra parte de la
        # interfaz cambia la capa activa. En ese caso se respeta la capa donde
        # empezó la edición y no la que casualmente esté activa al confirmar.
        capa = document.find_layer(layer_id) if layer_id is not None else document.active_layer
        if capa is None:
            return False
        anterior = capa.image.copy()

        # El cuadro de texto crece al escribir: no se pierde ninguna línea.
        documento_texto = self.layout_document(contenido, formato, area.width())
        alto_texto = int(documento_texto.size().height()) + 1
        if alto_texto > area.height():
            area.setHeight(min(alto_texto, document.height - area.y()))

        painter = QPainter(capa.image)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setClipRect(area)
            if formato.opaque_background:
                painter.fillRect(area, formato.background_color)

            # Misma maquetación que el cuadro de texto del editor: lo que se
            # ve al escribir es exactamente lo que queda en la capa.
            painter.translate(area.topLeft())
            documento_texto.drawContents(painter, QRectF(0, 0, area.width(), area.height()))
        finally:
            painter.end()

        if capa.image == anterior:
            return False

        self._copy_format(document.text_format, formato)
        document.invalidate()
        self.history.push(
            LayerImageCommand(
                layer_id=capa.id,
                before=anterior,
                after=capa.image.copy(),
                label="Agregar texto",
            )
        )
        return True

    @classmethod
    def layout_document(cls, text: str, text_format: TextFormat, width: int, zoom: float = 1.0) -> QTextDocument:
        documento = QTextDocument()
        documento.setDocumentMargin(0)
        fuente = text_format.font_px(zoom)
        documento.setDefaultFont(fuente)
        opciones = QTextOption()
        opciones.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        opciones.setAlignment(cls._normalizar_alineacion(text_format.alignment))
        documento.setDefaultTextOption(opciones)
        documento.setPlainText(str(text))
        documento.setTextWidth(max(1, int(width)))
        cursor = QTextCursor(documento)
        cursor.select(QTextCursor.SelectionType.Document)
        formato_caracter = QTextCharFormat()
        formato_caracter.setFont(fuente)
        formato_caracter.setForeground(text_format.text_color)
        cursor.mergeCharFormat(formato_caracter)
        bloque = cursor.blockFormat()
        bloque.setAlignment(cls._normalizar_alineacion(text_format.alignment))
        cursor.mergeBlockFormat(bloque)
        return documento

    @staticmethod
    def _copy_format(target: TextFormat, source: TextFormat) -> None:
        """Actualiza el formato sin romper referencias de controladores y View."""
        target.family = source.family
        target.size = source.size
        target.bold = source.bold
        target.italic = source.italic
        target.underline = source.underline
        target.alignment = source.alignment
        target.opaque_background = source.opaque_background
        target.text_color = source.text_color
        target.background_color = source.background_color

    @staticmethod
    def _normalizar_alineacion(alignment: Qt.AlignmentFlag) -> Qt.AlignmentFlag:
        if alignment & Qt.AlignmentFlag.AlignRight:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
