from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class EspectroColor(QWidget):
    """Espectro de color: tono en horizontal y saturación en vertical."""

    cambiado = Signal(float, float)  # tono (0..1), saturación (0..1)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(328, 208)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Espectro de color")
        self._tono = 0.0
        self._saturacion = 1.0
        self._imagen = self._generar()

    def _generar(self) -> QImage:
        ancho, alto = self.width(), self.height()
        tono = np.linspace(0.0, 1.0, ancho, endpoint=False)[None, :].repeat(alto, 0)
        saturacion = np.linspace(1.0, 0.0, alto)[:, None].repeat(ancho, 1)
        sector = tono * 6.0
        i = np.floor(sector).astype(int) % 6
        f = sector - np.floor(sector)
        v = np.ones_like(tono)
        p = v * (1 - saturacion)
        q = v * (1 - saturacion * f)
        t = v * (1 - saturacion * (1 - f))
        r = np.choose(i, [v, q, p, p, t, v])
        g = np.choose(i, [t, v, v, q, p, p])
        b = np.choose(i, [p, p, t, v, v, q])
        pixeles = np.empty((alto, ancho, 4), dtype=np.uint8)
        pixeles[:, :, 0] = np.clip(r * 255, 0, 255)
        pixeles[:, :, 1] = np.clip(g * 255, 0, 255)
        pixeles[:, :, 2] = np.clip(b * 255, 0, 255)
        pixeles[:, :, 3] = 255
        return QImage(pixeles.data, ancho, alto, ancho * 4, QImage.Format.Format_RGBA8888).copy()

    def set_valores(self, tono: float, saturacion: float) -> None:
        self._tono = max(0.0, min(1.0, tono))
        self._saturacion = max(0.0, min(1.0, saturacion))
        self.update()

    def _desde_raton(self, punto: QPointF) -> None:
        self._tono = max(0.0, min(0.9999, punto.x() / self.width()))
        self._saturacion = max(0.0, min(1.0, 1.0 - punto.y() / self.height()))
        self.update()
        self.cambiado.emit(self._tono, self._saturacion)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._desde_raton(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._desde_raton(event.position())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        recorte = QPainterPath()
        recorte.addRoundedRect(QRectF(self.rect()), 6, 6)
        painter.setClipPath(recorte)
        painter.drawImage(0, 0, self._imagen)
        painter.setClipping(False)
        x = self._tono * self.width()
        y = (1.0 - self._saturacion) * self.height()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 150), 3))
        painter.drawEllipse(QPointF(x, y), 7, 7)
        painter.setPen(QPen(QColor("white"), 1.6))
        painter.drawEllipse(QPointF(x, y), 7, 7)
        painter.end()


