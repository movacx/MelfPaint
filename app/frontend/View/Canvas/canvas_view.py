from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QPixmap,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

from frontend.Config import metrics as M
from frontend.Config.settings import resource_path
from frontend.Config.theme import colors


# Cursores propios: (archivo, punto activo en un lienzo de 32 px).
_CURSORES = {
    "pencil": ("pencil", 4, 28),
    "fill": ("fill", 5, 25),
    "bucket": ("fill", 5, 25),
    "eyedropper": ("eyedropper", 4, 28),
    "picker": ("eyedropper", 4, 28),
    "color_picker": ("eyedropper", 4, 28),
    "magnifier": ("magnifier", 13, 13),
    "zoom": ("magnifier", 13, 13),
}
_CACHE_CURSORES: dict[str, QCursor] = {}


def cursor_herramienta(tool_id: str) -> QCursor | None:
    datos = _CURSORES.get(tool_id)
    if datos is None:
        return None
    if tool_id not in _CACHE_CURSORES:
        nombre, x, y = datos
        renderer = QSvgRenderer(str(resource_path("cursors", f"{nombre}.svg")))
        if not renderer.isValid():
            return None
        lado = 32
        pixmap = QPixmap(lado, lado)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        _CACHE_CURSORES[tool_id] = QCursor(pixmap, x, y)
    return _CACHE_CURSORES[tool_id]


