from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QToolButton, QWidget

from frontend.Config import metrics as M
from frontend.Config.settings import icon_path
from frontend.Config.theme import colors


ICON_NAME_PROPERTY = "melfpaintIconName"
_ESTADO = {"oscuro": False}

# Colores de trazo de los iconos que se aclaran en el tema oscuro.
_REEMPLAZOS_OSCUROS = (
    (b"#424242", b"#e6e6e6"),
    (b"#5c5c5c", b"#cfcfcf"),
    (b"#344054", b"#d7e2ec"),
    (b"#26364a", b"#d7e2ec"),
)


def tema_oscuro_activo() -> bool:
    return _ESTADO["oscuro"]


@lru_cache(maxsize=256)
def cargar_icono(nombre: str, oscuro: bool = False) -> QIcon:
    ruta = icon_path(nombre)
    if not ruta.exists():
        return QIcon()
    if not oscuro:
        return QIcon(str(ruta))
    try:
        contenido = ruta.read_bytes()
    except OSError:
        return QIcon()
    for antes, despues in _REEMPLAZOS_OSCUROS:
        contenido = contenido.replace(antes, despues)
    renderer = QSvgRenderer(QByteArray(contenido))
    if not renderer.isValid():
        return QIcon(str(ruta))
    icono = QIcon()
    for lado in (16, 20, 24, 26, 32, 40, 48):
        pixmap = QPixmap(lado, lado)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        icono.addPixmap(pixmap)
    return icono


def registrar_icono(widget: QWidget, nombre: str) -> None:
    widget.setProperty(ICON_NAME_PROPERTY, str(nombre))


def aplicar_tema_iconos(root: QWidget, oscuro: bool) -> None:
    """Actualiza iconos SVG sin mantener dos carpetas de recursos."""

    _ESTADO["oscuro"] = bool(oscuro)
    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        nombre = widget.property(ICON_NAME_PROPERTY)
        if nombre:
            icono = cargar_icono(str(nombre), bool(oscuro))
            if isinstance(widget, QToolButton):
                widget.setIcon(icono)
            elif isinstance(widget, QLabel):
                lado = max(1, int(widget.property("melfpaintIconSize") or 16))
                widget.setPixmap(icono.pixmap(lado, lado))
        widget.update()


def dibujar_chevron(painter: QPainter, centro: QPointF, color: QColor, ancho: float = 8.0) -> None:
    """Flecha «v» fina de los botones desplegables."""

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    lapiz = QPen(color, 1.1)
    lapiz.setCapStyle(Qt.PenCapStyle.RoundCap)
    lapiz.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(lapiz)
    mitad = ancho / 2
    path = QPainterPath()
    path.moveTo(centro.x() - mitad, centro.y() - mitad / 2)
    path.lineTo(centro.x(), centro.y() + mitad / 2)
    path.lineTo(centro.x() + mitad, centro.y() - mitad / 2)
    painter.drawPath(path)
    painter.restore()


