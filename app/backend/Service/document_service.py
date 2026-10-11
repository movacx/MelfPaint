from __future__ import annotations

from math import isfinite, radians, tan
from typing import Callable

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

from backend.Model.document import Document, validar_tamano_lienzo
from backend.Model.layer import crear_imagen_transparente
from backend.Service.history_service import HistoryService


class DocumentService:
    """Transformaciones multicapa con una entrada de historial por accion."""

    FILTROS = {"grayscale", "sepia", "invert", "edge", "coloring_book", "blur", "sharpen", "black_white"}

    def __init__(self, history: HistoryService | None = None) -> None:
        self.history = history or HistoryService()

    def _apply(self, document: Document, label: str, operation: Callable[[], bool]) -> bool:
        before = self.history.capture(document)
        try:
            cambio = bool(operation())
        except Exception:
            before.restore(document)
            raise
        if cambio:
            self.history.record_snapshot(document, before, label)
        return cambio

    @staticmethod
    def _clear_selection(document: Document) -> None:
        document.selection.clear()
        document.selection_rect = None

    @staticmethod
    def _rect(value: QRect | tuple[int, int, int, int]) -> QRect:
        if isinstance(value, QRect):
            return QRect(value)
        if len(value) != 4:
            raise ValueError("El recorte necesita x, y, ancho y alto")
        return QRect(*(int(numero) for numero in value))

    def crop(self, document: Document, rect: QRect | tuple[int, int, int, int]) -> bool:
        recorte = self._rect(rect).normalized().intersected(QRect(0, 0, document.width, document.height))
        return self._apply(document, "Recortar", lambda: document.crop(recorte))

    def resize_image(
        self,
        document: Document,
        width: int,
        height: int,
        keep_aspect: bool = False,
        smooth: bool = True,
    ) -> bool:
        ancho, alto = validar_tamano_lienzo(width, height)
        if keep_aspect:
            proporcion = min(ancho / document.width, alto / document.height)
            ancho = max(1, round(document.width * proporcion))
            alto = max(1, round(document.height * proporcion))
            ancho, alto = validar_tamano_lienzo(ancho, alto)
        if (ancho, alto) == (document.width, document.height):
            return False

        def cambiar() -> bool:
            modo = (
                Qt.TransformationMode.SmoothTransformation
                if smooth
                else Qt.TransformationMode.FastTransformation
            )
            for capa in document.layers:
                capa.image = capa.image.scaled(ancho, alto, Qt.AspectRatioMode.IgnoreAspectRatio, modo)
            document.width, document.height = ancho, alto
            self._clear_selection(document)
            document.invalidate()
            return True

        return self._apply(document, "Cambiar tamano de imagen", cambiar)

    def resize_canvas(
        self,
        document: Document,
        width: int,
        height: int,
        anchor: str = "top_left",
        offset: QPoint | tuple[int, int] | None = None,
    ) -> bool:
        ancho, alto = validar_tamano_lienzo(width, height)
        if (ancho, alto) == (document.width, document.height):
            return False

        anclas = {
            "top_left": (0.0, 0.0),
            "top": (0.5, 0.0),
            "top_right": (1.0, 0.0),
            "left": (0.0, 0.5),
            "center": (0.5, 0.5),
            "right": (1.0, 0.5),
            "bottom_left": (0.0, 1.0),
            "bottom": (0.5, 1.0),
            "bottom_right": (1.0, 1.0),
        }
        if anchor not in anclas:
            raise ValueError(f"Ancla de lienzo no valida: {anchor}")
        factor_x, factor_y = anclas[anchor]
        mover_x = round((ancho - document.width) * factor_x)
        mover_y = round((alto - document.height) * factor_y)
        if offset is not None:
            if isinstance(offset, QPoint):
                mover_x += offset.x()
                mover_y += offset.y()
            else:
                mover_x += int(offset[0])
                mover_y += int(offset[1])

        def cambiar() -> bool:
            for capa in document.layers:
                nueva = crear_imagen_transparente(ancho, alto)
                painter = QPainter(nueva)
                try:
                    painter.drawImage(mover_x, mover_y, capa.image)
                finally:
                    painter.end()
                capa.image = nueva
            document.width, document.height = ancho, alto
            self._clear_selection(document)
            document.invalidate()
            return True

        return self._apply(document, "Cambiar tamano del lienzo", cambiar)

    def skew(self, document: Document, horizontal: float = 0.0, vertical: float = 0.0) -> bool:
        angulo_x, angulo_y = float(horizontal), float(vertical)
        if not isfinite(angulo_x) or not isfinite(angulo_y):
            raise ValueError("La inclinacion necesita numeros finitos")
        if abs(angulo_x) >= 89.0 or abs(angulo_y) >= 89.0:
            raise ValueError("La inclinacion debe estar entre -89 y 89 grados")
        if abs(angulo_x) < 0.0001 and abs(angulo_y) < 0.0001:
            return False

        transformacion = QTransform()
        transformacion.shear(tan(radians(angulo_x)), tan(radians(angulo_y)))
        limites = transformacion.mapRect(QRectF(0, 0, document.width, document.height)).toAlignedRect()
        validar_tamano_lienzo(limites.width(), limites.height())

        def cambiar() -> bool:
            imagenes = [
                capa.image.transformed(transformacion, Qt.TransformationMode.SmoothTransformation)
                for capa in document.layers
            ]
            document.width, document.height = imagenes[0].width(), imagenes[0].height()
            for capa, imagen in zip(document.layers, imagenes, strict=True):
                capa.image = imagen
            self._clear_selection(document)
            document.invalidate()
            return True

        return self._apply(document, "Inclinar imagen", cambiar)

    def rotate(self, document: Document, degrees: float, expand: bool = True) -> bool:
        grados = float(degrees) % 360.0
        if not isfinite(grados):
            raise ValueError("El giro necesita un numero finito")
        if abs(grados) < 0.0001 or abs(grados - 360.0) < 0.0001:
            return False
        transformacion = QTransform().rotate(grados)
        if expand:
            limites = transformacion.mapRect(QRectF(0, 0, document.width, document.height)).toAlignedRect()
            validar_tamano_lienzo(limites.width(), limites.height())

        def cambiar() -> bool:
            transformadas = [
                capa.image.transformed(transformacion, Qt.TransformationMode.SmoothTransformation)
                for capa in document.layers
            ]
            if expand:
                ancho, alto = transformadas[0].width(), transformadas[0].height()
                for capa, imagen in zip(document.layers, transformadas, strict=True):
                    capa.image = imagen
            else:
                ancho, alto = document.width, document.height
                for capa, imagen in zip(document.layers, transformadas, strict=True):
                    centrada = crear_imagen_transparente(ancho, alto)
                    painter = QPainter(centrada)
                    try:
                        painter.drawImage((ancho - imagen.width()) // 2, (alto - imagen.height()) // 2, imagen)
                    finally:
                        painter.end()
                    capa.image = centrada
            document.width, document.height = ancho, alto
            self._clear_selection(document)
            document.invalidate()
            return True

        return self._apply(document, f"Girar {degrees:g} grados", cambiar)

    def rotate_right(self, document: Document) -> bool:
        return self.rotate(document, 90.0)

    def rotate_left(self, document: Document) -> bool:
        return self.rotate(document, -90.0)

    def rotate_180(self, document: Document) -> bool:
        return self.rotate(document, 180.0)

    def rotate_free(self, document: Document, degrees: float, expand: bool = True) -> bool:
        return self.rotate(document, degrees, expand)

    def flip_horizontal(self, document: Document) -> bool:
        return self._flip(document, True, False, "Voltear horizontalmente")

    def flip_vertical(self, document: Document) -> bool:
        return self._flip(document, False, True, "Voltear verticalmente")

    def _flip(self, document: Document, horizontal: bool, vertical: bool, label: str) -> bool:
        def cambiar() -> bool:
            orientacion = Qt.Orientation(0)
            if horizontal:
                orientacion |= Qt.Orientation.Horizontal
            if vertical:
                orientacion |= Qt.Orientation.Vertical
            for capa in document.layers:
                if hasattr(capa.image, "flipped"):
                    capa.image = capa.image.flipped(orientacion)
                else:  # Compatibilidad con PySide6 anterior a Qt 6.9.
                    capa.image = capa.image.mirrored(horizontal, vertical)
            self._clear_selection(document)
            document.invalidate()
            return True

        return self._apply(document, label, cambiar)

    def set_background_visible(self, document: Document, visible: bool) -> bool:
        mostrar = bool(visible)
        if document.show_background == mostrar:
            return False

        def cambiar() -> bool:
            document.show_background = mostrar
            document.invalidate()
            return True

        return self._apply(document, "Mostrar u ocultar fondo", cambiar)

    def set_background_color(self, document: Document, color: QColor | str) -> bool:
        nuevo = QColor(color)
        if not nuevo.isValid():
            raise ValueError("El color de fondo no es valido")
        return self._apply(document, "Cambiar color de fondo", lambda: document.set_background_color(nuevo))

    @staticmethod
    def _rgba(image: QImage) -> tuple[QImage, np.ndarray]:
        copia = image.convertToFormat(QImage.Format.Format_RGBA8888).copy()
        datos = np.frombuffer(copia.bits(), dtype=np.uint8, count=copia.sizeInBytes())
        matriz = datos.reshape((copia.height(), copia.bytesPerLine()))[:, : copia.width() * 4]
        return copia, matriz.reshape((copia.height(), copia.width(), 4))

    @staticmethod
    def _filter_pixels(pixels: np.ndarray, name: str) -> None:
        rgb = pixels[:, :, :3].astype(np.float32)
        alpha = pixels[:, :, 3].copy()
        gris = np.clip(rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114, 0, 255)

        if name == "grayscale":
            pixels[:, :, :3] = gris[:, :, None].astype(np.uint8)
        elif name == "black_white":
            # «Blanco y negro» de Propiedades de imagen: umbral sin grises.
            pixels[:, :, :3] = np.where(gris >= 128, 255, 0)[:, :, None].astype(np.uint8)
        elif name == "sepia":
            resultado = np.empty_like(rgb)
            resultado[:, :, 0] = rgb[:, :, 0] * 0.393 + rgb[:, :, 1] * 0.769 + rgb[:, :, 2] * 0.189
            resultado[:, :, 1] = rgb[:, :, 0] * 0.349 + rgb[:, :, 1] * 0.686 + rgb[:, :, 2] * 0.168
            resultado[:, :, 2] = rgb[:, :, 0] * 0.272 + rgb[:, :, 1] * 0.534 + rgb[:, :, 2] * 0.131
            pixels[:, :, :3] = np.clip(resultado, 0, 255).astype(np.uint8)
        elif name == "invert":
            pixels[:, :, :3] = (255 - rgb).astype(np.uint8)
        elif name in {"edge", "coloring_book"}:
            gx = np.zeros_like(gris)
            gy = np.zeros_like(gris)
            gx[:, 1:-1] = gris[:, 2:] - gris[:, :-2]
            gy[1:-1, :] = gris[2:, :] - gris[:-2, :]
            borde = np.clip(np.hypot(gx, gy), 0, 255)
            salida = borde if name == "edge" else 255 - np.clip(borde * 2.5, 0, 255)
            pixels[:, :, :3] = salida[:, :, None].astype(np.uint8)
        elif name == "blur":
            relleno = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
            acumulado = np.zeros_like(rgb)
            for fila in range(3):
                for columna in range(3):
                    acumulado += relleno[fila : fila + rgb.shape[0], columna : columna + rgb.shape[1]]
            pixels[:, :, :3] = np.clip(acumulado / 9.0, 0, 255).astype(np.uint8)
        elif name == "sharpen":
            relleno = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
            alto, ancho = rgb.shape[:2]
            resultado = (
                rgb * 5.0
                - relleno[0:alto, 1 : ancho + 1]
                - relleno[2 : alto + 2, 1 : ancho + 1]
                - relleno[1 : alto + 1, 0:ancho]
                - relleno[1 : alto + 1, 2 : ancho + 2]
            )
            pixels[:, :, :3] = np.clip(resultado, 0, 255).astype(np.uint8)
        pixels[:, :, 3] = alpha

    def apply_filter(
        self,
        document: Document,
        name: str,
        layer_id: str | int | None = None,
        all_layers: bool = False,
    ) -> bool:
        filtro = str(name).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "gray": "grayscale",
            "greyscale": "grayscale",
            "negative": "invert",
            "edges": "edge",
            "coloringbook": "coloring_book",
            "libro_para_colorear": "coloring_book",
            "desenfocar": "blur",
            "enfocar": "sharpen",
            "blanco_y_negro": "black_white",
            "monochrome": "black_white",
        }
        filtro = aliases.get(filtro, filtro)
        if filtro not in self.FILTROS:
            raise ValueError(f"Filtro no compatible: {name}")
        capas = document.layers if all_layers else [
            document.find_layer(layer_id) if layer_id is not None else document.active_layer
        ]
        capas = [capa for capa in capas if capa is not None]
        if not capas:
            return False

        def cambiar() -> bool:
            for capa in capas:
                imagen, pixeles = self._rgba(capa.image)
                self._filter_pixels(pixeles, filtro)
                capa.image = imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            document.invalidate()
            return True

        nombres = {
            "grayscale": "Escala de grises",
            "sepia": "Sepia",
            "invert": "Invertir colores",
            "edge": "Detectar bordes",
            "coloring_book": "Libro para colorear",
            "blur": "Desenfocar",
            "sharpen": "Enfocar",
            "black_white": "Blanco y negro",
        }
        return self._apply(document, nombres.get(filtro, filtro), cambiar)

    def grayscale(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "grayscale", layer_id)

    def sepia(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "sepia", layer_id)

    def invert(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "invert", layer_id)

    def edge(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "edge", layer_id)

    def coloring_book(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "coloring_book", layer_id)

    def blur(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "blur", layer_id)

    def sharpen(self, document: Document, layer_id: str | int | None = None) -> bool:
        return self.apply_filter(document, "sharpen", layer_id)
