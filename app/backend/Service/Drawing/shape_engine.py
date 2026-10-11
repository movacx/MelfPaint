from __future__ import annotations

import math
import unicodedata
from functools import lru_cache
from typing import Iterable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPolygonF,
    QTransform,
)

from backend.Service.Drawing.drawing_utils import crear_imagen_transparente


SHAPE_ALIASES = {
    "linea": "line",
    "curva": "curve",
    "ovalo": "ellipse",
    "elipse": "ellipse",
    "rectangulo": "rectangle",
    "rectangulo_redondeado": "rounded_rectangle",
    "triangulo": "triangle",
    "triangulo_rectangulo": "right_triangle",
    "rombo": "diamond",
    "pentagono": "pentagon",
    "hexagono": "hexagon",
    "flecha_derecha": "right_arrow",
    "flecha_izquierda": "left_arrow",
    "flecha_arriba": "up_arrow",
    "flecha_abajo": "down_arrow",
    "estrella_4": "star_4",
    "estrella_5": "star_5",
    "estrella_6": "star_6",
    "llamada_rectangular": "rectangular_callout",
    "llamada": "speech_callout",
    "rounded_rectangular_callout": "speech_callout",
    "llamada_ovalada": "oval_callout",
    "pensamiento": "thought_callout",
    "cloud_callout": "thought_callout",
    "nube": "cloud",
    "corazon": "heart",
    "rayo": "lightning",
    "bolt": "lightning",
}


def _plain_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "rectangle"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.strip().lower().replace("-", "_").replace(" ", "_")
    return SHAPE_ALIASES.get(normalized, normalized)


def _normalized_rect(start: QPointF, end: QPointF) -> QRectF:
    left, right = sorted((float(start.x()), float(end.x())))
    top, bottom = sorted((float(start.y()), float(end.y())))
    return QRectF(left, top, max(1.0, right - left), max(1.0, bottom - top))


def _regular_polygon(rect: QRectF, sides: int, rotation: float = -math.pi / 2) -> QPolygonF:
    center = rect.center()
    radius_x, radius_y = rect.width() / 2.0, rect.height() / 2.0
    return QPolygonF(
        [
            QPointF(
                center.x() + math.cos(rotation + index * math.tau / sides) * radius_x,
                center.y() + math.sin(rotation + index * math.tau / sides) * radius_y,
            )
            for index in range(sides)
        ]
    )


def _fit_to_rect(polygon: QPolygonF, rect: QRectF) -> QPolygonF:
    """Escala el polígono para que ocupe todo el rectángulo."""

    bounds = polygon.boundingRect()
    if bounds.width() <= 0 or bounds.height() <= 0:
        return polygon
    sx = rect.width() / bounds.width()
    sy = rect.height() / bounds.height()
    return QPolygonF(
        [
            QPointF(rect.left() + (point.x() - bounds.left()) * sx, rect.top() + (point.y() - bounds.top()) * sy)
            for point in polygon
        ]
    )


def _star_polygon(rect: QRectF, points: int) -> QPolygonF:
    center = rect.center()
    outer_x, outer_y = rect.width() / 2.0, rect.height() / 2.0
    inner_ratio = 0.42 if points != 4 else 0.32
    result: list[QPointF] = []
    for index in range(points * 2):
        radius = 1.0 if index % 2 == 0 else inner_ratio
        angle = -math.pi / 2 + index * math.pi / points
        result.append(QPointF(center.x() + math.cos(angle) * outer_x * radius, center.y() + math.sin(angle) * outer_y * radius))
    return QPolygonF(result)


def _scale_points(rect: QRectF, values: Iterable[tuple[float, float]]) -> QPolygonF:
    return QPolygonF([QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height()) for x, y in values])


def _arrow_polygon(rect: QRectF, direction: str) -> QPolygonF:
    values = {
        "right_arrow": [(0.0, 0.32), (0.60, 0.32), (0.60, 0.05), (1.0, 0.5), (0.60, 0.95), (0.60, 0.68), (0.0, 0.68)],
        "left_arrow": [(1.0, 0.32), (0.40, 0.32), (0.40, 0.05), (0.0, 0.5), (0.40, 0.95), (0.40, 0.68), (1.0, 0.68)],
        "up_arrow": [(0.32, 1.0), (0.32, 0.40), (0.05, 0.40), (0.5, 0.0), (0.95, 0.40), (0.68, 0.40), (0.68, 1.0)],
        "down_arrow": [(0.32, 0.0), (0.32, 0.60), (0.05, 0.60), (0.5, 1.0), (0.95, 0.60), (0.68, 0.60), (0.68, 0.0)],
    }
    return _scale_points(rect, values[direction])


