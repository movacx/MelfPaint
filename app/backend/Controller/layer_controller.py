from __future__ import annotations

from collections.abc import Callable
from math import isfinite

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from backend.Model.document import Document
from backend.Model.layer import BLEND_MODES, Layer
from backend.Service.Drawing.selection_tools import commit_floating_selection
from backend.Service.history_service import (
    DocumentSnapshot,
    HistoryService,
    LayerImageCommand,
    LayerOpacityCommand,
)


class LayerController(QObject):
    """Punto unico para mutaciones del panel de capas."""

    layersChanged = Signal()
    activeLayerChanged = Signal(str)
    historyChanged = Signal()
    layers_changed = Signal()

    def __init__(self, document: Document, history: HistoryService | None = None) -> None:
        super().__init__()
        self.document = document
        self.history = history or HistoryService()
        self._opacity_layer_id: str | None = None
        self._opacity_before: float | None = None

    def bind(self, document: Document) -> None:
        self.document = document
        self._opacity_layer_id = None
        self._opacity_before = None
        self._emit_layers()

    def _emit_layers(self) -> None:
        self.layersChanged.emit()
        self.layers_changed.emit()

    def _commit_pending_selection(self) -> bool:
        if not self.document.selection.has_selection:
            return False
        command = commit_floating_selection(self.document)
        if command is None:
            return False
        self.history.push(command)
        self.historyChanged.emit()
        return True

    def _mutate(self, label: str, operation: Callable[[], object]) -> object:
        self._commit_pending_selection()
        before = self.history.capture(self.document)
        try:
            result = operation()
        except Exception:
            before.restore(self.document)
            raise
        if result is False or not self.history.record_snapshot(self.document, before, label):
            return result
        self._emit_layers()
        self.historyChanged.emit()
        return result

    def activate(self, layer_id: str | int) -> bool:
        if self.document.find_layer(layer_id) is None:
            return False
        self._commit_pending_selection()
        if not self.document.set_active_layer(layer_id):
            return False
        self.activeLayerChanged.emit(self.document.active_layer_id or "")
        self._emit_layers()
        return True

    def add_layer(self, name: str | None = None, image: QImage | None = None) -> Layer:
        return self._mutate("Agregar capa", lambda: self.document.add_layer(name, image))  # type: ignore[return-value]

    def duplicate_active(self, name: str | None = None) -> Layer:
        def duplicar() -> Layer:
            capa = self.document.duplicate_active_layer()
            if name is not None and name.strip():
                capa.name = name.strip()
            return capa

        return self._mutate("Duplicar capa", duplicar)  # type: ignore[return-value]

    duplicate_active_layer = duplicate_active

    def remove_active(self) -> bool:
        return bool(self._mutate("Eliminar capa", self.document.remove_active_layer))

    remove_active_layer = remove_active

    def rename_layer(self, layer_id: str | int, name: str) -> bool:
        nuevo = str(name).strip()
        if not nuevo:
            raise ValueError("El nombre de la capa no puede estar vacio")
        capa = self.document.find_layer(layer_id)
        if capa is None or capa.name == nuevo:
            return False

        def renombrar() -> bool:
            capa.name = nuevo
            self.document.invalidate()
            return True

        return bool(self._mutate("Renombrar capa", renombrar))

    def rename_active(self, name: str) -> bool:
        return self.rename_layer(self.document.active_layer_id or "", name)

    def set_layer_opacity(self, layer_id: str | int, opacity: float | int) -> bool:
        capa = self.document.find_layer(layer_id)
        if capa is None:
            return False
        valor = float(opacity)
        if not isfinite(valor):
            raise ValueError("La opacidad necesita un numero finito")
        if valor > 1.0:
            valor /= 100.0
        valor = max(0.0, min(1.0, valor))
        if abs(capa.opacity - valor) < 0.000001:
            return False

        anterior = capa.opacity
        capa.opacity = valor
        self.document.invalidate()

        if self._opacity_layer_id == capa.id and self._opacity_before is not None:
            # Durante un arrastre se presenta cada valor, pero el historial se
            # confirma una sola vez al soltar el deslizador.
            self._emit_layers()
            return True

        self.history.push(
            LayerOpacityCommand(
                layer_id=capa.id,
                before=anterior,
                after=valor,
            )
        )
        self._emit_layers()
        self.historyChanged.emit()
        return True

    def begin_opacity_change(self, layer_id: str | int) -> bool:
        capa = self.document.find_layer(layer_id)
        if capa is None:
            return False
        if self._opacity_layer_id is not None:
            self.end_opacity_change(self._opacity_layer_id)
        self._opacity_layer_id = capa.id
        self._opacity_before = capa.opacity
        return True

    def end_opacity_change(self, layer_id: str | int) -> bool:
        if self._opacity_layer_id is None or self._opacity_before is None:
            return False
        capa = self.document.find_layer(self._opacity_layer_id)
        before = self._opacity_before
        expected_id = str(layer_id)
        self._opacity_layer_id = None
        self._opacity_before = None
        if capa is None or capa.id != expected_id:
            self.history.update_modified(self.document)
            self._emit_layers()
            return False
        if abs(capa.opacity - before) < 0.000001:
            self.history.update_modified(self.document)
            self._emit_layers()
            return False
        self.history.push(LayerOpacityCommand(capa.id, before, capa.opacity))
        self.historyChanged.emit()
        return True

    def set_active_opacity(self, value: float | int) -> bool:
        return self.set_layer_opacity(self.document.active_layer_id or "", value)

    def set_layer_visibility(self, layer_id: str | int, visible: bool) -> bool:
        capa = self.document.find_layer(layer_id)
        mostrar = bool(visible)
        if capa is None or capa.visible == mostrar:
            return False

        def cambiar() -> bool:
            capa.visible = mostrar
            self.document.invalidate()
            return True

        return bool(self._mutate("Mostrar u ocultar capa", cambiar))

    def set_layer_locked(self, layer_id: str | int, locked: bool) -> bool:
        capa = self.document.find_layer(layer_id)
        bloquear = bool(locked)
        if capa is None or capa.locked == bloquear:
            return False

        def cambiar() -> bool:
            capa.locked = bloquear
            self.document.invalidate()
            return True

        return bool(self._mutate("Bloquear capa" if bloquear else "Desbloquear capa", cambiar))

    def set_layer_blend_mode(self, layer_id: str | int, blend_mode: str) -> bool:
        capa = self.document.find_layer(layer_id)
        modo = str(blend_mode)
        if capa is None or modo not in BLEND_MODES or capa.blend_mode == modo:
            return False

        def cambiar() -> bool:
            capa.blend_mode = modo
            self.document.invalidate()
            return True

        return bool(self._mutate("Modo de mezcla de capa", cambiar))

    def flatten(self) -> bool:
        return bool(self._mutate("Acoplar imagen", self.document.flatten_layers))

    def toggle_layer_visibility(self, layer_id: str | int) -> bool:
        capa = self.document.find_layer(layer_id)
        if capa is None:
            return False
        return self.set_layer_visibility(capa.id, not capa.visible)

    def toggle_active_visibility(self) -> bool:
        return self.toggle_layer_visibility(self.document.active_layer_id or "")

    def move_layer(self, layer_id: str | int, new_index: int) -> bool:
        capa = self.document.find_layer(layer_id)
        if capa is None:
            return False
        actual = self.document.layers.index(capa)
        destino = max(0, min(len(self.document.layers) - 1, int(new_index)))
        if actual == destino:
            return False

        def mover() -> bool:
            self.document.layers.pop(actual)
            self.document.layers.insert(destino, capa)
            self.document.invalidate()
            return True

        return bool(self._mutate("Reordenar capa", mover))

    reorder_layer = move_layer

    def move_active_up(self) -> bool:
        return self.move_layer(self.document.active_layer_id or "", self.document.active_layer_index + 1)

    def move_active_down(self) -> bool:
        return self.move_layer(self.document.active_layer_id or "", self.document.active_layer_index - 1)

    def merge_down(self) -> bool:
        return bool(self._mutate("Combinar capa hacia abajo", self.document.merge_active_down))

    merge_active_down = merge_down

    def replace_layer_image(
        self,
        layer_id: str | int,
        image: QImage,
        label: str = "Cambiar imagen de capa",
    ) -> bool:
        self._commit_pending_selection()
        capa = self.document.find_layer(layer_id)
        if capa is None:
            return False
        if image.size() != self.document.size:
            raise ValueError("La nueva imagen no coincide con el lienzo")
        if capa.image == image:
            return False
        before = capa.image.copy()
        capa.image = image.copy()
        self.document.invalidate()
        self.history.push(LayerImageCommand(capa.id, before, capa.image.copy(), label))
        self._emit_layers()
        self.historyChanged.emit()
        return True

    def record_image_change(
        self,
        layer_id: str | int,
        before: QImage,
        label: str = "Cambio en el lienzo",
    ) -> bool:
        self._commit_pending_selection()
        capa = self.document.find_layer(layer_id)
        if capa is None or before == capa.image:
            return False
        self.document.invalidate()
        self.history.push(LayerImageCommand(capa.id, before.copy(), capa.image.copy(), label))
        self._emit_layers()
        self.historyChanged.emit()
        return True

    def begin_change(self) -> DocumentSnapshot:
        return self.history.capture(self.document)

    def commit_change(self, before: DocumentSnapshot, label: str) -> bool:
        changed = self.history.record_snapshot(self.document, before, label)
        if changed:
            self._emit_layers()
            self.historyChanged.emit()
        return changed
