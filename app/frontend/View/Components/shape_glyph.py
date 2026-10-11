from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QToolButton, QWidget

from backend.Service.Drawing.shape_tools import shape_outline_path
from frontend.Config import metrics as M
from frontend.Config.theme import colors
from frontend.View.Components.ribbon_buttons import tema_oscuro_activo


class GlifoForma(QToolButton):
    """Celda de la galería de formas; dibuja la misma geometría que el lienzo."""

    formaSeleccionada = Signal(str)
    LADO_FIGURA = 15.0

    def __init__(self, forma: str, nombre: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.forma = forma
        self.setObjectName("ShapeGlyph")
        self.setCheckable(True)
        self.setFixedSize(M.SHAPE_CELL_WIDTH, M.SHAPE_CELL_HEIGHT)
        self.setToolTip(nombre)
        self.setAccessibleName(nombre)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.formaSeleccionada.emit(self.forma)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.isChecked():
            painter.setPen(QPen(QColor(c["checked_border"]), 1))
            painter.setBrush(QColor(c["checked_bg"]))
            painter.drawRoundedRect(area, 3, 3)
        elif self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c["hover"]))
            painter.drawRoundedRect(area, 3, 3)
        lapiz = QPen(QColor(c["icon"]), 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(lapiz)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        lado = self.LADO_FIGURA
        rect = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        painter.drawPath(shape_outline_path(self.forma, rect))
        painter.end()


ShapeGlyph = GlifoForma
