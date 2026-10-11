from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from backend.Service.Drawing.base_tool import PointerButton, Tool, color_del_boton, normalizar_boton
from backend.Service.Drawing.brush_engine import draw_brush_polyline, draw_brush_segment, normalizar_pincel
from backend.Service.Drawing.commands import LayerImageCommand
from backend.Service.Drawing.drawing_utils import (
    ancho_herramienta,
    buscar_capa,
    crear_imagen_transparente,
    imagenes_iguales,
    invalidar,
    obtener_id_capa,
    valor_config,
)
from backend.Service.Drawing.raster_engine import draw_line, flood_fill


def _opacity(settings: Any, *names: str) -> float:
    value = valor_config(settings, *names, default=1.0)
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _opaque(color: QColor) -> QColor:
    result = QColor(color)
    result.setAlpha(255)
    return result


class _StrokeTool(Tool):
    """Trazo a mano alzada sobre un búfer propio.

    El trazo completo se dibuja opaco en una imagen aparte y se mezcla con la
    capa original usando la opacidad elegida. Así un trazo semitransparente
    no se oscurece donde los segmentos se superponen.

    Con ``smooth`` cada tramo es una curva entre los puntos medios de los
    movimientos del ratón: los trazos rápidos no quedan poligonales. Solo se
    recompone y se guarda en el historial el rectángulo que el trazo toca.
    """

    erase = False
    multiplier = 1.0
    use_brush_width = False
    antialias = True
    smooth = False

    def __init__(self) -> None:
        self._last: QPointF | None = None
        self._smooth_end: QPointF | None = None
        self._before: QImage | None = None
        self._stroke: QImage | None = None
        self._layer_id: str | int | None = None
        self._button = PointerButton.PRIMARY
        self._color = QColor("black")
        self._opacity = 1.0
        self._dirty: QRect | None = None
        self._last_area: QRect | None = None

    def _width(self, settings: Any) -> float:
        return ancho_herramienta(settings, self.use_brush_width) * self.multiplier

    def _use_antialias(self, settings: Any) -> bool:
        return self.antialias and bool(valor_config(settings, "antialiasing", default=True))

    def _stroke_color(self, settings: Any) -> QColor:
        return _opaque(color_del_boton(settings, self._button))

    def _stroke_opacity(self, settings: Any) -> float:
        base = QColor(valor_config(settings, "secondary_color" if self._button is PointerButton.SECONDARY else "primary_color", default=QColor("black")))
        return _opacity(settings, "opacity") * (base.alpha() / 255.0)

    def _paint_segment(self, stroke: QImage, start: QPointF, end: QPointF, settings: Any) -> None:
        draw_line(stroke, start, end, self._color, self._width(settings), False, self._use_antialias(settings))

    def _paint_curve(self, stroke: QImage, desde: QPointF, control: QPointF, hasta: QPointF, settings: Any) -> None:
        painter = QPainter(stroke)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._use_antialias(settings))
            painter.setPen(QPen(self._color, max(1.0, self._width(settings)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if desde == hasta:
                painter.drawPoint(desde)
            else:
                path = QPainterPath(desde)
                path.quadTo(control, hasta)
                painter.drawPath(path)
        finally:
            painter.end()

    def _margin(self, settings: Any) -> int:
        return int(self._width(settings) * 1.6) + 4

    def _composite(self, layer_image: QImage, rect: QRect) -> None:
        if self._before is None or self._stroke is None:
            return
        area = rect.intersected(layer_image.rect())
        if area.isEmpty():
            return
        painter = QPainter(layer_image)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawImage(area.topLeft(), self._before, area)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_DestinationOut
                if self.erase
                else QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.setOpacity(self._opacity)
            painter.drawImage(area.topLeft(), self._stroke, area)
        finally:
            painter.end()

    def _flush(self, layer_image: QImage, rect: QRect) -> None:
        """Mezcla ``rect`` con la capa y recuerda qué zona cambió el trazo."""

        area = rect.intersected(layer_image.rect())
        self._last_area = area
        if area.isEmpty():
            return
        self._dirty = area if self._dirty is None else self._dirty.united(area)
        self._composite(layer_image, area)

    def _dirty_rect(self, start: QPointF, end: QPointF, settings: Any) -> QRect:
        margin = self._margin(settings)
        rect = QRectF(start, end).normalized().toAlignedRect()
        return rect.adjusted(-margin, -margin, margin, margin)

    def _apply(self, layer: Any, start: QPointF, end: QPointF, settings: Any) -> None:
        if self._stroke is None:
            return
        if not self.smooth:
            self._paint_segment(self._stroke, start, end, settings)
            self._flush(layer.image, self._dirty_rect(start, end, settings))
            return
        desde = self._smooth_end if self._smooth_end is not None else QPointF(start)
        hasta = _mid(start, end) if start != end else QPointF(end)
        self._paint_curve(self._stroke, desde, start, hasta, settings)
        self._smooth_end = hasta
        margen = self._margin(settings)
        # La curva queda dentro del triángulo de sus tres puntos de control.
        xs = (desde.x(), start.x(), hasta.x())
        ys = (desde.y(), start.y(), hasta.y())
        area = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))).toAlignedRect()
        self._flush(layer.image, area.adjusted(-margen, -margen, margen, margen))

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        layer = document.active_layer
        self._before = layer.image.copy()
        self._stroke = crear_imagen_transparente(layer.image.width(), layer.image.height())
        self._layer_id = obtener_id_capa(layer, document)
        self._last = QPointF(point)
        self._smooth_end = QPointF(point)
        self._dirty = None
        self._button = normalizar_boton(button)
        self._color = self._stroke_color(settings)
        self._opacity = self._stroke_opacity(settings)
        self._apply(layer, point, point, settings)
        invalidar(document, rect=self._last_area)

    def pointer_move(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        if self._last is None or self._layer_id is None:
            return
        layer = buscar_capa(document, self._layer_id)
        if layer is None:
            self.cancel()
            return
        if self.shift:
            # Mayús mantiene el trazo en horizontal o vertical.
            dx, dy = abs(point.x() - self._last.x()), abs(point.y() - self._last.y())
            point = QPointF(point.x(), self._last.y()) if dx >= dy else QPointF(self._last.x(), point.y())
        self._apply(layer, self._last, point, settings)
        self._last = QPointF(point)
        invalidar(document, rect=self._last_area)

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        if self._last is None or self._before is None or self._layer_id is None:
            self.cancel()
            return None
        self.pointer_move(document, point, button, settings)
        if self.smooth:
            # Las curvas llegan hasta el punto medio; este último tramo las
            # termina justo en el cursor.
            self.pointer_move(document, point, button, settings)
        layer = buscar_capa(document, self._layer_id)
        before, layer_id, rect = self._before, self._layer_id, self._dirty
        self._release()
        if layer is None or rect is None or rect.isEmpty():
            return None
        antes, despues = before.copy(rect), layer.image.copy(rect)
        if imagenes_iguales(antes, despues):
            return None
        return LayerImageCommand(layer_id=layer_id, before=antes, after=despues, label=self.name, rect=QRect(rect))

    def _release(self) -> None:
        self._last = None
        self._smooth_end = None
        self._before = None
        self._stroke = None
        self._layer_id = None
        self._dirty = None
        self._last_area = None

    def cancel(self, document: Any | None = None) -> None:
        if document is not None and self._before is not None and self._layer_id is not None:
            layer = buscar_capa(document, self._layer_id)
            if layer is not None:
                layer.image = self._before.copy()
                invalidar(document, modified=False)
        self._release()


class PencilTool(_StrokeTool):
    id = "pencil"
    name = "Lápiz"
    cursor = Qt.CursorShape.CrossCursor
    smooth = True

    def _width(self, settings: Any) -> float:
        return ancho_herramienta(settings)

    def _use_antialias(self, settings: Any) -> bool:
        # El lápiz de 1 px conserva el borde duro; con más grosor un
        # borde escalonado se ve mal, así que se suaviza.
        return self._width(settings) >= 2.0 and bool(valor_config(settings, "antialiasing", default=True))


# Opacidad propia de algunos pinceles: el marcador deja ver lo que
# hay debajo aunque la opacidad general esté al 100 %.
BRUSH_OPACITY = {"marker": 0.5}


# Grosor real de cada pincel respecto al tamaño elegido (1, 3, 5 u 8 px),
# para que cada uno se vea equilibrado con el mismo tamaño de la lista.
BRUSH_SCALE = {
    "round": 1.0,
    "calligraphy": 2.5,
    "calligraphy_pen": 2.2,
    "airbrush": 3.0,
    "oil": 2.5,
    "crayon": 2.0,
    "marker": 2.5,
    "natural_pencil": 1.5,
    "watercolor": 3.0,
}
BRUSH_MIN_WIDTH = {"airbrush": 8.0, "oil": 4.0, "watercolor": 5.0, "calligraphy": 3.0, "calligraphy_pen": 3.0}


def _mid(a: QPointF, b: QPointF) -> QPointF:
    return QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)


