from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap


def crear_imagen_transparente(width: int | QSize, height: int | None = None) -> QImage:
    """Crea el formato de imagen comun para todas las capas."""
    if isinstance(width, QSize):
        ancho = width.width()
        alto = width.height()
    else:
        ancho = int(width)
        alto = int(height if height is not None else width)

    imagen = QImage(max(1, ancho), max(1, alto), QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(QColor(0, 0, 0, 0))
    return imagen


# Modos de mezcla de capa: id -> (nombre en la interfaz, modo de composición de Qt).
BLEND_MODES: dict[str, tuple[str, QPainter.CompositionMode]] = {
    "normal": ("Normal", QPainter.CompositionMode.CompositionMode_SourceOver),
    "multiply": ("Multiplicar", QPainter.CompositionMode.CompositionMode_Multiply),
    "screen": ("Trama", QPainter.CompositionMode.CompositionMode_Screen),
    "overlay": ("Superponer", QPainter.CompositionMode.CompositionMode_Overlay),
    "darken": ("Oscurecer", QPainter.CompositionMode.CompositionMode_Darken),
    "lighten": ("Aclarar", QPainter.CompositionMode.CompositionMode_Lighten),
}


def modo_de_composicion(blend_mode: str) -> QPainter.CompositionMode:
    return BLEND_MODES.get(blend_mode, BLEND_MODES["normal"])[1]


# Nombre usado por las herramientas y por la primera version del proyecto.
make_transparent_image = crear_imagen_transparente


@dataclass
class Layer:
    name: str
    image: QImage
    visible: bool = True
    opacity: float = 1.0
    id: str = field(default_factory=lambda: uuid4().hex)
    locked: bool = False
    blend_mode: str = "normal"

    def __post_init__(self) -> None:
        self.name = str(self.name).strip() or "Capa"
        if not isinstance(self.image, QImage) or self.image.isNull():
            raise ValueError("La capa necesita una imagen valida")
        self.opacity = max(0.0, min(1.0, float(self.opacity)))
        self.visible = bool(self.visible)
        self.id = str(self.id or uuid4().hex)
        self.locked = bool(self.locked)
        self.blend_mode = self.blend_mode if self.blend_mode in BLEND_MODES else "normal"

    @classmethod
    def blank(cls, width: int, height: int, name: str = "Capa 1") -> Layer:
        return cls(name=name, image=crear_imagen_transparente(width, height))

    def clone(self, name: str | None = None, preserve_id: bool = False) -> Layer:
        copia = Layer(
            name=name or f"{self.name} copia",
            image=self.image.copy(),
            visible=self.visible,
            opacity=self.opacity,
            locked=self.locked,
            blend_mode=self.blend_mode,
        )
        if preserve_id:
            copia.id = self.id
        return copia

    def thumbnail(self, size: int = 48) -> QPixmap:
        lado = max(1, int(size))
        miniatura = crear_imagen_transparente(lado, lado)
        escalada = self.image.scaled(
            QSize(lado, lado),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(miniatura)
        try:
            painter.drawImage((lado - escalada.width()) // 2, (lado - escalada.height()) // 2, escalada)
        finally:
            painter.end()
        return QPixmap.fromImage(miniatura)
