from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


@dataclass
class TextFormat:
    family: str = "Calibri"
    size: int = 20
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft
    opaque_background: bool = False
    text_color: QColor = field(default_factory=lambda: QColor("black"))
    background_color: QColor = field(default_factory=lambda: QColor("white"))

    def __post_init__(self) -> None:
        self.family = str(self.family or "Calibri").strip()[:200] or "Calibri"
        self.size = max(1, min(1000, int(self.size)))
        for nombre in ("bold", "italic", "underline", "strikeout", "opaque_background"):
            if not isinstance(getattr(self, nombre), bool):
                raise ValueError(f"{nombre} necesita un valor booleano")
        self.alignment = Qt.AlignmentFlag(int(self.alignment))
        self.text_color = QColor(self.text_color)
        self.background_color = QColor(self.background_color)
        if not self.text_color.isValid() or not self.background_color.isValid():
            raise ValueError("El formato de texto contiene un color invalido")

    def font(self) -> QFont:
        fuente = QFont(self.family or "Calibri", max(1, int(self.size)))
        fuente.setBold(self.bold)
        fuente.setItalic(self.italic)
        fuente.setUnderline(self.underline)
        fuente.setStrikeOut(self.strikeout)
        return fuente

    def font_px(self, zoom: float = 1.0) -> QFont:
        """Fuente en píxeles (puntos a 96 ppp), igual en pantalla y en la capa."""

        fuente = QFont(self.family or "Calibri")
        fuente.setPixelSize(max(1, round(self.size * 96 / 72 * max(0.05, float(zoom)))))
        fuente.setBold(self.bold)
        fuente.setItalic(self.italic)
        fuente.setUnderline(self.underline)
        fuente.setStrikeOut(self.strikeout)
        return fuente

    def clone(self) -> TextFormat:
        return TextFormat(
            family=self.family,
            size=self.size,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strikeout=self.strikeout,
            alignment=self.alignment,
            opaque_background=self.opaque_background,
            text_color=QColor(self.text_color),
            background_color=QColor(self.background_color),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "size": int(self.size),
            "bold": bool(self.bold),
            "italic": bool(self.italic),
            "underline": bool(self.underline),
            "strikeout": bool(self.strikeout),
            "alignment": int(self.alignment),
            "opaque_background": bool(self.opaque_background),
            "text_color": self.text_color.name(QColor.NameFormat.HexArgb),
            "background_color": self.background_color.name(QColor.NameFormat.HexArgb),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> TextFormat:
        datos = data or {}

        def booleano(nombre: str, predeterminado: bool) -> bool:
            valor = datos.get(nombre, predeterminado)
            if not isinstance(valor, bool):
                raise ValueError(f"{nombre} necesita un valor booleano")
            return valor

        return cls(
            family=str(datos.get("family", "Calibri")),
            size=max(1, int(datos.get("size", 20))),
            bold=booleano("bold", False),
            italic=booleano("italic", False),
            underline=booleano("underline", False),
            strikeout=booleano("strikeout", False),
            alignment=Qt.AlignmentFlag(int(datos.get("alignment", int(Qt.AlignmentFlag.AlignLeft)))),
            opaque_background=booleano("opaque_background", False),
            text_color=QColor(str(datos.get("text_color", "#ff000000"))),
            background_color=QColor(str(datos.get("background_color", "#ffffffff"))),
        )
