from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QColor, QImage

from backend.Model.document import Document
from backend.Repository.project_repository import PROJECT_EXTENSIONS, ProjectRepository
from backend.Service.document_service import DocumentService
from backend.Service.history_service import DocumentSnapshot, HistoryService, LayerImageCommand


class DocumentController(QObject):
    """Coordina documento, persistencia, transformaciones e historial."""

    documentChanged = Signal(object)
    historyChanged = Signal()
    document_changed = Signal(object)

    def __init__(
        self,
        document: Document | None = None,
        history: HistoryService | None = None,
        repository: ProjectRepository | None = None,
        document_service: DocumentService | None = None,
    ) -> None:
        super().__init__()
        self.document = document or Document()
        self.history = history or HistoryService()
        self.repository = repository or ProjectRepository()
        self.document_service = document_service or DocumentService(self.history)
        self.document_service.history = self.history
        if not self.document.modified:
            self.history.mark_clean(self.document)

    def _emit_document(self) -> None:
        self.documentChanged.emit(self.document)
        self.document_changed.emit(self.document)

    def bind(self, document: Document, clear_history: bool = False) -> None:
        self.document = document
        if clear_history:
            self.history.clear()
            if document.modified:
                self.history.forget_clean()
            else:
                self.history.mark_clean(document)
            self.historyChanged.emit()
        self._emit_document()

    def new_document(
        self,
        width: int = 1920,
        height: int = 1080,
        background_color: QColor | str = "white",
        show_background: bool = True,
        dpi: int = 96,
    ) -> Document:
        document = Document(
            width=max(1, int(width)),
            height=max(1, int(height)),
            background_color=QColor(background_color),
            show_background=show_background,
            dpi=max(1, min(1200, int(dpi))),
        )
        self.bind(document, clear_history=True)
        return document

    def open_path(self, path: Path | str) -> Document:
        document = self.repository.open_document(path)
        self.bind(document, clear_history=True)
        return document

    def save(self, path: Path | str | None = None) -> Path:
        if path is None:
            if self.document.project_path is None:
                raise ValueError("Se necesita una ruta de proyecto para guardar")
            target = self.document.project_path
        else:
            target = Path(path)
        if target.suffix.lower() in PROJECT_EXTENSIONS or not target.suffix:
            return self.save_project(target)
        return self.export(target)

    def save_project(self, path: Path | str) -> Path:
        result = self.repository.save_project(self.document, path)
        self.history.mark_clean(self.document)
        self._emit_document()
        return result

    def mark_clean(self) -> None:
        self.history.mark_clean(self.document)
        self._emit_document()

    def save_recovery(self, path: Path | str) -> Path:
        return self.repository.save_recovery(self.document, path)

    guardar_recuperacion = save_recovery

    def export(self, path: Path | str, quality: int = -1) -> Path:
        result = self.repository.export_image(self.document, path, quality)
        self._emit_document()
        return result

    def undo(self) -> str | None:
        label = self.history.undo(self.document)
        if label is not None:
            self._emit_document()
            self.historyChanged.emit()
        return label

    def redo(self) -> str | None:
        label = self.history.redo(self.document)
        if label is not None:
            self._emit_document()
            self.historyChanged.emit()
        return label

    def _service_result(self, result: bool) -> bool:
        if result:
            self._emit_document()
            self.historyChanged.emit()
        return result

    def crop(self, rect: QRect | tuple[int, int, int, int]) -> bool:
        return self._service_result(self.document_service.crop(self.document, rect))

    def resize_image(self, width: int, height: int, keep_aspect: bool = False) -> bool:
        return self._service_result(
            self.document_service.resize_image(self.document, width, height, keep_aspect)
        )

    def resize_canvas(self, width: int, height: int, anchor: str = "top_left") -> bool:
        return self._service_result(self.document_service.resize_canvas(self.document, width, height, anchor))

    def skew(self, horizontal: float = 0.0, vertical: float = 0.0) -> bool:
        return self._service_result(self.document_service.skew(self.document, horizontal, vertical))

    def rotate(self, degrees: float, expand: bool = True) -> bool:
        return self._service_result(self.document_service.rotate(self.document, degrees, expand))

    def rotate_right(self) -> bool:
        return self._service_result(self.document_service.rotate_right(self.document))

    def rotate_left(self) -> bool:
        return self._service_result(self.document_service.rotate_left(self.document))

    def rotate_180(self) -> bool:
        return self._service_result(self.document_service.rotate_180(self.document))

    def flip_horizontal(self) -> bool:
        return self._service_result(self.document_service.flip_horizontal(self.document))

    def flip_vertical(self) -> bool:
        return self._service_result(self.document_service.flip_vertical(self.document))

    def set_background_visible(self, visible: bool) -> bool:
        return self._service_result(self.document_service.set_background_visible(self.document, visible))

    def set_background_color(self, color: QColor | str) -> bool:
        return self._service_result(self.document_service.set_background_color(self.document, color))

    def apply_filter(self, name: str, **options: object) -> bool:
        return self._service_result(self.document_service.apply_filter(self.document, name, **options))

    def replace_layer_image(
        self,
        layer_id: str | int,
        image: QImage,
        label: str = "Cambio en el lienzo",
    ) -> bool:
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
        self._emit_document()
        self.historyChanged.emit()
        return True

    def record_layer_image_change(
        self,
        layer_id: str | int,
        before: QImage,
        label: str = "Cambio en el lienzo",
    ) -> bool:
        capa = self.document.find_layer(layer_id)
        if capa is None or capa.image == before:
            return False
        self.document.invalidate()
        self.history.push(LayerImageCommand(capa.id, before.copy(), capa.image.copy(), label))
        self._emit_document()
        self.historyChanged.emit()
        return True

    def begin_change(self) -> DocumentSnapshot:
        return self.history.capture(self.document)

    def commit_change(self, before: DocumentSnapshot, label: str = "Cambio de documento") -> bool:
        changed = self.history.record_snapshot(self.document, before, label)
        if changed:
            self._emit_document()
            self.historyChanged.emit()
        return changed

    def mark_changed(self) -> None:
        self.document.invalidate()
        self._emit_document()