def _path_from_polygon(polygon: QPolygonF) -> QPainterPath:
    path = QPainterPath()
    if polygon.isEmpty():
        return path
    path.addPolygon(polygon)
    path.closeSubpath()
    return path


def _cloud_path(rect: QRectF) -> QPainterPath:
    pieces = [
        QRectF(rect.left() + rect.width() * 0.06, rect.top() + rect.height() * 0.36, rect.width() * 0.42, rect.height() * 0.53),
        QRectF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.10, rect.width() * 0.42, rect.height() * 0.64),
        QRectF(rect.left() + rect.width() * 0.47, rect.top() + rect.height() * 0.02, rect.width() * 0.39, rect.height() * 0.62),
        QRectF(rect.left() + rect.width() * 0.57, rect.top() + rect.height() * 0.31, rect.width() * 0.39, rect.height() * 0.57),
        QRectF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.48, rect.width() * 0.60, rect.height() * 0.45),
    ]
    path = QPainterPath()
    for piece in pieces:
        ellipse = QPainterPath()
        ellipse.addEllipse(piece)
        path = ellipse if path.isEmpty() else path.united(ellipse)
    return path


def _heart_path(rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(rect.center().x(), rect.bottom())
    path.cubicTo(rect.left() - rect.width() * 0.05, rect.top() + rect.height() * 0.56, rect.left(), rect.top(), rect.center().x(), rect.top() + rect.height() * 0.28)
    path.cubicTo(rect.right(), rect.top(), rect.right() + rect.width() * 0.05, rect.top() + rect.height() * 0.56, rect.center().x(), rect.bottom())
    path.closeSubpath()
    return path


def _callout_path(rect: QRectF, kind: str) -> QPainterPath:
    if kind == "rectangular_callout":
        return _path_from_polygon(
            _scale_points(rect, [(0.0, 0.0), (1.0, 0.0), (1.0, 0.72), (0.62, 0.72), (0.48, 1.0), (0.45, 0.72), (0.0, 0.72)])
        )
    if kind == "speech_callout":
        path = QPainterPath()
        body = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.78)
        path.addRoundedRect(body, min(18.0, body.width() * 0.15), min(18.0, body.height() * 0.2))
        tail = _path_from_polygon(_scale_points(rect, [(0.42, 0.72), (0.60, 0.72), (0.48, 1.0)]))
        return path.united(tail)
    if kind == "oval_callout":
        path = QPainterPath()
        path.addEllipse(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.78))
        tail = _path_from_polygon(_scale_points(rect, [(0.30, 0.66), (0.46, 0.74), (0.18, 1.0)]))
        return path.united(tail)
    body = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.74)
    path = _cloud_path(body)
    path.addEllipse(QRectF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.78, rect.width() * 0.12, rect.height() * 0.10))
    path.addEllipse(QRectF(rect.left() + rect.width() * 0.12, rect.top() + rect.height() * 0.91, rect.width() * 0.07, rect.height() * 0.07))
    return path


