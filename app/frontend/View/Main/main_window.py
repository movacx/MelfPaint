from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.Config import metrics as M
from frontend.Config.settings import APP_NAME, icon_path
from frontend.Config.theme import stylesheet
from frontend.View.Canvas.canvas_view import CanvasView
from frontend.View.Components.ribbon_buttons import aplicar_tema_iconos, cargar_icono
from frontend.View.Components.fullscreen_viewer import VisorPantallaCompleta
from frontend.View.Components.text_editor_overlay import TextEditorOverlay
from frontend.View.Main.title_bar_view import PaintTitleBarView, WindowResizeHandle
from frontend.View.Panels.stroke_size_rail_view import StrokeSizeRailView
from frontend.View.Panels.layers_panel_view import LayersPanelView
from frontend.View.Panels.status_bar_view import StatusBarView
from frontend.View.Panels.text_toolbar_view import TextToolbarView
from frontend.View.Ribbon.ribbon_view import RibbonView


ACTION_ICON_PROPERTY = "melfpaintActionIcon"


def registrar_icono_accion(accion: QAction, nombre: str) -> None:
    accion.setProperty(ACTION_ICON_PROPERTY, nombre)
    accion.setIcon(cargar_icono(nombre))


class MainWindow(QMainWindow):
    accionSolicitada = Signal(str)
    archivoSoltado = Signal(str)
    cierreSolicitado = Signal(object)

    def __init__(self, document: Any, tool_controller: Any) -> None:
        super().__init__()
        self.documento = document
        self.controlador_herramientas = tool_controller
        self.tema_oscuro = False
        self.acciones: dict[str, QAction] = {}
        self._menus: dict[str, QMenu] = {}

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAcceptDrops(True)
        self.setMinimumSize(1000, 620)
        self.resize(1500, 900)
        self.setWindowIcon(QIcon(str(icon_path("melfpaint"))))
        self._crear_acciones()
        self._crear_menus()
        self._crear_interfaz()
        self._conectar_vistas()
        self.set_dark_theme(False)
        self.actualizar_documento()

    # ------------------------------------------------------------------
    # Construcción de acciones y menús
    def _crear_acciones(self) -> None:
        definiciones = (
            # Archivo
            ("new", "Nuevo", QKeySequence.StandardKey.New, "new"),
            ("open", "Abrir", QKeySequence.StandardKey.Open, "open"),
            ("import_file", "Desde un archivo…", None, "open"),
            ("save", "Guardar", QKeySequence.StandardKey.Save, "save"),
            ("save_as", "Guardar como…", QKeySequence("Ctrl+Shift+S"), "save"),
            ("save_as_png", "Imagen PNG", None, None),
            ("save_as_jpeg", "Imagen JPEG", None, None),
            ("save_as_bmp", "Imagen BMP", None, None),
            ("save_as_gif", "Imagen GIF", None, None),
            ("save_as_other", "Otros formatos…", QKeySequence("F12"), None),
            ("save_project", "Proyecto de MelfPaint (con capas)", None, None),
            ("print", "Imprimir…", QKeySequence.StandardKey.Print, None),
            ("page_setup", "Configurar página…", None, None),
            ("print_preview", "Vista previa de impresión", None, None),
            ("wallpaper_fill", "Rellenar", None, None),
            ("wallpaper_tile", "Mosaico", None, None),
            ("wallpaper_center", "Centrar", None, None),
            ("image_properties", "Propiedades de imagen", QKeySequence("Ctrl+E"), "image-properties"),
            ("about", f"Acerca de {APP_NAME}", None, None),
            ("exit", "Salir", QKeySequence("Alt+F4"), None),
            # Editar
            ("undo", "Deshacer", QKeySequence.StandardKey.Undo, "undo"),
            ("redo", "Rehacer", QKeySequence("Ctrl+Y"), "redo"),
            ("cut", "Cortar", QKeySequence.StandardKey.Cut, "cut"),
            ("copy", "Copiar", QKeySequence.StandardKey.Copy, "copy"),
            ("paste", "Pegar", QKeySequence.StandardKey.Paste, "paste"),
            ("paste_from", "Pegar desde…", None, "open"),
            ("select_all", "Seleccionar todo", QKeySequence.StandardKey.SelectAll, "select-all"),
            ("invert_selection", "Invertir selección", None, "invert-selection"),
            ("deselect", "Anular selección", None, None),
            ("delete_selection", "Eliminar selección", QKeySequence.StandardKey.Delete, "delete"),
            ("edit_colors", "Editar colores…", None, "palette"),
            # Ver
            ("zoom_in", "Acercar", QKeySequence("Ctrl+PgUp"), "zoom-in"),
            ("zoom_out", "Alejar", QKeySequence("Ctrl+PgDown"), "zoom-out"),
            ("zoom_100", "Zoom al 100 %", QKeySequence("Ctrl+0"), None),
            ("fit_window", "Ajustar a la ventana", QKeySequence("Ctrl+9"), "status-canvas"),
            ("size_increase", "Aumentar grosor", QKeySequence("Ctrl++"), None),
            ("size_decrease", "Reducir grosor", QKeySequence("Ctrl+-"), None),
            ("toggle_rulers", "Reglas", QKeySequence("Ctrl+R"), None),
            ("toggle_grid", "Líneas de cuadrícula", QKeySequence("Ctrl+G"), None),
            ("toggle_statusbar", "Barra de estado", None, None),
            ("toggle_layers", "Capas", QKeySequence("F7"), "layers"),
            ("separate_drawing", "Dibujar sobre imágenes en capa aparte", None, None),
            ("toggle_ribbon", "Ocultar la cinta", QKeySequence("Ctrl+F1"), None),
            ("toggle_theme", "Tema oscuro", None, None),
            ("fullscreen", "Pantalla completa", QKeySequence("F11"), None),
            ("settings", "Configuración", None, "settings"),
            # Imagen
            ("crop", "Recortar", QKeySequence("Ctrl+Shift+X"), "crop"),
            ("resize_skew", "Cambiar tamaño y sesgar…", QKeySequence("Ctrl+W"), "resize"),
            ("rotate_right", "Girar 90° a la derecha", None, "rotate-right"),
            ("rotate_left", "Girar 90° a la izquierda", None, "rotate-left"),
            ("rotate_180", "Girar 180°", None, "rotate"),
            ("rotate_free", "Girar un ángulo…", None, None),
            ("flip_horizontal", "Voltear horizontalmente", None, "flip-horizontal"),
            ("flip_vertical", "Voltear verticalmente", None, "flip-vertical"),
            # Capas
            ("layer_add", "Nueva capa", QKeySequence("Ctrl+Shift+N"), "add"),
            ("layer_delete", "Eliminar capa", QKeySequence("Ctrl+Shift+Delete"), "delete"),
            ("layer_duplicate", "Duplicar capa", QKeySequence("Ctrl+J"), "duplicate"),
            ("layer_move_up", "Subir capa", QKeySequence("Ctrl+]"), "move-up"),
            ("layer_move_down", "Bajar capa", QKeySequence("Ctrl+["), "move-down"),
            ("layer_merge_down", "Combinar hacia abajo", QKeySequence("Ctrl+M"), "merge-down"),
            ("layer_rename", "Cambiar nombre de capa…", QKeySequence("F2"), "rename"),
            # Filtros
            ("filter_invert", "Invertir color", QKeySequence("Ctrl+Shift+I"), None),
            ("filter_grayscale", "Escala de grises", None, None),
            ("filter_black_white", "Blanco y negro", None, None),
            ("filter_sepia", "Sepia", None, None),
            ("filter_blur", "Desenfocar", None, None),
            ("filter_sharpen", "Enfocar", None, None),
            ("filter_edge", "Detectar bordes", None, None),
            ("filter_coloring_book", "Libro para colorear", None, None),
            # Ayuda
            ("shortcuts", "Métodos abreviados de teclado", QKeySequence("F1"), None),
        )

        marcables = {
            "toggle_grid",
            "toggle_rulers",
            "toggle_layers",
            "separate_drawing",
            "toggle_statusbar",
            "toggle_ribbon",
            "toggle_theme",
            "fullscreen",
        }
        for action_id, texto, atajo, icono in definiciones:
            accion = QAction(texto, self)
            accion.setObjectName(f"action_{action_id}")
            accion.setCheckable(action_id in marcables)
            if icono:
                registrar_icono_accion(accion, icono)
            if atajo is not None:
                accion.setShortcut(atajo)
                accion.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            accion.triggered.connect(
                lambda checked=False, value=action_id: self.accionSolicitada.emit(value)
            )
            self.acciones[action_id] = accion
            self.addAction(accion)

        self.acciones["toggle_statusbar"].setChecked(True)
        self.acciones["save_as"].setShortcuts([QKeySequence("Ctrl+Shift+S")])
        self.acciones["redo"].setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.acciones["zoom_in"].setShortcuts([QKeySequence("Ctrl+PgUp"), QKeySequence("Ctrl+=")])
        self.acciones["size_increase"].setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+Shift+=")])

    def _crear_menus(self) -> None:
        barra = self.menuBar()
        barra.clear()
        barra.hide()

        archivo = QMenu("Archivo", self)
        self._menus["file"] = archivo
        self._agregar_acciones(archivo, "new", "open")
        importar = archivo.addMenu("Importar al lienzo")
        self._agregar_acciones(importar, "import_file")
        self.menu_recientes = archivo.addMenu("Imágenes recientes")
        self.menu_recientes.setEnabled(False)
        archivo.addSeparator()
        self._agregar_acciones(archivo, "save")
        guardar_como = archivo.addMenu("Guardar como")
        self._menus["save_as"] = guardar_como
        self._agregar_acciones(guardar_como, "save_as_png", "save_as_jpeg", "save_as_bmp", "save_as_gif", "save_as_other")
        guardar_como.addSeparator()
        self._agregar_acciones(guardar_como, "save_project")
        archivo.addSeparator()
        imprimir = archivo.addMenu(cargar_icono("print"), "Imprimir")
        self._agregar_acciones(imprimir, "print", "page_setup", "print_preview")
        fondo = archivo.addMenu(cargar_icono("wallpaper"), "Establecer como fondo de escritorio")
        self._agregar_acciones(fondo, "wallpaper_fill", "wallpaper_tile", "wallpaper_center")
        archivo.addSeparator()
        self._agregar_acciones(archivo, "image_properties")
        archivo.addSeparator()
        self._agregar_acciones(archivo, "about", "exit")

        editar = QMenu("Editar", self)
        self._menus["edit"] = editar
        self._agregar_acciones(editar, "undo", "redo")
        editar.addSeparator()
        self._agregar_acciones(editar, "cut", "copy", "paste", "paste_from")
        editar.addSeparator()
        self._agregar_acciones(editar, "select_all", "invert_selection", "delete_selection")
        editar.addSeparator()

        imagen = QMenu("Imagen", self)
        self._menus["image"] = imagen
        self._agregar_acciones(imagen, "crop", "resize_skew")
        imagen.addSeparator()
        self._agregar_acciones(imagen, "rotate_right", "rotate_left", "rotate_180", "rotate_free")
        imagen.addSeparator()
        self._agregar_acciones(imagen, "flip_vertical", "flip_horizontal")
        imagen.addSeparator()
        self._agregar_acciones(imagen, "image_properties")

        capas = QMenu("Capas", self)
        self._menus["layers"] = capas
        self._agregar_acciones(
            capas,
            "layer_add",
            "layer_duplicate",
            "layer_rename",
            "layer_move_up",
            "layer_move_down",
            "layer_merge_down",
            "layer_delete",
        )

        filtros = QMenu("Efectos", self)
        self._menus["filters"] = filtros
        self._agregar_acciones(
            filtros,
            "filter_invert",
            "filter_grayscale",
            "filter_black_white",
            "filter_sepia",
            "filter_blur",
            "filter_sharpen",
            "filter_edge",
            "filter_coloring_book",
        )
        editar.addMenu(imagen)
        editar.addMenu(capas)
        editar.addMenu(filtros)
        editar.addSeparator()
        self._agregar_acciones(editar, "edit_colors")

        ver = QMenu("Ver", self)
        self._menus["view"] = ver
        zoom = ver.addMenu("Zoom")
        self._agregar_acciones(zoom, "zoom_in", "zoom_out", "zoom_100", "fit_window")
        mostrar = ver.addMenu("Mostrar")
        self._agregar_acciones(mostrar, "toggle_rulers", "toggle_grid", "toggle_statusbar")
        ver.addSeparator()
        self._agregar_acciones(ver, "toggle_layers", "separate_drawing", "toggle_ribbon", "fullscreen")
        ver.addSeparator()
        self._agregar_acciones(ver, "toggle_theme", "settings", "shortcuts")

    def _agregar_acciones(self, menu: QMenu, *ids: str) -> None:
        for action_id in ids:
            menu.addAction(self.acciones[action_id])

    def mostrar_menu_seleccion(self, posicion: QPoint) -> None:
        """Menú contextual del lienzo para la herramienta Seleccionar."""

        menu = QMenu(self)
        self._agregar_acciones(menu, "cut", "copy", "paste")
        menu.addSeparator()
        self._agregar_acciones(menu, "select_all", "invert_selection", "delete_selection")
        menu.addSeparator()
        girar = menu.addMenu(cargar_icono("rotate", self.tema_oscuro), "Girar")
        self._agregar_acciones(girar, "rotate_right", "rotate_left", "rotate_180", "rotate_free")
        girar.addSeparator()
        self._agregar_acciones(girar, "flip_vertical", "flip_horizontal")
        self._agregar_acciones(menu, "resize_skew", "filter_invert")
        menu.addSeparator()
        self._agregar_acciones(menu, "crop")
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._menu_contextual = menu
        menu.popup(posicion)

    def set_save_formats(self, formats: set[str]) -> None:
        """Oculta los formatos que este sistema no puede escribir."""

        for action_id, formato in (
            ("save_as_png", "PNG"),
            ("save_as_jpeg", "JPEG"),
            ("save_as_bmp", "BMP"),
            ("save_as_gif", "GIF"),
        ):
            self.acciones[action_id].setVisible(formato in formats)

    def set_recent_files(self, paths: list[str]) -> None:
        self.menu_recientes.clear()
        for path in paths[:10]:
            ruta = str(path)
            accion = self.menu_recientes.addAction(Path(ruta).name)
            accion.setToolTip(ruta)
            accion.triggered.connect(
                lambda checked=False, value=ruta: self.accionSolicitada.emit(f"open_recent::{value}")
            )
        self.menu_recientes.setEnabled(bool(paths))

    actualizar_recientes = set_recent_files

    def _crear_interfaz(self) -> None:
        central = QWidget(self)
        layout_principal = QVBoxLayout(central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        self.title_bar = PaintTitleBarView(self)
        layout_principal.addWidget(self.title_bar)

        self.ribbon = RibbonView(central)
        self.ribbon.set_application_menus(self._menus)
        self.ribbon.bind_actions(self.acciones)
        layout_principal.addWidget(self.ribbon)

        self.workspace = QWidget(central)
        self.workspace.setObjectName("PaintWorkspace")
        fila_trabajo = QHBoxLayout(self.workspace)
        fila_trabajo.setContentsMargins(0, 0, 0, 0)
        fila_trabajo.setSpacing(0)

        self.scroll_area = QScrollArea(self.workspace)
        self.scroll_area.setObjectName("CanvasScrollArea")
        self.scroll_area.setWidgetResizable(False)
        # El lienzo queda anclado arriba a la izquierda.
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.canvas = CanvasView(self.documento, self.controlador_herramientas, self.scroll_area)
        self.scroll_area.setWidget(self.canvas)
        # Barras laterales (grosor libre y opacidad), a la izquierda del lienzo.
        self.stroke_size_rail = StrokeSizeRailView(self.workspace)
        self.tool_size_rail = self.stroke_size_rail
        self.rail_contenedor = QWidget(self.workspace)
        columna_rail = QVBoxLayout(self.rail_contenedor)
        columna_rail.setContentsMargins(10, 18, 4, 18)
        columna_rail.addStretch(1)
        columna_rail.addWidget(self.stroke_size_rail, 100, Qt.AlignmentFlag.AlignHCenter)
        columna_rail.addStretch(1)
        fila_trabajo.addWidget(self.rail_contenedor)
        self.rail_contenedor.setVisible(False)
        self.stroke_size_rail.visibilityChanged.connect(self.rail_contenedor.setVisible)
        fila_trabajo.addWidget(self.scroll_area, 1)

        self.layers_panel = LayersPanelView(self.documento, self.workspace)
        self.layers_panel.setVisible(False)
        fila_trabajo.addWidget(self.layers_panel)
        layout_principal.addWidget(self.workspace, 1)

        self.status_bar_paint = StatusBarView(central)
        layout_principal.addWidget(self.status_bar_paint)
        self.setCentralWidget(central)
        self._crear_manejadores_ventana()

        self.text_toolbar = TextToolbarView(self.workspace)
        self.aviso = QLabel(self.workspace)
        self.aviso.setObjectName("Toast")
        self.aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.aviso.hide()
        self._temporizador_aviso = QTimer(self)
        self._temporizador_aviso.setSingleShot(True)
        self._temporizador_aviso.timeout.connect(self.aviso.hide)
        self._reposicionar_superposiciones()

        self.text_editor = TextEditorOverlay(self.canvas)
        self.text_editor.geometriaCambiada.connect(lambda rect: self._actualizar_editor_texto())

    def _conectar_vistas(self) -> None:
        self.ribbon.accionSolicitada.connect(self.accionSolicitada.emit)
        self.canvas.punteroMovido.connect(self.status_bar_paint.set_pointer_position)
        self.canvas.punteroSalio.connect(self.status_bar_paint.clear_pointer_position)
        self.canvas.zoomCambiado.connect(self.status_bar_paint.set_zoom)
        self.canvas.zoomCambiado.connect(self._actualizar_editor_texto)
        self.status_bar_paint.zoomSolicitado.connect(self.canvas.set_zoom_percent)
        self.status_bar_paint.ajustarSolicitado.connect(
            lambda: self.accionSolicitada.emit("fit_window")
        )
        self.status_bar_paint.cuadriculaCambiada.connect(self.canvas.set_grid_visible)
        self.status_bar_paint.reglasCambiadas.connect(self.canvas.set_rulers_visible)
        self.canvas.zoomEnPuntoSolicitado.connect(self.zoom_en_punto)
        self.canvas.menuContextualSolicitado.connect(self.mostrar_menu_seleccion)

    # ------------------------------------------------------------------
    # API pasiva usada por ApplicationController
    def set_document(self, document: Any) -> None:
        self.documento = document
        self.canvas.set_document(document)
        self.layers_panel.set_document(document)
        self.actualizar_documento()

    def actualizar_documento(self) -> None:
        self.canvas.resize(self.canvas.sizeHint())
        self.canvas.updateGeometry()
        self.canvas.update()
        self.layers_panel.actualizar(self.documento)
        self.status_bar_paint.set_document_size(
            int(getattr(self.documento, "width", 0)),
            int(getattr(self.documento, "height", 0)),
        )

        self.actualizar_titulo()
        self._reposicionar_superposiciones()

    def mostrar_capas(self, visible: bool) -> None:
        self.layers_panel.setVisible(bool(visible))
        self.acciones["toggle_layers"].setChecked(bool(visible))
        QTimer.singleShot(0, self._reposicionar_superposiciones)

    def mostrar_barra_estado(self, visible: bool) -> None:
        self.status_bar_paint.setVisible(bool(visible))
        self.acciones["toggle_statusbar"].setChecked(bool(visible))

    def mostrar_ribbon(self, visible: bool) -> None:
        # La cinta se contrae y deja solo la barra de menús.
        self.ribbon.set_collapsed(not bool(visible))
        self.acciones["toggle_ribbon"].setChecked(not bool(visible))
        QTimer.singleShot(0, self._reposicionar_superposiciones)

    def set_dark_theme(self, dark: bool) -> None:
        self.tema_oscuro = bool(dark)
        self.setStyleSheet(stylesheet(self.tema_oscuro))
        aplicar_tema_iconos(self, self.tema_oscuro)
        for accion in self.findChildren(QAction):
            nombre = accion.property(ACTION_ICON_PROPERTY)
            if nombre:
                accion.setIcon(cargar_icono(str(nombre), self.tema_oscuro))
        self.canvas.set_dark_theme(self.tema_oscuro)
        self.ribbon.set_dark_theme(self.tema_oscuro)
        self.acciones["toggle_theme"].setChecked(self.tema_oscuro)

    def actualizar_titulo(self, nombre: str | None = None) -> None:
        if nombre is None:
            ruta = (
                getattr(self.documento, "project_path", None)
                or getattr(self.documento, "source_path", None)
                or getattr(self.documento, "file_path", None)
            )
            nombre = Path(ruta).name if ruta else "Sin título"
        marca = "*" if bool(getattr(self.documento, "modified", False)) else ""
        titulo = f"{marca}{nombre} - {APP_NAME}"
        self.setWindowTitle(titulo)
        self.title_bar.set_title(titulo)

    def set_full_screen(self, enabled: bool) -> None:
        """La pantalla completa muestra solo la imagen."""

        visor = getattr(self, "_visor_pantalla", None)
        if enabled:
            if visor is None:
                composite = getattr(self.documento, "composite", None)
                imagen = composite() if callable(composite) else None
                visor = VisorPantallaCompleta(imagen if imagen is not None else QImage(), self)
                visor.cerrado.connect(self._visor_cerrado)
                self._visor_pantalla = visor
                visor.showFullScreen()
        elif visor is not None:
            visor.close()
        self.acciones["fullscreen"].setChecked(bool(enabled))

    def _visor_cerrado(self) -> None:
        self._visor_pantalla = None
        self.acciones["fullscreen"].setChecked(False)
        self.accionSolicitada.emit("fullscreen_exit")

    def mostrar_pantalla_completa(self) -> None:
        self.set_full_screen(True)

    def salir_pantalla_completa(self) -> None:
        self.set_full_screen(False)

    def mostrar_aviso(self, texto: str, duracion_ms: int = 2600) -> None:
        """Aviso breve sobre el lienzo (por ejemplo «Fondo de escritorio actualizado»)."""

        texto = str(texto or "").strip()
        if not texto:
            return
        self.aviso.setText(texto)
        self.aviso.adjustSize()
        self.aviso.resize(self.aviso.width() + 32, 36)
        self._reposicionar_superposiciones()
        self.aviso.show()
        self.aviso.raise_()
        self._temporizador_aviso.start(duracion_ms)

    def zoom_en_punto(self, porcentaje: int, x: float, y: float, vx: float = -1.0, vy: float = -1.0) -> None:
        """Cambia el zoom manteniendo el punto (x, y) del documento en pantalla.

        Si no se indica posición en la ventana (vx, vy), el punto queda centrado.
        """

        self.canvas.set_zoom_percent(porcentaje)
        self.canvas.resize(self.canvas.sizeHint())
        destino = self.canvas.document_to_screen(QPointF(x, y))
        viewport = self.scroll_area.viewport()
        if vx < 0 or vy < 0:
            vx, vy = viewport.width() / 2, viewport.height() / 2
        self.scroll_area.horizontalScrollBar().setValue(round(destino.x() - vx))
        self.scroll_area.verticalScrollBar().setValue(round(destino.y() - vy))

    def estado_ventana(self) -> dict[str, object]:
        geometria = self.normalGeometry() if self.isMaximized() else self.geometry()
        return {
            "x": geometria.x(),
            "y": geometria.y(),
            "ancho": geometria.width(),
            "alto": geometria.height(),
            "maximizada": self.isMaximized(),
        }

    def restaurar_estado_ventana(self, estado: dict[str, object]) -> None:
        """La ventana vuelve a abrirse con el tamaño y la posición de la última vez."""

        if not estado:
            return
        ancho = int(estado.get("ancho", 0) or 0)
        alto = int(estado.get("alto", 0) or 0)
        pantalla = QApplication.primaryScreen()
        disponible = pantalla.availableGeometry() if pantalla is not None else QRect(0, 0, 1920, 1080)
        if ancho >= self.minimumWidth() and alto >= self.minimumHeight():
            self.resize(min(ancho, disponible.width()), min(alto, disponible.height()))
            x, y = int(estado.get("x", 0) or 0), int(estado.get("y", 0) or 0)
            if disponible.intersects(QRect(x, y, ancho, alto)):
                self.move(x, y)
        if bool(estado.get("maximizada", False)):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def tamano_lienzo_sugerido(self) -> QSize:
        """Hoja inicial: su borde derecho llega al final de la cinta y cabe en alto."""

        ancho_cinta = sum(grupo.width() for grupo in self.ribbon.grupos_visibles)
        viewport = self.scroll_area.viewport()
        ancho = min(ancho_cinta - M.CANVAS_MARGIN - 27, viewport.width() - 2 * M.CANVAS_MARGIN)
        alto = viewport.height() - M.CANVAS_MARGIN_TOP - M.CANVAS_MARGIN
        return QSize(max(320, ancho), max(240, alto))

    def area_visible_documento(self) -> QRect:
        """Rectángulo del documento que se ve ahora (para pegar donde mira el usuario)."""

        viewport = self.scroll_area.viewport()
        origen = self.canvas.mapFrom(viewport, QPoint(0, 0))
        esquina = self.canvas.mapFrom(viewport, QPoint(viewport.width(), viewport.height()))
        a = self.canvas.screen_to_document(origen)
        b = self.canvas.screen_to_document(esquina)
        return QRect(QPoint(int(a.x()), int(a.y())), QPoint(int(b.x()), int(b.y()))).normalized()

    def preguntar_ampliar_lienzo(self) -> bool | None:
        respuesta = QMessageBox.question(
            self,
            APP_NAME,
            "La imagen del Portapapeles es más grande que el lienzo.\n¿Desea ampliar el lienzo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if respuesta == QMessageBox.StandardButton.Cancel:
            return None
        return respuesta == QMessageBox.StandardButton.Yes

    def confirmar(self, titulo: str, mensaje: str) -> bool:
        respuesta = QMessageBox.question(
            self,
            titulo,
            mensaje,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        return respuesta == QMessageBox.StandardButton.Ok

    def _actualizar_editor_texto(self, *args) -> None:
        if not self.text_editor.isVisible():
            return
        rectangulo_documento = getattr(self.text_editor, "rectangulo_documento", None)
        if rectangulo_documento is None or rectangulo_documento.isEmpty():
            return
        rectangulo = self.canvas.document_rect_to_screen(rectangulo_documento)
        self.text_editor.establecer_geometria(rectangulo, self.canvas.zoom)

    def _reposicionar_superposiciones(self) -> None:
        if not hasattr(self, "workspace") or not hasattr(self, "scroll_area"):
            return
        ancho_viewport = max(1, self.scroll_area.width())
        x_toolbar = self.scroll_area.x() + max(
            8,
            (ancho_viewport - self.text_toolbar.width()) // 2,
        )
        self.text_toolbar.move(x_toolbar, 6)
        self.text_toolbar.raise_()
        if hasattr(self, "aviso"):
            self.aviso.move(
                self.scroll_area.x() + (ancho_viewport - self.aviso.width()) // 2,
                self.scroll_area.height() - self.aviso.height() - 24,
            )

    def _crear_manejadores_ventana(self) -> None:
        izquierda = Qt.Edge.LeftEdge
        derecha = Qt.Edge.RightEdge
        arriba = Qt.Edge.TopEdge
        abajo = Qt.Edge.BottomEdge
        self._manejadores_ventana = {
            "left": WindowResizeHandle(self, izquierda, Qt.CursorShape.SizeHorCursor),
            "right": WindowResizeHandle(self, derecha, Qt.CursorShape.SizeHorCursor),
            "top": WindowResizeHandle(self, arriba, Qt.CursorShape.SizeVerCursor),
            "bottom": WindowResizeHandle(self, abajo, Qt.CursorShape.SizeVerCursor),
            "top_left": WindowResizeHandle(
                self,
                izquierda | arriba,
                Qt.CursorShape.SizeFDiagCursor,
            ),
            "top_right": WindowResizeHandle(
                self,
                derecha | arriba,
                Qt.CursorShape.SizeBDiagCursor,
            ),
            "bottom_left": WindowResizeHandle(
                self,
                izquierda | abajo,
                Qt.CursorShape.SizeBDiagCursor,
            ),
            "bottom_right": WindowResizeHandle(
                self,
                derecha | abajo,
                Qt.CursorShape.SizeFDiagCursor,
            ),
        }
        self._reposicionar_manejadores_ventana()

    def _reposicionar_manejadores_ventana(self) -> None:
        if not hasattr(self, "_manejadores_ventana"):
            return
        grosor = 5
        esquina = 9
        ancho, alto = self.width(), self.height()
        geometrias = {
            "left": (0, esquina, grosor, max(0, alto - (esquina * 2))),
            "right": (max(0, ancho - grosor), esquina, grosor, max(0, alto - (esquina * 2))),
            "top": (esquina, 0, max(0, ancho - (esquina * 2)), grosor),
            "bottom": (esquina, max(0, alto - grosor), max(0, ancho - (esquina * 2)), grosor),
            "top_left": (0, 0, esquina, esquina),
            "top_right": (max(0, ancho - esquina), 0, esquina, esquina),
            "bottom_left": (0, max(0, alto - esquina), esquina, esquina),
            "bottom_right": (max(0, ancho - esquina), max(0, alto - esquina), esquina, esquina),
        }
        habilitados = not self.isMaximized() and not self.isFullScreen()
        for nombre, manejador in self._manejadores_ventana.items():
            manejador.setGeometry(*geometrias[nombre])
            manejador.setVisible(habilitados)
            if habilitados:
                manejador.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposicionar_superposiciones()
        self._reposicionar_manejadores_ventana()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.title_bar.actualizar_estado()
            self._reposicionar_manejadores_ventana()

    # ------------------------------------------------------------------
    # Eventos delegados
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.archivoSoltado.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.cierreSolicitado.emit(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.accionSolicitada.emit("fullscreen_exit")
            event.accept()
            return
        super().keyPressEvent(event)
