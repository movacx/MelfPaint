from __future__ import annotations

from dataclasses import dataclass, field

# Tamaños que se ofrecen para cada familia de herramientas y el valor inicial.
TOOL_SIZE_CHOICES: dict[str, tuple[int, ...]] = {
    "pencil": (1, 2, 3, 4),
    "brush": (1, 3, 5, 8),
    "eraser": (4, 6, 8, 10),
    "shape": (1, 3, 5, 8),
}
DEFAULT_TOOL_SIZES: dict[str, float] = {"pencil": 1.0, "brush": 3.0, "eraser": 8.0, "shape": 3.0}
from math import isfinite

from PySide6.QtGui import QColor


@dataclass
class ToolSettings:
    active_tool: str = "pencil"
    primary_color: QColor = field(default_factory=lambda: QColor("black"))
    secondary_color: QColor = field(default_factory=lambda: QColor("white"))
    brush_size: float = 2.0
    line_width: float = 2.0
    opacity: float = 1.0
    eraser_opacity: float = 1.0
    hardness: float = 1.0
    fill_mode: str = "none"
    outline_mode: str = "solid"
    # El relleno también cubre los bordes suavizados del mismo color.
    fill_tolerance: int = 24
    outline_enabled: bool = True
    fill_enabled: bool = False
    brush_type: str = "round"
    transparent_selection: bool = False
    antialiasing: bool = True
    zoom: float = 1.0
    tool_sizes: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TOOL_SIZES))

    def __post_init__(self) -> None:
        valores = (
            float(self.brush_size),
            float(self.line_width),
            float(self.opacity),
            float(self.eraser_opacity),
            float(self.hardness),
            float(self.zoom),
        )
        if not all(isfinite(valor) for valor in valores):
            raise ValueError("La configuracion de herramienta contiene un numero invalido")
        self.brush_size = max(1.0, min(500.0, valores[0]))
        self.line_width = max(1.0, min(500.0, valores[1]))
        self.opacity = max(0.0, min(1.0, valores[2]))
        self.eraser_opacity = max(0.0, min(1.0, valores[3]))
        self.hardness = max(0.0, min(1.0, valores[4]))
        self.fill_tolerance = max(0, min(255, int(self.fill_tolerance)))
        self.zoom = max(0.1, min(8.0, valores[5]))
        self.primary_color = QColor(self.primary_color)
        self.secondary_color = QColor(self.secondary_color)
        if not self.primary_color.isValid() or not self.secondary_color.isValid():
            raise ValueError("La configuracion de herramienta contiene un color invalido")
        for nombre in (
            "outline_enabled",
            "fill_enabled",
            "transparent_selection",
            "antialiasing",
        ):
            if not isinstance(getattr(self, nombre), bool):
                raise ValueError(f"{nombre} necesita un valor booleano")
        self.active_tool = str(self.active_tool or "pencil")[:100]
        self.fill_mode = str(self.fill_mode or "none")[:100]
        self.outline_mode = str(self.outline_mode or "solid")[:100]
        self.brush_type = str(self.brush_type or "round")[:100]
        tamanos = dict(DEFAULT_TOOL_SIZES)
        for clave, valor in dict(self.tool_sizes or {}).items():
            try:
                numero = float(valor)
            except (TypeError, ValueError):
                continue
            if clave in tamanos and isfinite(numero):
                tamanos[clave] = max(1.0, min(256.0, numero))
        self.tool_sizes = tamanos

    @property
    def size(self) -> float:
        return self.brush_size

    @size.setter
    def size(self, value: float) -> None:
        self.brush_size = max(1.0, float(value))

    @property
    def stroke_width(self) -> float:
        """El trazo de figuras usa line_width; los pinceles usan brush_size."""
        return self.line_width

    @stroke_width.setter
    def stroke_width(self, value: float) -> None:
        self.line_width = max(1.0, float(value))

    @property
    def outline_style(self) -> str:
        return self.outline_mode

    @outline_style.setter
    def outline_style(self, value: str) -> None:
        self.outline_mode = str(value)

    @property
    def fill_style(self) -> str:
        return self.fill_mode

    @fill_style.setter
    def fill_style(self, value: str) -> None:
        self.fill_mode = str(value)

    def clone(self) -> ToolSettings:
        return ToolSettings(
            active_tool=self.active_tool,
            primary_color=QColor(self.primary_color),
            secondary_color=QColor(self.secondary_color),
            brush_size=self.brush_size,
            line_width=self.line_width,
            opacity=self.opacity,
            eraser_opacity=self.eraser_opacity,
            hardness=self.hardness,
            fill_mode=self.fill_mode,
            outline_mode=self.outline_mode,
            fill_tolerance=self.fill_tolerance,
            outline_enabled=self.outline_enabled,
            fill_enabled=self.fill_enabled,
            brush_type=self.brush_type,
            transparent_selection=self.transparent_selection,
            antialiasing=self.antialiasing,
            zoom=self.zoom,
            tool_sizes=dict(self.tool_sizes),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "active_tool": self.active_tool,
            "primary_color": self.primary_color.name(QColor.NameFormat.HexArgb),
            "secondary_color": self.secondary_color.name(QColor.NameFormat.HexArgb),
            "brush_size": self.brush_size,
            "line_width": self.line_width,
            "opacity": self.opacity,
            "eraser_opacity": self.eraser_opacity,
            "hardness": self.hardness,
            "fill_mode": self.fill_mode,
            "outline_mode": self.outline_mode,
            "fill_tolerance": self.fill_tolerance,
            "outline_enabled": self.outline_enabled,
            "fill_enabled": self.fill_enabled,
            "brush_type": self.brush_type,
            "transparent_selection": self.transparent_selection,
            "antialiasing": self.antialiasing,
            "zoom": self.zoom,
            "tool_sizes": dict(self.tool_sizes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> ToolSettings:
        datos = data or {}

        def booleano(nombre: str, predeterminado: bool) -> bool:
            valor = datos.get(nombre, predeterminado)
            if not isinstance(valor, bool):
                raise ValueError(f"{nombre} necesita un valor booleano")
            return valor

        return cls(
            active_tool=str(datos.get("active_tool", "pencil")),
            primary_color=QColor(str(datos.get("primary_color", "#ff000000"))),
            secondary_color=QColor(str(datos.get("secondary_color", "#ffffffff"))),
            brush_size=float(datos.get("brush_size", 2.0)),
            line_width=float(datos.get("line_width", 2.0)),
            opacity=float(datos.get("opacity", 1.0)),
            eraser_opacity=float(datos.get("eraser_opacity", 1.0)),
            hardness=float(datos.get("hardness", 1.0)),
            fill_mode=str(datos.get("fill_mode", "none")),
            outline_mode=str(datos.get("outline_mode", "solid")),
            fill_tolerance=int(datos.get("fill_tolerance", 24)),
            outline_enabled=booleano("outline_enabled", True),
            fill_enabled=booleano("fill_enabled", False),
            brush_type=str(datos.get("brush_type", "round")),
            transparent_selection=booleano("transparent_selection", False),
            antialiasing=booleano("antialiasing", True),
            zoom=float(datos.get("zoom", 1.0)),
            tool_sizes=datos.get("tool_sizes") if isinstance(datos.get("tool_sizes"), dict) else None,
        )
