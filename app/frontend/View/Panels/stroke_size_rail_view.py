from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from backend.Service.Drawing.shape_tools import PAINT_SHAPES

from frontend.Config import metrics as M
from frontend.Config.theme import colors
from frontend.View.Components.ribbon_buttons import cargar_icono, registrar_icono, tema_oscuro_activo


class _BarraVertical(QWidget):
    """Barra vertical: el mínimo queda abajo y el máximo arriba."""

    valorCambiado = Signal(int)

    def __init__(self, minimo: int, maximo: int, curva: float, nombre: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._minimo = minimo
        self._maximo = maximo
        self._curva = curva  # >1 da más precisión a los valores pequeños
        self._valor = maximo
        self.setFixedWidth(28)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(nombre)

    def valor(self) -> int:
        return self._valor

    def set_rango(self, minimo: int, maximo: int) -> None:
        self._minimo, self._maximo = minimo, maximo
        self.set_valor(self._valor)

    def set_valor(self, valor: int, emitir: bool = False) -> None:
        valor = max(self._minimo, min(self._maximo, int(valor)))
        if valor == self._valor:
            return
        self._valor = valor
        self.update()
        if emitir:
            self.valorCambiado.emit(valor)

    def _fraccion(self) -> float:
        total = self._maximo - self._minimo
        if total <= 0:
            return 0.0
        return ((self._valor - self._minimo) / total) ** (1.0 / self._curva)

    def _pista(self) -> QRectF:
        return QRectF(0, 10, self.width(), max(1, self.height() - 20))

    def _desde_posicion(self, y: float) -> int:
        pista = self._pista()
        fraccion = 1.0 - (y - pista.top()) / pista.height()
        fraccion = max(0.0, min(1.0, fraccion))
        return round(self._minimo + (self._maximo - self._minimo) * fraccion**self._curva)

    def _mover(self, valor: int) -> None:
        self.set_valor(valor, emitir=True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._mover(self._desde_posicion(event.position().y()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._mover(self._desde_posicion(event.position().y()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        paso = 1 if event.angleDelta().y() > 0 else -1
        self._mover(self._valor + paso)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        pasos = {
            Qt.Key.Key_Up: 1,
            Qt.Key.Key_Right: 1,
            Qt.Key.Key_Down: -1,
            Qt.Key.Key_Left: -1,
            Qt.Key.Key_PageUp: 10,
            Qt.Key.Key_PageDown: -10,
        }
        if event.key() in pasos:
            self._mover(self._valor + pasos[event.key()])
        elif event.key() == Qt.Key.Key_Home:
            self._mover(self._minimo)
        elif event.key() == Qt.Key.Key_End:
            self._mover(self._maximo)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        c = colors()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pista = self._pista()
        x = self.width() / 2
        y = pista.bottom() - pista.height() * self._fraccion()
        pintor.setPen(QPen(QColor(c["slider"]), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pintor.drawLine(QPointF(x, pista.top()), QPointF(x, pista.bottom()))
        pintor.setPen(QPen(QColor(c["accent"]), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pintor.drawLine(QPointF(x, y), QPointF(x, pista.bottom()))
        pintor.setPen(QPen(QColor(c["menu"]), 3))
        pintor.setBrush(QColor(c["accent"]))
        pintor.drawEllipse(QPointF(x, y), 6.5, 6.5)
        if self.hasFocus():
            pintor.setPen(QPen(QColor(c["accent"]), 1))
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawEllipse(QPointF(x, y), 10, 10)
        pintor.end()


class _Columna(QFrame):
    def __init__(self, icono: str, barra: _BarraVertical, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RailPill")
        self.setFixedWidth(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 6)
        layout.setSpacing(4)
        self.icono = QLabel(self)
        self.icono.setFixedSize(28, 24)
        self.icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.barra = barra
        self.valor = QLabel(self)
        self.valor.setObjectName("RailValue")
        self.valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.valor.setFixedHeight(16)
        layout.addWidget(self.icono, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(barra, 1, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.valor)
        self.set_icono(icono)

    def set_icono(self, nombre: str) -> None:
        registrar_icono(self.icono, nombre)
        self.icono.setPixmap(cargar_icono(nombre, tema_oscuro_activo()).pixmap(20, 20))


class StrokeSizeRailView(QFrame):
    """Barras laterales: grosor libre (1-256 px) y opacidad o tolerancia."""

    tamanoSeleccionado = Signal(int)
    opacidadSeleccionada = Signal(str, int)
    toleranciaSeleccionada = Signal(int)
    visibilityChanged = Signal(bool)

    HERRAMIENTAS_CON_TAMANO = {"pencil", "brush", "eraser"}
    HERRAMIENTAS_CON_OPACIDAD = {"pencil", "brush", "eraser"}
    TAMANO_MAXIMO = 256

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._herramienta = "pencil"
        self._modo = "opacity"
        self.setObjectName("StrokeSizeRail")
        # Se estira con el área de trabajo, dentro de unos límites.
        self.setFixedWidth(M.STROKE_RAIL_WIDTH)
        self.setMinimumHeight(M.STROKE_RAIL_MIN_HEIGHT)
        self.setMaximumHeight(M.STROKE_RAIL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._barra_tamano = _BarraVertical(1, self.TAMANO_MAXIMO, 2.0, "Grosor del trazo", self)
        self._barra_tamano.set_valor(2)
        self._barra_secundaria = _BarraVertical(0, 100, 1.0, "Opacidad", self)
        self.columna_tamano = _Columna("size", self._barra_tamano, self)
        self.columna_secundaria = _Columna("opacity", self._barra_secundaria, self)
        self.columna_tamano.setToolTip("Grosor (también Ctrl++ y Ctrl+-)")
        self.columna_secundaria.setToolTip("Opacidad")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.columna_tamano)
        layout.addWidget(self.columna_secundaria)

        self._barra_tamano.valorCambiado.connect(self._cambiar_tamano)
        self._barra_secundaria.valorCambiado.connect(self._cambiar_secundario)
        self._actualizar_etiquetas()
        self.hide()

    # ------------------------------------------------------------------
    def set_tool(self, tool_id: str) -> None:
        self._herramienta = str(tool_id)
        con_tamano = self._herramienta in self.HERRAMIENTAS_CON_TAMANO or self._es_forma(self._herramienta)
        es_relleno = self._herramienta == "fill"
        self.columna_tamano.setVisible(con_tamano)
        self._modo = "tolerance" if es_relleno else "opacity"
        con_secundaria = es_relleno or self._herramienta in self.HERRAMIENTAS_CON_OPACIDAD or self._es_forma(self._herramienta)
        self.columna_secundaria.setVisible(con_secundaria)
        self.setVisible(con_tamano or con_secundaria)
        if es_relleno:
            self._barra_secundaria.set_rango(0, 255)
            self.columna_secundaria.set_icono("tolerance")
            self.columna_secundaria.setToolTip("Tolerancia del relleno")
            self._barra_secundaria.setAccessibleName("Tolerancia del relleno")
        else:
            self._barra_secundaria.set_rango(0, 100)
            self.columna_secundaria.set_icono("opacity")
            tip = "Opacidad del borrador" if self._herramienta == "eraser" else "Opacidad"
            self.columna_secundaria.setToolTip(tip)
            self._barra_secundaria.setAccessibleName(tip)
        # Ancho según las columnas visibles.
        columnas = int(con_tamano) + int(con_secundaria)
        self.setFixedWidth(88 if columnas == 2 else 40)
        self._actualizar_etiquetas()
        self.visibilityChanged.emit(self.isVisibleTo(self.parentWidget()))

    @staticmethod
    def _es_forma(tool_id: str) -> bool:
        return tool_id in PAINT_SHAPES

    def set_size(self, value: int) -> None:
        self._barra_tamano.set_valor(int(value))
        self._actualizar_etiquetas()

    def set_values(self, size: int, opacity: int, tolerance: int) -> None:
        self._barra_tamano.set_valor(int(size))
        self._barra_secundaria.set_valor(int(tolerance if self._modo == "tolerance" else opacity))
        self._actualizar_etiquetas()

    def _cambiar_tamano(self, valor: int) -> None:
        self._actualizar_etiquetas()
        self.tamanoSeleccionado.emit(valor)

    def _cambiar_secundario(self, valor: int) -> None:
        self._actualizar_etiquetas()
        if self._modo == "tolerance":
            self.toleranciaSeleccionada.emit(valor)
        else:
            self.opacidadSeleccionada.emit(self._herramienta, valor)

    def _actualizar_etiquetas(self) -> None:
        self.columna_tamano.valor.setText(str(self._barra_tamano.valor()))
        sufijo = "" if self._modo == "tolerance" else "%"
        self.columna_secundaria.valor.setText(f"{self._barra_secundaria.valor()}{sufijo}")


ToolSizeRailView = StrokeSizeRailView
