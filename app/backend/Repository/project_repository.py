from __future__ import annotations

import json
import math
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QImageWriter, QPainter

from backend.Model.document import Document
from backend.Model.layer import Layer
from backend.Model.text_format import TextFormat
from backend.Model.tool_settings import ToolSettings

PROJECT_VERSION = 2
PROJECT_EXTENSIONS = {".melfpaint", ".paint"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".jfif",
    ".bmp",
    ".dib",
    ".gif",
    ".tif",
    ".tiff",
    ".ico",
    ".webp",
}
FORMAT_BY_EXTENSION = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jpe": "JPEG",
    ".jfif": "JPEG",
    ".bmp": "BMP",
    ".dib": "BMP",
    ".gif": "GIF",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".ico": "ICO",
    ".webp": "WEBP",
}
# Formatos sin canal alfa: se aplanan sobre el color de fondo.
OPAQUE_FORMATS = {"JPEG", "BMP"}


def _pillow():
    """Pillow es opcional: amplía los formatos cuando Qt no trae el códec."""

    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Image


def _qt_formats(writer: bool) -> set[str]:
    source = QImageWriter if writer else QImageReader
    return {bytes(item).decode("ascii", "ignore").upper() for item in source.supportedImageFormats()}


def writable_formats() -> set[str]:
    formatos = _qt_formats(True)
    if _pillow() is not None:
        formatos |= {"PNG", "JPEG", "BMP", "GIF", "TIFF", "ICO", "WEBP"}
    return formatos & set(FORMAT_BY_EXTENSION.values())


def readable_extensions() -> set[str]:
    formatos = _qt_formats(False)
    if _pillow() is not None:
        formatos |= {"PNG", "JPEG", "BMP", "GIF", "TIFF", "ICO", "WEBP"}
    return {extension for extension, formato in FORMAT_BY_EXTENSION.items() if formato in formatos}


class CodecError(RuntimeError):
    """Indica que una imagen o proyecto no se pudo leer o escribir."""


