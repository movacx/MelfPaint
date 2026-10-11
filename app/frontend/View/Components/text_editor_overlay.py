from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPalette, QPen, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import QTextEdit, QWidget

from backend.Model.text_format import TextFormat


class _MarcoTexto(QWidget):
    """Capa transparente que dibuja el marco del cuadro de texto encima del editor."""

    def __init__(self, editor: "TextEditorOverlay") -> None:
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self.editor._pintar_marco(painter)
        painter.end()


class TextEditorOverlay(QTextEdit):
    """Cuadro de texto colocado sobre el lienzo hasta confirmarlo.

    Tiene un marco discontinuo con tiradores: arrastrando el marco se mueve y
    arrastrando los tiradores cambia de tamaño. El texto se muestra con la
    misma fuente, tamaño y ajuste de línea con que se dibujará en la capa.
    """

    confirmarSolicitado = Signal()
    cancelarSolicitado = Signal()
    estiloSolicitado = Signal(str)
    geometriaCambiada = Signal(QRect)

    MARGEN = 7  # franja exterior para el marco y los tiradores

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rectangulo_documento = QRect()
        self.zoom = 1.0
        self.formato = TextFormat()
        self._arrastre: tuple[str, QPoint, QRect] | None = None
        self.setAcceptRichText(False)
        self.setUndoRedoEnabled(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(self.MARGEN, self.MARGEN, self.MARGEN, self.MARGEN)
        self.setMouseTracking(True)
        self.setObjectName("TextEditorOverlay")
        self.setAccessibleName("Cuadro de texto sobre el lienzo")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("QTextEdit#TextEditorOverlay { background: transparent; border: none; }")
        self.textChanged.connect(self._crecer_si_hace_falta)
        self._marco = _MarcoTexto(self)
        self.hide()

    # ------------------------------------------------------------------
    def empezar(self, rectangulo: QRect, formato: TextFormat, zoom: float) -> None:
        self.rectangulo_documento = QRect(rectangulo)
        self.zoom = max(0.1, float(zoom))
        self.formato = formato.clone()
        self.clear()
        self.actualizar_formato(formato)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def actualizar_formato(self, formato: TextFormat) -> None:
        self.formato = formato.clone()
        fuente = self.formato.font_px(self.zoom)
        caracter = QTextCharFormat()
        caracter.setFont(fuente)
        caracter.setForeground(self.formato.text_color)
        self.document().setDefaultFont(fuente)
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(caracter)
        self.mergeCurrentCharFormat(caracter)
        opcion = self.document().defaultTextOption()
        opcion.setAlignment(self._alineacion())
        opcion.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(opcion)
        cursor.select(QTextCursor.SelectionType.Document)
        bloque = cursor.blockFormat()
        bloque.setAlignment(self._alineacion())
        cursor.mergeBlockFormat(bloque)
        paleta = self.viewport().palette()
        fondo = QColor(self.formato.background_color) if self.formato.opaque_background else QColor(0, 0, 0, 0)
        paleta.setColor(QPalette.ColorRole.Base, fondo)
        paleta.setColor(QPalette.ColorRole.Text, self.formato.text_color)
        paleta.setColor(QPalette.ColorRole.Highlight, QColor("#99c9ef"))
        paleta.setColor(QPalette.ColorRole.HighlightedText, self.formato.text_color)
        self.viewport().setPalette(paleta)
        self.viewport().setAutoFillBackground(self.formato.opaque_background)
        self.viewport().update()
        self.update()

    def establecer_geometria(self, rectangulo: QRect, zoom: float) -> None:
        self.zoom = max(0.1, float(zoom))
        self.setGeometry(rectangulo.adjusted(-self.MARGEN, -self.MARGEN, self.MARGEN, self.MARGEN))
        self.actualizar_formato(self.formato)

    def terminar(self) -> None:
        self._arrastre = None
        self.hide()
        self.clearFocus()

    def _alineacion(self) -> Qt.AlignmentFlag:
        if self.formato.alignment & Qt.AlignmentFlag.AlignRight:
            return Qt.AlignmentFlag.AlignRight
        if self.formato.alignment & Qt.AlignmentFlag.AlignHCenter:
            return Qt.AlignmentFlag.AlignHCenter
        return Qt.AlignmentFlag.AlignLeft

    # ------------------------------------------------------------------
    # Marco, tiradores y arrastre
    def _area_texto(self) -> QRect:
        return self.rect().adjusted(self.MARGEN, self.MARGEN, -self.MARGEN, -self.MARGEN)

    def _tiradores(self) -> dict[str, QPoint]:
        area = self._area_texto().adjusted(0, 0, -1, -1)
        centro = area.center()
        return {
            "top_left": area.topLeft(),
            "top": QPoint(centro.x(), area.top()),
            "top_right": area.topRight(),
            "right": QPoint(area.right(), centro.y()),
            "bottom_right": area.bottomRight(),
            "bottom": QPoint(centro.x(), area.bottom()),
            "bottom_left": area.bottomLeft(),
            "left": QPoint(area.left(), centro.y()),
        }

    def _zona(self, punto: QPoint) -> str | None:
        for nombre, centro in self._tiradores().items():
            if abs(punto.x() - centro.x()) <= 5 and abs(punto.y() - centro.y()) <= 5:
                return nombre
        if self.rect().contains(punto) and not self._area_texto().adjusted(3, 3, -3, -3).contains(punto):
            return "move"
        return None

    @staticmethod
    def _cursor(zona: str | None) -> Qt.CursorShape:
        return {
            "move": Qt.CursorShape.SizeAllCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
        }.get(zona or "", Qt.CursorShape.IBeamCursor)

    def event(self, event: QEvent) -> bool:
        # Los clics sobre el marco no llegan al área de texto; aquí se usan
        # para mover o cambiar el tamaño del cuadro.
        tipo = event.type()
        if tipo == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            zona = self._zona(event.position().toPoint())
            if zona is not None:
                self._arrastre = (zona, event.globalPosition().toPoint(), QRect(self.rectangulo_documento))
                return True
        elif tipo == QEvent.Type.MouseMove:
            if self._arrastre is not None:
                self._arrastrar(event.globalPosition().toPoint())
                return True
            self.setCursor(self._cursor(self._zona(event.position().toPoint())))
        elif tipo == QEvent.Type.MouseButtonRelease and self._arrastre is not None:
            self._arrastre = None
            return True
        return super().event(event)

    def _arrastrar(self, global_pos: QPoint) -> None:
        zona, inicio, original = self._arrastre
        dx = round((global_pos.x() - inicio.x()) / self.zoom)
        dy = round((global_pos.y() - inicio.y()) / self.zoom)
        rect = QRect(original)
        if zona == "move":
            rect.translate(dx, dy)
        else:
            if "left" in zona:
                rect.setLeft(min(original.right() - 8, original.left() + dx))
            if "right" in zona:
                rect.setRight(max(original.left() + 8, original.right() + dx))
            if zona.startswith("top"):
                rect.setTop(min(original.bottom() - 8, original.top() + dy))
            if zona.startswith("bottom"):
                rect.setBottom(max(original.top() + 8, original.bottom() + dy))
        self.rectangulo_documento = rect
        self.geometriaCambiada.emit(QRect(rect))

    def _crecer_si_hace_falta(self) -> None:
        """El cuadro crece hacia abajo mientras se escribe."""

        if not self.isVisible() or self.rectangulo_documento.isEmpty():
            return
        alto_texto = self.document().size().height() / self.zoom
        if alto_texto > self.rectangulo_documento.height():
            rect = QRect(self.rectangulo_documento)
            rect.setHeight(int(alto_texto) + 2)
            self.rectangulo_documento = rect
            self.geometriaCambiada.emit(QRect(rect))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._marco.setGeometry(self.rect())
        self._marco.raise_()

    def _pintar_marco(self, painter: QPainter) -> None:
        area = QRectF(self._area_texto()).adjusted(-0.5, -0.5, -0.5, -0.5)
        for color, estilo in ((QColor("#111111"), Qt.PenStyle.DashLine), (QColor("#ffffff"), Qt.PenStyle.DotLine)):
            painter.setPen(QPen(color, 1, estilo))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.setBrush(QColor("#ffffff"))
        for punto in self._tiradores().values():
            painter.drawRect(QRectF(punto.x() - 3, punto.y() - 3, 6, 6))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            estilos = {
                Qt.Key.Key_B: "bold",
                Qt.Key.Key_I: "italic",
                Qt.Key.Key_U: "underline",
            }
            if event.key() in estilos:
                self.estiloSolicitado.emit(estilos[event.key()])
                event.accept()
                return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.confirmarSolicitado.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancelarSolicitado.emit()
            event.accept()
            return
        super().keyPressEvent(event)