def _quad_points(start: QPointF, control: QPointF, end: QPointF) -> list[QPointF]:
    longitud = (control - start).manhattanLength() + (end - control).manhattanLength()
    pasos = max(1, int(longitud / 1.5))
    puntos = []
    for indice in range(pasos + 1):
        t = indice / pasos
        u = 1.0 - t
        puntos.append(
            QPointF(
                u * u * start.x() + 2 * u * t * control.x() + t * t * end.x(),
                u * u * start.y() + 2 * u * t * control.y() + t * t * end.y(),
            )
        )
    return puntos


class BrushTool(_StrokeTool):
    """Pinceles con trazo suavizado.

    Cada tramo se dibuja como una curva entre los puntos medios de los
    movimientos del ratón, así los trazos rápidos no quedan poligonales.
    """

    id = "brush"
    name = "Pincel"
    use_brush_width = True

    smooth = True

    def _brush_type(self, settings: Any) -> str:
        return normalizar_pincel(str(valor_config(settings, "brush_type", default="round")))

    def _width(self, settings: Any) -> float:
        tipo = self._brush_type(settings)
        ancho = ancho_herramienta(settings, True) * BRUSH_SCALE.get(tipo, 1.0)
        return max(BRUSH_MIN_WIDTH.get(tipo, 1.0), ancho)

    def _use_antialias(self, settings: Any) -> bool:
        return True

    def _paint_curve(self, stroke: QImage, desde: QPointF, control: QPointF, hasta: QPointF, settings: Any) -> None:
        tipo = self._brush_type(settings)
        if tipo == "round":
            super()._paint_curve(stroke, desde, control, hasta, settings)
            return
        ancho = self._width(settings)
        puntos = _quad_points(desde, control, hasta)
        if len(puntos) == 1 or desde == hasta:
            draw_brush_segment(stroke, desde, desde, self._color, ancho, tipo)
        else:
            draw_brush_polyline(stroke, puntos, self._color, ancho, tipo)

    def _stroke_opacity(self, settings: Any) -> float:
        return super()._stroke_opacity(settings) * BRUSH_OPACITY.get(self._brush_type(settings), 1.0)

    def _margin(self, settings: Any) -> int:
        return int(self._width(settings) * 2.2) + 6

    def _paint_segment(self, stroke: QImage, start: QPointF, end: QPointF, settings: Any) -> None:
        draw_brush_segment(stroke, start, end, self._color, self._width(settings), self._brush_type(settings))

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        command = super().pointer_up(document, point, button, settings)
        if command is not None:
            command.label = BRUSH_NAMES.get(self._brush_type(settings), "Pincel")
        return command


