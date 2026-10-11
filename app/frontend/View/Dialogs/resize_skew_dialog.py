from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ResizeSkewDialog(QDialog):
    MAX_PIXELS = 100_000_000

    def __init__(self, width: int, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ancho_original = max(1, int(width))
        self.alto_original = max(1, int(height))
        self.proporcion = self.ancho_original / self.alto_original
        self._actualizando = False

        self.setWindowTitle("Cambiar tamaño y sesgar")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._construir_interfaz()

    def _construir_interfaz(self) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(16, 16, 16, 16)
        principal.setSpacing(12)

        cambiar = QGroupBox("Cambiar el tamaño", self)
        cambiar_layout = QVBoxLayout(cambiar)

        unidades = QHBoxLayout()
        self.porcentaje = QRadioButton("Porcentaje", cambiar)
        self.pixeles = QRadioButton("Píxeles", cambiar)
        self.pixeles.setChecked(True)
        unidades.addWidget(self.porcentaje)
        unidades.addWidget(self.pixeles)
        unidades.addStretch(1)
        cambiar_layout.addLayout(unidades)

        formulario = QFormLayout()
        self.horizontal = QSpinBox(cambiar)
        self.vertical = QSpinBox(cambiar)
        formulario.addRow("Horizontal:", self.horizontal)
        formulario.addRow("Vertical:", self.vertical)
        cambiar_layout.addLayout(formulario)

        self.mantener_proporcion = QCheckBox("Mantener relación de aspecto", cambiar)
        self.mantener_proporcion.setChecked(True)
        cambiar_layout.addWidget(self.mantener_proporcion)
        principal.addWidget(cambiar)

        sesgar = QGroupBox("Sesgar", self)
        sesgar_formulario = QFormLayout(sesgar)
        self.sesgo_horizontal = QSpinBox(sesgar)
        self.sesgo_vertical = QSpinBox(sesgar)
        for campo in (self.sesgo_horizontal, self.sesgo_vertical):
            campo.setRange(-89, 89)
            campo.setSuffix("°")
        sesgar_formulario.addRow("Horizontal:", self.sesgo_horizontal)
        sesgar_formulario.addRow("Vertical:", self.sesgo_vertical)
        principal.addWidget(sesgar)

        self.resumen = QLabel(self)
        self.resumen.setWordWrap(True)
        principal.addWidget(self.resumen)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        principal.addWidget(botones)

        self.pixeles.toggled.connect(self._cambiar_unidad)
        self.horizontal.valueChanged.connect(lambda value: self._sincronizar("horizontal", value))
        self.vertical.valueChanged.connect(lambda value: self._sincronizar("vertical", value))
        self._configurar_pixeles(self.ancho_original, self.alto_original)
        # Este cuadro se abre en «Porcentaje» con 100 % en ambos ejes.
        self.porcentaje.setChecked(True)

    def _cambiar_unidad(self, usar_pixeles: bool) -> None:
        if usar_pixeles:
            ancho = max(1, round(self.ancho_original * self.horizontal.value() / 100))
            alto = max(1, round(self.alto_original * self.vertical.value() / 100))
            self._configurar_pixeles(ancho, alto)
        else:
            self._configurar_porcentaje(self.horizontal.value(), self.vertical.value())

    def _configurar_pixeles(self, ancho: int, alto: int) -> None:
        self._actualizando = True
        try:
            for campo in (self.horizontal, self.vertical):
                campo.setRange(1, 32768)
                campo.setSuffix(" px")
            self.horizontal.setValue(max(1, ancho))
            self.vertical.setValue(max(1, alto))
        finally:
            self._actualizando = False
        self._actualizar_resumen()

    def _configurar_porcentaje(self, ancho: int, alto: int) -> None:
        self._actualizando = True
        try:
            for campo in (self.horizontal, self.vertical):
                campo.setRange(1, 500)
                campo.setSuffix(" %")
            self.horizontal.setValue(max(1, round(ancho / self.ancho_original * 100)))
            self.vertical.setValue(max(1, round(alto / self.alto_original * 100)))
        finally:
            self._actualizando = False
        self._actualizar_resumen()

    def _sincronizar(self, origen: str, value: int) -> None:
        if self._actualizando:
            return
        self._actualizando = True
        try:
            if self.mantener_proporcion.isChecked():
                if self.pixeles.isChecked():
                    if origen == "horizontal":
                        self.vertical.setValue(max(1, round(value / self.proporcion)))
                    else:
                        self.horizontal.setValue(max(1, round(value * self.proporcion)))
                else:
                    campo = self.vertical if origen == "horizontal" else self.horizontal
                    campo.setValue(value)
        finally:
            self._actualizando = False
        self._actualizar_resumen()

    def ancho_actual(self) -> int:
        if hasattr(self, "pixeles") and self.pixeles.isChecked():
            return max(1, self.horizontal.value())
        if hasattr(self, "horizontal"):
            return max(1, round(self.ancho_original * self.horizontal.value() / 100))
        return self.ancho_original

    def alto_actual(self) -> int:
        if hasattr(self, "pixeles") and self.pixeles.isChecked():
            return max(1, self.vertical.value())
        if hasattr(self, "vertical"):
            return max(1, round(self.alto_original * self.vertical.value() / 100))
        return self.alto_original

    def _actualizar_resumen(self) -> None:
        self.resumen.setText(f"Resultado: {self.ancho_actual()} × {self.alto_actual()} píxeles")

    def accept(self) -> None:
        if self.ancho_actual() * self.alto_actual() > self.MAX_PIXELS:
            QMessageBox.warning(
                self,
                "Imagen demasiado grande",
                "El resultado supera 100 millones de píxeles.",
            )
            return
        super().accept()

    def valores(self) -> dict:
        return {
            "width": self.ancho_actual(),
            "height": self.alto_actual(),
            "horizontal_skew": self.sesgo_horizontal.value(),
            "vertical_skew": self.sesgo_vertical.value(),
            "keep_aspect": self.mantener_proporcion.isChecked(),
            "mode": "pixels" if self.pixeles.isChecked() else "percent",
        }

    values = valores
