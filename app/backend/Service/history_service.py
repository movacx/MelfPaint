from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields
from hashlib import blake2b
from struct import pack
from typing import Callable, Iterator, Protocol, TypeVar

import numpy as np
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from backend.Model.document import Document
from backend.Model.layer import Layer
from backend.Model.selection_state import SelectionState
from backend.Model.text_format import TextFormat
from backend.Model.tool_settings import ToolSettings


EstadoRestaurable = ToolSettings | TextFormat | SelectionState


def _restaurar_estado(actual: EstadoRestaurable, guardado: EstadoRestaurable) -> None:
    """Copia un estado sin reemplazar la instancia compartida por los controladores."""

    if type(actual) is not type(guardado):
        raise TypeError("El estado guardado no coincide con el estado actual")
    copia = guardado.clone()
    for campo in fields(copia):
        setattr(actual, campo.name, getattr(copia, campo.name))


class HistoryCommand(Protocol):
    label: str

    def undo(self, document: Document) -> None: ...

    def redo(self, document: Document) -> None: ...


@dataclass(frozen=True)
class LayerSnapshot:
    id: str
    name: str
    image: QImage
    visible: bool
    opacity: float
    locked: bool = False
    blend_mode: str = "normal"

    @classmethod
    def capture(cls, layer: Layer) -> LayerSnapshot:
        return cls(
            layer.id, layer.name, layer.image.copy(), layer.visible, layer.opacity, layer.locked, layer.blend_mode
        )

    def restore(self) -> Layer:
        return Layer(
            id=self.id,
            name=self.name,
            image=self.image.copy(),
            visible=self.visible,
            opacity=self.opacity,
            locked=self.locked,
            blend_mode=self.blend_mode,
        )


@dataclass(frozen=True)
class DocumentSnapshot:
    width: int
    height: int
    dpi: int
    background_color: QColor
    show_background: bool
    layers: tuple[LayerSnapshot, ...]
    active_layer_id: str | None
    selection: SelectionState
    text_format: TextFormat
    tool_settings: ToolSettings
    selection_rect: QRect | None
    modified: bool

    @classmethod
    def capture(cls, document: Document) -> DocumentSnapshot:
        return cls(
            width=document.width,
            height=document.height,
            dpi=document.dpi,
            background_color=QColor(document.background_color),
            show_background=document.show_background,
            layers=tuple(LayerSnapshot.capture(capa) for capa in document.layers),
            active_layer_id=document.active_layer_id,
            selection=document.selection.clone(),
            text_format=document.text_format.clone(),
            tool_settings=document.tool_settings.clone(),
            selection_rect=QRect(document.selection_rect) if document.selection_rect is not None else None,
            modified=document.modified,
        )

    def restore(self, document: Document) -> None:
        document.width = self.width
        document.height = self.height
        document.dpi = self.dpi
        document.background_color = QColor(self.background_color)
        document.show_background = self.show_background
        document.layers = [capa.restore() for capa in self.layers]
        document.active_layer_id = self.active_layer_id
        _restaurar_estado(document.selection, self.selection)
        _restaurar_estado(document.text_format, self.text_format)
        _restaurar_estado(document.tool_settings, self.tool_settings)
        document.selection_rect = QRect(self.selection_rect) if self.selection_rect is not None else None
        document.invalidate(mark_modified=False)
        document.modified = self.modified

    def matches(self, document: Document) -> bool:
        if (
            self.width != document.width
            or self.height != document.height
            or self.dpi != document.dpi
            or self.background_color != document.background_color
            or self.show_background != document.show_background
            or self.active_layer_id != document.active_layer_id
            or len(self.layers) != len(document.layers)
        ):
            return False
        for guardada, actual in zip(self.layers, document.layers, strict=True):
            if (
                guardada.id != actual.id
                or guardada.name != actual.name
                or guardada.visible != actual.visible
                or guardada.opacity != actual.opacity
                or guardada.locked != actual.locked
                or guardada.blend_mode != actual.blend_mode
                or guardada.image != actual.image
            ):
                return False
        return True


@dataclass(frozen=True)
class LayerFingerprint:
    id: str
    name: str
    visible: bool
    opacity: float
    image_digest: bytes
    locked: bool = False
    blend_mode: str = "normal"

    @classmethod
    def capture(cls, layer: Layer) -> LayerFingerprint:
        digest = blake2b(digest_size=20)
        image = layer.image
        image_format = int(getattr(image.format(), "value", 0))
        digest.update(pack(">iiii", image.width(), image.height(), image.bytesPerLine(), image_format))
        digest.update(image.constBits())
        return cls(layer.id, layer.name, layer.visible, layer.opacity, digest.digest(), layer.locked, layer.blend_mode)


