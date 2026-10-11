from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ImagePropertiesDialog(QDialog):
    """«Propiedades de imagen» (Ctrl+E)."""

    MAX_PIXELS = 100_000_000
    DEFAULT_SIZE = (1152, 648)

    def __init__(
        self,
        width: int,
        height: int,
        parent: QWidget | None = None,
        file_path: str | Path | None = None,
        file_size: int | None = None,
        dpi: int = 96,
        transparent: bool = False,
        background: QColor | str = "#ffffff",
        modified: str = "",
    ) -> None:
        super().__init__(parent)
        self.ancho_pixeles = max(1, int(width))
        self.alto_pixeles = max(1, int(height))
        self.dpi_original = max(1, int(dpi))
        self.color_fondo = QColor(background)
        self._unidad = "px"
        self._actualizando = False

        self.setWindowTitle("Propiedades de imagen")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._construir_interfaz(file_path, file_size, transparent, modified)

    def _construir_interfaz(self, file_path, file_size, transparent: bool, modified: str) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(16, 16, 16, 16)
        principal.setSpacing(12)

        atributos = QGroupBox("Atributos del archivo", self)
        info_form = QFormLayout(atributos)
        ruta = Path(file_path) if file_path else None
        info_form.addRow("Nombre:", QLabel(ruta.name if ruta else "Sin título", atributos))
        info_form.addRow("Guardado por última vez:", QLabel(modified or "No disponible", atributos))
        info_form.addRow(
            "Tamaño en disco:",
            QLabel(self._tamano_legible(file_size) if file_size is not None else "No disponible", atributos),
        )
        self.resolucion = QSpinBox(atributos)
        self.resolucion.setRange(1, 1200)
        self.resolucion.setValue(self.dpi_original)
        self.resolucion.setSuffix(" PPP")
        self.resolucion.valueChanged.connect(self._resolucion_cambiada)
        info_form.addRow("Resolución:", self.resolucion)
        principal.addWidget(atributos)

        fila = QHBoxLayout()
        unidades = QGroupBox("Unidades", self)
        unidades_layout = QVBoxLayout(unidades)
        self.grupo_unidades = QButtonGroup(self)
        self.radios_unidad: dict[str, QRadioButton] = {}
        for valor, texto in (("in", "Pulgadas"), ("cm", "Centímetros"), ("px", "Píxeles")):
            radio = QRadioButton(texto, unidades)
            radio.setProperty("unidad", valor)
            self.grupo_unidades.addButton(radio)
            self.radios_unidad[valor] = radio
            unidades_layout.addWidget(radio)
        self.radios_unidad["px"].setChecked(True)
        self.grupo_unidades.buttonToggled.connect(self._cambiar_unidad)
        fila.addWidget(unidades)

        colores = QGroupBox("Colores", self)
        colores_layout = QVBoxLayout(colores)
        self.blanco_negro = QRadioButton("Blanco y negro", colores)
        self.color = QRadioButton("Color", colores)
        self.color.setChecked(True)
        colores_layout.addWidget(self.blanco_negro)
        colores_layout.addWidget(self.color)
        colores_layout.addStretch(1)
        fila.addWidget(colores)
        principal.addLayout(fila)

        dimensiones = QGroupBox("Tamaño", self)
        dimension_form = QFormLayout(dimensiones)
        self.ancho = QDoubleSpinBox(dimensiones)
        self.alto = QDoubleSpinBox(dimensiones)
        dimension_form.addRow("Ancho:", self.ancho)
        dimension_form.addRow("Alto:", self.alto)
        principal.addWidget(dimensiones)

        fondo = QGroupBox("Fondo", self)
        fondo_layout = QHBoxLayout(fondo)
        self.transparente = QCheckBox("Transparente", fondo)
        self.transparente.setChecked(transparent)
        self.transparente.toggled.connect(self._actualizar_fondo)
        fondo_layout.addWidget(self.transparente)
        self.btn_color = QPushButton("Elegir color…", fondo)
        self.btn_color.clicked.connect(self._elegir_color)
        fondo_layout.addWidget(self.btn_color)
        self.muestra = QLabel(fondo)
        self.muestra.setFixedSize(42, 24)
        fondo_layout.addWidget(self.muestra)
        fondo_layout.addStretch(1)
        principal.addWidget(fondo)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults,
            parent=self,
        )
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        predeterminado = botones.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        predeterminado.setText("Predeterminado")
        predeterminado.clicked.connect(self._predeterminado)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        principal.addWidget(botones)

        self._mostrar_dimensiones()
        self._pintar_muestra()
        self._actualizar_fondo(transparent)

    # ------------------------------------------------------------------
    def _factor(self, unidad: str) -> float:
        dpi = max(1, self.resolucion.value())
        if unidad == "in":
            return 1.0 / dpi
        if unidad == "cm":
            return 2.54 / dpi
        return 1.0

    def _mostrar_dimensiones(self) -> None:
        self._actualizando = True
        try:
            factor = self._factor(self._unidad)
            decimales = 0 if self._unidad == "px" else 2
            sufijo = {"px": " px", "in": " pulg.", "cm": " cm"}[self._unidad]
            for campo, pixeles in ((self.ancho, self.ancho_pixeles), (self.alto, self.alto_pixeles)):
                campo.setDecimals(decimales)
                campo.setRange(0.01 if decimales else 1, 32768 * factor if decimales else 32768)
                campo.setSuffix(sufijo)
                campo.setSingleStep(1 if self._unidad == "px" else 0.1)
                campo.setValue(pixeles * factor)
        finally:
            self._actualizando = False

    def _leer_pixeles(self) -> None:
        factor = self._factor(self._unidad)
        self.ancho_pixeles = max(1, round(self.ancho.value() / factor))
        self.alto_pixeles = max(1, round(self.alto.value() / factor))

    def _cambiar_unidad(self, boton: QRadioButton, marcado: bool) -> None:
        if not marcado or self._actualizando:
            return
        self._leer_pixeles()
        self._unidad = str(boton.property("unidad"))
        self._mostrar_dimensiones()

    def _resolucion_cambiada(self) -> None:
        if self._unidad != "px":
            self._mostrar_dimensiones()

    def _predeterminado(self) -> None:
        self.ancho_pixeles, self.alto_pixeles = self.DEFAULT_SIZE
        self.resolucion.setValue(96)
        self.color.setChecked(True)
        self._mostrar_dimensiones()

    def _dimensiones_pixeles(self) -> tuple[int, int]:
        self._leer_pixeles()
        return self.ancho_pixeles, self.alto_pixeles

    def _elegir_color(self) -> None:
        color = QColorDialog.getColor(self.color_fondo, self, "Color de fondo")
        if color.isValid():
            self.color_fondo = color
            self._pintar_muestra()

    def _pintar_muestra(self) -> None:
        self.muestra.setStyleSheet(
            f"background: {self.color_fondo.name()}; border: 1px solid #777; border-radius: 3px;"
        )

    def _actualizar_fondo(self, transparente: bool) -> None:
        self.btn_color.setEnabled(not transparente)
        self.muestra.setEnabled(not transparente)

    @staticmethod
    def _tamano_legible(value: int) -> str:
        tamano = float(value)
        for unidad in ("bytes", "KB", "MB", "GB"):
            if tamano < 1024 or unidad == "GB":
                return f"{tamano:.0f} {unidad}" if unidad == "bytes" else f"{tamano:.1f} {unidad}"
            tamano /= 1024
        return f"{tamano:.1f} GB"

    def accept(self) -> None:
        ancho, alto = self._dimensiones_pixeles()
        if ancho * alto > self.MAX_PIXELS:
            QMessageBox.warning(self, "Imagen demasiado grande", "El resultado supera 100 millones de píxeles.")
            return
        if self.blanco_negro.isChecked():
            respuesta = QMessageBox.warning(
                self,
                "Propiedades de imagen",
                "Convertir la imagen a blanco y negro elimina toda la información de color "
                "y no se puede deshacer más allá del historial. ¿Desea continuar?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if respuesta != QMessageBox.StandardButton.Ok:
                return
        super().accept()

    def valores(self) -> dict:
        ancho, alto = self._dimensiones_pixeles()
        return {
            "width": ancho,
            "height": alto,
            "dpi": self.resolucion.value(),
            "transparent": self.transparente.isChecked(),
            "background": QColor(self.color_fondo),
            "black_white": self.blanco_negro.isChecked(),
        }

    values = valores