class CanvasView(QWidget):
    punteroMovido = Signal(int, int)
    punteroSalio = Signal()
    zoomCambiado = Signal(int)
    rectanguloTextoSolicitado = Signal(QRect)
    comandoSeleccionSolicitado = Signal(str, int, int)
    redimensionLienzoSolicitado = Signal(int, int, str)
    zoomEnPuntoSolicitado = Signal(int, float, float, float, float)
    menuContextualSolicitado = Signal(QPoint)
    PASOS_ZOOM = (10, 12, 16, 25, 33, 50, 67, 100, 125, 150, 200, 300, 400, 500, 600, 700, 800)

    def __init__(self, document: Any, tool_controller: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.documento = document
        self.controlador_herramientas = tool_controller
        self.zoom = 1.0
        self.mostrar_cuadricula = False
        self.mostrar_reglas = False
        self.tema_oscuro = False
        self._dibujando = False
        self._manejador_lienzo: str | None = None
        self._redimension_previa: tuple[int, int, str] | None = None
        self._puntero: QPointF | None = None
        self._ultimo_punto: QPointF | None = None
        # El aerógrafo sigue rociando aunque el ratón esté quieto.
        self._temporizador_spray = QTimer(self)
        self._temporizador_spray.setInterval(45)
        self._temporizador_spray.timeout.connect(self._rociar)

        self.setObjectName("CanvasView")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Lienzo de dibujo de MelfPaint")
        self._conectar_controlador(tool_controller)

    # ------------------------------------------------------------------
    # Configuración pública de la vista
    def set_document(self, document: Any) -> None:
        self.documento = document
        self.resize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def set_tool_controller(self, controller: Any) -> None:
        anterior = self.controlador_herramientas
        senal_anterior = getattr(anterior, "changed", None)
        if senal_anterior is not None:
            try:
                senal_anterior.disconnect(self.update)
            except (RuntimeError, TypeError):
                pass
        self.controlador_herramientas = controller
        self._conectar_controlador(controller)
        self.update()

    def set_zoom_percent(self, value: int) -> None:
        porcentaje = max(10, min(800, int(value)))
        nuevo_zoom = porcentaje / 100.0
        if abs(nuevo_zoom - self.zoom) < 0.0001:
            return
        self.zoom = nuevo_zoom
        self.resize(self.sizeHint())
        self.updateGeometry()
        self.update()
        self.zoomCambiado.emit(porcentaje)

    def establecer_zoom(self, porcentaje: int) -> None:
        self.set_zoom_percent(porcentaje)

    def set_grid_visible(self, visible: bool) -> None:
        self.mostrar_cuadricula = bool(visible)
        self.update()

    def set_rulers_visible(self, visible: bool) -> None:
        self.mostrar_reglas = bool(visible)
        self.resize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def set_dark_theme(self, dark: bool) -> None:
        self.tema_oscuro = bool(dark)
        self.update()

    def fit_to_size(self, available: QSize) -> int:
        ancho = max(1, int(getattr(self.documento, "width", 1)))
        alto = max(1, int(getattr(self.documento, "height", 1)))
        regla = M.RULER_SIZE if self.mostrar_reglas else 0
        escala_x = max(0.1, (available.width() - M.CANVAS_MARGIN * 2 - regla) / ancho)
        escala_y = max(0.1, (available.height() - M.CANVAS_MARGIN_TOP - M.CANVAS_MARGIN - regla) / alto)
        porcentaje = max(10, min(800, round(min(escala_x, escala_y) * 100)))
        self.set_zoom_percent(porcentaje)
        return porcentaje

    # ------------------------------------------------------------------
    # Conversión de coordenadas
    def sizeHint(self) -> QSize:
        regla = M.RULER_SIZE if self.mostrar_reglas else 0
        ancho = round(max(1, int(getattr(self.documento, "width", 1))) * self.zoom)
        alto = round(max(1, int(getattr(self.documento, "height", 1))) * self.zoom)
        return QSize(ancho + (M.CANVAS_MARGIN * 2) + regla, alto + M.CANVAS_MARGIN_TOP + M.CANVAS_MARGIN + regla)

    def canvas_rect(self) -> QRect:
        regla = M.RULER_SIZE if self.mostrar_reglas else 0
        ancho = round(max(1, int(getattr(self.documento, "width", 1))) * self.zoom)
        alto = round(max(1, int(getattr(self.documento, "height", 1))) * self.zoom)
        return QRect(M.CANVAS_MARGIN + regla, M.CANVAS_MARGIN_TOP + regla, max(1, ancho), max(1, alto))

    def screen_to_document(self, point: QPoint | QPointF) -> QPointF:
        rectangulo = self.canvas_rect()
        return QPointF(
            (point.x() - rectangulo.x()) / self.zoom,
            (point.y() - rectangulo.y()) / self.zoom,
        )

    def document_to_screen(self, point: QPoint | QPointF) -> QPointF:
        rectangulo = self.canvas_rect()
        return QPointF(
            rectangulo.x() + point.x() * self.zoom,
            rectangulo.y() + point.y() * self.zoom,
        )

    def document_rect_to_screen(self, rectangulo: QRect) -> QRect:
        lienzo = self.canvas_rect()
        return QRect(
            round(lienzo.x() + rectangulo.x() * self.zoom),
            round(lienzo.y() + rectangulo.y() * self.zoom),
            max(1, round(rectangulo.width() * self.zoom)),
            max(1, round(rectangulo.height() * self.zoom)),
        )

    # ------------------------------------------------------------------
    # Dibujo
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        try:
            paleta = colors(self.tema_oscuro)
            painter.fillRect(self.rect(), QColor(paleta["workspace"]))

            rectangulo = self.canvas_rect()
            # Sombra muy suave alrededor de la hoja.
            for paso, alfa in ((3, 6), (2, 9), (1, 14)):
                painter.fillRect(rectangulo.adjusted(-paso + 1, -paso + 1, paso, paso + 1), QColor(0, 0, 0, alfa))
            self._dibujar_tablero(painter, rectangulo)

            composite = getattr(self.documento, "composite", None)
            imagen = composite() if callable(composite) else None
            if isinstance(imagen, QImage) and not imagen.isNull():
                self._dibujar_region(painter, rectangulo, imagen, event.rect())
            self._expuesto = event.rect()

            self._dibujar_vista_previa(painter, rectangulo)
            self._dibujar_seleccion(painter)
            self._dibujar_objeto_editable(painter)
            self._dibujar_contorno_herramienta(painter)

            if self.mostrar_cuadricula:
                self._dibujar_cuadricula(painter, rectangulo)
            if self.mostrar_reglas:
                self._dibujar_reglas(painter, rectangulo)

            self._dibujar_manejadores_lienzo(painter, rectangulo)
            self._dibujar_redimension_previa(painter)
        finally:
            painter.end()

    def _dibujar_region(self, painter: QPainter, rectangulo: QRect, imagen: QImage, expuesto: QRect) -> None:
        """Dibuja solo la parte visible; al acercar, píxeles nítidos."""

        visible = QRectF(expuesto.intersected(rectangulo))
        if visible.isEmpty():
            return
        escala_x = imagen.width() / max(1, rectangulo.width())
        escala_y = imagen.height() / max(1, rectangulo.height())
        origen = QRectF(
            (visible.x() - rectangulo.x()) * escala_x,
            (visible.y() - rectangulo.y()) * escala_y,
            visible.width() * escala_x,
            visible.height() * escala_y,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom < 1.0)
        painter.drawImage(visible, imagen, origen)
        painter.restore()

    def _dibujar_tablero(self, painter: QPainter, rectangulo: QRect) -> None:
        transparente = bool(getattr(self.documento, "transparent_background", False))
        color_base = QColor("#ffffff")
        if not transparente:
            fondo = getattr(self.documento, "background", color_base)
            color_base = QColor(fondo) if QColor(fondo).isValid() else color_base
        painter.fillRect(rectangulo, color_base)

        if not transparente:
            return

        oscuro = QColor("#d8d8d8") if not self.tema_oscuro else QColor("#707070")
        baldosa = max(5, round(M.CHECKER_SIZE * min(self.zoom, 2.0)))
        # Un patrón en mosaico se dibuja de una vez, aunque el lienzo sea enorme.
        patron = QPixmap(baldosa * 2, baldosa * 2)
        patron.fill(QColor("#ffffff"))
        pintor = QPainter(patron)
        pintor.fillRect(baldosa, 0, baldosa, baldosa, oscuro)
        pintor.fillRect(0, baldosa, baldosa, baldosa, oscuro)
        pintor.end()
        pincel = QBrush(patron)
        pincel.setTransform(QTransform.fromTranslate(rectangulo.left(), rectangulo.top()))
        painter.fillRect(rectangulo, pincel)

    def _dibujar_manejadores_lienzo(self, painter: QPainter, rectangulo: QRect) -> None:
        # Hay tres tiradores circulares: derecha, abajo y esquina.
        paleta = colors(self.tema_oscuro)
        radio = M.CANVAS_HANDLE / 2
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(paleta["handle_border"]), 1))
        painter.setBrush(QColor(paleta["workspace"]))
        for punto in self._puntos_manejadores(rectangulo).values():
            painter.drawEllipse(QPointF(punto.x() + 0.5, punto.y() + 0.5), radio, radio)
        painter.restore()

    @staticmethod
    def _puntos_manejadores(rectangulo: QRect) -> dict[str, QPoint]:
        derecha = rectangulo.right() + 1
        abajo = rectangulo.bottom() + 1
        return {
            "right": QPoint(derecha, rectangulo.center().y()),
            "bottom_right": QPoint(derecha, abajo),
            "bottom": QPoint(rectangulo.center().x(), abajo),
        }

    def _manejador_en(self, point: QPoint | QPointF) -> str | None:
        margen = max(6, M.CANVAS_HANDLE + 2)
        x, y = round(point.x()), round(point.y())
        for nombre, centro in self._puntos_manejadores(self.canvas_rect()).items():
            if abs(x - centro.x()) <= margen and abs(y - centro.y()) <= margen:
                return nombre
        return None

    @staticmethod
    def _cursor_manejador(nombre: str) -> Qt.CursorShape:
        if nombre in {"top_left", "bottom_right"}:
            return Qt.CursorShape.SizeFDiagCursor
        if nombre in {"top_right", "bottom_left"}:
            return Qt.CursorShape.SizeBDiagCursor
        if nombre in {"left", "right"}:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _dibujar_vista_previa(self, painter: QPainter, rectangulo: QRect) -> None:
        metodo = getattr(self.controlador_herramientas, "preview", None)
        if not callable(metodo):
            return
        vista_previa = metodo()
        if isinstance(vista_previa, QImage) and not vista_previa.isNull():
            self._dibujar_region(painter, rectangulo, vista_previa, getattr(self, "_expuesto", self.rect()))

    def _dibujar_seleccion(self, painter: QPainter) -> None:
        seleccion = getattr(self.documento, "selection", None)
        rectangulo_documento = None

        if seleccion is not None and bool(getattr(seleccion, "has_selection", False)):
            rectangulo_documento = getattr(seleccion, "current_rect", None)
            obtener_imagen = getattr(seleccion, "display_image", None)
            imagen = obtener_imagen() if callable(obtener_imagen) else None
            if isinstance(rectangulo_documento, QRect) and isinstance(imagen, QImage):
                painter.drawImage(self.document_rect_to_screen(rectangulo_documento), imagen)
            estado = getattr(seleccion, "state", None)
            if getattr(estado, "value", estado) == "moving":
                return
        else:
            rectangulo_documento = getattr(self.documento, "selection_rect", None)

        if not isinstance(rectangulo_documento, QRect) or rectangulo_documento.isEmpty():
            return

        destino = self.document_rect_to_screen(rectangulo_documento)
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)

        lapiz_negro = QPen(QColor("#111111"), 1, Qt.PenStyle.DashLine)
        lapiz_negro.setCosmetic(True)
        painter.setPen(lapiz_negro)
        painter.drawRect(destino.adjusted(0, 0, -1, -1))

        lapiz_blanco = QPen(QColor("#ffffff"), 1, Qt.PenStyle.DotLine)
        lapiz_blanco.setCosmetic(True)
        painter.setPen(lapiz_blanco)
        painter.drawRect(destino.adjusted(1, 1, -2, -2))
        painter.restore()
        if seleccion is not None and bool(getattr(seleccion, "has_selection", False)):
            self._dibujar_tiradores(painter, QRectF(destino.adjusted(0, 0, -1, -1)))

    def _dibujar_tiradores(self, painter: QPainter, rectangulo: QRectF) -> None:
        relleno = QColor("#ffffff")
        borde = QColor("#3a3a3a")
        lado = 7.0
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        lapiz = QPen(borde, 1)
        lapiz.setCosmetic(True)
        painter.setPen(lapiz)
        painter.setBrush(relleno)
        centro = rectangulo.center()
        puntos = (
            rectangulo.topLeft(),
            QPointF(centro.x(), rectangulo.top()),
            rectangulo.topRight(),
            QPointF(rectangulo.right(), centro.y()),
            rectangulo.bottomRight(),
            QPointF(centro.x(), rectangulo.bottom()),
            rectangulo.bottomLeft(),
            QPointF(rectangulo.left(), centro.y()),
        )
        for punto in puntos:
            painter.drawRect(QRectF(punto.x() - lado / 2, punto.y() - lado / 2, lado, lado))
        painter.restore()

    def _dibujar_objeto_editable(self, painter: QPainter) -> None:
        """Marco discontinuo y tiradores de la forma que todavía se puede editar."""

        metodo = getattr(self.controlador_herramientas, "overlay", None)
        datos = metodo() if callable(metodo) else None
        if not datos:
            return
        painter.save()
        try:
            if datos.get("kind") == "line":
                puntos = [self.document_to_screen(punto) for punto in datos.get("points", [])]
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                lapiz = QPen(QColor("#3a3a3a"), 1)
                lapiz.setCosmetic(True)
                painter.setPen(lapiz)
                painter.setBrush(QColor("#ffffff"))
                for punto in puntos:
                    painter.drawEllipse(punto, 4.5, 4.5)
                return
            rect_doc = datos.get("rect")
            if not isinstance(rect_doc, QRectF):
                return
            a = self.document_to_screen(rect_doc.topLeft())
            b = self.document_to_screen(rect_doc.bottomRight())
            rectangulo = QRectF(a, b).normalized()
            for color, estilo, desfase in ((QColor("#111111"), Qt.PenStyle.DashLine, 0), (QColor("#ffffff"), Qt.PenStyle.DotLine, 0)):
                lapiz = QPen(color, 1, estilo)
                lapiz.setCosmetic(True)
                painter.setPen(lapiz)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rectangulo.adjusted(desfase, desfase, -desfase, -desfase))
        finally:
            painter.restore()
        if datos.get("kind") != "line":
            self._dibujar_tiradores(painter, rectangulo)

    def _dibujar_contorno_herramienta(self, painter: QPainter) -> None:
        """Muestra el tamaño real del borrador y del pincel bajo el cursor."""

        if self._puntero is None:
            return
        tool_id = str(getattr(self.controlador_herramientas, "active_tool_id", ""))
        if tool_id not in {"eraser", "brush"}:
            return
        ajustes = getattr(self.documento, "tool_settings", None)
        herramienta = getattr(self.controlador_herramientas, "active_tool", None)
        ancho = getattr(herramienta, "_width", None)
        try:
            tamano = float(ancho(ajustes)) if callable(ancho) else float(getattr(ajustes, "brush_size", 1.0))
        except (TypeError, ValueError):
            tamano = float(getattr(ajustes, "brush_size", 1.0))
        lado = tamano * self.zoom
        if lado < 4:
            return
        centro = self.document_to_screen(self._puntero)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for color, ancho in ((QColor(255, 255, 255, 200), 3), (QColor(30, 30, 30, 220), 1)):
            lapiz = QPen(color, ancho)
            lapiz.setCosmetic(True)
            painter.setPen(lapiz)
            area = QRectF(centro.x() - lado / 2, centro.y() - lado / 2, lado, lado)
            if tool_id == "eraser":
                painter.drawRect(area)
            else:
                painter.drawEllipse(area)
        painter.restore()

    def _dibujar_redimension_previa(self, painter: QPainter) -> None:
        if self._redimension_previa is None:
            return
        ancho, alto, ancla = self._redimension_previa
        lienzo = self.canvas_rect()
        ancho_px = round(ancho * self.zoom)
        alto_px = round(alto * self.zoom)
        x = lienzo.right() + 1 - ancho_px if "right" in ancla else lienzo.left()
        y = lienzo.bottom() + 1 - alto_px if ancla.startswith("bottom") else lienzo.top()
        painter.save()
        lapiz = QPen(QColor("#2b2b2b") if not self.tema_oscuro else QColor("#e6e6e6"), 1, Qt.PenStyle.DashLine)
        lapiz.setCosmetic(True)
        painter.setPen(lapiz)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRect(x, y, max(1, ancho_px), max(1, alto_px)))
        painter.restore()

    def _dibujar_cuadricula(self, painter: QPainter, rectangulo: QRect) -> None:
        salto_documento = 1 if self.zoom >= 4.0 else 10
        salto = salto_documento * self.zoom
        if salto < 4:
            return

        painter.save()
        lapiz = QPen(QColor(65, 65, 65, 72), 1)
        lapiz.setCosmetic(True)
        painter.setPen(lapiz)

        x = float(rectangulo.left())
        while x <= rectangulo.right():
            painter.drawLine(round(x), rectangulo.top(), round(x), rectangulo.bottom())
            x += salto

        y = float(rectangulo.top())
        while y <= rectangulo.bottom():
            painter.drawLine(rectangulo.left(), round(y), rectangulo.right(), round(y))
            y += salto
        painter.restore()

    def _dibujar_reglas(self, painter: QPainter, rectangulo: QRect) -> None:
        paleta = colors(self.tema_oscuro)
        regla_fondo = QColor(paleta["ribbon"])
        texto = QColor(paleta["label"])
        borde = QColor(paleta["separator"])
        regla_horizontal = QRect(rectangulo.left(), M.CANVAS_MARGIN_TOP, rectangulo.width(), M.RULER_SIZE)
        regla_vertical = QRect(M.CANVAS_MARGIN, rectangulo.top(), M.RULER_SIZE, rectangulo.height())
        painter.fillRect(regla_horizontal, regla_fondo)
        painter.fillRect(regla_vertical, regla_fondo)
        painter.setPen(QPen(borde, 1))
        painter.drawRect(regla_horizontal.adjusted(0, 0, -1, -1))
        painter.drawRect(regla_vertical.adjusted(0, 0, -1, -1))

        paso = self._paso_regla()
        painter.setPen(QPen(texto, 1))
        fuente = painter.font()
        fuente.setPointSize(7)
        painter.setFont(fuente)

        ancho_documento = int(getattr(self.documento, "width", 0))
        alto_documento = int(getattr(self.documento, "height", 0))

        for valor in range(0, ancho_documento + 1, paso):
            x = round(rectangulo.left() + valor * self.zoom)
            painter.drawLine(x, regla_horizontal.bottom() - 6, x, regla_horizontal.bottom())
            painter.drawText(x + 2, regla_horizontal.top() + 10, str(valor))

        for valor in range(0, alto_documento + 1, paso):
            y = round(rectangulo.top() + valor * self.zoom)
            painter.drawLine(regla_vertical.right() - 6, y, regla_vertical.right(), y)
            if valor:
                painter.save()
                painter.translate(regla_vertical.left() + 9, y + 2)
                painter.rotate(-90)
                painter.drawText(0, 0, str(valor))
                painter.restore()

    def _paso_regla(self) -> int:
        if self.zoom >= 4:
            return 10
        if self.zoom >= 1:
            return 50
        if self.zoom >= 0.5:
            return 100
        return 250

    # ------------------------------------------------------------------
    # Eventos del usuario
    def _informar_modificadores(self, event: Any) -> None:
        metodo = getattr(self.controlador_herramientas, "set_modifiers", None)
        if callable(metodo):
            modificadores = event.modifiers()
            metodo(
                bool(modificadores & Qt.KeyboardModifier.ShiftModifier),
                bool(modificadores & Qt.KeyboardModifier.ControlModifier),
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            super().mousePressEvent(event)
            return

        manejador = self._manejador_en(event.position())
        pendiente = getattr(self.controlador_herramientas, "has_pending", lambda: False)()
        if event.button() == Qt.MouseButton.LeftButton and manejador is not None and not pendiente:
            self._manejador_lienzo = manejador
            self._redimension_previa = None
            self.setCursor(self._cursor_manejador(manejador))
            event.accept()
            return

        punto = self.screen_to_document(event.position())
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.RightButton and self._quiere_menu_contextual(punto):
            # El clic derecho con Seleccionar abre su menú.
            self.menuContextualSolicitado.emit(event.globalPosition().toPoint())
            event.accept()
            return
        self._informar_modificadores(event)
        self._dibujando = True
        self._ultimo_punto = QPointF(punto)
        metodo = getattr(self.controlador_herramientas, "pointer_down", None)
        if callable(metodo):
            metodo(punto, self._resolver_boton(event.button()))
        if self._es_aerografo():
            self._temporizador_spray.start()
        event.accept()

    def _es_aerografo(self) -> bool:
        if str(getattr(self.controlador_herramientas, "active_tool_id", "")) != "brush":
            return False
        ajustes = getattr(self.documento, "tool_settings", None)
        return str(getattr(ajustes, "brush_type", "")) in {"airbrush", "spray"}

    def _rociar(self) -> None:
        if not self._dibujando or self._ultimo_punto is None:
            self._temporizador_spray.stop()
            return
        metodo = getattr(self.controlador_herramientas, "pointer_move", None)
        if callable(metodo):
            metodo(QPointF(self._ultimo_punto))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        punto = self.screen_to_document(event.position())
        self._puntero = QPointF(punto)
        if self._punto_dentro(punto):
            self.punteroMovido.emit(int(punto.x()), int(punto.y()))
        else:
            # Fuera de la hoja no se muestra ninguna posición.
            self.punteroSalio.emit()

        if self._manejador_lienzo is not None:
            self._redimension_previa = self._calcular_redimension(
                self._manejador_lienzo,
                punto,
            )
            self.update()
            return

        if self._dibujando and event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
            self._informar_modificadores(event)
            self._ultimo_punto = QPointF(punto)
            metodo = getattr(self.controlador_herramientas, "pointer_move", None)
            if callable(metodo):
                metodo(punto)
            return

        manejador = self._manejador_en(event.position())
        pendiente = getattr(self.controlador_herramientas, "has_pending", lambda: False)()
        if manejador is not None and not pendiente:
            self.setCursor(self._cursor_manejador(manejador))
            self.update()
            return

        herramienta = getattr(self.controlador_herramientas, "active_tool", None)
        base = getattr(herramienta, "cursor", Qt.CursorShape.CrossCursor)
        cursor_en = getattr(self.controlador_herramientas, "cursor_at", None)
        cursor = cursor_en(punto) if callable(cursor_en) else None
        if cursor is None or cursor == base:
            tool_id = str(getattr(self.controlador_herramientas, "active_tool_id", ""))
            cursor = cursor_herramienta(tool_id) or base
        self.setCursor(cursor)
        self.update()

    def _quiere_menu_contextual(self, punto: QPointF) -> bool:
        tool_id = str(getattr(self.controlador_herramientas, "active_tool_id", ""))
        if tool_id in {"select", "freeform_select", "free_select", "rectangular_select"}:
            return True
        seleccion = getattr(self.documento, "selection", None)
        contiene = getattr(seleccion, "contains", None)
        return bool(getattr(seleccion, "has_selection", False)) and callable(contiene) and contiene(round(punto.x()), round(punto.y()))

    def contextMenuEvent(self, event) -> None:
        # Tecla «Menú» del teclado.
        if event.reason() == event.Reason.Keyboard:
            self.menuContextualSolicitado.emit(event.globalPos())
            event.accept()
            return
        event.ignore()

    def leaveEvent(self, event) -> None:
        self._puntero = None
        self.punteroSalio.emit()
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._manejador_lienzo is not None:
            previa = self._redimension_previa
            self._manejador_lienzo = None
            self._redimension_previa = None
            if previa is not None:
                self.redimensionLienzoSolicitado.emit(*previa)
            self.update()
            event.accept()
            return

        if not self._dibujando:
            super().mouseReleaseEvent(event)
            return

        self._dibujando = False
        self._temporizador_spray.stop()
        punto = self.screen_to_document(event.position())
        self._informar_modificadores(event)
        metodo = getattr(self.controlador_herramientas, "pointer_up", None)
        if callable(metodo):
            metodo(punto)

        herramienta = getattr(self.controlador_herramientas, "active_tool", None)
        if getattr(herramienta, "id", "") == "text":
            rectangulo = getattr(herramienta, "requested_rect", None)
            if isinstance(rectangulo, QRect) and not rectangulo.isEmpty():
                self.rectanguloTextoSolicitado.emit(QRect(rectangulo))
                herramienta.requested_rect = None
        event.accept()

    def _calcular_redimension(
        self,
        manejador: str,
        punto: QPointF,
    ) -> tuple[int, int, str]:
        ancho_actual = max(1, int(getattr(self.documento, "width", 1)))
        alto_actual = max(1, int(getattr(self.documento, "height", 1)))
        x, y = round(punto.x()), round(punto.y())
        ancho, alto = ancho_actual, alto_actual
        ancla = "top_left"

        if manejador in {"right", "top_right", "bottom_right"}:
            ancho = max(1, min(32768, x))
        elif manejador in {"left", "top_left", "bottom_left"}:
            ancho = max(1, min(32768, ancho_actual - x))

        if manejador in {"bottom", "bottom_left", "bottom_right"}:
            alto = max(1, min(32768, y))
        elif manejador in {"top", "top_left", "top_right"}:
            alto = max(1, min(32768, alto_actual - y))

        anclas = {
            "left": "top_right",
            "top_left": "bottom_right",
            "bottom_left": "top_right",
            "top": "bottom_left",
            "top_right": "bottom_left",
        }
        ancla = anclas.get(manejador, "top_left")
        return ancho, alto, ancla

    def keyPressEvent(self, event: QKeyEvent) -> None:
        paso = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        tecla = event.key()
        controlador = self.controlador_herramientas
        forma_pendiente = bool(getattr(controlador, "has_pending_shape", lambda: False)())

        if tecla in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter) and forma_pendiente:
            # Termina la curva o el polígono y fija la forma, como al hacer clic fuera.
            getattr(controlador, "finish_construction", lambda: None)()
            getattr(controlador, "commit_pending", lambda: False)()
        elif tecla == Qt.Key.Key_Escape:
            self.comandoSeleccionSolicitado.emit("cancelar", 0, 0)
        elif tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.comandoSeleccionSolicitado.emit("confirmar", 0, 0)
        elif tecla in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.comandoSeleccionSolicitado.emit("eliminar", 0, 0)
        else:
            flechas = {
                Qt.Key.Key_Left: (-paso, 0),
                Qt.Key.Key_Right: (paso, 0),
                Qt.Key.Key_Up: (0, -paso),
                Qt.Key.Key_Down: (0, paso),
            }
            if tecla not in flechas:
                super().keyPressEvent(event)
                return
            dx, dy = flechas[tecla]
            if forma_pendiente and getattr(controlador, "nudge_pending", lambda *_: False)(dx, dy):
                event.accept()
                return
            self.comandoSeleccionSolicitado.emit("mover", dx, dy)

        event.accept()

    def _area_desplazable(self) -> QAbstractScrollArea | None:
        padre = self.parentWidget()
        while padre is not None and not isinstance(padre, QAbstractScrollArea):
            padre = padre.parentWidget()
        return padre

    def wheelEvent(self, event: QWheelEvent) -> None:
        modificadores = event.modifiers()
        if modificadores & Qt.KeyboardModifier.ShiftModifier and not modificadores & Qt.KeyboardModifier.ControlModifier:
            area = self._area_desplazable()
            if area is not None:
                barra = area.horizontalScrollBar()
                barra.setValue(barra.value() - event.angleDelta().y())
                event.accept()
                return
        if not modificadores & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return

        actual = round(self.zoom * 100)
        if event.angleDelta().y() > 0:
            siguiente = next((valor for valor in self.PASOS_ZOOM if valor > actual), 800)
        else:
            siguiente = next((valor for valor in reversed(self.PASOS_ZOOM) if valor < actual), 10)
        punto = self.screen_to_document(event.position())
        area = self._area_desplazable()
        if area is not None:
            en_vista = self.mapTo(area.viewport(), event.position().toPoint())
            self.zoomEnPuntoSolicitado.emit(siguiente, punto.x(), punto.y(), float(en_vista.x()), float(en_vista.y()))
        else:
            self.set_zoom_percent(siguiente)
        event.accept()

    # ------------------------------------------------------------------
    # Utilidades internas
    def _conectar_controlador(self, controller: Any) -> None:
        senal = getattr(controller, "changed", None)
        if senal is not None and hasattr(senal, "connect"):
            senal.connect(self.update)

    def _punto_dentro(self, punto: QPointF) -> bool:
        ancho = int(getattr(self.documento, "width", 0))
        alto = int(getattr(self.documento, "height", 0))
        return 0 <= punto.x() < ancho and 0 <= punto.y() < alto

    def _resolver_boton(self, boton_qt: Qt.MouseButton) -> Any:
        actual = getattr(self.controlador_herramientas, "active_button", None)
        tipo_boton = type(actual) if actual is not None else None
        nombre = "SECONDARY" if boton_qt == Qt.MouseButton.RightButton else "PRIMARY"

        if tipo_boton is not None and hasattr(tipo_boton, nombre):
            return getattr(tipo_boton, nombre)

        try:
            from backend.Service.Drawing.base_tool import PointerButton

            return getattr(PointerButton, nombre)
        except ImportError:
            return "secondary" if nombre == "SECONDARY" else "primary"


VistaLienzo = CanvasView
