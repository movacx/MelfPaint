from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QEnterEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from backend.Service.Drawing.shape_tools import PAINT_SHAPE_ORDER, PAINT_SHAPES
from frontend.Config import metrics as M
from frontend.Config.theme import colors
from frontend.View.Components.color_swatch import MuestraColor
from frontend.View.Components.ribbon_buttons import (
    BotonPaint,
    GrupoRibbon,
    cargar_icono,
    tema_oscuro_activo,
)
from frontend.View.Components.shape_glyph import GlifoForma


def _accion(menu: QMenu, texto: str, icono: str | None = None, callback=None, checkable: bool = False) -> QAction:
    accion = QAction(texto, menu)
    # Las opciones marcables muestran una marca y no un icono.
    if icono and not checkable:
        accion.setProperty("melfpaintActionIcon", icono)
        accion.setIcon(cargar_icono(icono, tema_oscuro_activo()))
    accion.setCheckable(checkable)
    if callback is not None:
        accion.triggered.connect(callback)
    menu.addAction(accion)
    return accion


def _ayuda(titulo: str, texto: str, atajo: str = "") -> str:
    """Información sobre herramientas con título y descripción."""

    encabezado = f"<b>{titulo}</b>" + (f" ({atajo})" if atajo else "")
    return f"<p style='white-space:pre-wrap; margin:0'>{encabezado}<br>{texto}</p>"


DESCRIPCIONES = {
    "paste": _ayuda("Pegar", "Pega el contenido del Portapapeles en el lienzo.", "Ctrl+V"),
    "cut": _ayuda("Cortar", "Corta la selección y la coloca en el Portapapeles.", "Ctrl+X"),
    "copy": _ayuda("Copiar", "Copia la selección en el Portapapeles.", "Ctrl+C"),
    "select": _ayuda("Seleccionar", "Selecciona una parte de la imagen para moverla, copiarla o editarla."),
    "crop": _ayuda("Recortar", "Recorta la imagen para que solo quede la selección.", "Ctrl+Mayús+X"),
    "resize": _ayuda("Cambiar tamaño y sesgar", "Cambia el tamaño de la imagen o de la selección y la inclina.", "Ctrl+W"),
    "rotate": _ayuda("Girar", "Gira la imagen o la selección."),
    "flip": _ayuda("Voltear", "Voltea la imagen o la selección en horizontal o en vertical."),
    "pencil": _ayuda("Lápiz", "Dibuja una línea a mano alzada con el grosor seleccionado."),
    "fill": _ayuda("Relleno con color", "Haga clic en un área del lienzo para rellenarla con el color 1, o con el color 2 usando el clic derecho."),
    "text": _ayuda("Texto", "Agrega texto a la imagen."),
    "eraser": _ayuda("Borrador", "Borra parte de la imagen. Con el clic derecho cambia el color 1 por el color 2."),
    "eyedropper": _ayuda("Selector de color", "Toma un color de la imagen y lo usa para dibujar."),
    "magnifier": _ayuda("Lupa", "Acerca con un clic y aleja con el clic derecho."),
    "brush": _ayuda("Pinceles", "Dibuja con distintos tipos de pincel."),
    "outline": _ayuda("Contorno de forma", "Elige el material del contorno de la forma."),
    "shape-fill": _ayuda("Relleno de forma", "Elige el material del relleno de la forma (usa el color 2)."),
    "layers": _ayuda("Capas", "Muestra u oculta el panel de capas.", "F7"),
    "size": _ayuda("Tamaño", "Elige el grosor de la herramienta seleccionada.", "Ctrl++ / Ctrl+-"),
    "edit-colors": _ayuda("Editar colores", "Elige cualquier color con el selector de color."),
}


