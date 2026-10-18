from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from backend.Controller.document_controller import DocumentController
from backend.Controller.layer_controller import LayerController
from backend.Controller.selection_controller import SelectionController
from backend.Controller.text_controller import TextController
from backend.Controller.tool_controller import ToolController
from backend.Model.document import Document
from backend.Repository.project_repository import (
    IMAGE_EXTENSIONS,
    PROJECT_EXTENSIONS,
    ProjectRepository,
    readable_extensions,
    writable_formats,
)
from backend.Service.Drawing.base_tool import PointerButton
from backend.Model.tool_settings import DEFAULT_TOOL_SIZES, TOOL_SIZE_CHOICES
from backend.Service.Drawing.selection_tools import commit_floating_selection
from backend.Service.Drawing.shape_tools import PAINT_SHAPES
from backend.Service.document_service import DocumentService
from backend.Service.history_service import HistoryService
from backend.Service.print_service import PrintService
from backend.Service.recovery_service import RecoveryMetadata, RecoveryService
from backend.Service.settings_service import SettingsService
from backend.Service.text_service import TextService
from backend.Service.wallpaper_service import WallpaperService
from version import __version__ as APP_VERSION

# Filtros de los diálogos de archivo, en el orden de «Guardar como».
SAVE_FILTERS = {
    "png": ("PNG (*.png)", ".png"),
    "jpeg": ("JPEG (*.jpg *.jpeg *.jpe *.jfif)", ".jpg"),
    "bmp": ("Mapa de bits (*.bmp *.dib)", ".bmp"),
    "gif": ("GIF (*.gif)", ".gif"),
    "tiff": ("TIFF (*.tif *.tiff)", ".tiff"),
    "ico": ("Icono (*.ico)", ".ico"),
    "webp": ("WebP (*.webp)", ".webp"),
    "project": ("Proyecto de MelfPaint (*.melfpaint *.paint)", ".melfpaint"),
}
FORMAT_KEYS = {"PNG": "png", "JPEG": "jpeg", "BMP": "bmp", "GIF": "gif", "TIFF": "tiff", "ICO": "ico", "WEBP": "webp"}


