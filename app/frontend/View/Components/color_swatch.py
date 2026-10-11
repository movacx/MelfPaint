from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QToolButton, QWidget

from frontend.Config import metrics as M
from frontend.Config.theme import colors
from frontend.View.Components.ribbon_buttons import tema_oscuro_activo


class MuestraColor(QToolButton):
    """Círculo de color de la paleta (o color 1 / color 2 si ``grande``)."""

    colorSeleccionado = Signal(QColor, str)

    def __init__(
        self,
        color: QColor | str,
        grande: bool = False,
        vacio: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.color = QColor(color)
        self._seleccionada = False
        self._grande = grande
        self._vacio = bool(vacio)
        self._diametro = M.COLOR_ACTIVE if grande else M.COLOR_SWATCH
        lado = self._diametro + (10 if grande else 6)
        self.setFixedSize(lado, lado)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAccessibleName("Color personalizado vacío" if self._vacio else f"Color {self.color.name()}")
        self.setToolTip("Color personalizado" if self._vacio else self._nombre())

    def _nombre(self) -> str:
        return f"Rojo {self.color.red()}, verde {self.color.green()}, azul {self.color.blue()}"

    def set_color(self, color: QColor | str) -> None:
        nuevo_color = QColor(color)
        if not nuevo_color.isValid():
            return
        self.color = nuevo_color
        self._vacio = False
        self.setAccessibleName(f"Color {self.color.name()}")
        self.setToolTip(self._nombre())
        self.update()

    @property
    def vacio(self) -> bool:
        return self._vacio

    def set_vacio(self) -> None:
        self._vacio = True
        self.color = QColor("#ffffff")
        self.setAccessibleName("Color personalizado vacío")
        self.setToolTip("Color personalizado")
        self.update()

    def set_selected(self, seleccionada: bool) -> None:
        self._seleccionada = seleccionada
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._vacio:
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.colorSeleccionado.emit(QColor(self.color), "secundario")
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.colorSeleccionado.emit(QColor(self.color), "primario")
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        centro = QRectF(self.rect()).center()
        radio = self._diametro / 2

        if self._seleccionada:
            anillo = QPen(QColor(c["checked_border"]), 1.6)
            painter.setPen(anillo)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centro, radio + 3.2, radio + 3.2)
        elif self.underMouse() and not self._vacio:
            painter.setPen(QPen(QColor(c["swatch_border"]), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centro, radio + 2.5, radio + 2.5)

        borde = QColor(0, 0, 0, 72) if not tema_oscuro_activo() else QColor(255, 255, 255, 70)
        painter.setPen(QPen(borde, 1))
        if self._vacio:
            painter.setBrush(QColor(c["ribbon"]) if tema_oscuro_activo() else QColor("#ffffff"))
        else:
            if self.color.alpha() < 255:
                painter.setBrush(QColor("#ffffff"))
                painter.drawEllipse(centro, radio - 0.5, radio - 0.5)
            painter.setBrush(self.color)
        painter.drawEllipse(centro, radio - 0.5, radio - 0.5)
        painter.end()


ColorSwatch = MuestraColor