# ----------------------------------------------------------------------
# Grupos de la cinta. Las coordenadas están en metrics.
class ClipboardGroupView(GrupoRibbon):
    accionSolicitada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Portapapeles", M.GROUP_CLIPBOARD, parent)
        menu = QMenu("Pegar", self)
        _accion(menu, "Pegar", "paste", lambda: self.accionSolicitada.emit("paste"))
        _accion(menu, "Pegar desde", "open", lambda: self.accionSolicitada.emit("paste_from"))
        self.btn_pegar = BotonPaint(
            "Pegar (Ctrl+V)", "paste", 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, "below", menu, split=True,
            callback=lambda: self.accionSolicitada.emit("paste"),
        )
        self.btn_cortar = BotonPaint("Cortar (Ctrl+X)", "cut", callback=lambda: self.accionSolicitada.emit("cut"))
        self.btn_copiar = BotonPaint("Copiar (Ctrl+C)", "copy", callback=lambda: self.accionSolicitada.emit("copy"))
        self.poner(self.btn_pegar, 15, M.RIBBON_BIG_TOP)
        self.poner(self.btn_cortar, 77, M.RIBBON_ROW_1 - M.BUTTON // 2)
        self.poner(self.btn_copiar, 77, M.RIBBON_ROW_2 - M.BUTTON // 2)

    def set_seleccion_activa(self, activa: bool) -> None:
        self.btn_cortar.setEnabled(activa)
        self.btn_copiar.setEnabled(activa)


class ImageGroupView(GrupoRibbon):
    herramientaSeleccionada = Signal(str)
    accionSolicitada = Signal(str)
    seleccionTransparenteCambiada = Signal(bool)

    FORMAS_SELECCION = (("select", "Selección rectangular", "select"), ("freeform_select", "Selección de forma libre", "free-select"))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Imagen", M.GROUP_IMAGE, parent)
        self._forma = "select"

        menu = QMenu("Seleccionar", self)
        grupo = QActionGroup(menu)
        self.acciones_forma: dict[str, QAction] = {}
        for tool_id, texto, icono in self.FORMAS_SELECCION:
            accion = _accion(menu, texto, icono, lambda checked=False, value=tool_id: self._elegir(value), checkable=True)
            grupo.addAction(accion)
            self.acciones_forma[tool_id] = accion
        self.acciones_forma["select"].setChecked(True)
        menu.addSeparator()
        _accion(menu, "Seleccionar todo", "select-all", lambda: self.accionSolicitada.emit("select_all"))
        _accion(menu, "Invertir selección", "invert-selection", lambda: self.accionSolicitada.emit("invert_selection"))
        _accion(menu, "Eliminar", "delete", lambda: self.accionSolicitada.emit("delete_selection"))
        menu.addSeparator()
        self.accion_transparente = _accion(menu, "Selección transparente", "transparent", checkable=True)
        self.accion_transparente.toggled.connect(self.seleccionTransparenteCambiada.emit)
        self.btn_seleccionar = BotonPaint(
            "Seleccionar", "select", 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, "below", menu, split=True,
            callback=lambda: self._elegir(self._forma),
        )
        self.btn_seleccionar.setCheckable(True)

        self.btn_recortar = BotonPaint("Recortar (Ctrl+Mayús+X)", "crop", callback=lambda: self.accionSolicitada.emit("crop"))
        self.btn_tamano = BotonPaint("Cambiar tamaño y sesgar (Ctrl+W)", "resize", callback=lambda: self.accionSolicitada.emit("resize_skew"))

        menu_girar = QMenu("Girar", self)
        _accion(menu_girar, "Girar 90° a la derecha", "rotate-right", lambda: self.accionSolicitada.emit("rotate_right"))
        _accion(menu_girar, "Girar 90° a la izquierda", "rotate-left", lambda: self.accionSolicitada.emit("rotate_left"))
        _accion(menu_girar, "Girar 180°", "rotate-180", lambda: self.accionSolicitada.emit("rotate_180"))
        _accion(menu_girar, "Girar un ángulo…", "rotate", lambda: self.accionSolicitada.emit("rotate_free"))
        self.btn_girar = BotonPaint("Girar", "rotate", 54, M.BUTTON, M.ICON, "right", menu_girar)

        menu_voltear = QMenu("Voltear", self)
        _accion(menu_voltear, "Voltear verticalmente", "flip-vertical", lambda: self.accionSolicitada.emit("flip_vertical"))
        _accion(menu_voltear, "Voltear horizontalmente", "flip-horizontal", lambda: self.accionSolicitada.emit("flip_horizontal"))
        self.btn_voltear = BotonPaint("Voltear", "flip", 54, M.BUTTON, M.ICON, "right", menu_voltear)

        self.poner(self.btn_seleccionar, 12, M.RIBBON_BIG_TOP)
        self.poner(self.btn_recortar, 69, M.RIBBON_ROW_1 - M.BUTTON // 2)
        self.poner(self.btn_tamano, 69, M.RIBBON_ROW_2 - M.BUTTON // 2)
        self.poner(self.btn_girar, 119, M.RIBBON_ROW_1 - M.BUTTON // 2)
        self.poner(self.btn_voltear, 119, M.RIBBON_ROW_2 - M.BUTTON // 2)

    def _elegir(self, tool_id: str) -> None:
        self.herramientaSeleccionada.emit(tool_id)

    def set_herramienta_activa(self, tool_id: str) -> None:
        tool_id = "freeform_select" if tool_id == "free_select" else str(tool_id)
        activa = tool_id in self.acciones_forma
        self.btn_seleccionar.setChecked(activa)
        if activa:
            self._forma = tool_id
            self.acciones_forma[tool_id].setChecked(True)
            icono = dict((clave, nombre) for clave, _texto, nombre in self.FORMAS_SELECCION)[tool_id]
            self.btn_seleccionar.set_icono(icono)

    def set_transparente(self, enabled: bool) -> None:
        self.accion_transparente.blockSignals(True)
        self.accion_transparente.setChecked(bool(enabled))
        self.accion_transparente.blockSignals(False)

    def set_recorte_habilitado(self, enabled: bool) -> None:
        self.btn_recortar.setEnabled(bool(enabled))


class ToolsGroupView(GrupoRibbon):
    herramientaSeleccionada = Signal(str)

    HERRAMIENTAS = (
        ("pencil", "Lápiz", "pencil"),
        ("fill", "Relleno con color", "fill"),
        ("text", "Texto", "text"),
        ("eraser", "Borrador", "eraser"),
        ("eyedropper", "Selector de color", "eyedropper"),
        ("magnifier", "Lupa", "magnifier"),
    )
    ALIAS = {"picker": "eyedropper", "color_picker": "eyedropper", "zoom": "magnifier", "bucket": "fill"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Herramientas", M.GROUP_TOOLS, parent)
        self.botones: dict[str, BotonPaint] = {}
        for indice, (tool_id, texto, icono) in enumerate(self.HERRAMIENTAS):
            boton = BotonPaint(texto, icono, callback=lambda checked=False, value=tool_id: self.herramientaSeleccionada.emit(value))
            boton.setCheckable(True)
            self.botones[tool_id] = boton
            self.poner(boton, 17 + (indice % 3) * 50, (M.RIBBON_ROW_1 - M.BUTTON // 2) + (indice // 3) * (M.RIBBON_ROW_2 - M.RIBBON_ROW_1))

    def set_herramienta_activa(self, tool_id: str) -> None:
        tool_id = self.ALIAS.get(str(tool_id), str(tool_id))
        for clave, boton in self.botones.items():
            boton.setChecked(clave == tool_id)


class BrushesGroupView(GrupoRibbon):
    pincelSeleccionado = Signal(str)

    PINCELES = (
        ("round", "Pincel", "brush"),
        ("calligraphy", "Pincel de caligrafía", "calligraphy"),
        ("calligraphy_pen", "Pluma de caligrafía", "calligraphy-pen"),
        ("airbrush", "Aerógrafo", "spray"),
        ("oil", "Pincel al óleo", "oil-brush"),
        ("crayon", "Crayón", "crayon"),
        ("marker", "Marcador", "marker"),
        ("natural_pencil", "Lápiz natural", "natural-pencil"),
        ("watercolor", "Pincel de acuarela", "watercolor"),
    )
    ALIAS = {"brush": "round", "spray": "airbrush"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Pinceles", M.GROUP_BRUSHES, parent)
        self._pincel_activo = "round"
        menu = QMenu("Pinceles", self)
        grupo = QActionGroup(menu)
        self.botones: dict[str, QAction] = {}
        for brush_id, texto, icono in self.PINCELES:
            accion = _accion(menu, texto, icono, lambda checked=False, value=brush_id: self._seleccionar(value), checkable=True)
            grupo.addAction(accion)
            self.botones[brush_id] = accion
        self.btn_pincel = BotonPaint(
            "Pinceles", "brush", 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, "below", menu, split=True,
            callback=lambda: self.pincelSeleccionado.emit(self._pincel_activo),
        )
        self.btn_pincel.setCheckable(True)
        self.poner(self.btn_pincel, 19, M.RIBBON_BIG_TOP)
        self.botones["round"].setChecked(True)

    def _seleccionar(self, brush_id: str) -> None:
        self.set_pincel_activo(brush_id)
        self.pincelSeleccionado.emit(brush_id)

    def set_pincel_activo(self, brush_id: str) -> None:
        brush_id = self.ALIAS.get(str(brush_id), str(brush_id))
        accion = self.botones.get(brush_id)
        if accion is None:
            return
        self._pincel_activo = brush_id
        accion.setChecked(True)
        # El botón muestra el pincel elegido.
        icono = dict((clave, nombre) for clave, _texto, nombre in self.PINCELES)[brush_id]
        self.btn_pincel.set_icono(icono)
        self.btn_pincel.setToolTip(_ayuda(f"Pinceles: {accion.text()}", "Dibuja con distintos tipos de pincel."))

    def set_activo(self, active: bool) -> None:
        self.btn_pincel.setChecked(bool(active))


class _GaleriaFormas(QFrame):
    """Recuadro de la galería con su indicador de desplazamiento."""

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(c["gallery_border"]), 1))
        painter.setBrush(QColor(c["gallery"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["scroll_thumb"]))
        painter.drawRoundedRect(QRectF(self.width() - 5, 15, 2.4, self.height() - 30), 1.2, 1.2)
        painter.end()


class ShapesGroupView(GrupoRibbon):
    formaSeleccionada = Signal(str)
    contornoCambiado = Signal(str)
    rellenoCambiado = Signal(str)

    ESTILOS = (
        ("solid", "Color sólido"),
        ("crayon", "Crayón"),
        ("marker", "Marcador"),
        ("oil", "Óleo"),
        ("natural_pencil", "Lápiz natural"),
        ("watercolor", "Acuarela"),
    )
    ALIAS = {
        "rect": "rectangle",
        "rounded_rect": "rounded_rectangle",
        "oval": "ellipse",
        "arrow": "right_arrow",
        "star": "star_5",
        "callout": "speech_callout",
        "bolt": "lightning",
        "cloud_callout": "thought_callout",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Formas", M.GROUP_SHAPES, parent)
        self.galeria = _GaleriaFormas(self)
        self.galeria.setObjectName("ShapeGallery")
        self.galeria.setFixedSize(242, M.SHAPE_CELL_HEIGHT * 3 + 6)
        self.poner(self.galeria, 17, 7)
        self.botones: dict[str, GlifoForma] = {}
        for indice, shape_id in enumerate(PAINT_SHAPE_ORDER):
            boton = GlifoForma(shape_id, PAINT_SHAPES[shape_id], self.galeria)
            boton.formaSeleccionada.connect(self.formaSeleccionada.emit)
            boton.move(10 + (indice % M.SHAPE_COLUMNS) * M.SHAPE_CELL_WIDTH, 3 + (indice // M.SHAPE_COLUMNS) * M.SHAPE_CELL_HEIGHT)
            self.botones[shape_id] = boton

        self.btn_contorno, self._acciones_contorno = self._menu_estilo("Contorno de forma", "outline", "Sin contorno", self.contornoCambiado)
        self.btn_relleno, self._acciones_relleno = self._menu_estilo("Relleno de forma", "shape-fill", "Sin relleno", self.rellenoCambiado)
        self.poner(self.btn_contorno, 272, M.RIBBON_ROW_1 - M.BUTTON // 2)
        self.poner(self.btn_relleno, 272, M.RIBBON_ROW_2 - M.BUTTON // 2)
        self.set_estilos("solid", "none")
        self.set_estilos_habilitados(False)

    def _menu_estilo(self, titulo: str, icono: str, sin_estilo: str, signal: Signal) -> tuple[BotonPaint, dict[str, QAction]]:
        menu = QMenu(titulo, self)
        grupo = QActionGroup(menu)
        acciones: dict[str, QAction] = {}
        for value, texto in (("none", sin_estilo), *self.ESTILOS):
            accion = _accion(menu, texto, None, lambda checked=False, dato=value: signal.emit(dato), checkable=True)
            grupo.addAction(accion)
            acciones[value] = accion
        boton = BotonPaint(titulo, icono, 58, M.BUTTON, M.ICON, "right", menu, centro_icono=(20, M.BUTTON / 2), centro_chevron=(44, M.BUTTON / 2))
        return boton, acciones

    def set_estilos(self, contorno: str, relleno: str) -> None:
        for acciones, valor in ((self._acciones_contorno, contorno), (self._acciones_relleno, relleno)):
            accion = acciones.get(str(valor)) or acciones.get("solid")
            if accion is not None:
                accion.setChecked(True)

    def set_estilos_habilitados(self, enabled: bool) -> None:
        # Contorno y relleno solo se activan con una forma elegida.
        self.btn_contorno.setEnabled(bool(enabled))
        self.btn_relleno.setEnabled(bool(enabled))

    def set_forma_activa(self, shape_id: str | None) -> None:
        shape_id = self.ALIAS.get(str(shape_id), str(shape_id))
        for clave, boton in self.botones.items():
            boton.setChecked(clave == shape_id)
        self.set_estilos_habilitados(shape_id in self.botones)

    def set_columnas(self, columnas: int) -> None:  # compatibilidad
        return None


class _LineaTamano(QWidget):
    """Elemento del menú «Tamaño»: una línea del grosor indicado."""

    elegido = Signal(int)

    def __init__(self, valor: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.valor = valor
        self.activo = False
        self.setFixedSize(160, 36)
        self.setMouseTracking(True)
        self.setToolTip(f"{valor} px")

    def enterEvent(self, event: QEnterEvent) -> None:
        self.update()

    def leaveEvent(self, event) -> None:
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self.elegido.emit(self.valor)

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(4, 2, -4, -2)
        if self.activo or self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c["pressed"] if self.activo else c["hover"]))
            painter.drawRoundedRect(area, 4, 4)
        if self.activo:
            painter.setBrush(QColor(c["accent"]))
            painter.drawRoundedRect(QRectF(area.left(), area.center().y() - 8, 3, 16), 1.5, 1.5)
        painter.setPen(QPen(QColor(c["text"]), self.valor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        y = area.center().y()
        painter.drawLine(QPointF(area.left() + 18, y), QPointF(area.right() - 16, y))
        painter.end()


class _FilaOpacidad(QWidget):
    """Deslizador de opacidad al pie del menú «Tamaño»."""

    cambiada = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 8)
        layout.setSpacing(2)
        fila = QHBoxLayout()
        etiqueta = QLabel("Opacidad", self)
        etiqueta.setObjectName("StatusMetric")
        self.valor = QLabel("100%", self)
        self.valor.setObjectName("StatusMetric")
        fila.addWidget(etiqueta)
        fila.addStretch(1)
        fila.addWidget(self.valor)
        layout.addLayout(fila)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(1, 100)
        self.slider.setValue(100)
        self.slider.setAccessibleName("Opacidad")
        self.slider.valueChanged.connect(self._cambiar)
        layout.addWidget(self.slider)

    def _cambiar(self, valor: int) -> None:
        self.valor.setText(f"{valor}%")
        self.cambiada.emit(valor)

    def set_valor(self, valor: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(max(1, min(100, int(valor))))
        self.slider.blockSignals(False)
        self.valor.setText(f"{self.slider.value()}%")


class SizeGroupView(GrupoRibbon):
    tamanoSeleccionado = Signal(int)
    opacidadCambiada = Signal(int)

    TAMANOS = (1, 3, 5, 8)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Tamaño", M.GROUP_SIZE, parent)
        self.menu = QMenu("Tamaño", self)
        self._lineas: list[_LineaTamano] = []
        self.opacidad = _FilaOpacidad(self)
        self.opacidad.cambiada.connect(self.opacidadCambiada.emit)
        self.set_tamanos(self.TAMANOS)
        self.btn_tamano = BotonPaint("Tamaño (Ctrl++ / Ctrl+-)", "size", 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, "below", self.menu)
        self.poner(self.btn_tamano, 12, M.RIBBON_BIG_TOP)
        self.set_tamano(1)

    def set_tamanos(self, tamanos) -> None:  # noqa: ANN001
        """Cada herramienta tiene su propia lista de grosores."""

        tamanos = tuple(int(valor) for valor in tamanos)
        if tamanos == self.TAMANOS and self._lineas:
            return
        self.TAMANOS = tamanos
        if not hasattr(self, "_separador_opacidad"):
            self._separador_opacidad = self.menu.addSeparator()
            accion_opacidad = QWidgetAction(self.menu)
            accion_opacidad.setDefaultWidget(self.opacidad)
            self.menu.addAction(accion_opacidad)
            self._acciones_lineas: list[QWidgetAction] = []
        # Solo se reemplazan las líneas de grosor; la opacidad se conserva.
        for accion in self._acciones_lineas:
            self.menu.removeAction(accion)
            accion.deleteLater()
        self._acciones_lineas = []
        self._lineas = []
        for valor in tamanos:
            linea = _LineaTamano(valor, self.menu)
            linea.elegido.connect(self._elegir)
            accion = QWidgetAction(self.menu)
            accion.setDefaultWidget(linea)
            self.menu.insertAction(self._separador_opacidad, accion)
            self._acciones_lineas.append(accion)
            self._lineas.append(linea)

    def _elegir(self, valor: int) -> None:
        self.menu.hide()
        self.set_tamano(valor)
        self.tamanoSeleccionado.emit(valor)

    def set_tamano(self, valor: int) -> None:
        cercano = min(self.TAMANOS, key=lambda tamano: abs(tamano - float(valor)))
        for linea in self._lineas:
            linea.activo = linea.valor == cercano
            linea.update()

    def set_habilitado(self, enabled: bool) -> None:
        self.btn_tamano.setEnabled(bool(enabled))


class ColorsGroupView(GrupoRibbon):
    """Color 1, color 2, paleta de 20 colores, 10 personalizados y «Editar colores»."""

    colorPrimarioCambiado = Signal(QColor)
    colorSecundarioCambiado = Signal(QColor)
    editarColoresSolicitado = Signal()
    coloresPersonalizadosCambiados = Signal(list)

    PALETA = (
        "#000000", "#7f7f7f", "#880015", "#ed1c24", "#ff7f27", "#fff200",
        "#22b14c", "#00a2e8", "#3f48cc", "#a349a4",
        "#ffffff", "#c3c3c3", "#b97a57", "#ffaec9", "#ffc90e", "#efe4b0",
        "#b5e61d", "#99d9ea", "#7092be", "#c8bfe7",
    )
    PERSONALIZADOS = 10

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Colores", M.GROUP_COLORS, parent)
        self._activo = "primario"
        self.muestra_primaria = MuestraColor("#000000", grande=True)
        self.muestra_primaria.setToolTip("Color 1 (primer plano)")
        self.muestra_primaria.setAccessibleName("Color 1")
        self.muestra_primaria.colorSeleccionado.connect(lambda *_: self.set_color_activo("primario"))
        self.muestra_secundaria = MuestraColor("#ffffff", grande=True)
        self.muestra_secundaria.setToolTip("Color 2 (fondo)")
        self.muestra_secundaria.setAccessibleName("Color 2")
        self.muestra_secundaria.colorSeleccionado.connect(lambda *_: self.set_color_activo("secundario"))
        self.poner_centrado(self.muestra_primaria, 48, M.RIBBON_ROW_1 + 1)
        self.poner_centrado(self.muestra_secundaria, 48, M.RIBBON_ROW_2 + 1)

        self.muestras_paleta: list[MuestraColor] = []
        filas = (18, 18 + M.COLOR_STEP_Y, 18 + 2 * M.COLOR_STEP_Y)
        for indice in range(len(self.PALETA) + self.PERSONALIZADOS):
            vacio = indice >= len(self.PALETA)
            muestra = MuestraColor(self.PALETA[indice] if not vacio else "#ffffff", vacio=vacio)
            muestra.colorSeleccionado.connect(self._seleccionar_color)
            self.muestras_paleta.append(muestra)
            self.poner_centrado(muestra, 103 + (indice % 10) * M.COLOR_STEP_X, filas[indice // 10])

        self.btn_editar = BotonPaint("Editar colores", "edit-colors", 40, 40, 28, callback=self.editarColoresSolicitado.emit)
        self.poner_centrado(self.btn_editar, 426, 18 + M.COLOR_STEP_Y)
        self.set_color_activo("primario")

    @property
    def color_activo(self) -> str:
        return self._activo

    def set_color_activo(self, destino: str) -> None:
        self._activo = "secundario" if destino == "secundario" else "primario"
        self.muestra_primaria.set_selected(self._activo == "primario")
        self.muestra_secundaria.set_selected(self._activo == "secundario")

    def _seleccionar_color(self, color: QColor, destino: str) -> None:
        self.aplicar_color(color, "secundario" if destino == "secundario" else self._activo)

    def aplicar_color(self, color: QColor, destino: str | None = None) -> None:
        objetivo = destino or self._activo
        if objetivo == "secundario":
            self.set_color_secundario(color)
            self.colorSecundarioCambiado.emit(QColor(color))
            return
        self.set_color_primario(color)
        self.colorPrimarioCambiado.emit(QColor(color))

    def set_color_primario(self, color: QColor | str) -> None:
        self.muestra_primaria.set_color(color)

    def set_color_secundario(self, color: QColor | str) -> None:
        self.muestra_secundaria.set_color(color)

    def colores_personalizados(self) -> list[str]:
        return [
            muestra.color.name(QColor.NameFormat.HexArgb)
            for muestra in self.muestras_paleta[len(self.PALETA):]
            if not muestra.vacio
        ]

    def set_colores_personalizados(self, colores: list[str]) -> None:
        validos = [QColor(color) for color in colores if QColor(color).isValid()][: self.PERSONALIZADOS]
        for indice, muestra in enumerate(self.muestras_paleta[len(self.PALETA):]):
            if indice < len(validos):
                muestra.set_color(validos[indice])
            else:
                muestra.set_vacio()

    def agregar_color_personalizado(self, color: QColor) -> None:
        nombre = QColor(color).name(QColor.NameFormat.HexArgb)
        actuales = [item for item in self.colores_personalizados() if item != nombre]
        self.set_colores_personalizados([*actuales, nombre][-self.PERSONALIZADOS:])
        self.coloresPersonalizadosCambiados.emit(self.colores_personalizados())


class LayersGroupView(GrupoRibbon):
    """Botón «Capas» al final de la cinta: muestra u oculta el panel de capas (F7)."""

    accionSolicitada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Capas", M.GROUP_LAYERS, parent, separador=False)
        self.btn_capas = BotonPaint(
            "Capas (F7)", "layers", 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, None,
            callback=lambda checked=False: self.accionSolicitada.emit("toggle_layers"),
        )
        self.btn_capas.setCheckable(True)
        self.poner(self.btn_capas, 11, M.RIBBON_BIG_TOP)

    def set_activo(self, activo: bool) -> None:
        self.btn_capas.setChecked(bool(activo))


class _VentanaGrupo(QFrame):
    """Ventana emergente que muestra un grupo plegado de la cinta."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("RibbonGroupPopup")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)


class GrupoPlegado(GrupoRibbon):
    """Grupo compacto: un botón con el icono del grupo que despliega el grupo completo."""

    def __init__(self, grupo: GrupoRibbon, titulo: str, icono: str, parent: QWidget | None = None) -> None:
        super().__init__(titulo, 72, parent)
        self.grupo = grupo
        self.ventana = _VentanaGrupo(self)
        self.boton = BotonPaint(titulo, icono, 48, M.RIBBON_BIG_HEIGHT, M.ICON_BIG, "below", callback=self.mostrar)
        self.poner(self.boton, 12, M.RIBBON_BIG_TOP)

    def mostrar(self) -> None:
        self.ventana.layout().addWidget(self.grupo)
        self.grupo.show()
        self.ventana.adjustSize()
        self.ventana.move(self.mapToGlobal(self.boton.geometry().bottomLeft()))
        self.ventana.show()


# ----------------------------------------------------------------------
class RibbonView(QFrame):
    """Barra de menús (Archivo, Editar, Ver) y la cinta."""

    accionSolicitada = Signal(str)
    herramientaSeleccionada = Signal(str)
    pincelSeleccionado = Signal(str)
    formaSeleccionada = Signal(str)
    tamanoSeleccionado = Signal(int)
    colorPrimarioCambiado = Signal(QColor)
    colorSecundarioCambiado = Signal(QColor)
    contornoCambiado = Signal(str)
    rellenoCambiado = Signal(str)
    seleccionTransparenteCambiada = Signal(bool)
    opacidadBorradorCambiada = Signal(int)
    opacidadHerramientaCambiada = Signal(str, int)
    toleranciaRellenoCambiada = Signal(int)
    coloresPersonalizadosCambiados = Signal(list)
    capasSolicitadas = Signal()
    colapsadoCambiado = Signal(bool)
    autoOcultarCambiado = Signal(bool)

    HERRAMIENTAS_CON_TAMANO = {"pencil", "brush", "eraser", *PAINT_SHAPES}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._colapsado = False
        self._herramienta = "pencil"
        self.setObjectName("PaintRibbon")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._construir_interfaz()
        self._conectar_grupos()
        self._actualizar_altura()

    def _construir_interfaz(self) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        principal.setSpacing(0)

        # Barra de menús: se conserva «Archivo · Editar · Ver» de MelfPaint.
        self.barra_comandos = QFrame(self)
        self.barra_comandos.setObjectName("AppBar")
        self.barra_comandos.setFixedHeight(M.MENU_BAR_HEIGHT)
        barra = QHBoxLayout(self.barra_comandos)
        barra.setContentsMargins(6, 0, 8, 0)
        barra.setSpacing(0)
        self.botones_menu: dict[str, QToolButton] = {}
        for menu_id, texto in (("file", "Archivo"), ("edit", "Editar"), ("view", "Ver")):
            boton = QToolButton(self.barra_comandos)
            boton.setObjectName("TopMenuButton")
            boton.setText(texto)
            boton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            boton.setFixedHeight(32)
            boton.setAccessibleName(f"Menú {texto}")
            self.botones_menu[menu_id] = boton
            barra.addWidget(boton, 0, Qt.AlignmentFlag.AlignVCenter)

        barra.addSpacing(11)
        barra.addWidget(self._separador_barra(), 0, Qt.AlignmentFlag.AlignVCenter)
        barra.addSpacing(7)
        self.botones_comando: dict[str, BotonPaint] = {}
        self.botones_comando["save"] = BotonPaint("Guardar (Ctrl+S)", "save", callback=lambda: self.accionSolicitada.emit("save"))
        barra.addWidget(self.botones_comando["save"], 0, Qt.AlignmentFlag.AlignVCenter)
        barra.addSpacing(7)
        barra.addWidget(self._separador_barra(), 0, Qt.AlignmentFlag.AlignVCenter)
        barra.addSpacing(8)
        for action_id, texto, icono in (("undo", "Deshacer (Ctrl+Z)", "undo"), ("redo", "Rehacer (Ctrl+Y)", "redo")):
            boton = BotonPaint(texto, icono, callback=lambda checked=False, value=action_id: self.accionSolicitada.emit(value))
            self.botones_comando[action_id] = boton
            barra.addWidget(boton, 0, Qt.AlignmentFlag.AlignVCenter)
            if action_id == "undo":
                barra.addSpacing(10)
        barra.addStretch(1)
        self.btn_configuracion = BotonPaint("Configuración", "settings", callback=lambda: self.accionSolicitada.emit("settings"))
        barra.addWidget(self.btn_configuracion, 0, Qt.AlignmentFlag.AlignVCenter)
        principal.addWidget(self.barra_comandos)

        self.contenedor_grupos = QFrame(self)
        self.contenedor_grupos.setObjectName("RibbonGroups")
        self.contenedor_grupos.setFixedHeight(M.RIBBON_HEIGHT)
        grupos = QHBoxLayout(self.contenedor_grupos)
        grupos.setContentsMargins(0, 0, 0, 0)
        grupos.setSpacing(0)

        self.portapapeles = ClipboardGroupView(self.contenedor_grupos)
        self.imagen = ImageGroupView(self.contenedor_grupos)
        self.seleccion = self.imagen
        self.herramientas = ToolsGroupView(self.contenedor_grupos)
        self.pinceles = BrushesGroupView(self.contenedor_grupos)
        self.formas = ShapesGroupView(self.contenedor_grupos)
        self.tamano = SizeGroupView(self.contenedor_grupos)
        self.colores = ColorsGroupView(self.contenedor_grupos)
        self.capas = LayersGroupView(self.contenedor_grupos)
        self.grupos_visibles = (
            self.portapapeles,
            self.imagen,
            self.herramientas,
            self.pinceles,
            self.formas,
            self.tamano,
            self.colores,
            self.capas,
        )
        for grupo in self.grupos_visibles:
            grupos.addWidget(grupo, 0, Qt.AlignmentFlag.AlignTop)
        self._aplicar_descripciones()
        # En ventanas estrechas algunos grupos se pliegan.
        self._plegables = [
            (self.colores, GrupoPlegado(self.colores, "Colores", "palette", self.contenedor_grupos)),
            (self.formas, GrupoPlegado(self.formas, "Formas", "shape-fill", self.contenedor_grupos)),
            (self.imagen, GrupoPlegado(self.imagen, "Imagen", "image-properties", self.contenedor_grupos)),
        ]
        for grupo, plegado in self._plegables:
            plegado.hide()
            grupos.insertWidget(grupos.indexOf(grupo), plegado, 0, Qt.AlignmentFlag.AlignTop)
        self._layout_grupos = grupos
        grupos.addStretch(1)
        principal.addWidget(self.contenedor_grupos)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._ajustar_plegado()

    def _ajustar_plegado(self) -> None:
        if not hasattr(self, "_plegables"):
            return
        disponible = self.width()
        necesario = sum(grupo.width() for grupo in self.grupos_visibles)
        for grupo, plegado in self._plegables:
            plegar = necesario > disponible
            if plegar:
                necesario -= grupo.width() - plegado.width()
            # isHidden() no depende de que la ventana ya se haya mostrado.
            if plegar and plegado.isHidden():
                grupo.hide()
                plegado.show()
            elif not plegar and not plegado.isHidden():
                plegado.ventana.hide()
                indice = self._layout_grupos.indexOf(plegado)
                self._layout_grupos.insertWidget(indice + 1, grupo, 0, Qt.AlignmentFlag.AlignTop)
                plegado.hide()
                grupo.show()

    def _aplicar_descripciones(self) -> None:
        for boton in self.contenedor_grupos.findChildren(BotonPaint):
            descripcion = DESCRIPCIONES.get(getattr(boton, "_nombre_icono", ""))
            if descripcion:
                boton.setToolTip(descripcion)

    def _separador_barra(self) -> QFrame:
        separador = QFrame(self.barra_comandos)
        separador.setObjectName("AppBarSeparator")
        separador.setFixedSize(1, 24)
        return separador

    def set_application_menus(self, menus: dict[str, QMenu]) -> None:
        for menu_id, boton in self.botones_menu.items():
            menu = menus.get(menu_id)
            if menu is None:
                continue
            boton.setMenu(menu)
            boton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def bind_actions(self, actions: dict[str, QAction]) -> None:
        for action_id, boton in self.botones_comando.items():
            action = actions.get(action_id)
            if action is None:
                continue
            boton.setEnabled(action.isEnabled())
            action.changed.connect(lambda watched=action, target=boton: target.setEnabled(watched.isEnabled()))
        capas = actions.get("toggle_layers")
        if capas is not None:
            self.capas.set_activo(capas.isChecked())
            capas.toggled.connect(self.capas.set_activo)

    def _conectar_grupos(self) -> None:
        self.portapapeles.accionSolicitada.connect(self.accionSolicitada.emit)
        self.imagen.herramientaSeleccionada.connect(self.herramientaSeleccionada.emit)
        self.imagen.accionSolicitada.connect(self.accionSolicitada.emit)
        self.imagen.seleccionTransparenteCambiada.connect(self.seleccionTransparenteCambiada.emit)
        self.herramientas.herramientaSeleccionada.connect(self.herramientaSeleccionada.emit)
        self.pinceles.pincelSeleccionado.connect(self.pincelSeleccionado.emit)
        self.formas.formaSeleccionada.connect(self.formaSeleccionada.emit)
        self.formas.contornoCambiado.connect(self.contornoCambiado.emit)
        self.formas.rellenoCambiado.connect(self.rellenoCambiado.emit)
        self.capas.accionSolicitada.connect(self.accionSolicitada.emit)
        self.tamano.tamanoSeleccionado.connect(self.tamanoSeleccionado.emit)
        self.tamano.opacidadCambiada.connect(lambda valor: self.opacidadHerramientaCambiada.emit(self._herramienta, valor))
        self.colores.colorPrimarioCambiado.connect(self.colorPrimarioCambiado.emit)
        self.colores.colorSecundarioCambiado.connect(self.colorSecundarioCambiado.emit)
        self.colores.editarColoresSolicitado.connect(lambda: self.accionSolicitada.emit("edit_colors"))
        self.colores.coloresPersonalizadosCambiados.connect(self.coloresPersonalizadosCambiados.emit)

    # ------------------------------------------------------------------
    # Estado público
    def set_herramienta_activa(self, tool_id: str) -> None:
        tool_id = str(tool_id)
        self._herramienta = tool_id
        self.herramientas.set_herramienta_activa(tool_id)
        self.imagen.set_herramienta_activa(tool_id)
        self.pinceles.set_activo(tool_id == "brush")
        forma = self.formas.ALIAS.get(tool_id, tool_id)
        self.formas.set_forma_activa(forma if forma in self.formas.botones else None)
        self.tamano.set_habilitado(tool_id in self.HERRAMIENTAS_CON_TAMANO or forma in self.formas.botones)

    def set_pincel_activo(self, brush_id: str) -> None:
        self.pinceles.set_pincel_activo(brush_id)

    def set_forma_activa(self, shape_id: str | None) -> None:
        self.formas.set_forma_activa(shape_id)

    def set_estilos_forma(self, contorno: str, relleno: str) -> None:
        self.formas.set_estilos(contorno, relleno)

    def set_tamano(self, value: int) -> None:
        self.tamano.set_tamano(value)

    def set_tamanos(self, values) -> None:  # noqa: ANN001
        self.tamano.set_tamanos(values)

    def set_colores(self, primario: QColor | str, secundario: QColor | str) -> None:
        self.colores.set_color_primario(primario)
        self.colores.set_color_secundario(secundario)

    def set_seleccion_transparente(self, enabled: bool) -> None:
        self.imagen.set_transparente(enabled)

    def set_recorte_habilitado(self, enabled: bool) -> None:
        self.imagen.set_recorte_habilitado(enabled)
        self.portapapeles.set_seleccion_activa(enabled)

    def set_opacidad_borrador(self, value: int) -> None:
        if getattr(self, "_herramienta", "") == "eraser":
            self.tamano.opacidad.set_valor(value)

    def set_opacidad_trazo(self, value: int) -> None:
        if getattr(self, "_herramienta", "") != "eraser":
            self.tamano.opacidad.set_valor(value)

    def set_dark_theme(self, dark: bool) -> None:
        self.update()

    def set_collapsed(self, collapsed: bool) -> None:
        self._colapsado = bool(collapsed)
        self.contenedor_grupos.setVisible(not self._colapsado)
        self._actualizar_altura()
        self.colapsadoCambiado.emit(self._colapsado)

    def is_collapsed(self) -> bool:
        return self._colapsado

    def set_auto_hide(self, enabled: bool) -> None:
        if enabled:
            self.set_collapsed(True)
        self.autoOcultarCambiado.emit(bool(enabled))

    def _actualizar_altura(self) -> None:
        self.setFixedHeight(M.MENU_BAR_HEIGHT + (0 if self._colapsado else M.RIBBON_HEIGHT))


PaintRibbon = RibbonView