BRUSH_NAMES = {
    "round": "Pincel",
    "calligraphy": "Pincel de caligrafía",
    "calligraphy_pen": "Pluma de caligrafía",
    "airbrush": "Aerógrafo",
    "oil": "Pincel al óleo",
    "crayon": "Crayón",
    "marker": "Marcador",
    "natural_pencil": "Lápiz natural",
    "watercolor": "Pincel de acuarela",
}


class EraserTool(_StrokeTool):
    """Borrador.

    Con el botón principal borra (deja transparente la capa). Con el botón
    secundario funciona como «borrador de color»: solo cambia los píxeles del
    color 1 por el color 2.
    """

    id = "eraser"
    name = "Borrador"
    cursor = Qt.CursorShape.PointingHandCursor
    erase = True
    multiplier = 1.0
    use_brush_width = True

    def _stroke_color(self, settings: Any) -> QColor:
        return QColor(0, 0, 0, 255)

    def _stroke_opacity(self, settings: Any) -> float:
        return _opacity(settings, "eraser_opacity", "opacity")

    def _paint_segment(self, stroke: QImage, start: QPointF, end: QPointF, settings: Any) -> None:
        # El borrador es un cuadrado sin suavizado que barre el trazo.
        draw_square_sweep(stroke, start, end, self._width(settings), self._color)

    def _composite(self, layer_image: QImage, rect: QRect) -> None:
        if self._button is not PointerButton.SECONDARY:
            super()._composite(layer_image, rect)
            return
        if self._before is None or self._stroke is None:
            return
        area = rect.intersected(layer_image.rect())
        if area.isEmpty():
            return
        replace_color_under_mask(layer_image, self._before, self._stroke, area, self._target, self._replacement)

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        self._target = QColor(valor_config(settings, "primary_color", default=QColor("black")))
        self._replacement = QColor(valor_config(settings, "secondary_color", default=QColor("white")))
        super().pointer_down(document, point, button, settings)

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        secondary = self._button is PointerButton.SECONDARY
        command = super().pointer_up(document, point, button, settings)
        if command is not None and secondary:
            command.label = "Borrador de color"
        return command


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    puntos = sorted(set(points))
    if len(puntos) <= 2:
        return puntos

    def giro(o, a, b):  # noqa: ANN001, ANN202
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inferior: list[tuple[float, float]] = []
    for punto in puntos:
        while len(inferior) >= 2 and giro(inferior[-2], inferior[-1], punto) <= 0:
            inferior.pop()
        inferior.append(punto)
    superior: list[tuple[float, float]] = []
    for punto in reversed(puntos):
        while len(superior) >= 2 and giro(superior[-2], superior[-1], punto) <= 0:
            superior.pop()
        superior.append(punto)
    return inferior[:-1] + superior[:-1]