class ProjectRepository:
    """Persistencia atomica con limites para archivos recibidos."""

    MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
    MAX_RASTER_SIZE = 512 * 1024 * 1024
    MAX_UNCOMPRESSED_SIZE = 1024 * 1024 * 1024
    MAX_ENTRY_SIZE = 256 * 1024 * 1024
    MAX_MANIFEST_SIZE = 1024 * 1024
    MAX_COMPRESSION_RATIO = 250
    MAX_ARCHIVE_ENTRIES = 520
    MAX_LAYERS = 256
    MAX_CANVAS_SIDE = 32768
    MAX_CANVAS_PIXELS = 100_000_000
    MAX_DECODED_LAYER_BYTES = 1024 * 1024 * 1024

    @staticmethod
    def _absolute(path: Path | str) -> Path:
        return Path(path).expanduser().absolute()

    @classmethod
    def _validate_dimensions(cls, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise CodecError("El documento tiene dimensiones invalidas")
        if width > cls.MAX_CANVAS_SIDE or height > cls.MAX_CANVAS_SIDE:
            raise CodecError("El documento supera el limite por lado")
        if width * height > cls.MAX_CANVAS_PIXELS:
            raise CodecError("El documento supera el limite de pixeles")

    @classmethod
    def qimage_to_png_bytes(cls, image: QImage) -> bytes:
        if image.isNull():
            raise CodecError("No se puede guardar una imagen vacia")
        cls._validate_dimensions(image.width(), image.height())
        datos = QByteArray()
        buffer = QBuffer(datos)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            raise CodecError("No se pudo crear el buffer de imagen")
        if not image.save(buffer, "PNG"):
            raise CodecError("No se pudo codificar la imagen PNG")
        buffer.close()
        return bytes(datos)

    @classmethod
    def qimage_from_bytes(cls, data: bytes, expected_size: QSize | None = None) -> QImage:
        if not data or len(data) > cls.MAX_ENTRY_SIZE:
            raise CodecError("La imagen interna esta vacia o excede el limite")
        arreglo = QByteArray(data)
        buffer = QBuffer(arreglo)
        if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            raise CodecError("No se pudo abrir el buffer de imagen")
        lector = QImageReader(buffer)
        tamano = lector.size()
        if not tamano.isValid():
            raise CodecError("No se pudo leer el encabezado de la imagen")
        cls._validate_dimensions(tamano.width(), tamano.height())
        if expected_size is not None and tamano != expected_size:
            raise CodecError("Una capa no coincide con el tamano declarado")
        imagen = lector.read()
        buffer.close()
        if imagen.isNull():
            raise CodecError(f"No se pudo decodificar la imagen: {lector.errorString()}")
        return imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    @staticmethod
    def _image_dpi(image: QImage) -> int:
        puntos_por_metro = image.dotsPerMeterX() or image.dotsPerMeterY()
        if puntos_por_metro <= 0:
            return 96
        return max(1, min(1200, round(puntos_por_metro * 0.0254)))

    @classmethod
    def _read_raster(cls, path: Path) -> QImage:
        try:
            tamano_archivo = path.stat().st_size
        except OSError as error:
            raise CodecError(f"No se pudo abrir el archivo: {path}") from error
        if tamano_archivo <= 0 or tamano_archivo > cls.MAX_RASTER_SIZE:
            raise CodecError("La imagen esta vacia o supera el limite permitido")

        lector = QImageReader(str(path))
        lector.setAutoTransform(True)
        tamano = lector.size()
        if not tamano.isValid():
            imagen = cls._read_with_pillow(path)
            if imagen is not None:
                return imagen
            raise CodecError(f"Formato no compatible o archivo danado: {path.name}")
        cls._validate_dimensions(tamano.width(), tamano.height())
        imagen = lector.read()
        if imagen.isNull():
            raise CodecError(f"No se pudo decodificar la imagen: {lector.errorString()}")
        return imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    @classmethod
    def _read_with_pillow(cls, path: Path) -> QImage | None:
        Image = _pillow()
        if Image is None:
            return None
        try:
            with Image.open(path) as original:
                cls._validate_dimensions(original.width, original.height)
                rgba = original.convert("RGBA")
                datos = rgba.tobytes()
                imagen = QImage(datos, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
        except CodecError:
            raise
        except Exception:  # Pillow lanza muchos tipos distintos de error.
            return None
        return imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    def read_image(self, path: Path | str) -> QImage:
        """Lee una imagen suelta (por ejemplo para «Pegar desde»)."""

        return self._read_raster(self._absolute(path))

    def open_document(self, path: Path | str) -> Document:
        ruta = self._absolute(path)
        if ruta.suffix.lower() in PROJECT_EXTENSIONS:
            return self.load_project(ruta)
        imagen = self._read_raster(ruta)
        capa = Layer(name=ruta.stem or "Imagen", image=imagen)
        return Document(
            width=imagen.width(),
            height=imagen.height(),
            dpi=self._image_dpi(imagen),
            show_background=not imagen.hasAlphaChannel(),
            layers=[capa],
            active_layer_id=capa.id,
            source_path=ruta,
            project_path=None,
            modified=False,
        )

    @staticmethod
    def _color_data(color: QColor) -> list[int]:
        return [color.red(), color.green(), color.blue(), color.alpha()]

    @staticmethod
    def _color_from_data(value: object) -> QColor:
        if not isinstance(value, list) or len(value) != 4:
            raise CodecError("El color de fondo del proyecto es invalido")
        try:
            canales = [max(0, min(255, int(canal))) for canal in value]
        except (TypeError, ValueError) as error:
            raise CodecError("El color de fondo del proyecto es invalido") from error
        return QColor(*canales)

    def _manifest(self, document: Document) -> dict[str, object]:
        if document.selection.has_selection:
            raise CodecError("Confirme o cancele la seleccion antes de guardar")
        self._validate_dimensions(document.width, document.height)
        if not 1 <= len(document.layers) <= self.MAX_LAYERS:
            raise CodecError("La cantidad de capas no es valida")
        if document.width * document.height * 4 * len(document.layers) > self.MAX_DECODED_LAYER_BYTES:
            raise CodecError("Las capas del proyecto exceden el limite de memoria")
        if not isinstance(document.dpi, int) or not 1 <= document.dpi <= 1200:
            raise CodecError("La resolucion del proyecto no es valida")
        if not document.background_color.isValid():
            raise CodecError("El color de fondo del proyecto no es valido")

        layer_entries: list[dict[str, object]] = []
        layer_ids: set[str] = set()
        for indice, capa in enumerate(document.layers):
            layer_id = str(capa.id).strip()
            try:
                opacity = float(capa.opacity)
            except (TypeError, ValueError) as error:
                raise CodecError("La opacidad de una capa no es valida") from error
            if not layer_id or layer_id in layer_ids:
                raise CodecError("Cada capa necesita un identificador unico")
            if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
                raise CodecError("La opacidad de una capa no es valida")
            if not isinstance(capa.name, str):
                raise CodecError("El nombre de una capa no es valido")
            layer_ids.add(layer_id)
            layer_entries.append(
                {
                    "id": layer_id,
                    "name": capa.name,
                    "visible": bool(capa.visible),
                    "opacity": opacity,
                    "locked": bool(capa.locked),
                    "blend_mode": str(capa.blend_mode),
                    "file": f"layers/{indice:03d}.png",
                }
            )
        if document.active_layer_id not in layer_ids:
            raise CodecError("La capa activa del proyecto no es valida")
        try:
            text_format = document.text_format.clone().to_dict()
            tool_settings = document.tool_settings.clone().to_dict()
        except (OverflowError, TypeError, ValueError) as error:
            raise CodecError("La configuracion del proyecto no es valida") from error
        return {
            "format": "MelfPaint Project",
            "version": PROJECT_VERSION,
            "width": document.width,
            "height": document.height,
            "dpi": document.dpi,
            "show_background": document.show_background,
            "transparent_background": not document.show_background,
            "background": self._color_data(document.background_color),
            "active_layer_id": document.active_layer_id,
            "text_format": text_format,
            "tool_settings": tool_settings,
            "layers": layer_entries,
        }

    @staticmethod
    def _sync_file(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _replace_atomic(source: Path, target: Path) -> None:
        os.replace(source, target)
        try:
            descriptor = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            # Algunos sistemas no permiten sincronizar directorios.
            pass

    def save_project(
        self,
        document: Document,
        path: Path | str,
        mark_clean: bool = True,
    ) -> Path:
        ruta = self._absolute(path)
        if ruta.suffix.lower() not in PROJECT_EXTENSIONS:
            ruta = ruta.with_suffix(".melfpaint")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        manifest = self._manifest(document)
        manifest_data = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        if len(manifest_data) > self.MAX_MANIFEST_SIZE:
            raise CodecError("Los metadatos del proyecto exceden el limite")

        descriptor, temporal_nombre = tempfile.mkstemp(
            prefix=f".{ruta.name}.",
            suffix=".tmp",
            dir=str(ruta.parent),
        )
        os.close(descriptor)
        temporal = Path(temporal_nombre)
        try:
            with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
                archivo.writestr("manifest.json", manifest_data)
                miniatura = document.composite().scaled(
                    256,
                    256,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # PNG ya comprime sus datos. Guardarlo otra vez con DEFLATE
                # produce relaciones extremas en lienzos vacios y puede hacer
                # que un proyecto legitimo parezca una bomba ZIP.
                archivo.writestr(
                    "thumbnail.png",
                    self.qimage_to_png_bytes(miniatura),
                    compress_type=zipfile.ZIP_STORED,
                )
                for indice, capa in enumerate(document.layers):
                    if capa.image.size() != document.size:
                        raise CodecError("Una capa no coincide con el tamano del documento")
                    archivo.writestr(
                        f"layers/{indice:03d}.png",
                        self.qimage_to_png_bytes(capa.image),
                        compress_type=zipfile.ZIP_STORED,
                    )
            self._sync_file(temporal)
            self._replace_atomic(temporal, ruta)
        except CodecError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise CodecError(f"No se pudo guardar el proyecto: {error}") from error
        finally:
            temporal.unlink(missing_ok=True)

        if mark_clean:
            document.project_path = ruta
            document.modified = False
        return ruta

    def save_recovery(self, document: Document, path: Path | str) -> Path:
        """Guarda una copia sin cambiar la identidad ni el estado del documento."""
        return self.save_project(document, path, mark_clean=False)

    guardar_recuperacion = save_recovery

    @classmethod
    def _validate_member_name(cls, name: str) -> None:
        ruta = PurePosixPath(name)
        if not name or "\\" in name or ruta.is_absolute() or ".." in ruta.parts:
            raise CodecError("El proyecto contiene una ruta interna insegura")

    @classmethod
    def _validate_archive(cls, archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
        entradas = archive.infolist()
        if not entradas or len(entradas) > cls.MAX_ARCHIVE_ENTRIES:
            raise CodecError("La cantidad de archivos internos no es valida")
        total = 0
        indice: dict[str, zipfile.ZipInfo] = {}
        for entrada in entradas:
            cls._validate_member_name(entrada.filename)
            if entrada.filename in indice:
                raise CodecError("El proyecto contiene archivos internos duplicados")
            indice[entrada.filename] = entrada
            if entrada.is_dir():
                continue
            if entrada.flag_bits & 0x1:
                raise CodecError("Los proyectos cifrados no son compatibles")
            if entrada.file_size < 0 or entrada.file_size > cls.MAX_ENTRY_SIZE:
                raise CodecError("Un archivo interno excede el limite")
            total += entrada.file_size
            if total > cls.MAX_UNCOMPRESSED_SIZE:
                raise CodecError("El proyecto descomprimido excede el limite")
            # Se toleran entradas pequenas muy compresibles para abrir los
            # proyectos creados por versiones anteriores, que comprimian PNG
            # una segunda vez. El limite de tamano sigue acotando la expansion.
            if entrada.file_size > 8 * 1024 * 1024:
                proporcion = entrada.file_size / max(1, entrada.compress_size)
                if proporcion > cls.MAX_COMPRESSION_RATIO:
                    raise CodecError("El proyecto tiene una compresion sospechosa")
        manifest_info = indice.get("manifest.json")
        if manifest_info is None or manifest_info.file_size > cls.MAX_MANIFEST_SIZE:
            raise CodecError("El proyecto no contiene metadatos validos")
        return indice

    def load_project(self, path: Path | str) -> Document:
        ruta = self._absolute(path)
        try:
            if ruta.stat().st_size > self.MAX_ARCHIVE_SIZE:
                raise CodecError("El proyecto supera el limite permitido")
            with zipfile.ZipFile(ruta, "r") as archivo:
                entradas = self._validate_archive(archivo)
                manifest = json.loads(archivo.read("manifest.json").decode("utf-8"))
                document = self._document_from_archive(archivo, entradas, manifest, ruta)
        except CodecError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            zipfile.BadZipFile,
            RuntimeError,
            RecursionError,
            NotImplementedError,
            OverflowError,
            TypeError,
            ValueError,
        ) as error:
            raise CodecError(f"Proyecto danado o incompleto: {ruta.name}") from error
        return document

    def _document_from_archive(
        self,
        archive: zipfile.ZipFile,
        entries: dict[str, zipfile.ZipInfo],
        manifest: object,
        path: Path,
    ) -> Document:
        if not isinstance(manifest, dict) or manifest.get("format") != "MelfPaint Project":
            raise CodecError("El archivo no es un proyecto MelfPaint")
        try:
            version = int(manifest.get("version", 0))
            width = int(manifest["width"])
            height = int(manifest["height"])
        except (KeyError, TypeError, ValueError) as error:
            raise CodecError("Los metadatos del proyecto son invalidos") from error
        if not 1 <= version <= PROJECT_VERSION:
            raise CodecError(f"Version de proyecto no compatible: {version}")
        self._validate_dimensions(width, height)
        expected_size = QSize(width, height)

        layer_data = manifest.get("layers")
        if not isinstance(layer_data, list) or not 1 <= len(layer_data) <= self.MAX_LAYERS:
            raise CodecError("El proyecto no contiene una lista de capas valida")
        if width * height * 4 * len(layer_data) > self.MAX_DECODED_LAYER_BYTES:
            raise CodecError("Las capas del proyecto exceden el limite de memoria")
        layers: list[Layer] = []
        ids: set[str] = set()
        files: set[str] = set()
        for item in layer_data:
            if not isinstance(item, dict):
                raise CodecError("Los datos de una capa son invalidos")
            try:
                layer_id_value = item["id"]
                filename_value = item["file"]
                name_value = item.get("name", "Capa")
                if not isinstance(layer_id_value, str) or not isinstance(filename_value, str):
                    raise TypeError
                if not isinstance(name_value, str):
                    raise TypeError
                layer_id = layer_id_value.strip()
                filename = filename_value
                opacity = float(item.get("opacity", 1.0))
                if not math.isfinite(opacity):
                    raise ValueError
                opacity = max(0.0, min(1.0, opacity))
                visible_value = item.get("visible", True)
                if not isinstance(visible_value, bool):
                    raise TypeError
                locked_value = item.get("locked", False)
                if not isinstance(locked_value, bool):
                    raise TypeError
                blend_value = item.get("blend_mode", "normal")
                if not isinstance(blend_value, str):
                    raise TypeError
            except (KeyError, TypeError, ValueError) as error:
                raise CodecError("Los datos de una capa son invalidos") from error
            self._validate_member_name(filename)
            if not layer_id or layer_id in ids or filename in files:
                raise CodecError("El proyecto contiene capas duplicadas")
            if not filename.startswith("layers/") or filename not in entries or entries[filename].is_dir():
                raise CodecError("Falta la imagen de una capa")
            ids.add(layer_id)
            files.add(filename)
            image = self.qimage_from_bytes(archive.read(filename), expected_size)
            layers.append(
                Layer(
                    id=layer_id,
                    name=name_value[:500],
                    image=image,
                    visible=visible_value,
                    opacity=opacity,
                    locked=locked_value,
                    blend_mode=blend_value,
                )
            )

        active_value = manifest.get("active_layer_id")
        if active_value in (None, ""):
            active_layer_id = layers[-1].id
        elif not isinstance(active_value, str) or active_value not in ids:
            raise CodecError("La capa activa del proyecto no es valida")
        else:
            active_layer_id = active_value

        color = self._color_from_data(manifest.get("background", [255, 255, 255, 255]))
        if "show_background" in manifest:
            show_background_value = manifest["show_background"]
            if not isinstance(show_background_value, bool):
                raise CodecError("La configuracion de fondo no es valida")
            show_background = show_background_value
        else:
            transparent_value = manifest.get("transparent_background", False)
            if not isinstance(transparent_value, bool):
                raise CodecError("La configuracion de fondo no es valida")
            show_background = not transparent_value
        try:
            dpi = max(1, min(1200, int(manifest.get("dpi", 96))))
            text_data = manifest.get("text_format")
            tool_data = manifest.get("tool_settings")
            if text_data is not None and not isinstance(text_data, dict):
                raise TypeError
            if tool_data is not None and not isinstance(tool_data, dict):
                raise TypeError
            text_format = TextFormat.from_dict(
                text_data
            )
            tool_settings = ToolSettings.from_dict(
                tool_data
            )
        except (OverflowError, TypeError, ValueError) as error:
            raise CodecError("La configuracion guardada del proyecto no es valida") from error
        return Document(
            width=width,
            height=height,
            dpi=dpi,
            background_color=color,
            show_background=show_background,
            layers=layers,
            active_layer_id=active_layer_id,
            project_path=path,
            source_path=None,
            modified=False,
            text_format=text_format,
            tool_settings=tool_settings,
        )

    @staticmethod
    def _format_for_extension(extension: str) -> str:
        try:
            return FORMAT_BY_EXTENSION[extension]
        except KeyError as error:
            raise CodecError(f"Formato de exportacion no compatible: {extension}") from error

    @staticmethod
    def _save_image(imagen: QImage, path: Path, formato: str, quality: int) -> None:
        if formato in _qt_formats(True):
            if imagen.save(str(path), formato, int(quality)):
                return
        Image = _pillow()
        if Image is None:
            raise CodecError(
                f"Este sistema no puede guardar {formato}. Instale Pillow (python3-pillow) para habilitarlo."
            )
        rgba = imagen.convertToFormat(QImage.Format.Format_RGBA8888)
        datos = bytes(rgba.constBits())[: rgba.sizeInBytes()]
        original = Image.frombuffer("RGBA", (rgba.width(), rgba.height()), datos, "raw", "RGBA", rgba.bytesPerLine(), 1)
        dpi = round(imagen.dotsPerMeterX() * 0.0254) or 96
        opciones: dict[str, object] = {}
        if formato == "GIF":
            alfa = original.getchannel("A")
            convertida = original.convert("RGB").quantize(colors=255)
            if alfa.getextrema()[0] < 128:
                # Se reserva el índice 255 para la transparencia.
                mascara = alfa.point(lambda valor: 255 if valor < 128 else 0)
                convertida.paste(255, mask=mascara)
                opciones["transparency"] = 255
            original = convertida
        elif formato == "ICO":
            lado = min(256, max(original.width, original.height))
            opciones["sizes"] = [(tam, tam) for tam in (16, 24, 32, 48, 64, 128, 256) if tam <= lado] or [(lado, lado)]
        elif formato in {"JPEG", "WEBP"} and quality >= 0:
            opciones["quality"] = int(quality)
        if formato == "JPEG":
            original = original.convert("RGB")
        if formato in {"PNG", "JPEG", "TIFF", "BMP"}:
            opciones["dpi"] = (dpi, dpi)
        try:
            original.save(path, format=formato, **opciones)
        except Exception as error:  # noqa: BLE001 - se informa como error de códec
            raise CodecError(f"No se pudo codificar la imagen {formato}: {error}") from error

    def export_image(
        self,
        document: Document,
        path: Path | str,
        quality: int = -1,
        include_background: bool | None = None,
    ) -> Path:
        if document.selection.has_selection:
            raise CodecError("Confirme o cancele la seleccion antes de exportar")
        ruta = self._absolute(path)
        extension = ruta.suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            raise CodecError("La ruta de exportacion necesita una extension de imagen compatible")
        formato = self._format_for_extension(extension)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        imagen = document.composite(include_background)
        puntos_por_metro = round(document.dpi / 0.0254)
        imagen.setDotsPerMeterX(puntos_por_metro)
        imagen.setDotsPerMeterY(puntos_por_metro)
        if formato in OPAQUE_FORMATS and imagen.hasAlphaChannel():
            plana = QImage(document.width, document.height, QImage.Format.Format_RGB32)
            plana.fill(document.background_color if document.show_background else QColor("white"))
            painter = QPainter(plana)
            try:
                painter.drawImage(0, 0, imagen)
            finally:
                painter.end()
            imagen = plana
            # La imagen opaca es una instancia nueva. QImage no copia en ella la
            # resolución configurada arriba, por lo que JPEG terminaba usando el
            # valor predeterminado del plugin (100 ppp).
            imagen.setDotsPerMeterX(puntos_por_metro)
            imagen.setDotsPerMeterY(puntos_por_metro)

        descriptor, temporal_nombre = tempfile.mkstemp(
            prefix=f".{ruta.stem}.",
            suffix=extension,
            dir=str(ruta.parent),
        )
        os.close(descriptor)
        temporal = Path(temporal_nombre)
        try:
            self._save_image(imagen, temporal, formato, int(quality))
            self._sync_file(temporal)
            self._replace_atomic(temporal, ruta)
        except CodecError:
            raise
        except OSError as error:
            raise CodecError(f"No se pudo exportar la imagen: {error}") from error
        finally:
            temporal.unlink(missing_ok=True)

        document.last_export_path = ruta
        return ruta


_DEFAULT_REPOSITORY = ProjectRepository()
open_document = _DEFAULT_REPOSITORY.open_document
save_project = _DEFAULT_REPOSITORY.save_project
load_project = _DEFAULT_REPOSITORY.load_project
export_image = _DEFAULT_REPOSITORY.export_image
