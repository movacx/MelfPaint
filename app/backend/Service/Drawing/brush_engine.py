from __future__ import annotations

import itertools
import math
import zlib

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QRadialGradient

from backend.Service.Drawing.raster_engine import draw_line, interpolate_points


BRUSH_ALIASES = {
    "normal": "round",
    "redondo": "round",
    "pincel": "round",
    "brush": "round",
    "lapiz": "natural_pencil",
    "lápiz": "natural_pencil",
    "lapiz_natural": "natural_pencil",
    "lápiz_natural": "natural_pencil",
    "pencil": "natural_pencil",
    "caligrafia": "calligraphy",
    "caligrafía": "calligraphy",
    "pluma": "calligraphy_pen",
    "pluma_de_caligrafia": "calligraphy_pen",
    "pen": "calligraphy_pen",
    "marcador": "marker",
    "aerografo": "airbrush",
    "aerógrafo": "airbrush",
    "spray": "airbrush",
    "crayon": "crayon",
    "crayón": "crayon",
    "oleo": "oil",
    "óleo": "oil",
    "acuarela": "watercolor",
}


def normalizar_pincel(name: str | None) -> str:
    value = str(name or "round").strip().lower().replace(" ", "_")
    return BRUSH_ALIASES.get(value, value)


def _painter(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return painter


_SALTS: dict[str, int] = {}


def _stable_rng(point: QPointF, salt: str | int) -> np.random.Generator:
    """Mismo punto, mismo grano; sin el coste de un hash criptográfico por sello."""

    clave = _SALTS.get(str(salt))
    if clave is None:
        clave = _SALTS[str(salt)] = zlib.crc32(str(salt).encode("utf-8"))
    semilla = (round(point.x() * 16) * 73856093) ^ (round(point.y() * 16) * 19349663) ^ (clave * 83492791)
    return np.random.Generator(np.random.PCG64(semilla & 0xFFFFFFFFFFFF))


def _stamp_round(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        radius = max(0.5, width / 2.0)
        painter.drawEllipse(point, radius, radius)
    finally:
        painter.restore()


def _stamp_calligraphy(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    painter.save()
    try:
        painter.translate(point)
        painter.rotate(-32)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(-width * 0.58, -width * 0.16, width * 1.16, width * 0.32))
    finally:
        painter.restore()


def _stamp_calligraphy_pen(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    """Plumilla rígida a 45°: trazo fino en una dirección y grueso en la otra."""

    painter.save()
    try:
        painter.translate(point)
        painter.rotate(-45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRect(QRectF(-width * 0.5, -max(0.5, width * 0.06), width, max(1.0, width * 0.12)))
    finally:
        painter.restore()


def _stamp_natural_pencil(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    """Grafito: grano fino y semitransparente."""

    rng = _stable_rng(point, "natural_pencil")
    count = max(6, round(width * 2.4))
    xs = (rng.uniform(-width * 0.45, width * 0.45, count) + point.x()).tolist()
    ys = (rng.uniform(-width * 0.45, width * 0.45, count) + point.y()).tolist()
    sizes = rng.uniform(0.35, max(0.55, width * 0.09), count).tolist()
    alphas = (rng.uniform(0.25, 0.75, count) * color.alpha()).round().astype(int).tolist()
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        shade = QColor(color)
        for x, y, size, alpha in zip(xs, ys, sizes, alphas):
            shade.setAlpha(alpha)
            painter.setBrush(shade)
            painter.drawEllipse(QPointF(x, y), size, size)
    finally:
        painter.restore()


def _stamp_marker(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    # El marcador se estampa opaco; su transparencia característica se aplica
    # una sola vez al mezclar el trazo completo con la capa.
    marker = QColor(color)
    painter.save()
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(marker)
        painter.drawRoundedRect(QRectF(point.x() - width * 0.6, point.y() - width * 0.22, width * 1.2, width * 0.44), 1.5, 1.5)
    finally:
        painter.restore()


_SPRAY_COUNTER = itertools.count()


def _stamp_airbrush(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    painter.save()
    try:
        radius = max(1.0, width)
        gradient = QRadialGradient(point, radius)
        center = QColor(color)
        center.setAlpha(min(95, center.alpha()))
        edge = QColor(center)
        edge.setAlpha(0)
        gradient.setColorAt(0.0, center)
        gradient.setColorAt(0.65, QColor(center.red(), center.green(), center.blue(), max(5, center.alpha() // 4)))
        gradient.setColorAt(1.0, edge)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(point, radius, radius)

        # Cada ráfaga es distinta para que el spray se acumule al mantenerlo.
        rng = _stable_rng(point, f"airbrush{next(_SPRAY_COUNTER) % 64}")
        dot = QColor(color)
        dot.setAlpha(min(70, dot.alpha()))
        painter.setBrush(dot)
        count = max(8, round(width * 2.2))
        angulos = rng.uniform(0.0, math.tau, count)
        distancias = radius * np.sqrt(rng.uniform(0.0, 1.0, count))
        xs = (point.x() + np.cos(angulos) * distancias).tolist()
        ys = (point.y() + np.sin(angulos) * distancias).tolist()
        for x, y in zip(xs, ys):
            painter.drawEllipse(QPointF(x, y), 0.45, 0.45)
    finally:
        painter.restore()


def _stamp_crayon(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    rng = _stable_rng(point, "crayon")
    count = max(10, round(width * 3))
    # Cada grano aclara u oscurece un poco el color base.
    claro = rng.random(count) > 0.5
    factor = np.where(claro, rng.integers(85, 121, count) / 100.0, 100.0 / rng.integers(100, 135, count))
    base = np.array([color.red(), color.green(), color.blue()], dtype=float)
    rgb = np.clip(base[None, :] * factor[:, None], 0, 255).astype(int).tolist()
    alphas = (rng.uniform(0.35, 0.9, count) * color.alpha()).round().astype(int).tolist()
    xs = (rng.normal(0.0, width * 0.25, count) + point.x()).tolist()
    ys = (rng.normal(0.0, width * 0.25, count) + point.y()).tolist()
    sizes = rng.uniform(0.45, max(0.7, width * 0.16), count).tolist()
    ratios = rng.uniform(0.35, 0.9, count).tolist()
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        for (r, g, b), alpha, x, y, size, ratio in zip(rgb, alphas, xs, ys, sizes, ratios):
            painter.setBrush(QColor(r, g, b, alpha))
            painter.drawEllipse(QPointF(x, y), size, size * ratio)
    finally:
        painter.restore()


def _stamp_oil(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    rng = _stable_rng(point, "oil")
    cerdas = max(4, round(width / 2))
    offsets = rng.uniform(-width * 0.35, width * 0.35, cerdas).tolist()
    angles = rng.uniform(-12, 12, cerdas).tolist()
    tonos = [QColor(color).lighter(100 + indice * 8) for indice in range(3)]
    for tono in tonos:
        tono.setAlpha(min(230, color.alpha()))
    mitad = max(0.6, width * 0.055)
    rect = QRectF(-width * 0.55, -mitad, width * 1.1, max(1.2, width * 0.11))
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        for indice, (offset, angle) in enumerate(zip(offsets, angles)):
            painter.setBrush(tonos[indice % 3])
            painter.save()
            painter.translate(point.x(), point.y() + offset)
            painter.rotate(angle)
            painter.drawRoundedRect(rect, 1.0, 1.0)
            painter.restore()
    finally:
        painter.restore()


def _stamp_watercolor(painter: QPainter, point: QPointF, color: QColor, width: float) -> None:
    rng = _stable_rng(point, "watercolor")
    offsets = rng.normal(0.0, width * 0.12, (4, 2)).tolist()
    radios = rng.uniform(0.48, 0.72, 4).tolist()
    ratios = rng.uniform(0.72, 1.1, 4).tolist()
    painter.save()
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        for capa, ((dx, dy), radio, ratio) in enumerate(zip(offsets, radios, ratios)):
            wash = QColor(color)
            wash.setAlpha(min(24 + capa * 5, max(1, color.alpha())))
            painter.setBrush(wash)
            radius = width * radio
            painter.drawEllipse(QPointF(point.x() + dx, point.y() + dy), radius, radius * ratio)
    finally:
        painter.restore()


_STAMPERS = {
    "round": _stamp_round,
    "calligraphy": _stamp_calligraphy,
    "calligraphy_pen": _stamp_calligraphy_pen,
    "natural_pencil": _stamp_natural_pencil,
    "marker": _stamp_marker,
    "airbrush": _stamp_airbrush,
    "crayon": _stamp_crayon,
    "oil": _stamp_oil,
    "watercolor": _stamp_watercolor,
}
_DENSE = {"marker", "watercolor", "calligraphy", "calligraphy_pen"}


def stamp_brush(image: QImage, point: QPointF, color: QColor, width: float, brush_type: str = "round") -> None:
    width = max(1.0, float(width))
    stamper = _STAMPERS.get(normalizar_pincel(brush_type), _stamp_round)
    painter = _painter(image)
    try:
        stamper(painter, point, color, width)
    finally:
        painter.end()


def _spacing(width: float, brush_type: str) -> float:
    return max(0.55, width * (0.08 if brush_type in _DENSE else 0.16))


def draw_brush_polyline(
    image: QImage,
    points: list[QPointF],
    color: QColor,
    width: float,
    brush_type: str,
) -> None:
    """Estampa el pincel a lo largo de varios puntos con un solo QPainter."""

    brush_type = normalizar_pincel(brush_type)
    width = max(1.0, float(width))
    if brush_type == "round":
        for a, b in zip(points, points[1:]):
            draw_line(image, a, b, color, width, antialias=True)
        return
    stamper = _STAMPERS.get(brush_type, _stamp_round)
    spacing = _spacing(width, brush_type)
    painter = _painter(image)
    try:
        if len(points) == 1:
            stamper(painter, points[0], color, width)
        for a, b in zip(points, points[1:]):
            for punto in interpolate_points(a, b, spacing):
                stamper(painter, punto, color, width)
    finally:
        painter.end()


def draw_brush_segment(
    image: QImage,
    start: QPointF,
    end: QPointF,
    color: QColor,
    width: float,
    brush_type: str,
) -> None:
    brush_type = normalizar_pincel(brush_type)
    if brush_type == "round":
        draw_line(image, start, end, color, width, antialias=True)
        return
    if start == end:
        stamp_brush(image, start, color, width, brush_type)
        return
    draw_brush_polyline(image, [start, end], color, width, brush_type)