def shape_path(shape: str, start: QPointF, end: QPointF, points: list[QPointF] | None = None) -> QPainterPath:
    shape = _plain_name(shape)
    rect = _normalized_rect(start, end)
    path = QPainterPath()

    if shape == "line":
        path.moveTo(start)
        path.lineTo(end)
    elif shape == "curve":
        control = points or []
        path.moveTo(start)
        if len(control) >= 2:
            path.cubicTo(control[0], control[1], end)
        elif len(control) == 1:
            path.quadTo(control[0], end)
        else:
            lift = max(12.0, abs(end.y() - start.y()) * 0.35 + abs(end.x() - start.x()) * 0.12)
            path.cubicTo(QPointF(start.x() + (end.x() - start.x()) * 0.33, start.y() - lift), QPointF(start.x() + (end.x() - start.x()) * 0.67, end.y() + lift), end)
    elif shape in {"ellipse", "oval"}:
        path.addEllipse(rect)
    elif shape == "rectangle":
        path.addRect(rect)
    elif shape in {"rounded_rectangle", "round_rectangle"}:
        radius = max(2.0, min(rect.width(), rect.height()) * 0.16)
        path.addRoundedRect(rect, radius, radius)
    elif shape == "polygon":
        if points and len(points) >= 3:
            polygon = QPolygonF([QPointF(point) for point in points])
        else:
            polygon = _scale_points(rect, [(0.02, 0.38), (0.28, 0.02), (0.72, 0.12), (0.98, 0.55), (0.72, 0.96), (0.20, 0.88)])
        path = _path_from_polygon(polygon)
    elif shape == "triangle":
        path = _path_from_polygon(_scale_points(rect, [(0.5, 0.0), (1.0, 1.0), (0.0, 1.0)]))
    elif shape == "right_triangle":
        path = _path_from_polygon(_scale_points(rect, [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0)]))
    elif shape == "diamond":
        path = _path_from_polygon(_scale_points(rect, [(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)]))
    elif shape in {"pentagon", "hexagon"}:
        sides = 5 if shape == "pentagon" else 6
        rotation = -math.pi / 2 if sides == 5 else 0.0
        path = _path_from_polygon(_fit_to_rect(_regular_polygon(rect, sides, rotation), rect))
    elif shape in {"right_arrow", "left_arrow", "up_arrow", "down_arrow"}:
        path = _path_from_polygon(_arrow_polygon(rect, shape))
    elif shape.startswith("star"):
        try:
            amount = int(shape.rsplit("_", 1)[-1])
        except ValueError:
            amount = 5
        path = _path_from_polygon(_fit_to_rect(_star_polygon(rect, max(4, min(12, amount))), rect))
    elif shape in {"rectangular_callout", "speech_callout", "oval_callout", "thought_callout", "callout"}:
        path = _callout_path(rect, "speech_callout" if shape == "callout" else shape)
    elif shape == "cloud":
        path = _cloud_path(rect)
    elif shape == "heart":
        path = _heart_path(rect)
    elif shape in {"lightning", "lightning_bolt"}:
        path = _path_from_polygon(_scale_points(rect, [(0.54, 0.0), (0.16, 0.56), (0.43, 0.56), (0.30, 1.0), (0.86, 0.38), (0.58, 0.38)]))
    else:
        path.addRect(rect)
    if shape in _FIT_TO_BOX:
        path = _fit_path(path, rect)
    return path


# Formas curvas cuya geometría base no toca los cuatro lados del rectángulo.
_FIT_TO_BOX = {"heart", "cloud", "thought_callout", "speech_callout", "oval_callout", "rectangular_callout", "lightning"}


def _fit_path(path: QPainterPath, rect: QRectF) -> QPainterPath:
    """Escala el trazado para que ocupe exactamente el rectángulo."""

    bounds = path.boundingRect()
    if bounds.width() <= 0 or bounds.height() <= 0:
        return path
    transform = QTransform()
    transform.translate(rect.left(), rect.top())
    transform.scale(rect.width() / bounds.width(), rect.height() / bounds.height())
    transform.translate(-bounds.left(), -bounds.top())
    return transform.map(path)


# Estilos de contorno y relleno: color sólido y texturas de pincel.
TEXTURE_STYLES = {"crayon", "marker", "oil", "natural_pencil", "watercolor"}
STYLE_ALIASES = {
    "solido": "solid",
    "sólido": "solid",
    "solid_color": "solid",
    "crayón": "crayon",
    "marcador": "marker",
    "oleo": "oil",
    "óleo": "oil",
    "pencil": "natural_pencil",
    "lapiz_natural": "natural_pencil",
    "acuarela": "watercolor",
    "sin_contorno": "none",
    "sin_relleno": "none",
    "transparent": "none",
}
_TILE = 128


def normalize_style(style: str | None) -> str:
    value = str(style or "solid").strip().lower().replace(" ", "_").replace("-", "_")
    return STYLE_ALIASES.get(value, value)


def _periodic_noise(seed: int, sigma_x: float, sigma_y: float) -> np.ndarray:
    """Ruido suave y repetible en mosaico (se filtra en el dominio de Fourier)."""

    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((_TILE, _TILE))
    fy = np.fft.fftfreq(_TILE)[:, None]
    fx = np.fft.fftfreq(_TILE)[None, :]
    filtro = np.exp(-((fx / max(1e-4, sigma_x)) ** 2 + (fy / max(1e-4, sigma_y)) ** 2))
    campo = np.real(np.fft.ifft2(np.fft.fft2(noise) * filtro))
    campo -= campo.min()
    maximo = campo.max()
    return campo / maximo if maximo > 0 else campo