class BotonPaint(QToolButton):
    """Botón plano de la cinta con el icono y la flecha en posiciones fijas.

    ``chevron`` puede ser ``None``, ``"below"`` (botón grande con la flecha
    debajo) o ``"right"`` (botón pequeño con la flecha a la derecha). Con
    ``split=True`` el clic sobre el icono ejecuta la acción y el clic sobre la
    flecha abre el menú, como «Pegar», «Seleccionar» o «Pinceles».
    """

    def __init__(
        self,
        texto: str,
        icono: str,
        ancho: int = M.BUTTON,
        alto: int = M.BUTTON,
        lado_icono: int = M.ICON,
        chevron: str | None = None,
        menu: QMenu | None = None,
        split: bool = False,
        callback: Callable[..., None] | None = None,
        centro_icono: tuple[float, float] | None = None,
        centro_chevron: tuple[float, float] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PaintButton")
        self.setToolTip(texto)
        self.setToolTipDuration(8000)
        self.setAccessibleName(texto)
        self.setFixedSize(ancho, alto)
        self.setIconSize(QSize(lado_icono, lado_icono))
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._nombre_icono = icono
        self._lado_icono = lado_icono
        self._chevron = chevron
        self._split = bool(split)
        self._menu_abierto = False
        if chevron == "below":
            self._centro_icono = QPointF(*(centro_icono or (ancho / 2, M.RIBBON_BIG_ICON - M.RIBBON_BIG_TOP)))
            self._centro_chevron = QPointF(*(centro_chevron or (ancho / 2, M.RIBBON_BIG_CHEVRON - M.RIBBON_BIG_TOP)))
        elif chevron == "right":
            self._centro_icono = QPointF(*(centro_icono or (20, alto / 2)))
            self._centro_chevron = QPointF(*(centro_chevron or (ancho - 11, alto / 2)))
        else:
            self._centro_icono = QPointF(*(centro_icono or (ancho / 2, alto / 2)))
            self._centro_chevron = QPointF()
        if icono:
            registrar_icono(self, icono)
            self.setIcon(cargar_icono(icono, tema_oscuro_activo()))
        if menu is not None:
            self.setMenu(menu)
            menu.aboutToShow.connect(lambda: self._set_menu_abierto(True))
            menu.aboutToHide.connect(lambda: self._set_menu_abierto(False))
            self.setPopupMode(
                QToolButton.ToolButtonPopupMode.DelayedPopup
                if self._split
                else QToolButton.ToolButtonPopupMode.InstantPopup
            )
        if callback is not None:
            self.clicked.connect(callback)

    def _set_menu_abierto(self, abierto: bool) -> None:
        self._menu_abierto = abierto
        self.update()

    def set_icono(self, nombre: str) -> None:
        self._nombre_icono = nombre
        registrar_icono(self, nombre)
        self.setIcon(cargar_icono(nombre, tema_oscuro_activo()))
        self.update()

    def _zona_chevron(self, y: float) -> bool:
        if self._chevron == "below":
            return y >= self._centro_chevron.y() - 12
        if self._chevron == "right":
            return False
        return False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._split and self.menu() is not None and event.button() == Qt.MouseButton.LeftButton:
            en_flecha = self._zona_chevron(event.position().y()) or (
                self._chevron == "right" and event.position().x() >= self._centro_chevron.x() - 8
            )
            if en_flecha:
                self.showMenu()
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        c = colors(tema_oscuro_activo())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked():
            painter.setPen(QPen(QColor(c["checked_border"]), 1))
            painter.setBrush(QColor(c["checked_bg"]))
            painter.drawRoundedRect(area, M.BUTTON_RADIUS, M.BUTTON_RADIUS)
        elif self.isEnabled() and (self.isDown() or self._menu_abierto):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c["pressed"]))
            painter.drawRoundedRect(area, M.BUTTON_RADIUS, M.BUTTON_RADIUS)
        elif self.isEnabled() and self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(c["hover"]))
            painter.drawRoundedRect(area, M.BUTTON_RADIUS, M.BUTTON_RADIUS)

        modo = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        lado = self._lado_icono
        pixmap = self.icon().pixmap(QSize(lado, lado), self.devicePixelRatioF(), modo)
        if not self.isEnabled():
            painter.setOpacity(0.38)
        destino = QRect(round(self._centro_icono.x() - lado / 2), round(self._centro_icono.y() - lado / 2), lado, lado)
        painter.drawPixmap(destino, pixmap)
        if self._chevron:
            dibujar_chevron(painter, self._centro_chevron, QColor(c["icon"]))
        painter.end()


class GrupoRibbon(QFrame):
    """Grupo de la cinta con su título abajo y un separador a la derecha.

    Los controles se colocan con ``poner`` en coordenadas relativas al grupo.
    """

    def __init__(self, titulo: str, ancho: int = 100, parent: QWidget | None = None, separador: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setFixedSize(ancho, M.RIBBON_HEIGHT)
        self._separador = separador
        self.contenido = self
        self.etiqueta_titulo = QLabel(titulo, self)
        self.etiqueta_titulo.setObjectName("RibbonGroupTitle")
        self.etiqueta_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_titulo.setGeometry(0, M.RIBBON_LABEL_CENTER - M.RIBBON_LABEL_HEIGHT // 2, ancho, M.RIBBON_LABEL_HEIGHT)

    def poner(self, widget: QWidget, x: float, y: float) -> QWidget:
        widget.setParent(self)
        widget.move(round(x), round(y))
        widget.show()
        return widget

    def poner_centrado(self, widget: QWidget, cx: float, cy: float) -> QWidget:
        return self.poner(widget, cx - widget.width() / 2, cy - widget.height() / 2)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._separador:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(colors(tema_oscuro_activo())["separator"]), 1))
        x = self.width() - 1
        painter.drawLine(x, 8, x, M.RIBBON_HEIGHT - 9)
        painter.end()


# Botones de versiones anteriores, todavía usados por algunos paneles.
class BotonRibbon(QToolButton):
    def __init__(self, texto: str, icono: str = "", callback: Callable[..., None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(texto)
        self.setToolTip(texto)
        self.setAccessibleName(texto)
        if icono:
            registrar_icono(self, icono)
            self.setIcon(cargar_icono(icono))
        if callback is not None:
            self.clicked.connect(callback)


class BotonRibbonPequeno(BotonRibbon):
    def __init__(self, texto: str, icono: str = "", callback: Callable[..., None] | None = None, mostrar_texto: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(texto, icono, callback, parent)
        self.setIconSize(QSize(M.ICON, M.ICON))
        self.setFixedHeight(M.BUTTON)
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon if mostrar_texto else Qt.ToolButtonStyle.ToolButtonIconOnly
        )


class BotonRibbonAlternable(BotonRibbonPequeno):
    def __init__(self, texto: str, icono: str = "", callback: Callable[..., None] | None = None, mostrar_texto: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(texto, icono, callback, mostrar_texto, parent)
        self.setCheckable(True)


RibbonButton = BotonRibbon
SmallRibbonButton = BotonRibbonPequeno
ToggleRibbonButton = BotonRibbonAlternable
PaintButton = BotonPaint
RibbonGroup = GrupoRibbon
