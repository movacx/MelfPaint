from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QToolButton, QWidget

from frontend.Config import metrics as M
from frontend.Config.theme import colors
from frontend.View.Components.ribbon_buttons import BotonPaint, cargar_icono, registrar_icono, tema_oscuro_activo


class ZoomSlider(QWidget):
    """Deslizador de zoom: pista fina gris y tramo de acento hasta el pulgar.

    La escala es logarítmica en dos tramos: de 10 % a 100 % ocupa el 85 % de
    la pista y de 100 % a 800 % el resto, que es donde queda el pulgar
    con el zoom al 100 %.
    """

    valorCambiado = Signal(int)
    MINIMO, MAXIMO, PUNTO_100 = 10, 800, 0.85

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valor = 100
        self._arrastrando = False
        self.setFixedSize(M.ZOOM_SLIDER_WIDTH, 24)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAccessibleName("Zoom")

    def value(self) -> int:
        return self._valor

    def setValue(self, valor: int) -> None:
        self._valor = max(self.MINIMO, min(self.MAXIMO, int(valor)))
        self.update()

    def _fraccion(self, valor: float) -> float:
        if valor <= 100:
            return self.PUNTO_100 * math.log(valor / self.MINIMO) / math.log(100 / self.MINIMO)
        return self.PUNTO_100 + (1 - self.PUNTO_100) * math.log(valor / 100) / math.log(self.MAXIMO / 100)

    def _valor_en(self, fraccion: float) -> int:
        fraccion = max(0.0, min(1.0, fraccion))
        if fraccion <= self.PUNTO_100:
            return round(self.MINIMO * (100 / self.MINIMO) ** (fraccion / self.PUNTO_100))
        return round(100 * (self.MAXIMO / 100) ** ((fraccion - self.PUNTO_100) / (1 - self.PUNTO_100)))

    def _pista(self) -> tuple[float, float]:
        return 7.0, self.width() - 7.0

    def _desde_raton(self, x: float) -> None:
        inicio, fin = self._pista()
        valor = self._valor_en((x - inicio) / (fin - inicio))
        # Imanta al 100 %.
        if abs(valor - 100) <= 4:
            valor = 100
        if valor != self._valor:
            self._valor = valor
            self.update()
            self.valorCambiado.emit(valor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._arrastrando = True
            self._desde_raton(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._arrastrando:
            self._desde_raton(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._arrastrando = False

    def wheelEvent(self, event) -> None:
        paso = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
        self.setValue(round(self._valor * paso))
        self.valorCambiado.emit(self._valor)

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inicio, fin = self._pista()
        y = self.height() / 2
        x = inicio + (fin - inicio) * self._fraccion(self._valor)
        painter.setPen(QPen(QColor(c["slider"]), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x, y), QPointF(fin, y))
        painter.setPen(QPen(QColor(c["accent"]), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(inicio, y), QPointF(x, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["accent"]))
        radio = 6.5 if (self.underMouse() or self._arrastrando) else 6.0
        painter.drawEllipse(QPointF(x, y), radio, radio)
        painter.end()


class StatusBarView(QFrame):
    """Barra de estado: puntero, selección, lienzo y zoom."""

    zoomSolicitado = Signal(int)
    ajustarSolicitado = Signal()
    cuadriculaCambiada = Signal(bool)
    reglasCambiadas = Signal(bool)

    PRESETS_ZOOM = (800, 700, 600, 500, 400, 300, 200, 100, 50, 25, 12)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PaintStatusBar")
        self.setFixedHeight(M.STATUS_BAR_HEIGHT)
        self._mensaje = ""

        self.icono_puntero = self._icono("status-pointer", 25)
        self.posicion = self._etiqueta(40, 120)
        self.icono_seleccion = self._icono("status-selection", 197)
        self.tamano_seleccion = self._etiqueta(212, 140)
        self.icono_lienzo = self._icono("status-canvas", 367)
        self.tamano_documento = self._etiqueta(380, 160)

        self.porcentaje = QToolButton(self)
        self.porcentaje.setObjectName("StatusZoomText")
        self.porcentaje.setText("100%")
        self.porcentaje.setToolTip("Zoom")
        self.porcentaje.setFixedSize(52, 30)
        menu = QMenu(self.porcentaje)
        for valor in self.PRESETS_ZOOM:
            menu.addAction(f"{valor}%").triggered.connect(lambda checked=False, v=valor: self._pedir_zoom(v))
        menu.addSeparator()
        menu.addAction("Ajustar a la ventana").triggered.connect(self.ajustarSolicitado.emit)
        self.porcentaje.setMenu(menu)
        self.porcentaje.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.selector_zoom = self.porcentaje

        self.btn_zoom_menos = BotonPaint("Alejar", "zoom-out", 32, 32, 16, callback=lambda: self._paso(-1), parent=self)
        self.slider_zoom = ZoomSlider(self)
        self.slider_zoom.valorCambiado.connect(self._slider_cambiado)
        self.btn_zoom_mas = BotonPaint("Acercar", "zoom-in", 32, 32, 16, callback=lambda: self._paso(1), parent=self)
        self.btn_ajustar = self.btn_zoom_menos  # compatibilidad
        self._colocar_derecha()

    def _icono(self, nombre: str, centro_x: int) -> QLabel:
        etiqueta = QLabel(self)
        registrar_icono(etiqueta, nombre)
        etiqueta.setProperty("melfpaintIconSize", 16)
        etiqueta.setPixmap(cargar_icono(nombre, tema_oscuro_activo()).pixmap(16, 16))
        etiqueta.setGeometry(centro_x - 8, (M.STATUS_BAR_HEIGHT - 16) // 2, 16, 16)
        return etiqueta

    def _etiqueta(self, x: int, ancho: int) -> QLabel:
        etiqueta = QLabel("", self)
        etiqueta.setObjectName("StatusMetric")
        etiqueta.setGeometry(x, 0, ancho, M.STATUS_BAR_HEIGHT)
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return etiqueta

    def _colocar_derecha(self) -> None:
        ancho = self.width()
        alto = M.STATUS_BAR_HEIGHT
        # Distancias medidas desde el borde derecho.
        self.porcentaje.move(ancho - 308 - 26, (alto - 30) // 2)
        self.btn_zoom_menos.move(ancho - 257 - 16, (alto - 32) // 2)
        self.slider_zoom.move(ancho - 232, (alto - self.slider_zoom.height()) // 2)
        self.btn_zoom_mas.move(ancho - 43 - 16, (alto - 32) // 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._colocar_derecha()

    def _pedir_zoom(self, valor: int) -> None:
        self.set_zoom(valor)
        self.zoomSolicitado.emit(valor)

    def _slider_cambiado(self, valor: int) -> None:
        self.porcentaje.setText(f"{valor}%")
        self.zoomSolicitado.emit(valor)

    def _paso(self, direccion: int) -> None:
        pasos = sorted(self.PRESETS_ZOOM + (10, 16, 33, 67, 150))
        actual = self.slider_zoom.value()
        if direccion > 0:
            valor = next((item for item in pasos if item > actual), 800)
        else:
            valor = next((item for item in reversed(pasos) if item < actual), 10)
        self._pedir_zoom(valor)

    def set_zoom(self, porcentaje: int) -> None:
        porcentaje = max(10, min(800, int(porcentaje)))
        self.slider_zoom.setValue(porcentaje)
        self.porcentaje.setText(f"{porcentaje}%")

    def set_pointer_position(self, x: int, y: int) -> None:
        self.posicion.setText(f"{x}, {y}px")

    def clear_pointer_position(self) -> None:
        self.posicion.setText("")

    def set_document_size(self, ancho: int, alto: int) -> None:
        self.tamano_documento.setText(f"{ancho} × {alto}px")

    def set_selection_size(self, ancho: int = 0, alto: int = 0) -> None:
        self.tamano_seleccion.setText(f"{ancho} × {alto}px" if ancho > 0 and alto > 0 else "")

    def set_status_message(self, mensaje: str) -> None:
        # Los mensajes no se muestran en la barra de estado; se conservan como
        # descripción accesible para lectores de pantalla.
        self._mensaje = str(mensaje or "")
        self.setAccessibleDescription(self._mensaje)

    showMessage = set_status_message


StatusBar = StatusBarView
