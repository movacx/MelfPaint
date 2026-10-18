import platform

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.Config.settings import APP_NAME, icon_path


class AboutDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        version: str = "1.0.1",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Acerca de {APP_NAME}")
        self.setModal(True)
        self.setFixedWidth(500)
        self._construir_interfaz(version)

    def _construir_interfaz(self, version: str) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(20, 20, 20, 16)
        principal.setSpacing(14)

        encabezado = QHBoxLayout()
        logo = QLabel(self)
        pixmap = QPixmap(str(icon_path("melfpaint")))
        logo.setPixmap(
            pixmap.scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        encabezado.addWidget(logo)

        textos = QVBoxLayout()
        nombre = QLabel(APP_NAME, self)
        nombre.setObjectName("DialogTitle")
        textos.addWidget(nombre)
        from version import CHANNEL

        textos.addWidget(QLabel(f"Versión {version} ({CHANNEL})", self))
        lema = QLabel("Editor de imágenes de escritorio para Linux.", self)
        lema.setWordWrap(True)
        textos.addWidget(lema)
        encabezado.addLayout(textos, 1)
        principal.addLayout(encabezado)

        descripcion = QLabel(
            "MelfPaint es software libre. Sus iconos y recursos visuales son propios.",
            self,
        )
        descripcion.setWordWrap(True)
        principal.addWidget(descripcion)

        sistema = QLabel(
            f"Python {platform.python_version()} · PySide6 {pyside_version}\n"
            f"{platform.system()} {platform.release()} · {platform.machine() or 'arquitectura desconocida'}",
            self,
        )
        sistema.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        principal.addWidget(sistema)

        licencia = QLabel("Software libre con licencia GPL-3.0-or-later. Versión beta: puede contener errores.", self)
        licencia.setWordWrap(True)
        principal.addWidget(licencia)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botones.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        botones.rejected.connect(self.reject)
        principal.addWidget(botones)


def show_about(parent: QWidget | None = None, version: str = "1.0.1") -> int:
    return AboutDialog(parent, version).exec()
