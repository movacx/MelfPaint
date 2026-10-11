from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage


class SelectionMode(str, Enum):
    NONE = "none"
    CREATING = "creating"
    FLOATING = "floating"
    MOVING = "moving"
    COMMITTED = "committed"


@dataclass
class SelectionState:
    source_rect: QRect = field(default_factory=QRect)
    floating_image: QImage | None = None
    mask: QImage | None = None
    offset: QPoint = field(default_factory=QPoint)
    original_layer_id: str | None = None
    original_layer_before: QImage | None = None
    source_was_cleared: bool = False
    # Indica que la imagen flotante cambió (girada, escalada, duplicada…) y
    # que ya no basta con restaurar la capa original al confirmar.
    transformed: bool = False
    transparent_mode: bool = True
    background_key_color: QColor = field(default_factory=lambda: QColor("white"))
    state: SelectionMode = SelectionMode.NONE
    _display_cache: QImage | None = field(default=None, init=False, repr=False)
    _cache_key: tuple[int, bool, int] | None = field(default=None, init=False, repr=False)

    @property
    def active(self) -> bool:
        return self.has_selection

    @active.setter
    def active(self, value: bool) -> None:
        if value and self.floating_image is not None and not self.source_rect.isEmpty():
            self.state = SelectionMode.FLOATING
        elif not value:
            self.state = SelectionMode.NONE

    @property
    def has_selection(self) -> bool:
        return (
            self.state in {SelectionMode.FLOATING, SelectionMode.MOVING}
            and self.floating_image is not None
            and not self.source_rect.isEmpty()
        )

    @property
    def transparent(self) -> bool:
        return self.transparent_mode

    @transparent.setter
    def transparent(self, value: bool) -> None:
        self.transparent_mode = bool(value)
        self.invalidate_cache()

    @property
    def current_rect(self) -> QRect:
        if self.source_rect.isEmpty():
            return QRect()
        return QRect(QPoint(self.offset), self.source_rect.size())

    def contains(self, x: int | QPoint, y: int | None = None) -> bool:
        punto = QPoint(x) if isinstance(x, QPoint) else QPoint(int(x), int(y or 0))
        return self.current_rect.contains(punto)

    def clear(self) -> None:
        self.source_rect = QRect()
        self.floating_image = None
        self.mask = None
        self.offset = QPoint()
        self.original_layer_id = None
        self.original_layer_before = None
        self.source_was_cleared = False
        self.transformed = False
        self.state = SelectionMode.NONE
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        self._display_cache = None
        self._cache_key = None

    def clone(self) -> SelectionState:
        copia = SelectionState(
            source_rect=QRect(self.source_rect),
            floating_image=self.floating_image.copy() if self.floating_image is not None else None,
            mask=self.mask.copy() if self.mask is not None else None,
            offset=QPoint(self.offset),
            original_layer_id=self.original_layer_id,
            original_layer_before=(
                self.original_layer_before.copy() if self.original_layer_before is not None else None
            ),
            source_was_cleared=self.source_was_cleared,
            transformed=self.transformed,
            transparent_mode=self.transparent_mode,
            background_key_color=QColor(self.background_key_color),
            state=self.state,
        )
        return copia

    def display_image(self) -> QImage | None:
        if self.floating_image is None:
            return None

        color = QColor(self.background_key_color)
        clave = (int(self.floating_image.cacheKey()), self.transparent_mode, color.rgba())
        if self._display_cache is not None and clave == self._cache_key:
            return self._display_cache
        if not self.transparent_mode:
            self._display_cache = self.floating_image
            self._cache_key = clave
            return self._display_cache

        imagen = self.floating_image.convertToFormat(QImage.Format.Format_RGBA8888).copy()
        ancho, alto = imagen.width(), imagen.height()
        datos = np.frombuffer(imagen.bits(), dtype=np.uint8, count=imagen.sizeInBytes())
        filas = datos.reshape((alto, imagen.bytesPerLine()))[:, : ancho * 4]
        pixeles = filas.reshape((alto, ancho, 4))
        diferencia = np.abs(pixeles[:, :, :3].astype(np.int16) - np.array(color.getRgb()[:3]))
        coincide = np.all(diferencia <= 2, axis=2) & (pixeles[:, :, 3] > 0)
        pixeles[:, :, 3][coincide] = 0

        self._display_cache = imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self._cache_key = clave
        return self._display_cache