@dataclass(frozen=True)
class DocumentFingerprint:
    """Firma el estado guardado sin retener otra copia completa de las capas."""

    width: int
    height: int
    dpi: int
    background_rgba: int
    show_background: bool
    layers: tuple[LayerFingerprint, ...]

    @classmethod
    def capture(cls, document: Document) -> DocumentFingerprint:
        return cls(
            width=document.width,
            height=document.height,
            dpi=document.dpi,
            background_rgba=document.background_color.rgba(),
            show_background=document.show_background,
            layers=tuple(LayerFingerprint.capture(layer) for layer in document.layers),
        )


@dataclass
class DocumentStateCommand:
    before: DocumentSnapshot
    after: DocumentSnapshot
    label: str = "Cambio de documento"

    @classmethod
    def from_change(
        cls,
        document: Document,
        before: DocumentSnapshot,
        label: str = "Cambio de documento",
    ) -> DocumentStateCommand:
        return cls(before=before, after=DocumentSnapshot.capture(document), label=label)

    def undo(self, document: Document) -> None:
        self.before.restore(document)

    def redo(self, document: Document) -> None:
        self.after.restore(document)

    def revert(self, document: Document) -> None:
        self.undo(document)

    def apply(self, document: Document) -> None:
        self.redo(document)


@dataclass
class LayerImageCommand:
    layer_id: str | int
    before: QImage
    after: QImage
    label: str = "Cambio en el lienzo"
    # Con ``rect``, before y after son solo ese rectángulo de la capa: un trazo
    # guarda unos pocos píxeles en lugar de dos copias completas del lienzo.
    rect: QRect | None = None

    def _restore(self, document: Document, image: QImage) -> None:
        capa = document.find_layer(self.layer_id)
        if capa is None:
            return
        if self.rect is not None:
            if image.size() != self.rect.size() or not QRect(QPoint(0, 0), document.size).contains(self.rect):
                raise ValueError("El parche del historial no cabe en el lienzo")
            painter = QPainter(capa.image)
            try:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                painter.drawImage(self.rect.topLeft(), image)
            finally:
                painter.end()
            document.invalidate_region(self.rect)
            return
        if image.size() != document.size:
            raise ValueError("La imagen del historial no coincide con el lienzo")
        capa.image = image.copy()
        document.invalidate(mark_modified=True)

    def undo(self, document: Document) -> None:
        self._restore(document, self.before)

    def redo(self, document: Document) -> None:
        self._restore(document, self.after)

    def revert(self, document: Document) -> None:
        self.undo(document)

    def apply(self, document: Document) -> None:
        self.redo(document)


@dataclass
class LayerOpacityCommand:
    """Guarda solamente la propiedad que cambia al mover el deslizador."""

    layer_id: str | int
    before: float
    after: float
    label: str = "Cambiar opacidad de capa"

    def _restore(self, document: Document, opacity: float) -> None:
        capa = document.find_layer(self.layer_id)
        if capa is None:
            return
        capa.opacity = max(0.0, min(1.0, float(opacity)))
        document.invalidate(mark_modified=True)

    def undo(self, document: Document) -> None:
        self._restore(document, self.before)

    def redo(self, document: Document) -> None:
        self._restore(document, self.after)

    def revert(self, document: Document) -> None:
        self.undo(document)

    def apply(self, document: Document) -> None:
        self.redo(document)


Resultado = TypeVar("Resultado")