def draw_square_sweep(image: QImage, start: QPointF, end: QPointF, size: float, color: QColor) -> None:
    """Rellena el área que recorre un cuadrado alineado al moverse de start a end."""

    lado = max(1.0, float(size))
    mitad = lado / 2.0
    esquinas = []
    for centro in (start, end):
        x0, y0 = round(centro.x() - mitad), round(centro.y() - mitad)
        esquinas += [(x0, y0), (x0 + lado, y0), (x0, y0 + lado), (x0 + lado, y0 + lado)]
    poligono = QPolygonF([QPointF(x, y) for x, y in _convex_hull(esquinas)])
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(poligono)
    finally:
        painter.end()


def replace_color_under_mask(
    target: QImage,
    before: QImage,
    mask: QImage,
    area: QRect,
    color: QColor,
    replacement: QColor,
    tolerance: int = 24,
) -> None:
    """Sustituye ``color`` por ``replacement`` donde la máscara está pintada."""

    region_before = before.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
    region_mask = mask.copy(area).convertToFormat(QImage.Format.Format_RGBA8888)
    height, width = region_before.height(), region_before.width()

    def view(image: QImage) -> np.ndarray:
        raw = np.frombuffer(image.bits(), dtype=np.uint8, count=image.sizeInBytes())
        return raw.reshape(height, image.bytesPerLine())[:, : width * 4].reshape(height, width, 4)

    pixels = view(region_before)
    covered = view(region_mask)[:, :, 3] > 0
    reference = np.array([color.red(), color.green(), color.blue()], dtype=np.int16)
    matches = np.max(np.abs(pixels[:, :, :3].astype(np.int16) - reference), axis=2) <= tolerance
    matches &= pixels[:, :, 3] > 0
    selected = covered & matches
    if selected.any():
        pixels[selected] = np.array(
            [replacement.red(), replacement.green(), replacement.blue(), replacement.alpha()], dtype=np.uint8
        )
    painter = QPainter(target)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(area.topLeft(), region_before)
    finally:
        painter.end()


class FillTool(Tool):
    id = "fill"
    name = "Relleno"

    def __init__(self) -> None:
        self._command: LayerImageCommand | None = None

    def pointer_down(self, document: Any, point: QPointF, button: Any, settings: Any) -> None:
        layer = document.active_layer
        before = layer.image.copy()
        tolerance = valor_config(settings, "fill_tolerance", default=0)
        try:
            tolerance = int(tolerance)
        except (TypeError, ValueError):
            tolerance = 0
        changed = flood_fill(
            layer.image,
            QPoint(round(point.x()), round(point.y())),
            color_del_boton(settings, button),
            tolerance,
        )
        if not changed:
            self._command = None
            return
        invalidar(document)
        self._command = LayerImageCommand(
            layer_id=obtener_id_capa(layer, document),
            before=before,
            after=layer.image.copy(),
            label=self.name,
        )

    def pointer_up(self, document: Any, point: QPointF, button: Any, settings: Any) -> LayerImageCommand | None:
        command = self._command
        self._command = None
        return command

    def cancel(self, document: Any | None = None) -> None:
        if document is not None and self._command is not None:
            self._command.undo(document)
        self._command = None
