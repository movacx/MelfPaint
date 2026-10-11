from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage, QPainter

from backend.Model.layer import Layer, crear_imagen_transparente, modo_de_composicion
from backend.Model.selection_state import SelectionState
from backend.Model.text_format import TextFormat
from backend.Model.tool_settings import ToolSettings


MAX_CANVAS_SIDE = 32768
MAX_CANVAS_PIXELS = 100_000_000


def validar_tamano_lienzo(width: int, height: int) -> tuple[int, int]:
    ancho = max(1, int(width))
    alto = max(1, int(height))
    if ancho > MAX_CANVAS_SIDE or alto > MAX_CANVAS_SIDE:
        raise ValueError(f"El lienzo no puede superar {MAX_CANVAS_SIDE} píxeles por lado")
    if ancho * alto > MAX_CANVAS_PIXELS:
        raise ValueError("El lienzo no puede superar 100 millones de píxeles")
    return ancho, alto


@dataclass
class Document:
    width: int = 1024
    height: int = 768
    background_color: QColor = field(default_factory=lambda: QColor("white"))
    show_background: bool = True
    dpi: int = 96
    layers: list[Layer] = field(default_factory=list)
    active_layer_id: str | None = None
    modified: bool = False
    project_path: Path | None = None
    source_path: Path | None = None
    last_export_path: Path | None = None
    selection: SelectionState = field(default_factory=SelectionState)
    text_format: TextFormat = field(default_factory=TextFormat)
    tool_settings: ToolSettings = field(default_factory=ToolSettings)
    selection_rect: QRect | None = None
    _composition_cache: QImage | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.width, self.height = validar_tamano_lienzo(self.width, self.height)
        self.background_color = QColor(self.background_color)
        if not self.background_color.isValid():
            self.background_color = QColor("white")
        self.show_background = bool(self.show_background)
        self.dpi = max(1, min(1200, int(self.dpi)))
        self.project_path = Path(self.project_path) if self.project_path is not None else None
        self.source_path = Path(self.source_path) if self.source_path is not None else None
        self.last_export_path = Path(self.last_export_path) if self.last_export_path is not None else None

        if not self.layers:
            self.layers.append(Layer.blank(self.width, self.height, "Capa 1"))
        self._validate_layers()
        if self.find_layer(self.active_layer_id) is None:
            self.active_layer_id = self.layers[-1].id

    def _validate_layers(self) -> None:
        ids: set[str] = set()
        for capa in self.layers:
            if capa.image.size() != self.size:
                raise ValueError("Todas las capas deben medir lo mismo que el documento")
            if capa.id in ids:
                raise ValueError("Cada capa necesita un identificador unico")
            ids.add(capa.id)

    @property
    def size(self) -> QSize:
        return QSize(self.width, self.height)

    @property
    def background(self) -> QColor:
        return QColor(self.background_color)

    @background.setter
    def background(self, value: QColor) -> None:
        color = QColor(value)
        if not color.isValid():
            raise ValueError("El color de fondo no es valido")
        self.background_color = color
        self.invalidate()

    @property
    def transparent_background(self) -> bool:
        return not self.show_background

    @transparent_background.setter
    def transparent_background(self, value: bool) -> None:
        self.show_background = not bool(value)
        self.invalidate()

    @property
    def file_path(self) -> Path | None:
        """Alias para vistas antiguas; un proyecto siempre tiene prioridad."""
        return self.project_path or self.source_path

    @file_path.setter
    def file_path(self, value: Path | str | None) -> None:
        if value is None:
            self.project_path = None
            self.source_path = None
            return
        ruta = Path(value)
        if ruta.suffix.lower() in {".melfpaint", ".paint"}:
            self.project_path = ruta
        else:
            self.source_path = ruta

    @property
    def active_layer(self) -> Layer:
        capa = self.find_layer(self.active_layer_id)
        if capa is not None:
            return capa
        self.active_layer_id = self.layers[-1].id
        return self.layers[-1]

    @property
    def active_layer_index(self) -> int:
        for indice, capa in enumerate(self.layers):
            if capa.id == self.active_layer_id:
                return indice
        self.active_layer_id = self.layers[-1].id
        return len(self.layers) - 1

    def find_layer(self, layer_id: str | int | None) -> Layer | None:
        if isinstance(layer_id, int):
            if 0 <= layer_id < len(self.layers):
                return self.layers[layer_id]
            return None
        for capa in self.layers:
            if capa.id == layer_id:
                return capa
        return None

    def set_active_layer(self, layer_id: str | int) -> bool:
        capa = self.find_layer(layer_id)
        if capa is None:
            return False
        self.active_layer_id = capa.id
        return True

    def invalidate(self, mark_modified: bool = True) -> None:
        self._composition_cache = None
        if mark_modified:
            self.modified = True

    def invalidate_region(self, rect: QRect, mark_modified: bool = True) -> None:
        """Recompone solo ``rect`` en el caché en vez de descartarlo entero.

        Un trazo toca unos pocos píxeles; recomponer todas las capas completas
        en cada movimiento del ratón hacía lenta la edición de lienzos grandes.
        """

        if mark_modified:
            self.modified = True
        cache = self._composition_cache
        if cache is None:
            return
        area = rect.normalized().intersected(QRect(0, 0, self.width, self.height))
        if area.isEmpty() or cache.size() != self.size:
            return
        painter = QPainter(cache)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(area, self.background_color if self.show_background else QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for capa in self.layers:
                if not capa.visible or capa.opacity <= 0.0:
                    continue
                painter.setOpacity(capa.opacity)
                painter.setCompositionMode(modo_de_composicion(capa.blend_mode))
                painter.drawImage(area.topLeft(), capa.image, area)
        finally:
            painter.end()

    def composite(self, include_background: bool | None = None) -> QImage:
        usar_fondo = self.show_background if include_background is None else bool(include_background)
        if include_background is None and self._composition_cache is not None:
            # QImage usa copia en escritura. Entregar otra referencia evita que
            # un exportador o una vista modifique accidentalmente nuestro caché.
            return QImage(self._composition_cache)

        resultado = crear_imagen_transparente(self.width, self.height)
        if usar_fondo:
            resultado.fill(self.background_color)
        painter = QPainter(resultado)
        try:
            for capa in self.layers:
                if not capa.visible or capa.opacity <= 0.0:
                    continue
                painter.setOpacity(capa.opacity)
                painter.setCompositionMode(modo_de_composicion(capa.blend_mode))
                painter.drawImage(0, 0, capa.image)
        finally:
            painter.end()

        if include_background is None:
            self._composition_cache = resultado
            return QImage(self._composition_cache)
        return resultado

    def add_layer(self, name: str | None = None, image: QImage | None = None) -> Layer:
        if image is None:
            capa = Layer.blank(self.width, self.height, name or f"Capa {len(self.layers) + 1}")
        else:
            if image.size() != self.size:
                raise ValueError("La imagen de la capa no coincide con el lienzo")
            capa = Layer(name=name or f"Capa {len(self.layers) + 1}", image=image.copy())
        indice = self.active_layer_index + 1
        self.layers.insert(indice, capa)
        self.active_layer_id = capa.id
        self.invalidate()
        return capa

    def duplicate_active_layer(self) -> Layer:
        copia = self.active_layer.clone()
        self.layers.insert(self.active_layer_index + 1, copia)
        self.active_layer_id = copia.id
        self.invalidate()
        return copia

    def remove_active_layer(self) -> bool:
        if len(self.layers) == 1:
            vacia = crear_imagen_transparente(self.width, self.height)
            if self.active_layer.image == vacia:
                return False
            self.active_layer.image = vacia
        else:
            indice = self.active_layer_index
            self.layers.pop(indice)
            self.active_layer_id = self.layers[max(0, indice - 1)].id
        self.invalidate()
        return True

    def merge_active_down(self) -> bool:
        indice = self.active_layer_index
        if indice <= 0:
            return False

        superior = self.layers[indice]
        inferior = self.layers[indice - 1]
        combinada = crear_imagen_transparente(self.width, self.height)
        painter = QPainter(combinada)
        try:
            if inferior.visible:
                painter.setOpacity(inferior.opacity)
                painter.drawImage(0, 0, inferior.image)
            if superior.visible:
                painter.setOpacity(superior.opacity)
                painter.setCompositionMode(modo_de_composicion(superior.blend_mode))
                painter.drawImage(0, 0, superior.image)
        finally:
            painter.end()

        inferior.image = combinada
        inferior.visible = inferior.visible or superior.visible
        inferior.opacity = 1.0
        self.layers.pop(indice)
        self.active_layer_id = inferior.id
        self.invalidate()
        return True

    def flatten_layers(self) -> bool:
        """Acopla todas las capas visibles en una sola, sin el color de fondo."""

        if len(self.layers) <= 1:
            return False
        plana = self.composite(include_background=False)
        base = self.layers[0]
        nueva = Layer(name=base.name, image=plana, id=base.id)
        self.layers = [nueva]
        self.active_layer_id = nueva.id
        self.invalidate()
        return True

    def resize_canvas(self, width: int, height: int) -> bool:
        ancho, alto = validar_tamano_lienzo(width, height)
        if (ancho, alto) == (self.width, self.height):
            return False
        for capa in self.layers:
            nueva = crear_imagen_transparente(ancho, alto)
            painter = QPainter(nueva)
            try:
                painter.drawImage(0, 0, capa.image)
            finally:
                painter.end()
            capa.image = nueva
        self.width, self.height = ancho, alto
        self._clear_selection()
        self.invalidate()
        return True

    def crop(self, rect: QRect) -> bool:
        recorte = rect.normalized().intersected(QRect(0, 0, self.width, self.height))
        if recorte.isEmpty() or recorte == QRect(0, 0, self.width, self.height):
            return False
        for capa in self.layers:
            capa.image = capa.image.copy(recorte)
        self.width, self.height = recorte.width(), recorte.height()
        self._clear_selection()
        self.invalidate()
        return True

    def set_transparent_background(self) -> bool:
        if not self.show_background:
            return False
        self.show_background = False
        self.invalidate()
        return True

    def set_background_color(self, color: QColor) -> bool:
        nuevo = QColor(color)
        if not nuevo.isValid():
            raise ValueError("El color de fondo no es valido")
        if self.show_background and nuevo == self.background_color:
            return False
        self.background_color = nuevo
        self.show_background = True
        self.invalidate()
        return True

    def _clear_selection(self) -> None:
        self.selection.clear()
        self.selection_rect = None