class BarraBrillo(QWidget):
    """Barra de brillo (valor) con el tono y la saturación actuales."""

    cambiado = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(328, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Brillo")
        self._color = QColor("red")
        self._valor = 1.0

    def set_color(self, tono: float, saturacion: float, valor: float) -> None:
        self._color = QColor.fromHsvF(tono, saturacion, 1.0)
        self._valor = max(0.0, min(1.0, valor))
        self.update()

    def _desde_raton(self, x: float) -> None:
        self._valor = max(0.0, min(1.0, (x - 10) / (self.width() - 20)))
        self.update()
        self.cambiado.emit(self._valor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._desde_raton(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._desde_raton(event.position().x())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pista = QRectF(0, 4, self.width(), self.height() - 8)
        degradado = QLinearGradient(pista.topLeft(), pista.topRight())
        degradado.setColorAt(0.0, QColor("black"))
        degradado.setColorAt(1.0, self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(degradado)
        painter.drawRoundedRect(pista, pista.height() / 2, pista.height() / 2)
        x = 10 + self._valor * (self.width() - 20)
        centro = QPointF(x, self.height() / 2)
        painter.setBrush(QColor.fromHsvF(self._color.hsvHueF() if self._color.hsvHueF() >= 0 else 0, self._color.hsvSaturationF(), self._valor))
        painter.setPen(QPen(QColor("white"), 2.5))
        painter.drawEllipse(centro, 9, 9)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centro, 10.5, 10.5)
        painter.end()


class VistaPreviaColor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 208)
        self.nuevo = QColor("black")
        self.actual = QColor("black")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        recorte = QPainterPath()
        recorte.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        painter.setClipPath(recorte)
        mitad = self.height() / 2
        painter.fillRect(QRectF(0, 0, self.width(), mitad), self.nuevo)
        painter.fillRect(QRectF(0, mitad, self.width(), mitad), self.actual)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(recorte)
        painter.end()


class EditColorsDialog(QDialog):
    """«Editar colores»: espectro, brillo, RGB/HSV y hexadecimal."""

    colorConfirmado = Signal(QColor)

    def __init__(self, color: QColor | str = "#000000", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        inicial = QColor(color)
        if not inicial.isValid():
            inicial = QColor("#000000")
        inicial.setAlpha(255)
        self._inicial = QColor(inicial)
        self._actualizando = False
        tono, saturacion, valor = inicial.hsvHueF(), inicial.hsvSaturationF(), inicial.valueF()
        self._tono = tono if tono >= 0 else 0.0
        self._saturacion = saturacion
        self._valor = valor
        self.setWindowTitle("Editar colores")
        self.setModal(True)
        self._construir_interfaz()
        self._sincronizar(desde="inicio")

    def _construir_interfaz(self) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(24, 20, 24, 20)
        principal.setSpacing(14)

        titulo = QLabel("Editar colores", self)
        titulo.setObjectName("DialogTitle")
        principal.addWidget(titulo)

        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.espectro = EspectroColor(self)
        self.espectro.cambiado.connect(self._espectro_cambiado)
        fila.addWidget(self.espectro)
        self.vista_previa = VistaPreviaColor(self)
        self.vista_previa.actual = QColor(self._inicial)
        self.vista_previa.setToolTip("Arriba: color nuevo · Abajo: color actual")
        fila.addWidget(self.vista_previa)
        principal.addLayout(fila)

        self.brillo = BarraBrillo(self)
        self.brillo.cambiado.connect(self._brillo_cambiado)
        principal.addWidget(self.brillo)

        campos = QGridLayout()
        campos.setHorizontalSpacing(10)
        campos.setVerticalSpacing(8)
        self.modo = QComboBox(self)
        self.modo.addItem("RGB", "rgb")
        self.modo.addItem("HSV", "hsv")
        self.modo.setAccessibleName("Modelo de color")
        self.modo.currentIndexChanged.connect(lambda: self._sincronizar(desde="modo"))
        campos.addWidget(self.modo, 0, 0)
        self.hexadecimal = QLineEdit(self)
        self.hexadecimal.setAccessibleName("Código hexadecimal")
        self.hexadecimal.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^#?[0-9A-Fa-f]{0,6}$"), self.hexadecimal)
        )
        self.hexadecimal.editingFinished.connect(self._hex_cambiado)
        campos.addWidget(self.hexadecimal, 0, 1)

        self.etiquetas: list[QLabel] = []
        self.valores: list[QSpinBox] = []
        for indice in range(3):
            caja = QSpinBox(self)
            caja.setKeyboardTracking(False)
            caja.valueChanged.connect(lambda _valor: self._campos_cambiados())
            etiqueta = QLabel(self)
            self.valores.append(caja)
            self.etiquetas.append(etiqueta)
            campos.addWidget(caja, indice + 1, 0)
            campos.addWidget(etiqueta, indice + 1, 1)
        principal.addLayout(campos)

        botones = QHBoxLayout()
        botones.setSpacing(8)
        self.btn_aceptar = QPushButton("Aceptar", self)
        self.btn_aceptar.setObjectName("PrimaryButton")
        self.btn_aceptar.setDefault(True)
        self.btn_aceptar.clicked.connect(self.accept)
        self.btn_cancelar = QPushButton("Cancelar", self)
        self.btn_cancelar.clicked.connect(self.reject)
        for boton in (self.btn_aceptar, self.btn_cancelar):
            boton.setMinimumWidth(150)
            botones.addWidget(boton)
        principal.addLayout(botones)

    # ------------------------------------------------------------------
    def color_actual(self) -> QColor:
        return QColor.fromHsvF(self._tono, self._saturacion, self._valor)

    def _espectro_cambiado(self, tono: float, saturacion: float) -> None:
        self._tono, self._saturacion = tono, saturacion
        self._sincronizar(desde="espectro")

    def _brillo_cambiado(self, valor: float) -> None:
        self._valor = valor
        self._sincronizar(desde="brillo")

    def _hex_cambiado(self) -> None:
        texto = self.hexadecimal.text().strip().lstrip("#")
        if len(texto) == 3:
            texto = "".join(caracter * 2 for caracter in texto)
        color = QColor(f"#{texto}")
        if len(texto) != 6 or not color.isValid():
            self._sincronizar(desde="modo")
            return
        self._desde_color(color)
        self._sincronizar(desde="hex")

    def _campos_cambiados(self) -> None:
        if self._actualizando:
            return
        a, b, c = (caja.value() for caja in self.valores)
        if self.modo.currentData() == "rgb":
            self._desde_color(QColor(a, b, c))
        else:
            self._tono = (a % 360) / 360.0
            self._saturacion = b / 100.0
            self._valor = c / 100.0
        self._sincronizar(desde="campos")

    def _desde_color(self, color: QColor) -> None:
        tono = color.hsvHueF()
        # Un gris no tiene tono: se conserva el que ya estaba elegido.
        if tono >= 0:
            self._tono = tono
        self._saturacion = color.hsvSaturationF()
        self._valor = color.valueF()

    def _sincronizar(self, desde: str) -> None:
        self._actualizando = True
        try:
            color = self.color_actual()
            if desde != "espectro":
                self.espectro.set_valores(self._tono, self._saturacion)
            self.brillo.set_color(self._tono, self._saturacion, self._valor)
            self.vista_previa.nuevo = color
            self.vista_previa.update()
            if desde != "hex":
                self.hexadecimal.setText(color.name().upper())
            rgb = self.modo.currentData() == "rgb"
            nombres = ("Rojo", "Verde", "Azul") if rgb else ("Tono", "Saturación", "Valor")
            maximos = (255, 255, 255) if rgb else (359, 100, 100)
            valores = (
                (color.red(), color.green(), color.blue())
                if rgb
                else (round(self._tono * 360) % 360, round(self._saturacion * 100), round(self._valor * 100))
            )
            if desde != "campos":
                for caja, etiqueta, nombre, maximo, valor in zip(self.valores, self.etiquetas, nombres, maximos, valores):
                    caja.setRange(0, maximo)
                    caja.setValue(int(valor))
                    caja.setAccessibleName(nombre)
                    etiqueta.setText(nombre)
        finally:
            self._actualizando = False

    def accept(self) -> None:
        if self.hexadecimal.hasFocus():
            self._hex_cambiado()
        self.colorConfirmado.emit(self.color_seleccionado())
        super().accept()

    def color_seleccionado(self) -> QColor:
        return self.color_actual()

    selected_color = color_seleccionado
