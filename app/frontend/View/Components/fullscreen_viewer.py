from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget


class VisorPantallaCompleta(QWidget):
    """«Pantalla completa»: solo la imagen, sin interfaz.

    Se cierra con Esc, F11 o un clic.
    """

    cerrado = Signal()

    def __init__(self, imagen: QImage, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Pantalla completa")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._imagen = QImage(imagen)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if not self._imagen.isNull():
            tamano = self._imagen.size()
            if tamano.width() > self.width() or tamano.height() > self.height():
                tamano.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            destino = QRect(
                (self.width() - tamano.width()) // 2,
                (self.height() - tamano.height()) // 2,
                tamano.width(),
                tamano.height(),
            )
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(destino, self._imagen)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.close()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.close()

    def closeEvent(self, event) -> None:
        self.cerrado.emit()
        super().closeEvent(event)