class HistoryService:
    """Administra cambios ya aplicados sin acoplarse con la interfaz."""

    def __init__(self, limit: int = 1000, max_bytes: int = 1024 * 1024 * 1024) -> None:
        self.limit = max(1, int(limit))
        self.max_bytes = max(16 * 1024 * 1024, int(max_bytes))
        self.undo_stack: list[HistoryCommand] = []
        self.redo_stack: list[HistoryCommand] = []
        self._clean_fingerprint: DocumentFingerprint | None = None

    def mark_clean(self, document: Document) -> None:
        """Registra el contenido que corresponde al ultimo guardado real."""

        self._clean_fingerprint = DocumentFingerprint.capture(document)
        document.modified = False

    def forget_clean(self) -> None:
        """Indica que no conocemos un estado equivalente a un archivo guardado."""

        self._clean_fingerprint = None

    def update_modified(self, document: Document) -> bool:
        if self._clean_fingerprint is None:
            return bool(document.modified)
        document.modified = self._clean_fingerprint != DocumentFingerprint.capture(document)
        return document.modified

    def push(self, command: HistoryCommand) -> None:
        if not callable(getattr(command, "undo", None)) or not callable(getattr(command, "redo", None)):
            raise TypeError("El historial solo acepta comandos con undo y redo")
        self.undo_stack.append(self._compact(command))
        while len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        while len(self.undo_stack) > 1 and self.estimated_bytes() > self.max_bytes:
            self.undo_stack.pop(0)

    @staticmethod
    def _compact(command: HistoryCommand) -> HistoryCommand:
        """Reduce un cambio de capa completa al rectángulo que realmente cambió.

        Rellenar, pegar o confirmar una selección guardaban dos copias enteras
        de la capa; con un lienzo grande el historial se llenaba en pocos pasos.
        """

        if not isinstance(command, LayerImageCommand) or command.rect is not None:
            return command
        antes, despues = command.before, command.after
        if antes.size() != despues.size() or antes.format() != despues.format() or antes.isNull():
            return command
        ancho, alto = antes.width(), antes.height()
        profundidad = antes.depth() // 8
        a = np.frombuffer(antes.constBits(), dtype=np.uint8, count=antes.sizeInBytes())
        b = np.frombuffer(despues.constBits(), dtype=np.uint8, count=despues.sizeInBytes())
        a = a.reshape(alto, antes.bytesPerLine())[:, : ancho * profundidad]
        b = b.reshape(alto, despues.bytesPerLine())[:, : ancho * profundidad]
        distinto = a != b
        filas = np.flatnonzero(distinto.any(axis=1))
        if filas.size == 0:
            return command
        columnas = np.flatnonzero(distinto.any(axis=0)) // profundidad
        rect = QRect(int(columnas[0]), int(filas[0]), int(columnas[-1] - columnas[0] + 1), int(filas[-1] - filas[0] + 1))
        if rect.width() * rect.height() * 10 >= ancho * alto * 7:
            return command
        return LayerImageCommand(command.layer_id, antes.copy(rect), despues.copy(rect), command.label, rect)

    @staticmethod
    def _selection_bytes(selection: SelectionState) -> int:
        images = (selection.floating_image, selection.mask, selection.original_layer_before)
        return sum(image.sizeInBytes() for image in images if image is not None and not image.isNull())

    @classmethod
    def _snapshot_bytes(cls, snapshot: DocumentSnapshot) -> int:
        layers = sum(layer.image.sizeInBytes() for layer in snapshot.layers)
        return layers + cls._selection_bytes(snapshot.selection)

    @classmethod
    def _command_bytes(cls, command: HistoryCommand) -> int:
        if isinstance(command, LayerImageCommand):
            return command.before.sizeInBytes() + command.after.sizeInBytes()
        if isinstance(command, DocumentStateCommand):
            return cls._snapshot_bytes(command.before) + cls._snapshot_bytes(command.after)
        return 0

    def estimated_bytes(self) -> int:
        """Estimación conservadora de imágenes retenidas por undo y redo."""

        return sum(self._command_bytes(command) for command in (*self.undo_stack, *self.redo_stack))

    def capture(self, document: Document) -> DocumentSnapshot:
        return DocumentSnapshot.capture(document)

    def record_snapshot(
        self,
        document: Document,
        before: DocumentSnapshot,
        label: str = "Cambio de documento",
    ) -> bool:
        if before.matches(document):
            return False
        self.push(DocumentStateCommand.from_change(document, before, label))
        return True

    def execute(
        self,
        document: Document,
        label: str,
        operation: Callable[[], Resultado],
    ) -> Resultado:
        before = self.capture(document)
        resultado = operation()
        self.record_snapshot(document, before, label)
        return resultado

    @contextmanager
    def transaction(self, document: Document, label: str) -> Iterator[DocumentSnapshot]:
        before = self.capture(document)
        try:
            yield before
        except Exception:
            before.restore(document)
            raise
        else:
            self.record_snapshot(document, before, label)

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self, document: Document) -> str | None:
        if not self.undo_stack:
            return None
        command = self.undo_stack.pop()
        command.undo(document)
        self.redo_stack.append(command)
        self.update_modified(document)
        return command.label

    def redo(self, document: Document) -> str | None:
        if not self.redo_stack:
            return None
        command = self.redo_stack.pop()
        command.redo(document)
        self.undo_stack.append(command)
        self.update_modified(document)
        return command.label

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.forget_clean()

    # Alias breve para controladores escritos en espanol.
    registrar_cambio = record_snapshot
