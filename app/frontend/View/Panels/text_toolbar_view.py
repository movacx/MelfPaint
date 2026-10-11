from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from frontend.Config import metrics as M
from frontend.View.Components.ribbon_buttons import cargar_icono, registrar_icono


class TextToolbarView(QFrame):
    formatoCambiado = Signal(dict)
    confirmarSolicitado = Signal()
    cancelarSolicitado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actualizando = True
        self.setObjectName("TextToolbarHost")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(M.TEXT_TOOLBAR_WIDTH + 24, M.TEXT_TOOLBAR_HEIGHT + 12)
        self._construir_interfaz()
        self._actualizando = False
        self.setVisible(False)

    def _construir_interfaz(self) -> None:
        anfitrion = QHBoxLayout(self)
        anfitrion.setContentsMargins(12, 6, 12, 12)

        self.superficie = QFrame(self)
        self.superficie.setObjectName("TextToolbarSurface")
        self.superficie.setFixedSize(M.TEXT_TOOLBAR_WIDTH, M.TEXT_TOOLBAR_SURFACE_HEIGHT)
        anfitrion.addWidget(self.superficie)

        sombra = QGraphicsDropShadowEffect(self.superficie)
        sombra.setBlurRadius(16)
        sombra.setOffset(0, 4)
        sombra.setColor(QColor(0, 0, 0, 45))
        self.superficie.setGraphicsEffect(sombra)

        layout = QHBoxLayout(self.superficie)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(5)

        self.familia = QFontComboBox(self.superficie)
        self.familia.setEditable(True)
        self.familia.setFixedSize(190, 36)
        self.familia.setAccessibleName("Familia de fuente")
        self.familia.currentTextChanged.connect(self._emitir_formato)
        self.familia.setCurrentText("Calibri")
        layout.addWidget(self.familia)

        self.tamano = QComboBox(self.superficie)
        for valor in (8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72, 96):
            self.tamano.addItem(str(valor), valor)
        self.tamano.setCurrentIndex(self.tamano.findData(20))
        self.tamano.setFixedSize(72, 36)
        self.tamano.setAccessibleName("Tamaño del texto")
        self.tamano.currentIndexChanged.connect(self._emitir_formato)
        layout.addWidget(self.tamano)

        self.negrita = self._boton("Negrita", "bold", checkable=True)
        self.cursiva = self._boton("Cursiva", "italic", checkable=True)
        self.subrayado = self._boton("Subrayado", "underline", checkable=True)
        self.tachado = self._boton("Tachado", "strikethrough", checkable=True)
        for boton in (self.negrita, self.cursiva, self.subrayado, self.tachado):
            boton.toggled.connect(self._emitir_formato)
            layout.addWidget(boton)

        separador = QFrame(self.superficie)
        separador.setObjectName("TextToolbarSeparator")
        separador.setFixedSize(1, 24)
        layout.addWidget(separador)

        self.grupo_alineacion = QButtonGroup(self)
        self.grupo_alineacion.setExclusive(True)
        self.grupo_alineacion.buttonClicked.connect(self._emitir_formato)
        self.botones_alineacion: dict[str, QToolButton] = {}
        for value, texto, icono in (
            ("left", "Alinear a la izquierda", "align-left"),
            ("center", "Centrar", "align-center"),
            ("right", "Alinear a la derecha", "align-right"),
        ):
            boton = self._boton(texto, icono, checkable=True)
            boton.setProperty("alignmentValue", value)
            self.grupo_alineacion.addButton(boton)
            self.botones_alineacion[value] = boton
            layout.addWidget(boton)
        self.botones_alineacion["left"].setChecked(True)

        self.fondo = QCheckBox("Relleno de fondo", self.superficie)
        self.fondo.setObjectName("BackgroundFillCheck")
        self.fondo.setAccessibleName("Relleno de fondo del texto")
        self.fondo.setFixedHeight(36)
        self.fondo.toggled.connect(self._emitir_formato)
        layout.addWidget(self.fondo)

        # El texto se confirma al cambiar de herramienta o al hacer clic fuera. Se
        # conservan estos objetos invisibles para integraciones anteriores.
        self.btn_confirmar = self._boton("Confirmar texto", "check")
        self.btn_confirmar.clicked.connect(self.confirmarSolicitado.emit)
        self.btn_confirmar.hide()
        self.btn_cancelar = self._boton("Cancelar texto", "cancel")
        self.btn_cancelar.clicked.connect(self.cancelarSolicitado.emit)
        self.btn_cancelar.hide()

    def _boton(self, tooltip: str, icono: str, checkable: bool = False) -> QToolButton:
        boton = QToolButton(self.superficie)
        boton.setObjectName("TextFormatButton")
        registrar_icono(boton, icono)
        boton.setIcon(cargar_icono(icono))
        boton.setIconSize(QSize(18, 18))
        boton.setToolTip(tooltip)
        boton.setAccessibleName(tooltip)
        boton.setCheckable(checkable)
        boton.setFixedSize(36, 36)
        return boton

    def formato_actual(self) -> dict:
        alineacion = next(
            (
                value
                for value, boton in self.botones_alineacion.items()
                if boton.isChecked()
            ),
            "left",
        )
        return {
            "familia": self.familia.currentText().strip() or "Calibri",
            "tamano": int(self.tamano.currentData()),
            "negrita": self.negrita.isChecked(),
            "cursiva": self.cursiva.isChecked(),
            "subrayado": self.subrayado.isChecked(),
            "tachado": self.tachado.isChecked(),
            "alineacion": alineacion,
            "fondo": "opaque" if self.fondo.isChecked() else "transparent",
        }

    def set_format(self, formato: dict) -> None:
        self._actualizando = True
        try:
            if "familia" in formato:
                self.familia.setCurrentText(str(formato["familia"]))
            if "tamano" in formato:
                value = int(formato["tamano"])
                indice = self.tamano.findData(value)
                if indice < 0:
                    self.tamano.addItem(str(value), value)
                    indice = self.tamano.count() - 1
                self.tamano.setCurrentIndex(indice)
            self.negrita.setChecked(bool(formato.get("negrita", False)))
            self.cursiva.setChecked(bool(formato.get("cursiva", False)))
            self.subrayado.setChecked(bool(formato.get("subrayado", False)))
            self.tachado.setChecked(bool(formato.get("tachado", False)))
            value = str(formato.get("alineacion", "left"))
            self.botones_alineacion.get(value, self.botones_alineacion["left"]).setChecked(True)
            self.fondo.setChecked(formato.get("fondo", "transparent") == "opaque")
        finally:
            self._actualizando = False

    def set_text_mode(self, active: bool) -> None:
        self.setVisible(bool(active))
        if active:
            self.raise_()

    def _emitir_formato(self, *args) -> None:
        if not self._actualizando:
            self.formatoCambiado.emit(self.formato_actual())


TextToolbar = TextToolbarView