class ApplicationController(QObject):
    """Ensambla la aplicación y mantiene la View libre de reglas de negocio."""

    documentChanged = Signal(object)
    statusChanged = Signal(str)
    errorOccurred = Signal(str)

    def __init__(
        self,
        window: Any | None = None,
        document: Document | None = None,
        document_controller: DocumentController | None = None,
        layer_controller: LayerController | None = None,
        tool_controller: ToolController | None = None,
        selection_controller: SelectionController | None = None,
        text_controller: TextController | None = None,
        history: HistoryService | None = None,
        repository: ProjectRepository | None = None,
        settings_service: SettingsService | None = None,
        print_service: PrintService | None = None,
        recovery_service: RecoveryService | None = None,
        window_factory: Callable[[Document, ToolController], Any] | None = None,
        autosave_interval_ms: int = 120_000,
    ) -> None:
        super().__init__()

        if document_controller is None:
            shared_history = history or HistoryService()
            document_controller = DocumentController(
                document=document or Document(),
                history=shared_history,
                repository=repository or ProjectRepository(),
            )
        self.document_controller = document_controller
        self.history = self.document_controller.history
        self.repository = self.document_controller.repository
        self.document_service = self.document_controller.document_service

        current = self.document_controller.document
        self.layer_controller = layer_controller or LayerController(current, self.history)
        self.tool_controller = tool_controller or ToolController(
            current,
            self.history,
            color_callback=self._color_sampled,
            zoom_callback=self._zoom_from_tool,
        )
        self.selection_controller = selection_controller or SelectionController(
            current,
            self.history,
            self.tool_controller,
            current.tool_settings,
        )
        self.text_controller = text_controller or TextController(current, self.history)
        self.settings_service = settings_service or SettingsService()
        self.print_service = print_service or PrintService()
        self.recovery_service = recovery_service or RecoveryService(repository=self.repository)
        self.wallpaper_service = WallpaperService()

        self.window = window or self._create_window(window_factory)
        self.view = self.window
        self._applying_settings = False
        self._tool_size_prefs: dict[str, float] = {}
        self.separate_drawing = True
        self._image_layer_ids: set[Any] = set()
        self.tool_controller.before_paint = self._before_paint
        self._size_save_timer = QTimer(self)
        self._size_save_timer.setSingleShot(True)
        self._size_save_timer.setInterval(400)
        self._size_save_timer.timeout.connect(self._save_tool_sizes)
        self._full_screen = False
        self._last_shape = "line"
        self._last_error = ""
        self._text_layer_id: str | None = None
        self._theme_mode = "sistema"

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(max(5_000, int(autosave_interval_ms or 120_000)))
        self.autosave_timer.timeout.connect(lambda: self._safe_slot(self.autosave))
        self._autosave_enabled = int(autosave_interval_ms) > 0

        self._connect_controllers()
        self._connect_view()
        self._apply_saved_settings()
        self._apply_tool_size(self.tool_controller.active_tool_id)
        self.refresh()

    @property
    def document(self) -> Document:
        return self.document_controller.document

    # ------------------------------------------------------------------
    # Ensamblaje y utilidades de View
    def _create_window(self, factory: Callable[[Document, ToolController], Any] | None) -> Any:
        if factory is not None:
            return factory(self.document, self.tool_controller)
        from frontend.View.Main.main_window import MainWindow

        return MainWindow(self.document, self.tool_controller)

    @staticmethod
    def _signal(obj: Any, name: str) -> Any | None:
        signal = getattr(obj, name, None)
        return signal if signal is not None and hasattr(signal, "connect") else None

    def _connect(self, obj: Any, signal_name: str, callback: Callable[..., Any]) -> bool:
        signal = self._signal(obj, signal_name)
        if signal is None:
            return False
        signal.connect(lambda *args, fn=callback: self._safe_slot(fn, *args))
        return True

    def _safe_slot(self, callback: Callable[..., Any], *args: Any) -> Any:
        try:
            return callback(*args)
        except Exception as error:  # El límite de la interfaz no debe cerrar la aplicación.
            self._show_error("No se pudo completar la acción", error)
            return False

    @staticmethod
    def _call_optional(obj: Any, names: str | Iterable[str], *args: Any) -> Any:
        candidates = (names,) if isinstance(names, str) else tuple(names)
        for name in candidates:
            method = getattr(obj, name, None)
            if callable(method):
                return method(*args)
        return None

    def _show_error(self, title: str, error: object) -> None:
        message = str(error).strip() or type(error).__name__
        self._last_error = message
        self.errorOccurred.emit(message)
        method = getattr(self.window, "mostrar_error", None)
        if callable(method):
            method(title, message)
            return
        if QApplication.instance() is not None and hasattr(self.window, "winId"):
            QMessageBox.critical(self.window, title, message)

    def _show_info(self, title: str, message: str) -> None:
        method = getattr(self.window, "mostrar_informacion", None)
        if callable(method):
            method(title, message)
            return
        if QApplication.instance() is not None and hasattr(self.window, "winId"):
            QMessageBox.information(self.window, title, message)

    # Mensajes de rutina que no merecen un aviso visible.
    _SILENT_STATUS = (
        "Copia de recuperación",
        "Deshacer:",
        "Rehacer:",
        "Abierto:",
        "Documento nuevo",
        "Lienzo:",
        "Imagen girada",
        "Imagen volteada",
        "Imagen recortada",
        "Filtro aplicado",
        "Selección redimensionada",
    )

    def _status(self, message: str) -> None:
        self.statusChanged.emit(message)
        if not str(message).startswith(self._SILENT_STATUS):
            self._call_optional(self.window, "mostrar_aviso", str(message))
        status = getattr(self.window, "status_bar_paint", None)
        self._call_optional(status, ("set_status_message", "showMessage"), message)

    def _connect_controllers(self) -> None:
        self._connect(self.document_controller, "documentChanged", self._document_emitted)
        self._connect(self.document_controller, "historyChanged", self.refresh)
        self._connect(self.layer_controller, "layersChanged", self.refresh)
        self._connect(self.layer_controller, "historyChanged", self.refresh)
        self._connect(self.tool_controller, "changed", self._drawing_changed)
        self._connect(self.tool_controller, "tool_changed", self._tool_changed)
        self._connect(self.tool_controller, "command_created", self.refresh)
        self._connect(self.tool_controller, "aviso", self._status)
        self._connect(self.text_controller, "textChanged", self._text_format_changed)
        self._connect(self.text_controller, "historyChanged", self.refresh)

    def _connect_view(self) -> None:
        self._connect(self.window, "accionSolicitada", self.execute_action)
        self._connect(self.window, "archivoSoltado", self.open_document)
        self._connect(self.window, "cierreSolicitado", self.request_close)

        ribbon = getattr(self.window, "ribbon", None)
        if ribbon is not None:
            self._connect(ribbon, "herramientaSeleccionada", self.select_tool)
            self._connect(ribbon, "pincelSeleccionado", self.select_brush)
            self._connect(ribbon, "formaSeleccionada", self.select_shape)
            self._connect(ribbon, "tamanoSeleccionado", self.set_tool_size)
            self._connect(ribbon, "colorPrimarioCambiado", self.set_primary_color)
            self._connect(ribbon, "colorSecundarioCambiado", self.set_secondary_color)
            self._connect(ribbon, "contornoCambiado", self.set_outline_style)
            self._connect(ribbon, "rellenoCambiado", self.set_fill_style)
            self._connect(ribbon, "seleccionTransparenteCambiada", self.set_transparent_selection)
            if not self._connect(ribbon, "opacidadHerramientaCambiada", self.set_tool_opacity):
                self._connect(ribbon, "opacidadBorradorCambiada", self.set_eraser_opacity)
            self._connect(ribbon, "toleranciaRellenoCambiada", self.set_fill_tolerance)
            self._connect(ribbon, "coloresPersonalizadosCambiados", self._custom_colors_changed)

        rail = getattr(self.window, "stroke_size_rail", None)
        if rail is not None:
            self._connect(rail, "tamanoSeleccionado", self._rail_size_changed)
            self._connect(rail, "opacidadSeleccionada", self.set_tool_opacity)
            self._connect(rail, "toleranciaSeleccionada", self.set_fill_tolerance)

        canvas = getattr(self.window, "canvas", None)
        if canvas is not None:
            self._connect(canvas, "rectanguloTextoSolicitado", self.start_text)
            self._connect(canvas, "comandoSeleccionSolicitado", self.selection_command)
            self._connect(canvas, "redimensionLienzoSolicitado", self.resize_canvas_from_handle)
            self._connect(canvas, "zoomCambiado", self._zoom_changed)

        panel = getattr(self.window, "layers_panel", None)
        if panel is not None:
            self._connect(panel, "activarSolicitado", self.activate_layer)
            self._connect(panel, "agregarSolicitado", self.add_layer)
            self._connect(panel, "eliminarSolicitado", self.delete_layer)
            self._connect(panel, "duplicarSolicitado", self.duplicate_layer)
            self._connect(panel, "moverSolicitado", self.move_layer)
            self._connect(panel, "combinarSolicitado", self.merge_layer_down)
            self._connect(panel, "renombrarSolicitado", self.rename_layer)
            self._connect(panel, "visibilidadSolicitada", self.set_layer_visibility)
            self._connect(panel, "bloqueoSolicitado", self.set_layer_locked)
            self._connect(panel, "mezclaSolicitada", self.set_layer_blend_mode)
            self._connect(panel, "acoplarSolicitado", self.flatten_layers)
            self._connect(panel, "opacidadInicioSolicitada", self.begin_layer_opacity)
            self._connect(panel, "opacidadSolicitada", self.set_layer_opacity)
            self._connect(panel, "opacidadFinSolicitada", self.end_layer_opacity)

        toolbar = getattr(self.window, "text_toolbar", None)
        if toolbar is not None:
            self._connect(toolbar, "formatoCambiado", self.update_text_format)
            self._connect(toolbar, "confirmarSolicitado", self.confirm_text)
            self._connect(toolbar, "cancelarSolicitado", self.cancel_text)

        editor = getattr(self.window, "text_editor", None)
        if editor is not None:
            self._connect(editor, "confirmarSolicitado", self.confirm_text)
            self._connect(editor, "cancelarSolicitado", self.cancel_text)
            self._connect(editor, "estiloSolicitado", self.toggle_text_style)

        status = getattr(self.window, "status_bar_paint", None)
        if status is not None:
            self._connect(status, "cuadriculaCambiada", self.set_grid_visible)
            self._connect(status, "reglasCambiadas", self.set_rulers_visible)

    # ------------------------------------------------------------------
    # Inicio, documento actual y refresco
    def start(self, paths: Iterable[str | Path] | None = None) -> bool:
        opened = False
        for path in paths or []:
            opened = bool(self.open_document(path, ask_changes=False))
            if opened:
                break
        if not opened:
            self.offer_recovery()
        if self._autosave_enabled:
            self.autosave_timer.start()
        self._call_optional(self.window, "show")
        self.refresh()
        if not opened:
            # Se espera a que el gestor de ventanas fije el tamaño definitivo.
            QTimer.singleShot(150, lambda: self._safe_slot(self._fit_initial_canvas))
        return True

    def _document_is_pristine(self) -> bool:
        document = self.document
        return (
            document.project_path is None
            and document.source_path is None
            and not document.modified
            and len(document.layers) == 1
            and not self.history.can_undo()
            and not self.has_pending_edits()
        )

    DEFAULT_CANVAS_SCALE = 1.45

    def _suggested_canvas_size(self) -> QSize | None:
        method = getattr(self.window, "tamano_lienzo_sugerido", None)
        size = method() if callable(method) else None
        if not isinstance(size, QSize) or not size.isValid():
            return None
        # La hoja inicial es más grande que la ventana (se ve ajustada con zoom).
        return QSize(round(size.width() * self.DEFAULT_CANVAS_SCALE), round(size.height() * self.DEFAULT_CANVAS_SCALE))

    def _fit_initial_canvas(self) -> bool:
        """La hoja en blanco inicial se adapta a la ventana."""

        size = self._suggested_canvas_size()
        if size is None or not self._document_is_pristine():
            return False
        if (size.width(), size.height()) == (self.document.width, self.document.height):
            return False
        document = self.document_controller.new_document(
            size.width(), size.height(), QColor(self.document.background_color), self.document.show_background, dpi=self.document.dpi
        )
        self._replace_document(document, clear_history=True)
        document.modified = False
        self.refresh()
        self.fit_window()
        return True

    iniciar = start

    def _document_emitted(self, document: Document) -> None:
        if self.layer_controller.document is not document:
            self._bind_secondary_controllers(document)
            self._call_optional(self.window, "set_document", document)
            self._apply_tool_size_prefs()
        self.refresh()

    def _bind_secondary_controllers(self, document: Document) -> None:
        self._text_layer_id = None
        self.layer_controller.bind(document)
        self.tool_controller.bind(document, document.tool_settings)
        self.selection_controller.bind(document)
        self.selection_controller.settings = document.tool_settings
        self.text_controller.bind(document)
        self._apply_tool_size(self.tool_controller.active_tool_id)

    def _replace_document(self, document: Document, clear_history: bool = True) -> None:
        self.cancel_text()
        if self.document_controller.document is not document:
            self.document_controller.bind(document, clear_history=clear_history)
        elif clear_history:
            self.history.clear()
        self._bind_secondary_controllers(document)
        self._call_optional(self.window, "set_document", document)
        self._apply_tool_size_prefs()
        self.documentChanged.emit(document)
        self.refresh()

    def refresh(self, *args: Any) -> None:
        self._call_optional(self.window, "actualizar_documento")
        self._call_optional(self.window, "actualizar_titulo")
        ribbon = getattr(self.window, "ribbon", None)
        settings = self.document.tool_settings
        has_selection = self.selection_controller.has_selection()
        if ribbon is not None:
            self._call_optional(ribbon, "set_herramienta_activa", self.tool_controller.active_tool_id)
            self._call_optional(ribbon, "set_pincel_activo", settings.brush_type)
            self._call_optional(ribbon, "set_estilos_forma", settings.outline_mode, settings.fill_mode)
            self._call_optional(ribbon, "set_tamano", round(settings.brush_size))
            self._call_optional(ribbon, "set_colores", settings.primary_color, settings.secondary_color)
            self._call_optional(ribbon, "set_opacidad_borrador", round(settings.eraser_opacity * 100))
            self._call_optional(ribbon, "set_opacidad_trazo", round(settings.opacity * 100))
            self._call_optional(ribbon, "set_seleccion_transparente", settings.transparent_selection)
        self._sync_rail()
        self._drawing_changed()

    def _update_selection_actions(self) -> None:
        """Copiar, cortar, recortar… dependen de la selección actual.

        Se actualizan con cada cambio de la selección (no solo en ``refresh``):
        si no, justo después de seleccionar con el ratón seguían deshabilitados
        y Ctrl+C no hacía nada.
        """

        has_selection = self.selection_controller.has_selection()
        actions = getattr(self.window, "acciones", {})
        for action_id in ("cut", "copy", "deselect", "crop"):
            self._set_action_enabled(actions, action_id, has_selection)
        self._set_action_enabled(
            actions, "delete_selection", has_selection or self.tool_controller.has_pending_shape()
        )
        self._call_optional(getattr(self.window, "ribbon", None), "set_recorte_habilitado", has_selection)

    @staticmethod
    def _set_action_enabled(actions: Any, action_id: str, enabled: bool) -> None:
        action = actions.get(action_id) if isinstance(actions, dict) else None
        if action is not None and hasattr(action, "setEnabled"):
            action.setEnabled(bool(enabled))

    def _drawing_changed(self) -> None:
        self._call_optional(self.window, "actualizar_titulo")
        actions = getattr(self.window, "acciones", {})
        self._set_action_enabled(actions, "undo", self.history.can_undo() or self.tool_controller.has_pending_shape())
        self._set_action_enabled(actions, "redo", self.history.can_redo())
        self._update_selection_actions()
        status = getattr(self.window, "status_bar_paint", None)
        rect = self.selection_controller.selection_rect()
        bounds = getattr(self.tool_controller.active_tool, "bounds", None)
        if rect.isEmpty() and callable(bounds) and self.tool_controller.has_pending_shape():
            # La barra de estado muestra el tamaño de la forma.
            rect = bounds().toAlignedRect()
        self._call_optional(
            status,
            "set_selection_size",
            rect.width() if not rect.isEmpty() else 0,
            rect.height() if not rect.isEmpty() else 0,
        )

    # ------------------------------------------------------------------
    # Texto y selección pendientes
    def _editor_visible(self) -> bool:
        editor = getattr(self.window, "text_editor", None)
        if editor is None:
            return False
        method = getattr(editor, "isVisible", None)
        return bool(method()) if callable(method) else bool(getattr(editor, "visible", False))

    def _editor_text(self) -> str:
        editor = getattr(self.window, "text_editor", None)
        if editor is None:
            return ""
        method = getattr(editor, "toPlainText", None)
        return str(method()) if callable(method) else str(getattr(editor, "text", ""))

    def _editor_rect(self) -> QRect:
        editor = getattr(self.window, "text_editor", None)
        value = getattr(editor, "rectangulo_documento", QRect()) if editor is not None else QRect()
        return QRect(value) if isinstance(value, QRect) else QRect()

    def has_pending_edits(self) -> bool:
        return (
            self.selection_controller.has_selection()
            or self.tool_controller.has_pending_shape()
            or (self._editor_visible() and bool(self._editor_text().strip()))
        )

    def confirm_pending_edits(self) -> bool:
        if self._editor_visible():
            self.confirm_text()
        self.tool_controller.commit_pending()
        if self.selection_controller.has_selection():
            self.selection_controller.commit(push_history=True)
        return True

    confirmar_ediciones_pendientes = confirm_pending_edits

    def start_text(self, rect: QRect) -> bool:
        area = QRect(rect).intersected(QRect(0, 0, self.document.width, self.document.height))
        if area.isEmpty():
            return False
        if self._editor_visible():
            self.confirm_text()
        editor = getattr(self.window, "text_editor", None)
        toolbar = getattr(self.window, "text_toolbar", None)
        canvas = getattr(self.window, "canvas", None)
        zoom = float(getattr(canvas, "zoom", 1.0))
        self._call_optional(editor, ("empezar", "start"), area, self.document.text_format, zoom)
        self._text_layer_id = self.document.active_layer_id
        if canvas is not None and hasattr(canvas, "document_rect_to_screen"):
            screen_rect = canvas.document_rect_to_screen(area)
            self._call_optional(editor, "establecer_geometria", screen_rect, zoom)
        self._call_optional(toolbar, "set_format", self._text_format_values())
        self._call_optional(toolbar, "set_text_mode", True)
        return True

    def confirm_text(self) -> bool:
        if not self._editor_visible():
            return False
        text = self._editor_text()
        rect = self._editor_rect()
        changed = False
        layer_id = self._text_layer_id
        if text.strip() and not rect.isEmpty():
            changed = self.text_controller.insert_text(rect, text, layer_id)
        self._text_layer_id = None
        editor = getattr(self.window, "text_editor", None)
        toolbar = getattr(self.window, "text_toolbar", None)
        self._call_optional(editor, ("terminar", "finish"))
        self._call_optional(toolbar, "set_text_mode", False)
        self.refresh()
        return changed

    def cancel_text(self) -> bool:
        if not self._editor_visible():
            self._text_layer_id = None
            return False
        self._text_layer_id = None
        self._call_optional(getattr(self.window, "text_editor", None), ("terminar", "finish"))
        self._call_optional(getattr(self.window, "text_toolbar", None), "set_text_mode", False)
        return True

    def _text_format_values(self) -> dict[str, object]:
        value = self.document.text_format
        if value.alignment & Qt.AlignmentFlag.AlignRight:
            alignment = "right"
        elif value.alignment & Qt.AlignmentFlag.AlignHCenter:
            alignment = "center"
        else:
            alignment = "left"
        return {
            "familia": value.family,
            "tamano": value.size,
            "negrita": value.bold,
            "cursiva": value.italic,
            "subrayado": value.underline,
            "tachado": value.strikeout,
            "alineacion": alignment,
            "fondo": "opaque" if value.opaque_background else "transparent",
        }

    def update_text_format(self, values: dict[str, object]) -> None:
        value = self.text_controller.update_format(values)
        self._call_optional(getattr(self.window, "text_editor", None), "actualizar_formato", value)

    def toggle_text_style(self, style: str) -> None:
        names = {
            "bold": "negrita",
            "italic": "cursiva",
            "underline": "subrayado",
            "strikeout": "tachado",
        }
        key = names.get(str(style).lower())
        if key is None:
            return
        toolbar = getattr(self.window, "text_toolbar", None)
        method = getattr(toolbar, "formato_actual", None)
        values = dict(method()) if callable(method) else self._text_format_values()
        values[key] = not bool(values.get(key, False))
        self.text_controller.update_format(values)
        self._call_optional(toolbar, "set_format", values)
        self._text_format_changed()

    def _text_format_changed(self) -> None:
        self._call_optional(
            getattr(self.window, "text_editor", None),
            "actualizar_formato",
            self.document.text_format,
        )

    def selection_command(self, command: str, dx: int = 0, dy: int = 0) -> Any:
        command = str(command).lower()
        if command in {"confirmar", "commit", "enter"}:
            result = self.selection_controller.commit(push_history=True)
        elif command in {"cancelar", "cancel", "escape"}:
            result = self.selection_controller.cancel()
        elif command in {"eliminar", "delete", "backspace"}:
            result = self.delete_selection()
        elif command in {"mover", "move"}:
            result = self.selection_controller.move_by(dx, dy)
        else:
            return False
        self.refresh()
        return result

    # ------------------------------------------------------------------
    # Confirmación de cambios
    def _document_name(self) -> str:
        path = self.document.project_path or self.document.source_path
        return path.name if path is not None else "Sin título"

    @staticmethod
    def _normalize_prompt_result(value: Any) -> str:
        if value is True:
            return "discard"
        if value in {False, None}:
            return "cancel"
        text = " ".join(str(value).strip().lower().replace("_", " ").split())
        choices = {
            "save": "save",
            "guardar": "save",
            "standardbutton.save": "save",
            "discard": "discard",
            "descartar": "discard",
            "no": "discard",
            "no guardar": "discard",
            "don't save": "discard",
            "dont save": "discard",
            "standardbutton.discard": "discard",
            "cancel": "cancel",
            "cancelar": "cancel",
            "later": "cancel",
        }
        return choices.get(text, "cancel")

    def _ask_unsaved(self) -> str:
        method = getattr(self.window, "confirmar_cambios", None)
        if callable(method):
            return self._normalize_prompt_result(method(self._document_name()))
        if QApplication.instance() is None or not hasattr(self.window, "winId"):
            return "cancel"
        dialogo = QMessageBox(self.window)
        dialogo.setWindowTitle("MelfPaint")
        dialogo.setIcon(QMessageBox.Icon.NoIcon)
        dialogo.setText(f"¿Desea guardar los cambios en {self._document_name()}?")
        guardar = dialogo.addButton("Guardar", QMessageBox.ButtonRole.AcceptRole)
        no_guardar = dialogo.addButton("No guardar", QMessageBox.ButtonRole.DestructiveRole)
        cancelar = dialogo.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        guardar.setObjectName("PrimaryButton")
        dialogo.setDefaultButton(guardar)
        dialogo.setEscapeButton(cancelar)
        dialogo.exec()
        pulsado = dialogo.clickedButton()
        if pulsado is guardar:
            return "save"
        if pulsado is no_guardar:
            return "discard"
        return "cancel"

    def confirm_discard_changes(self) -> bool:
        if not self.document.modified and not self.has_pending_edits():
            return True
        choice = self._ask_unsaved()
        if choice == "save":
            saved = bool(self.save_document())
            return saved and not self.document.modified and not self.has_pending_edits()
        if choice == "discard":
            self.cancel_text()
            self.selection_controller.cancel()
            return True
        return False

    confirmar_descartar = confirm_discard_changes

    # ------------------------------------------------------------------
    # Rutas y persistencia
    @staticmethod
    def _path_from_dialog(value: Any, default_suffix: str | None = None) -> Path | None:
        selected_filter = ""
        if isinstance(value, (tuple, list)):
            selected_filter = str(value[1]) if len(value) > 1 else ""
            value = value[0] if value else ""
        if value is None or not str(value).strip():
            return None
        path = Path(str(value)).expanduser()
        if path.suffix:
            return path

        suffix = next(
            (extension for filtro, extension in SAVE_FILTERS.values() if filtro.lower() == selected_filter.lower()),
            default_suffix,
        )
        return path.with_suffix(suffix) if suffix else path

    @staticmethod
    def _open_filter(include_projects: bool = True) -> str:
        extensiones = sorted(readable_extensions())
        patrones = " ".join(f"*{extension}" for extension in extensiones)
        if include_projects:
            patrones = "*.melfpaint *.paint " + patrones
            return f"Todos los archivos de imagen ({patrones});;Proyecto de MelfPaint (*.melfpaint *.paint);;Todos los archivos (*)"
        return f"Todos los archivos de imagen ({patrones});;Todos los archivos (*)"

    def _start_directory(self) -> str:
        path = self.document.project_path or self.document.source_path
        if path is not None:
            return str(path.parent)
        pictures = Path.home() / "Imágenes"
        if not pictures.is_dir():
            pictures = Path.home() / "Pictures"
        return str(pictures if pictures.is_dir() else Path.home())

    def _choose_open_path(self, title: str = "Abrir", include_projects: bool = True) -> Path | None:
        method = getattr(self.window, "seleccionar_archivo_abrir", None)
        if callable(method):
            return self._path_from_dialog(method())
        value = QFileDialog.getOpenFileName(self.window, title, self._start_directory(), self._open_filter(include_projects))
        return self._path_from_dialog(value)

    def _choose_save_path(self, mode: str) -> Path | None:
        method_names = {
            "project": ("seleccionar_proyecto_guardar", "seleccionar_archivo_guardar"),
            "save_as": ("seleccionar_guardar_como", "seleccionar_archivo_guardar"),
            "export": ("seleccionar_archivo_exportar", "seleccionar_exportar"),
        }
        for name in method_names[mode]:
            method = getattr(self.window, name, None)
            if callable(method):
                default_suffix = ".png" if mode == "export" else ".melfpaint"
                return self._path_from_dialog(method(), default_suffix)
        return self._choose_save_path_for("project" if mode == "project" else None)

    def _available_save_keys(self) -> list[str]:
        disponibles = {FORMAT_KEYS[formato] for formato in writable_formats() if formato in FORMAT_KEYS}
        return [key for key in ("png", "jpeg", "bmp", "gif", "tiff", "ico", "webp") if key in disponibles]

    def _choose_save_path_for(self, preferred: str | None) -> Path | None:
        claves = self._available_save_keys() + ["project"]
        if preferred in claves:
            claves.remove(preferred)
            claves.insert(0, preferred)
        filtros = [SAVE_FILTERS[clave][0] for clave in claves]
        nombre_base = (self.document.project_path or self.document.source_path)
        if nombre_base is not None:
            sufijo = SAVE_FILTERS[claves[0]][1]
            inicial = str(nombre_base.with_suffix(sufijo))
        else:
            inicial = str(Path(self._start_directory()) / f"Sin título{SAVE_FILTERS[claves[0]][1]}")
        value = QFileDialog.getSaveFileName(self.window, "Guardar como", inicial, ";;".join(filtros), filtros[0])
        return self._path_from_dialog(value, SAVE_FILTERS[claves[0]][1])

    def new_document(self, values: dict[str, Any] | None = None) -> bool:
        ajustar = values is None
        if values is None:
            method = getattr(self.window, "valores_nuevo_documento", None)
            if callable(method):
                values = method()
            else:
                # La hoja en blanco se crea al instante, del tamaño de la ventana.
                size = self._suggested_canvas_size()
                values = {
                    "width": size.width() if size is not None else 1152,
                    "height": size.height() if size is not None else 648,
                    "background": QColor("white"),
                    "transparent": False,
                    "dpi": 96,
                }
        if not values:
            return False
        if not self.confirm_discard_changes():
            return False
        try:
            document = self.document_controller.new_document(
                int(values.get("width", 1920)),
                int(values.get("height", 1080)),
                QColor(values.get("background", "white")),
                not bool(values.get("transparent", False)),
                dpi=int(values.get("dpi", 96)),
            )
            self._replace_document(document, clear_history=False)
            self._discard_current_recovery()
            self._status("Documento nuevo")
            if ajustar:
                self.fit_window()
            return True
        except Exception as error:
            self._show_error("No se pudo crear el documento", error)
            return False

    nuevo = new_document

    def open_document(self, path: str | Path | None = None, ask_changes: bool = True) -> bool:
        target = Path(path).expanduser() if path is not None else self._choose_open_path()
        if target is None:
            return False
        if ask_changes and not self.confirm_discard_changes():
            return False
        try:
            document = self.document_controller.open_path(target)
            self._replace_document(document, clear_history=False)
            if self.document.project_path is None and len(self.document.layers) == 1:
                # Una imagen abierta es la base: dibujar encima abre su propia capa.
                self._image_layer_ids.add(self.document.layers[0].id)
            self._discard_current_recovery()
            self._add_recent(target)
            self._status(f"Abierto: {target.name}")
            return True
        except Exception as error:
            self._show_error("No se pudo abrir el archivo", error)
            return False

    abrir = open_document

    def save_document(self) -> bool:
        try:
            if self.document.project_path is not None:
                self.confirm_pending_edits()
                target = self.document_controller.save_project(self.document.project_path)
            elif self.document.source_path is not None:
                if len(self.document.layers) > 1:
                    self._status("Elija un proyecto MelfPaint para conservar todas las capas")
                    return self.save_as()
                self.confirm_pending_edits()
                target = self.document_controller.export(self.document.source_path)
                self.document_controller.mark_clean()
            else:
                return self.save_as()
            self._after_successful_save(target)
            return True
        except Exception as error:
            self._show_error("No se pudo guardar", error)
            return False

    guardar = save_document

    def save_project(self, path: str | Path | None = None) -> bool:
        target = Path(path).expanduser() if path is not None else self._choose_save_path("project")
        if target is None:
            return False
        self.confirm_pending_edits()
        try:
            result = self.document_controller.save_project(target)
            self._after_successful_save(result)
            return True
        except Exception as error:
            self._show_error("No se pudo guardar el proyecto", error)
            return False

    guardar_proyecto = save_project

    def save_as_format(self, key: str | None) -> bool:
        target = self._choose_save_path_for(key)
        if target is None:
            return False
        return self.save_as(target)

    def save_as(self, path: str | Path | None = None) -> bool:
        target = Path(path).expanduser() if path is not None else self._choose_save_path("save_as")
        if target is None:
            return False
        self.confirm_pending_edits()
        try:
            extension = target.suffix.lower()
            if extension in PROJECT_EXTENSIONS or not extension:
                result = self.document_controller.save_project(target)
                self._after_successful_save(result)
            elif extension in IMAGE_EXTENSIONS:
                identity = (
                    self.document.project_path,
                    self.document.source_path,
                    self.document.modified,
                )
                result = self.document_controller.export(target)
                old_project, old_source, old_modified = identity
                if old_project is None and len(self.document.layers) == 1:
                    self.document.source_path = result
                    self.document_controller.mark_clean()
                    self._after_successful_save(result)
                else:
                    # Guardar como imagen equivale a exportar cuando existe un
                    # proyecto o hay varias capas. No roba la identidad ni hace
                    # pasar una copia aplanada por un guardado completo.
                    self.document.project_path = old_project
                    self.document.source_path = old_source
                    self.document.modified = old_modified if old_project is not None else True
                    self._add_recent(result)
                    if old_project is None:
                        self._status(
                            f"Imagen exportada: {result.name}; guarde como proyecto para conservar las capas"
                        )
                    else:
                        self._status(f"Imagen exportada: {result.name}")
                    self.refresh()
            else:
                raise ValueError("La extensión elegida no es compatible")
            return True
        except Exception as error:
            self._show_error("No se pudo guardar como", error)
            return False

    guardar_como = save_as

    def export_image(self, path: str | Path | None = None, quality: int = -1) -> bool:
        target = Path(path).expanduser() if path is not None else self._choose_save_path("export")
        if target is None:
            return False
        self.confirm_pending_edits()
        identity = (self.document.project_path, self.document.source_path, self.document.modified)
        try:
            result = self.document_controller.export(target, quality)
            self.document.project_path, self.document.source_path, self.document.modified = identity
            self._add_recent(result)
            self._status(f"Exportado: {result.name}")
            self.refresh()
            return True
        except Exception as error:
            self.document.project_path, self.document.source_path, self.document.modified = identity
            self._show_error("No se pudo exportar", error)
            return False

    exportar = export_image

    def _after_successful_save(self, path: Path) -> None:
        self._add_recent(path)
        if not self.document.modified:
            self._discard_current_recovery()
        self._status(f"Guardado: {path.name}")
        self.refresh()

    def _add_recent(self, path: Path) -> None:
        try:
            self.settings_service.agregar_archivo_reciente(Path(path))
        except OSError:
            return
        self._call_optional(
            self.window,
            ("set_recent_files", "actualizar_recientes"),
            list(self.settings_service.obtener("archivos_recientes", [])),
        )

    def _discard_current_recovery(self) -> bool:
        try:
            return bool(self.recovery_service.discard())
        except OSError as error:
            self._show_error("No se pudo limpiar la copia de recuperación", error)
            return False

    def open_recent(self, path: str | Path) -> bool:
        return self.open_document(path)

    # ------------------------------------------------------------------
    # Herramientas, colores y zoom
    def select_tool(self, tool_id: str) -> bool:
        tool_id = str(tool_id)
        if tool_id == "shape":
            tool_id = self._last_shape
        aliases = {"free_select": "freeform_select", "picker": "eyedropper", "zoom": "magnifier"}
        tool_id = aliases.get(tool_id, tool_id)
        if tool_id != "text" and self._editor_visible():
            self.confirm_text()
        self.tool_controller.set_tool(tool_id)
        self._call_optional(getattr(self.window, "ribbon", None), "set_herramienta_activa", tool_id)
        return True

    def select_brush(self, brush_id: str) -> None:
        if self._editor_visible():
            self.confirm_text()
        aliases = {"brush": "round", "spray": "airbrush"}
        self.document.tool_settings.brush_type = aliases.get(str(brush_id), str(brush_id))
        self.tool_controller.set_tool("brush")
        self._call_optional(getattr(self.window, "ribbon", None), "set_herramienta_activa", "brush")
        self._call_optional(getattr(self.window, "ribbon", None), "set_pincel_activo", str(brush_id))

    def select_shape(self, shape_id: str) -> None:
        if self._editor_visible():
            self.confirm_text()
        self._last_shape = str(shape_id)
        self.tool_controller.set_tool(self._last_shape)
        self._call_optional(getattr(self.window, "ribbon", None), "set_herramienta_activa", self._last_shape)

    @staticmethod
    def _size_family(tool_id: str) -> str | None:
        tool_id = str(tool_id)
        if tool_id in {"pencil", "brush", "eraser"}:
            return tool_id
        if tool_id in PAINT_SHAPES or tool_id in {"rect", "rounded_rect", "oval", "arrow", "star", "callout", "bolt", "bubble", "spark"}:
            return "shape"
        return None

    def _apply_tool_size(self, tool_id: str) -> None:
        """Se recuerda un grosor distinto para lápiz, pinceles, borrador y formas."""

        family = self._size_family(tool_id)
        ribbon = getattr(self.window, "ribbon", None)
        if family is None:
            return
        settings = self.document.tool_settings
        size = float(settings.tool_sizes.get(family, DEFAULT_TOOL_SIZES[family]))
        settings.brush_size = size
        settings.line_width = size
        self._call_optional(ribbon, "set_tamanos", list(TOOL_SIZE_CHOICES[family]))
        self._call_optional(ribbon, "set_tamano", round(size))
        self._sync_rail()

    def _rail_size_changed(self, value: int) -> None:
        self.set_tool_size(value)
        self._call_optional(getattr(self.window, "ribbon", None), "set_tamano", value)

    def _sync_rail(self) -> None:
        rail = getattr(self.window, "stroke_size_rail", None)
        if rail is None:
            return
        settings = self.document.tool_settings
        tool_id = self.tool_controller.active_tool_id
        rail.set_tool(tool_id)
        opacity = settings.eraser_opacity if tool_id == "eraser" else settings.opacity
        rail.set_values(round(settings.brush_size), round(opacity * 100), settings.fill_tolerance)

    def set_tool_size(self, value: int | float) -> None:
        size = max(1.0, min(256.0, float(value)))
        settings = self.document.tool_settings
        settings.brush_size = size
        settings.line_width = size
        family = self._size_family(self.tool_controller.active_tool_id)
        if family is not None:
            settings.tool_sizes[family] = size
            self._tool_size_prefs[family] = size
            self._size_save_timer.start()
        self.tool_controller.refresh_preview()

    def _save_tool_sizes(self) -> None:
        """Recuerda el grosor de cada herramienta entre sesiones y documentos."""

        self._size_save_timer.stop()
        self._save_setting("tamanos_herramienta", dict(self._tool_size_prefs))

    def _load_tool_size_prefs(self) -> None:
        guardados = self.settings_service.obtener("tamanos_herramienta", {})
        if isinstance(guardados, dict):
            self._tool_size_prefs = {str(k): float(v) for k, v in guardados.items()}
        self._apply_tool_size_prefs()

    def _apply_tool_size_prefs(self) -> None:
        """Los grosores elegidos valen para cualquier documento, nuevo o abierto."""

        if not self._tool_size_prefs:
            return
        self.document.tool_settings.tool_sizes.update(self._tool_size_prefs)
        self._apply_tool_size(self.tool_controller.active_tool_id)

    def change_tool_size(self, amount: int) -> int:
        sizes = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256]
        current = float(self.document.tool_settings.brush_size)
        if amount > 0:
            value = next((size for size in sizes if size > current), sizes[-1])
        else:
            value = next((size for size in reversed(sizes) if size < current), sizes[0])
        self._rail_size_changed(value)
        self._sync_rail()
        return value

    def set_primary_color(self, color: QColor | str) -> None:
        value = QColor(color)
        if not value.isValid():
            raise ValueError("El color primario no es válido")
        self.document.tool_settings.primary_color = value
        self.text_controller.set_colors(value, self.document.tool_settings.secondary_color)
        self._text_format_changed()
        self.tool_controller.refresh_preview()

    def set_secondary_color(self, color: QColor | str) -> None:
        value = QColor(color)
        if not value.isValid():
            raise ValueError("El color secundario no es válido")
        self.document.tool_settings.secondary_color = value
        self.text_controller.set_colors(self.document.tool_settings.primary_color, value)
        self.selection_controller.set_transparent(self.document.tool_settings.transparent_selection)
        self._text_format_changed()
        self.tool_controller.refresh_preview()

    def _color_sampled(self, color: QColor, button: PointerButton) -> None:
        if button is PointerButton.SECONDARY:
            self.set_secondary_color(color)
        else:
            self.set_primary_color(color)
        self.refresh()

    def set_outline_style(self, style: str) -> None:
        value = str(style or "none")
        self.document.tool_settings.outline_mode = value
        self.document.tool_settings.outline_enabled = value != "none"
        self.tool_controller.refresh_preview()

    def set_fill_style(self, style: str) -> None:
        value = str(style or "none")
        self.document.tool_settings.fill_mode = value
        self.document.tool_settings.fill_enabled = value != "none"
        self.tool_controller.refresh_preview()

    def set_transparent_selection(self, enabled: bool) -> None:
        self.document.tool_settings.transparent_selection = bool(enabled)
        self.selection_controller.set_transparent(enabled)
        self._call_optional(getattr(self.window, "canvas", None), "update")

    @staticmethod
    def _opacity_fraction(value: int | float) -> float:
        """Los enteros son porcentajes (1 = 1 %); los decimales hasta 1.0, fracciones."""

        opacity = float(value)
        if isinstance(value, float) and opacity <= 1.0:
            return min(1.0, max(0.0, opacity))
        return max(0.0, min(1.0, opacity / 100.0))

    def set_eraser_opacity(self, value: int | float) -> None:
        self.document.tool_settings.eraser_opacity = self._opacity_fraction(value)

    def set_tool_opacity(self, tool_id: str, value: int | float) -> None:
        if str(tool_id) == "eraser":
            self.set_eraser_opacity(value)
            return
        self.document.tool_settings.opacity = self._opacity_fraction(value)
        self.tool_controller.refresh_preview()

    def set_fill_tolerance(self, value: int | float) -> None:
        self.document.tool_settings.fill_tolerance = max(0, min(255, round(float(value))))

    def _tool_changed(self, tool_id: str) -> None:
        self._apply_tool_size(tool_id)
        self._call_optional(getattr(self.window, "ribbon", None), "set_herramienta_activa", tool_id)
        self._sync_rail()

    ZOOM_STEPS = (10, 12, 16, 25, 33, 50, 67, 100, 125, 150, 200, 300, 400, 500, 600, 700, 800)

    def _next_zoom(self, direction: int) -> int:
        current = round(float(getattr(getattr(self.window, "canvas", None), "zoom", 1.0)) * 100)
        if direction > 0:
            return next((value for value in self.ZOOM_STEPS if value > current), 800)
        return next((value for value in reversed(self.ZOOM_STEPS) if value < current), 10)

    def _zoom_from_tool(self, point: QPointF, button: PointerButton | int) -> None:
        # La lupa acerca con clic y aleja con clic derecho, centrando
        # la vista en el punto pulsado.
        zoom_out = button is PointerButton.SECONDARY or (isinstance(button, int) and button < 0)
        value = self._next_zoom(-1 if zoom_out else 1)
        method = getattr(self.window, "zoom_en_punto", None)
        if callable(method):
            method(value, float(point.x()), float(point.y()))
            self.document.tool_settings.zoom = value / 100.0
            return
        self.set_zoom(value)

    def set_zoom(self, percent: int | float) -> int:
        value = max(10, min(800, round(float(percent))))
        self._call_optional(getattr(self.window, "canvas", None), ("set_zoom_percent", "establecer_zoom"), value)
        self._call_optional(getattr(self.window, "status_bar_paint", None), "set_zoom", value)
        self.document.tool_settings.zoom = value / 100.0
        return value

    def _zoom_changed(self, percent: int) -> None:
        self.document.tool_settings.zoom = max(0.1, float(percent) / 100.0)
        if not self._applying_settings:
            self._save_setting("zoom", int(percent))

    def zoom_in(self) -> int:
        return self.set_zoom(self._next_zoom(1))

    def zoom_out(self) -> int:
        return self.set_zoom(self._next_zoom(-1))

    def fit_window(self) -> int:
        canvas = getattr(self.window, "canvas", None)
        scroll = getattr(self.window, "scroll_area", None)
        viewport = getattr(scroll, "viewport", None)
        available = viewport().size() if callable(viewport) else QSize(900, 600)
        method = getattr(canvas, "fit_to_size", None)
        return int(method(available)) if callable(method) else self.set_zoom(100)

    # ------------------------------------------------------------------
    # Portapapeles y selección
    def _paste_position(self) -> QPoint:
        method = getattr(self.window, "area_visible_documento", None)
        if not callable(method):
            return QPoint(0, 0)
        visible = method()
        x = max(0, min(self.document.width - 1, visible.x()))
        y = max(0, min(self.document.height - 1, visible.y()))
        return QPoint(x, y)

    def paste_image(self, image: QImage | None = None) -> bool:
        """Pega la imagen; si no cabe, ofrece ampliar el lienzo."""

        self.confirm_pending_edits()
        floating = image if image is not None else self.selection_controller.clipboard_image()
        if floating is None or floating.isNull():
            self._status("El Portapapeles no contiene una imagen")
            return False
        if self.separate_drawing:
            self._image_layer_ids.add(self.layer_controller.add_layer("Imagen").id)
        position = self._paste_position()
        if floating.width() > self.document.width or floating.height() > self.document.height:
            ask = getattr(self.window, "preguntar_ampliar_lienzo", None)
            answer = ask() if callable(ask) else True
            if answer is None:
                return False
            if answer:
                width = max(self.document.width, floating.width())
                height = max(self.document.height, floating.height())
                self.document_controller.resize_canvas(width, height, "top_left")
            position = QPoint(0, 0)
        result = self.selection_controller.paste(floating, position)
        self.refresh()
        return bool(result)

    def _before_paint(self) -> None:
        """Con la separación activa, dibujar sobre una imagen pegada abre una capa «Dibujo».

        El borrador y el relleno siguen actuando sobre la capa activa, de modo
        que borrar el dibujo nunca toca la imagen de debajo.
        """

        if not self.separate_drawing or self.tool_controller.active_tool_id in ("eraser", "fill", "bucket"):
            return
        layer = self.document.active_layer
        if layer is None or getattr(layer, "id", None) not in self._image_layer_ids:
            return
        self._image_layer_ids.discard(layer.id)
        self.layer_controller.add_layer("Dibujo")

    def set_separate_drawing(self, enabled: bool) -> None:
        self.separate_drawing = bool(enabled)
        self._set_action_checked("separate_drawing", self.separate_drawing)
        if not self._applying_settings:
            self._save_setting("dibujo_en_capa_aparte", self.separate_drawing)

    def paste_from_file(self) -> bool:
        target = self._choose_open_path("Pegar desde", include_projects=False)
        if target is None:
            return False
        try:
            image = self.repository.read_image(target)
        except Exception as error:
            self._show_error("No se pudo abrir el archivo", error)
            return False
        return self.paste_image(image)

    def invert_selection(self) -> bool:
        self.tool_controller.commit_pending()
        result = self.selection_controller.invert()
        self.refresh()
        return bool(result)

    def delete_selection(self) -> Any:
        if self.tool_controller.has_pending_shape():
            result = self.tool_controller.discard_pending_shape()
        else:
            result = self.selection_controller.delete()
        self.refresh()
        return result

    def select_all(self) -> bool:
        self.tool_controller.commit_pending()
        result = self.selection_controller.select_all()
        self.refresh()
        return bool(result)

    # ------------------------------------------------------------------
    # Capas
    def activate_layer(self, layer_id: str) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.activate(layer_id)
        self.refresh()
        return result

    def add_layer(self, name: str | None = None) -> bool:
        self.confirm_pending_edits()
        self.layer_controller.add_layer(name)
        self.refresh()
        return True

    def duplicate_layer(self) -> bool:
        self.confirm_pending_edits()
        self.layer_controller.duplicate_active()
        self.refresh()
        return True

    def delete_layer(self) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.remove_active()
        self.refresh()
        return result

    def move_layer(self, layer_id: str, direction: int) -> bool:
        self.confirm_pending_edits()
        layer = self.document.find_layer(layer_id)
        if layer is None:
            return False
        current = self.document.layers.index(layer)
        result = self.layer_controller.move_layer(layer.id, current + int(direction))
        self.refresh()
        return result

    def move_active_layer(self, direction: int) -> bool:
        self.confirm_pending_edits()
        result = (
            self.layer_controller.move_active_up()
            if int(direction) > 0
            else self.layer_controller.move_active_down()
        )
        self.refresh()
        return result

    def merge_layer_down(self) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.merge_down()
        self.refresh()
        return result

    def rename_layer(self, layer_id: str, name: str) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.rename_layer(layer_id, name)
        self.refresh()
        return result

    def rename_active_layer(self, name: str | None = None) -> bool:
        if name is None:
            if QApplication.instance() is None or not hasattr(self.window, "winId"):
                return False
            name, accepted = QInputDialog.getText(
                self.window,
                "Renombrar capa",
                "Nuevo nombre:",
                text=self.document.active_layer.name,
            )
            if not accepted:
                return False
        return self.rename_layer(self.document.active_layer_id or "", str(name))

    def set_layer_visibility(self, layer_id: str, visible: bool) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.set_layer_visibility(layer_id, visible)
        self.refresh()
        return result

    def set_layer_locked(self, layer_id: str, locked: bool) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.set_layer_locked(layer_id, locked)
        self.refresh()
        return result

    def set_layer_blend_mode(self, layer_id: str, blend_mode: str) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.set_layer_blend_mode(layer_id, blend_mode)
        self.refresh()
        return result

    def flatten_layers(self) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.flatten()
        self.refresh()
        if result:
            self._status("Capas acopladas en una sola")
        return result

    def set_layer_opacity(self, layer_id: str, opacity: int | float) -> bool:
        self.confirm_pending_edits()
        result = self.layer_controller.set_layer_opacity(layer_id, opacity)
        return result

    def begin_layer_opacity(self, layer_id: str) -> bool:
        self.confirm_pending_edits()
        return self.layer_controller.begin_opacity_change(layer_id)

    def end_layer_opacity(self, layer_id: str) -> bool:
        result = self.layer_controller.end_opacity_change(layer_id)
        self.refresh()
        return result

    # ------------------------------------------------------------------
    # Transformaciones y propiedades
    def _document_mutation(self, callback: Callable[[], Any], success: str = "") -> bool:
        self.confirm_pending_edits()
        try:
            changed = bool(callback())
            if changed:
                self.refresh()
                if success:
                    self._status(success)
            return changed
        except Exception as error:
            self._show_error("No se pudo modificar la imagen", error)
            return False

    def crop_selection(self) -> bool:
        rect = self.selection_controller.selection_rect()
        if rect.isEmpty():
            self._status("Seleccione un área antes de recortar")
            return False
        self.confirm_pending_edits()
        return self._document_mutation(lambda: self.document_controller.crop(rect), "Imagen recortada")

    recortar = crop_selection

    def resize_and_skew(self, values: dict[str, Any] | None = None) -> bool:
        selection_active = self.selection_controller.has_selection()
        selection_rect = self.selection_controller.selection_rect()
        base_width = selection_rect.width() if selection_active else self.document.width
        base_height = selection_rect.height() if selection_active else self.document.height
        if values is None:
            method = getattr(self.window, "valores_cambiar_tamano", None)
            if callable(method):
                values = method()
            else:
                from frontend.View.Dialogs.resize_skew_dialog import ResizeSkewDialog

                dialog = ResizeSkewDialog(base_width, base_height, self.window)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return False
                values = dialog.valores()
        if not values:
            return False
        if selection_active:
            if self._editor_visible():
                self.confirm_text()
            try:
                changed = self.selection_controller.resize_and_skew(
                    int(values.get("width", base_width)),
                    int(values.get("height", base_height)),
                    bool(values.get("keep_aspect", False)),
                    float(values.get("horizontal_skew", 0)),
                    float(values.get("vertical_skew", 0)),
                )
                if changed:
                    self.refresh()
                    self._status("Selección redimensionada")
                return changed
            except Exception as error:
                self._show_error("No se pudo cambiar el tamaño de la selección", error)
                return False
        self.confirm_pending_edits()
        before = self.history.capture(self.document)
        temporary_service = DocumentService(HistoryService())
        try:
            changed = temporary_service.resize_image(
                self.document,
                int(values.get("width", self.document.width)),
                int(values.get("height", self.document.height)),
                bool(values.get("keep_aspect", False)),
            )
            horizontal = float(values.get("horizontal_skew", 0))
            vertical = float(values.get("vertical_skew", 0))
            if horizontal or vertical:
                changed = temporary_service.skew(self.document, horizontal, vertical) or changed
            if changed:
                self.document_controller.commit_change(before, "Cambiar tamaño y sesgar")
                self.refresh()
            return bool(changed)
        except Exception as error:
            before.restore(self.document)
            self._show_error("No se pudo cambiar el tamaño", error)
            return False

    cambiar_tamano = resize_and_skew

    def resize_canvas_from_handle(self, width: int, height: int, anchor: str) -> bool:
        self.confirm_pending_edits()
        try:
            changed = self.document_controller.resize_canvas(width, height, anchor)
        except (ValueError, MemoryError) as error:
            self._show_error("No se pudo redimensionar el lienzo", error)
            return False
        if changed:
            self.refresh()
            self._status(f"Lienzo: {width} × {height} px")
        return bool(changed)

    def image_properties(self, values: dict[str, Any] | None = None) -> bool:
        if values is None:
            method = getattr(self.window, "valores_propiedades", None)
            if callable(method):
                values = method()
            else:
                from frontend.View.Dialogs.image_properties_dialog import ImagePropertiesDialog

                path = self.document.project_path or self.document.source_path
                try:
                    file_size = path.stat().st_size if path is not None else None
                except OSError:
                    file_size = None
                dialog = ImagePropertiesDialog(
                    self.document.width,
                    self.document.height,
                    self.window,
                    path,
                    file_size,
                    dpi=self.document.dpi,
                    transparent=not self.document.show_background,
                    background=self.document.background_color,
                    modified=self._last_saved_text(path),
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return False
                values = dialog.valores()
        if not values:
            return False
        self.confirm_pending_edits()
        before = self.history.capture(self.document)
        try:
            changed = self.document.resize_canvas(
                int(values.get("width", self.document.width)),
                int(values.get("height", self.document.height)),
            )
            dpi = max(1, min(1200, int(values.get("dpi", self.document.dpi))))
            if dpi != self.document.dpi:
                self.document.dpi = dpi
                self.document.invalidate()
                changed = True
            if bool(values.get("transparent", False)):
                changed = self.document.set_transparent_background() or changed
            else:
                changed = self.document.set_background_color(QColor(values.get("background", "white"))) or changed
            if bool(values.get("black_white", False)):
                # Se convierte todo el dibujo a blanco y negro sin grises.
                DocumentService(HistoryService()).apply_filter(self.document, "black_white", all_layers=True)
                if self.document.show_background:
                    gray = QColor(self.document.background_color).lightness()
                    self.document.background_color = QColor("white" if gray >= 128 else "black")
                changed = True
            if changed:
                self.document_controller.commit_change(before, "Propiedades de imagen")
                self.refresh()
            return bool(changed)
        except Exception as error:
            before.restore(self.document)
            self._show_error("No se pudieron cambiar las propiedades", error)
            return False

    propiedades = image_properties

    @staticmethod
    def _last_saved_text(path: Path | None) -> str:
        if path is None:
            return ""
        try:
            from datetime import datetime

            return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        except OSError:
            return ""

    def rotate_right(self) -> bool:
        if self.selection_controller.has_selection():
            changed = self.selection_controller.rotate(90.0)
            self.refresh()
            return changed
        return self._document_mutation(self.document_controller.rotate_right, "Imagen girada")

    def rotate_left(self) -> bool:
        if self.selection_controller.has_selection():
            changed = self.selection_controller.rotate(-90.0)
            self.refresh()
            return changed
        return self._document_mutation(self.document_controller.rotate_left, "Imagen girada")

    def rotate_180(self) -> bool:
        if self.selection_controller.has_selection():
            changed = self.selection_controller.rotate(180.0)
            self.refresh()
            return changed
        return self._document_mutation(self.document_controller.rotate_180, "Imagen girada")

    def rotate_free(self, degrees: float | None = None, expand: bool = True) -> bool:
        if degrees is None:
            if QApplication.instance() is None or not hasattr(self.window, "winId"):
                return False
            degrees, accepted = QInputDialog.getDouble(
                self.window,
                "Girar un ángulo",
                "Ángulo en grados:",
                0.0,
                -359.9,
                359.9,
                1,
            )
            if not accepted:
                return False
        if self.selection_controller.has_selection():
            changed = self.selection_controller.rotate(float(degrees))
            self.refresh()
            return changed
        return self._document_mutation(
            lambda: self.document_controller.rotate(float(degrees), bool(expand)),
            "Imagen girada",
        )

    def flip_horizontal(self) -> bool:
        if self.selection_controller.has_selection():
            changed = self.selection_controller.flip(horizontal=True)
            self.refresh()
            return changed
        return self._document_mutation(self.document_controller.flip_horizontal, "Imagen volteada")

    def flip_vertical(self) -> bool:
        if self.selection_controller.has_selection():
            changed = self.selection_controller.flip(horizontal=False)
            self.refresh()
            return changed
        return self._document_mutation(self.document_controller.flip_vertical, "Imagen volteada")

    def apply_filter(self, name: str) -> bool:
        normalized = str(name).lower().removeprefix("filter_")
        if self.selection_controller.has_selection():
            if self._editor_visible():
                self.confirm_text()
            changed = self.selection_controller.apply_filter(normalized)
            self.refresh()
            return changed
        return self._document_mutation(
            lambda: self.document_controller.apply_filter(normalized),
            "Filtro aplicado",
        )

    # ------------------------------------------------------------------
    # Vista, preferencias e impresión
    def _save_setting(self, key: str, value: Any) -> None:
        try:
            self.settings_service.cambiar(key, value)
        except OSError as error:
            self._show_error("No se pudieron guardar las preferencias", error)

    def _checked_action(self, action_id: str, fallback: bool = False) -> bool:
        action = getattr(self.window, "acciones", {}).get(action_id)
        method = getattr(action, "isChecked", None)
        return bool(method()) if callable(method) else bool(fallback)

    def set_grid_visible(self, visible: bool) -> None:
        self._call_optional(getattr(self.window, "canvas", None), "set_grid_visible", bool(visible))
        self._set_action_checked("toggle_grid", visible)
        if not self._applying_settings:
            self._save_setting("mostrar_cuadricula", bool(visible))

    def set_rulers_visible(self, visible: bool) -> None:
        self._call_optional(getattr(self.window, "canvas", None), "set_rulers_visible", bool(visible))
        self._set_action_checked("toggle_rulers", visible)
        if not self._applying_settings:
            self._save_setting("mostrar_regla", bool(visible))

    def set_layers_visible(self, visible: bool) -> None:
        self._call_optional(self.window, "mostrar_capas", bool(visible))
        if not self._applying_settings:
            self._save_setting("mostrar_panel_capas", bool(visible))

    def set_statusbar_visible(self, visible: bool) -> None:
        self._call_optional(self.window, "mostrar_barra_estado", bool(visible))
        if not self._applying_settings:
            self._save_setting("mostrar_barra_estado", bool(visible))

    def set_ribbon_visible(self, visible: bool) -> None:
        self._call_optional(self.window, "mostrar_ribbon", bool(visible))

    def _set_action_checked(self, action_id: str, checked: bool) -> None:
        action = getattr(self.window, "acciones", {}).get(action_id)
        if action is not None and hasattr(action, "setChecked"):
            action.setChecked(bool(checked))

    def set_dark_theme(self, dark: bool) -> None:
        self.set_theme_mode("oscuro" if dark else "claro")

    @staticmethod
    def _system_prefers_dark() -> bool:
        app = QGuiApplication.instance()
        if app is None:
            return False
        try:
            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:
            return QGuiApplication.palette().window().color().lightness() < 128

    def set_theme_mode(self, mode: str) -> None:
        """Tema «claro», «oscuro» o «sistema»."""

        mode = mode if mode in {"claro", "oscuro", "sistema"} else "sistema"
        self._theme_mode = mode
        dark = mode == "oscuro" or (mode == "sistema" and self._system_prefers_dark())
        self._call_optional(self.window, "set_dark_theme", dark)
        if not self._applying_settings:
            self._save_setting("tema", mode)

    def _system_theme_changed(self, *args: Any) -> None:
        if self._theme_mode == "sistema":
            self.set_theme_mode("sistema")

    def show_settings(self) -> bool:
        from frontend.View.Dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self._theme_mode, APP_VERSION, self.window)
        dialog.temaCambiado.connect(lambda value: self._safe_slot(self.set_theme_mode, value))
        dialog.acercaDeSolicitado.connect(lambda: self._safe_slot(self.show_about))
        dialog.exec()
        return True

    def set_full_screen(self, enabled: bool) -> None:
        self._full_screen = bool(enabled)
        self._call_optional(self.window, "set_full_screen", self._full_screen)

    def _apply_saved_settings(self) -> None:
        self._applying_settings = True
        try:
            self.set_grid_visible(bool(self.settings_service.obtener("mostrar_cuadricula", False)))
            self.set_rulers_visible(bool(self.settings_service.obtener("mostrar_regla", False)))
            self.set_layers_visible(bool(self.settings_service.obtener("mostrar_panel_capas", False)))
            self.set_statusbar_visible(bool(self.settings_service.obtener("mostrar_barra_estado", True)))
            theme = str(self.settings_service.obtener("tema", "sistema"))
            self.set_theme_mode(theme)
            hints = QGuiApplication.styleHints() if QGuiApplication.instance() is not None else None
            signal = getattr(hints, "colorSchemeChanged", None)
            if signal is not None:
                signal.connect(lambda *args: self._safe_slot(self._system_theme_changed))
            colors = getattr(getattr(self.window, "ribbon", None), "colores", None)
            self._call_optional(
                colors,
                "set_colores_personalizados",
                list(self.settings_service.obtener("colores_personalizados", [])),
            )
            self._load_tool_size_prefs()
            self.set_separate_drawing(bool(self.settings_service.obtener("dibujo_en_capa_aparte", True)))
            self._call_optional(self.window, "set_save_formats", writable_formats())
            self._call_optional(self.window, "restaurar_estado_ventana", dict(self.settings_service.obtener("ventana", {})))
            self.set_zoom(int(self.settings_service.obtener("zoom", 100)))
            self._call_optional(
                self.window,
                ("set_recent_files", "actualizar_recientes"),
                list(self.settings_service.obtener("archivos_recientes", [])),
            )
        finally:
            self._applying_settings = False

    def print_document(self) -> bool:
        self.confirm_pending_edits()
        try:
            return bool(self.print_service.imprimir(self.document, self.window))
        except Exception as error:
            self._show_error("No se pudo imprimir", error)
            return False

    def print_preview(self) -> bool:
        self.confirm_pending_edits()
        try:
            self.print_service.vista_previa(self.document, self.window)
            return True
        except Exception as error:
            self._show_error("No se pudo mostrar la vista previa", error)
            return False

    def page_setup(self) -> bool:
        try:
            return bool(self.print_service.configurar_pagina(self.window))
        except Exception as error:
            self._show_error("No se pudo configurar la página", error)
            return False

    def set_as_wallpaper(self, mode: str) -> bool:
        self.confirm_pending_edits()
        if self.document.modified or (self.document.project_path is None and self.document.source_path is None):
            ask = getattr(self.window, "confirmar", None)
            message = "Se usará la imagen tal como se ve ahora en el lienzo como fondo de escritorio."
            if callable(ask) and not ask("Establecer como fondo de escritorio", message):
                return False
        try:
            self.wallpaper_service.apply(self.document.composite(True), mode)
        except Exception as error:
            self._show_error("No se pudo establecer el fondo de escritorio", error)
            return False
        self._status("Fondo de escritorio actualizado")
        return True

    def _custom_colors_changed(self, colors: list[str]) -> None:
        self._save_setting("colores_personalizados", list(colors))

    def edit_colors(self) -> bool:
        ribbon_colors = getattr(getattr(self.window, "ribbon", None), "colores", None)
        target = str(getattr(ribbon_colors, "color_activo", "primario"))
        settings = self.document.tool_settings
        initial = settings.secondary_color if target == "secundario" else settings.primary_color
        method = getattr(self.window, "seleccionar_color_personalizado", None)
        if callable(method):
            color = QColor(method(initial))
        else:
            from frontend.View.Dialogs.edit_colors_dialog import EditColorsDialog

            dialog = EditColorsDialog(initial, self.window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            color = dialog.color_seleccionado()
        if not color.isValid():
            return False
        # Se aplica el color al color activo y se guarda en la fila personalizada.
        if target == "secundario":
            self.set_secondary_color(color)
        else:
            self.set_primary_color(color)
        self._call_optional(ribbon_colors, "agregar_color_personalizado", color)
        self.refresh()
        return True

    def show_about(self) -> bool:
        from frontend.View.Dialogs.about_dialog import AboutDialog

        AboutDialog(self.window, APP_VERSION).exec()
        return True

    def show_shortcuts(self) -> bool:
        filas = (
            ("Ctrl+N", "Nuevo"),
            ("Ctrl+O", "Abrir"),
            ("Ctrl+S", "Guardar"),
            ("Ctrl+Mayús+S", "Guardar como"),
            ("F12", "Guardar en otros formatos"),
            ("Ctrl+P", "Imprimir"),
            ("Ctrl+E", "Propiedades de imagen"),
            ("Ctrl+Z / Ctrl+Y", "Deshacer / Rehacer"),
            ("Ctrl+X / Ctrl+C / Ctrl+V", "Cortar / Copiar / Pegar"),
            ("Ctrl+A", "Seleccionar todo"),
            ("Supr", "Eliminar selección o forma"),
            ("Esc", "Cancelar selección o terminar forma"),
            ("Flechas (Mayús)", "Mover la selección o forma 1 px (10 px)"),
            ("Ctrl+arrastrar", "Duplicar la selección"),
            ("Mayús+arrastrar", "Cuadrado, círculo o línea a 45°"),
            ("Ctrl+W", "Cambiar tamaño y sesgar"),
            ("Ctrl+Mayús+X", "Recortar a la selección"),
            ("Ctrl+B / Ctrl+I / Ctrl+U", "Negrita / Cursiva / Subrayado (texto)"),
            ("Ctrl+Mayús+I", "Invertir color"),
            ("Ctrl+Mayús+N", "Nueva capa"),
            ("Ctrl++ / Ctrl+-", "Aumentar / reducir grosor"),
            ("Ctrl+RePág / Ctrl+AvPág", "Acercar / Alejar"),
            ("Ctrl+rueda del ratón", "Zoom en el cursor"),
            ("Ctrl+R / Ctrl+G", "Reglas / Líneas de cuadrícula"),
            ("F7", "Capas"),
            ("F11", "Pantalla completa"),
            ("Ctrl+F1", "Ocultar la cinta"),
            ("Clic derecho", "Dibujar con el color 2 (menú contextual con Seleccionar)"),
            ("Mantener pulsado (aerógrafo)", "Seguir rociando sin mover el ratón"),
            ("Esc / Clic", "Salir de la pantalla completa"),
        )
        texto = "<table>" + "".join(
            f"<tr><td style='padding-right:18px'><b>{atajo}</b></td><td>{accion}</td></tr>" for atajo, accion in filas
        ) + "</table>"
        self._show_info("Métodos abreviados de teclado", texto)
        return True

    # ------------------------------------------------------------------
    # Despacho de acciones de menú y cinta
    def execute_action(self, action_id: str) -> Any:
        action = str(action_id).strip().lower()
        if action.startswith("open_recent::"):
            return self.open_recent(str(action_id).split("::", 1)[1])
        simple: dict[str, Callable[[], Any]] = {
            "new": self.new_document,
            "open": self.open_document,
            "save": self.save_document,
            "save_project": self.save_project,
            "save_as": self.save_as,
            "save_as_png": lambda: self.save_as_format("png"),
            "save_as_jpeg": lambda: self.save_as_format("jpeg"),
            "save_as_bmp": lambda: self.save_as_format("bmp"),
            "save_as_gif": lambda: self.save_as_format("gif"),
            "save_as_other": lambda: self.save_as_format(None),
            "export": self.export_image,
            "import_file": self.paste_from_file,
            "paste_from": self.paste_from_file,
            "print": self.print_document,
            "page_setup": self.page_setup,
            "print_preview": self.print_preview,
            "wallpaper_fill": lambda: self.set_as_wallpaper("fill"),
            "wallpaper_tile": lambda: self.set_as_wallpaper("tile"),
            "wallpaper_center": lambda: self.set_as_wallpaper("center"),
            "undo": self.undo,
            "redo": self.redo,
            "cut": self.selection_controller.cut,
            "copy": self.selection_controller.copy,
            "paste": self.paste_image,
            "select_all": self.select_all,
            "invert_selection": self.invert_selection,
            "deselect": self.selection_controller.deselect,
            "delete_selection": self.delete_selection,
            "settings": self.show_settings,
            "zoom_in": self.zoom_in,
            "zoom_out": self.zoom_out,
            "zoom_100": lambda: self.set_zoom(100),
            "fit_window": self.fit_window,
            "size_increase": lambda: self.change_tool_size(1),
            "size_decrease": lambda: self.change_tool_size(-1),
            "crop": self.crop_selection,
            "resize_skew": self.resize_and_skew,
            "image_properties": self.image_properties,
            "rotate_right": self.rotate_right,
            "rotate_left": self.rotate_left,
            "rotate_180": self.rotate_180,
            "rotate_free": self.rotate_free,
            "flip_horizontal": self.flip_horizontal,
            "flip_vertical": self.flip_vertical,
            "layer_add": self.add_layer,
            "layer_delete": self.delete_layer,
            "layer_duplicate": self.duplicate_layer,
            "layer_move_up": lambda: self.move_active_layer(1),
            "layer_move_down": lambda: self.move_active_layer(-1),
            "layer_merge_down": self.merge_layer_down,
            "layer_rename": self.rename_active_layer,
            "filter_invert": lambda: self.apply_filter("invert"),
            "filter_grayscale": lambda: self.apply_filter("grayscale"),
            "filter_black_white": lambda: self.apply_filter("black_white"),
            "filter_sepia": lambda: self.apply_filter("sepia"),
            "filter_blur": lambda: self.apply_filter("blur"),
            "filter_sharpen": lambda: self.apply_filter("sharpen"),
            "filter_edge": lambda: self.apply_filter("edge"),
            "filter_coloring_book": lambda: self.apply_filter("coloring_book"),
            "edit_colors": self.edit_colors,
            "shortcuts": self.show_shortcuts,
            "about": self.show_about,
        }
        if action in simple:
            result = simple[action]()
            self.refresh()
            return result

        if action == "toggle_grid":
            return self.set_grid_visible(not bool(self.settings_service.obtener("mostrar_cuadricula", False)))
        if action == "toggle_rulers":
            return self.set_rulers_visible(not bool(self.settings_service.obtener("mostrar_regla", False)))
        if action == "separate_drawing":
            return self.set_separate_drawing(not self.separate_drawing)
        if action == "toggle_layers":
            return self.set_layers_visible(not bool(self.settings_service.obtener("mostrar_panel_capas", False)))
        if action == "toggle_statusbar":
            return self.set_statusbar_visible(not bool(self.settings_service.obtener("mostrar_barra_estado", True)))
        if action == "toggle_ribbon":
            # La acción está marcada cuando la cinta está oculta.
            ribbon = getattr(self.window, "ribbon", None)
            collapsed = bool(getattr(ribbon, "is_collapsed", lambda: False)())
            return self.set_ribbon_visible(not self._checked_action(action, not collapsed))
        if action == "toggle_theme":
            return self.set_dark_theme(self._checked_action(action, not bool(getattr(self.window, "tema_oscuro", False))))
        if action == "theme_dark":
            return self.set_dark_theme(True)
        if action == "theme_light":
            return self.set_dark_theme(False)
        if action == "fullscreen":
            return self.set_full_screen(self._checked_action(action, not self._full_screen))
        if action == "fullscreen_exit":
            return self.set_full_screen(False)
        if action == "exit":
            return self._call_optional(self.window, "close")

        self._status(f"Acción todavía no disponible: {action_id}")
        return False

    ejecutar_accion = execute_action

    def undo(self) -> bool:
        if self.tool_controller.has_pending_shape():
            # Al deshacer con una forma editable, simplemente se quita.
            self.tool_controller.discard_pending_shape()
            self.refresh()
            return True
        self.confirm_pending_edits()
        label = self.document_controller.undo()
        if label is None:
            return False
        self._status(f"Deshacer: {label}")
        self.refresh()
        return True

    def redo(self) -> bool:
        self.confirm_pending_edits()
        label = self.document_controller.redo()
        if label is None:
            return False
        self._status(f"Rehacer: {label}")
        self.refresh()
        return True

    # ------------------------------------------------------------------
    # Autoguardado y recuperación
    def _recovery_copy(self) -> Document:
        snapshot = self.history.capture(self.document)
        copy = Document(width=1, height=1)
        snapshot.restore(copy)
        copy.project_path = self.document.project_path
        copy.source_path = self.document.source_path
        copy.last_export_path = self.document.last_export_path
        if copy.selection.has_selection:
            commit_floating_selection(copy, "Confirmar selección para recuperación")

        if self._editor_visible():
            text = self._editor_text()
            rect = self._editor_rect()
            if text.strip() and not rect.isEmpty():
                TextService(HistoryService()).insert_text(
                    copy,
                    rect,
                    text,
                    copy.text_format,
                    self._text_layer_id,
                )
        copy.modified = self.document.modified or self.has_pending_edits()
        return copy

    def autosave(self) -> bool:
        if not self.document.modified and not self.has_pending_edits():
            return False
        try:
            self.recovery_service.save(self._recovery_copy(), display_name=self._document_name())
            self._status("Copia de recuperación actualizada")
            return True
        except Exception as error:
            self._show_error("No se pudo crear la copia de recuperación", error)
            return False

    autoguardar = autosave

    def offer_recovery(self) -> bool:
        try:
            # Una segunda ventana de MelfPaint no debe ofrecer ni borrar el
            # autoguardado que pertenece a una instancia que sigue viva.
            recoveries = self.recovery_service.list_stale_recoveries()
        except Exception as error:
            self._show_error("No se pudieron revisar las recuperaciones", error)
            return False
        if not recoveries:
            return False

        choice: Any = None
        method = getattr(self.window, "elegir_recuperacion", None)
        if callable(method):
            choice = method(recoveries)
        elif QApplication.instance() is not None and hasattr(self.window, "winId"):
            latest = recoveries[0]
            result = QMessageBox.question(
                self.window,
                "Recuperar documento",
                f"Se encontró una copia de «{latest.display_name}». ¿Desea recuperarla?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if result == QMessageBox.StandardButton.Yes:
                choice = latest
            elif result == QMessageBox.StandardButton.No:
                choice = "discard"

        if isinstance(choice, RecoveryMetadata):
            return self.recover(choice)
        if isinstance(choice, str) and choice not in {"discard", "cancel", "later", ""}:
            return self.recover(choice)
        if choice == "discard":
            # El diálogo sencillo presenta la copia más reciente; descartar
            # significa descartar esa copia, no todas las sesiones encontradas.
            self.recovery_service.discard(recoveries[0])
            return False
        return False

    def recover(self, recovery: RecoveryMetadata | str | None = None) -> bool:
        if not self.confirm_discard_changes():
            return False
        try:
            document = self.recovery_service.load(recovery)
        except Exception as error:
            self._show_error("No se pudo recuperar el documento", error)
            return False
        self._replace_document(document, clear_history=True)

        if isinstance(recovery, RecoveryMetadata):
            previous_session_id = recovery.session_id
        elif recovery is None:
            previous_session_id = self.recovery_service.session_id
        else:
            previous_session_id = str(recovery)

        # Primero se rearma el autoguardado para la sesión actual. Si el
        # proceso fallara justo después de recuperar, todavía quedará al menos
        # una copia válida en disco.
        rearmed = False
        try:
            self.recovery_service.save(document, display_name=self._document_name())
            rearmed = True
        except Exception as error:
            self._show_error("No se pudo rearmar la copia de recuperación", error)

        if rearmed and previous_session_id != self.recovery_service.session_id:
            try:
                self.recovery_service.discard(previous_session_id)
            except OSError as error:
                self._show_error("No se pudo limpiar la copia recuperada", error)
        self._status("Documento recuperado")
        return True

    recuperar = recover

    # ------------------------------------------------------------------
    # Cierre controlado
    def request_close(self, event: Any | None = None) -> bool:
        if not self.confirm_discard_changes():
            self._call_optional(event, "ignore")
            return False
        self.autosave_timer.stop()
        if self._size_save_timer.isActive():
            self._save_tool_sizes()
        estado = self._call_optional(self.window, "estado_ventana")
        if isinstance(estado, dict):
            self._save_setting("ventana", estado)
        try:
            self.recovery_service.discard()
        except OSError:
            pass
        self._call_optional(event, "accept")
        return True

    solicitar_cierre = request_close