@lru_cache(maxsize=16)
def _texture_profile(style: str) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (alfa 0..1, brillo relativo) para cada textura."""

    if style == "crayon":
        grano = _periodic_noise(11, 0.45, 0.45)
        veta = _periodic_noise(12, 0.03, 0.30)
        alfa = np.clip((grano * 0.65 + veta * 0.35 - 0.30) * 2.6, 0.0, 1.0)
        brillo = 0.88 + veta * 0.24
    elif style == "oil":
        veta = _periodic_noise(21, 0.015, 0.22)
        detalle = _periodic_noise(22, 0.25, 0.25)
        alfa = np.clip(0.80 + veta * 0.20, 0.0, 1.0)
        brillo = 0.78 + veta * 0.32 + detalle * 0.10
    elif style == "natural_pencil":
        grano = _periodic_noise(31, 0.50, 0.50)
        veta = _periodic_noise(32, 0.05, 0.40)
        alfa = np.clip((grano * 0.55 + veta * 0.45 - 0.30) * 2.6, 0.0, 0.92)
        brillo = np.full_like(alfa, 1.0)
    elif style == "watercolor":
        mancha = _periodic_noise(41, 0.035, 0.035)
        detalle = _periodic_noise(42, 0.12, 0.12)
        alfa = np.clip(0.22 + mancha * 0.38 + detalle * 0.12, 0.0, 1.0)
        brillo = 0.95 + mancha * 0.10
    else:  # marker
        alfa = np.full((_TILE, _TILE), 0.55)
        brillo = np.full((_TILE, _TILE), 1.0)
    return alfa.astype(np.float32), brillo.astype(np.float32)


@lru_cache(maxsize=96)
def _texture_tile(style: str, rgba: int) -> QImage:
    color = QColor.fromRgba(rgba)
    alfa, brillo = _texture_profile(style)
    rgb = np.array([color.red(), color.green(), color.blue()], dtype=np.float32)
    pixeles = np.empty((_TILE, _TILE, 4), dtype=np.uint8)
    pixeles[:, :, :3] = np.clip(rgb[None, None, :] * brillo[:, :, None], 0, 255).astype(np.uint8)
    pixeles[:, :, 3] = np.clip(alfa * color.alpha(), 0, 255).astype(np.uint8)
    imagen = QImage(pixeles.data, _TILE, _TILE, _TILE * 4, QImage.Format.Format_RGBA8888)
    return imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def _style_brush(color: QColor, style: str) -> QBrush:
    if style == "solid":
        return QBrush(QColor(color))
    return QBrush(_texture_tile(style, QColor(color).rgba()))


def _fill_brush(color: QColor | None, style: str) -> QBrush:
    style = normalize_style(style)
    if color is None or style == "none":
        return QBrush(Qt.BrushStyle.NoBrush)
    if style not in TEXTURE_STYLES:
        style = "solid"
    return _style_brush(color, style)


def _stroke_outline(path: QPainterPath, width: float, open_path: bool) -> QPainterPath:
    stroker = QPainterPathStroker()
    stroker.setWidth(max(1.0, float(width)))
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap if open_path else Qt.PenCapStyle.FlatCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    contorno = stroker.createStroke(path)
    contorno.setFillRule(Qt.FillRule.WindingFill)
    return contorno


def draw_shape(
    painter: QPainter,
    shape: str,
    start: QPointF,
    end: QPointF,
    outline_color: QColor | None,
    fill_color: QColor | None,
    stroke_width: float = 1.0,
    outline_style: str = "solid",
    fill_style: str = "solid",
    points: list[QPointF] | None = None,
) -> None:
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        nombre = _plain_name(shape)
        path = shape_path(nombre, start, end, points)
        abierta = nombre in {"line", "curve"}

        relleno = _fill_brush(fill_color, fill_style)
        if not abierta and relleno.style() != Qt.BrushStyle.NoBrush:
            painter.fillPath(path, relleno)

        estilo = normalize_style(outline_style)
        if outline_color is None or estilo == "none":
            return
        if estilo not in TEXTURE_STYLES:
            # Contorno sólido. El trazo se convierte en área para que un color
            # semitransparente no se oscurezca donde el contorno se cruza.
            painter.fillPath(_stroke_outline(path, stroke_width, abierta), QBrush(QColor(outline_color)))
            return
        painter.fillPath(_stroke_outline(path, stroke_width, abierta), _style_brush(QColor(outline_color), estilo))
    finally:
        painter.restore()


def create_shape_preview(
    size: tuple[int, int],
    shape: str,
    start: QPointF,
    end: QPointF,
    outline_color: QColor | None,
    fill_color: QColor | None,
    stroke_width: float = 1.0,
    outline_style: str = "solid",
    fill_style: str = "solid",
    points: list[QPointF] | None = None,
) -> QImage:
    image = crear_imagen_transparente(size[0], size[1])
    painter = QPainter(image)
    try:
        draw_shape(painter, shape, start, end, outline_color, fill_color, stroke_width, outline_style, fill_style, points)
    finally:
        painter.end()
    return image


# Alias corto para código de la View que use la nomenclatura anterior.
draw_shape_preview = create_shape_preview
