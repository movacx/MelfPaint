from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from frontend.Config.settings import APP_NAME, icon_path


class SettingsDialog(QDialog):
    """Página de configuración: tema de la aplicación y «Acerca de»."""

    temaCambiado = Signal(str)
    acercaDeSolicitado = Signal()

    TEMAS = (
        ("claro", "Claro"),
        ("oscuro", "Oscuro"),
        ("sistema", "Usar la configuración del sistema"),
    )

    def __init__(self, tema: str = "sistema", version: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setModal(True)
        self.setMinimumWidth(420)

        principal = QVBoxLayout(self)
        principal.setContentsMargins(20, 18, 20, 16)
        principal.setSpacing(14)

        titulo = QLabel("Configuración", self)
        titulo.setObjectName("DialogTitle")
        principal.addWidget(titulo)

        grupo = QGroupBox("Tema de la aplicación", self)
        grupo_layout = QVBoxLayout(grupo)
        self.botones = QButtonGroup(self)
        self._radios: dict[str, QRadioButton] = {}
        for valor, texto in self.TEMAS:
            radio = QRadioButton(texto, grupo)
            radio.setProperty("tema", valor)
            self.botones.addButton(radio)
            self._radios[valor] = radio
            grupo_layout.addWidget(radio)
        self._radios.get(tema, self._radios["sistema"]).setChecked(True)
        self.botones.buttonToggled.connect(self._cambio)
        principal.addWidget(grupo)

        acerca = QGroupBox(f"Acerca de {APP_NAME}", self)
        acerca_layout = QHBoxLayout(acerca)
        logo = QLabel(acerca)
        logo.setPixmap(
            QPixmap(str(icon_path("melfpaint"))).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        acerca_layout.addWidget(logo)
        textos = QVBoxLayout()
        textos.addWidget(QLabel(f"<b>{APP_NAME}</b>", acerca))
        if version:
            textos.addWidget(QLabel(f"Versión {version}", acerca))
        acerca_layout.addLayout(textos, 1)
        boton_acerca = QPushButton("Más información", acerca)
        boton_acerca.clicked.connect(self.acercaDeSolicitado.emit)
        acerca_layout.addWidget(boton_acerca)
        principal.addWidget(acerca)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botones.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        botones.rejected.connect(self.reject)
        principal.addWidget(botones)

    def _cambio(self, boton: QRadioButton, marcado: bool) -> None:
        if marcado:
            self.temaCambiado.emit(str(boton.property("tema")))

    def tema(self) -> str:
        boton = self.botones.checkedButton()
        return str(boton.property("tema")) if boton is not None else "sistema"
