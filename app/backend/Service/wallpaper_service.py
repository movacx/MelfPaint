from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtGui import QImage

from backend.Service.xdg_service import obtener_carpeta_datos


class WallpaperError(RuntimeError):
    """El escritorio actual no permite cambiar el fondo desde MelfPaint."""


class WallpaperService:
    """Equivalente a «Establecer como fondo de escritorio».

    Guarda una copia PNG de la imagen y pide al entorno de escritorio que la
    use. Admite GNOME y derivados (Cinnamon, Budgie, MATE), KDE Plasma y XFCE.
    """

    MODOS = {"fill", "tile", "center"}

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or obtener_carpeta_datos()

    @staticmethod
    def _desktop() -> str:
        return ":".join(
            os.environ.get(name, "") for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
        ).lower()

    @staticmethod
    def _run(*command: str) -> None:
        subprocess.run(list(command), check=True, timeout=15, capture_output=True)

    def save_copy(self, image: QImage) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / "fondo-de-escritorio.png"
        temporary = target.with_suffix(".tmp.png")
        if not image.save(str(temporary), "PNG"):
            raise WallpaperError("No se pudo guardar la imagen del fondo de escritorio")
        temporary.replace(target)
        return target

    def apply(self, image: QImage, mode: str = "fill") -> Path:
        mode = mode if mode in self.MODOS else "fill"
        path = self.save_copy(image)
        uri = path.resolve().as_uri()
        desktop = self._desktop()
        try:
            if "kde" in desktop or "plasma" in desktop:
                self._apply_plasma(path, mode)
            elif "xfce" in desktop:
                self._apply_xfce(path, mode)
            elif "mate" in desktop and shutil.which("gsettings"):
                self._apply_gsettings("org.mate.background", "picture-filename", str(path), "picture-options", mode)
            elif "cinnamon" in desktop and shutil.which("gsettings"):
                self._apply_gsettings("org.cinnamon.desktop.background", "picture-uri", uri, "picture-options", mode)
            elif shutil.which("gsettings"):
                self._apply_gsettings("org.gnome.desktop.background", "picture-uri", uri, "picture-options", mode)
                try:
                    self._run("gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri)
                except (OSError, subprocess.SubprocessError):
                    pass
            else:
                raise WallpaperError("No se reconoció el entorno de escritorio")
        except (OSError, subprocess.SubprocessError) as error:
            raise WallpaperError(f"El escritorio rechazó el cambio de fondo: {error}") from error
        return path

    def _apply_gsettings(self, schema: str, key: str, value: str, options_key: str, mode: str) -> None:
        options = {"fill": "zoom", "tile": "wallpaper", "center": "centered"}[mode]
        self._run("gsettings", "set", schema, key, value)
        self._run("gsettings", "set", schema, options_key, options)

    def _apply_plasma(self, path: Path, mode: str) -> None:
        fill_mode = {"fill": 2, "tile": 3, "center": 6}[mode]
        script = (
            "desktops().forEach(function (d) {"
            " d.wallpaperPlugin = 'org.kde.image';"
            " d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];"
            f" d.writeConfig('Image', {path.resolve().as_uri()!r});"
            f" d.writeConfig('FillMode', {fill_mode});"
            "});"
        )
        for tool in ("qdbus6", "qdbus", "qdbus-qt6"):
            if shutil.which(tool):
                self._run(tool, "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script)
                return
        if shutil.which("plasma-apply-wallpaperimage"):
            self._run("plasma-apply-wallpaperimage", str(path))
            return
        raise WallpaperError("No se encontró qdbus ni plasma-apply-wallpaperimage")

    def _apply_xfce(self, path: Path, mode: str) -> None:
        if not shutil.which("xfconf-query"):
            raise WallpaperError("No se encontró xfconf-query")
        style = {"fill": "5", "tile": "2", "center": "1"}[mode]
        listado = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-l"], check=True, timeout=15, capture_output=True, text=True
        ).stdout.splitlines()
        rutas = [linea for linea in listado if linea.endswith("/last-image")]
        if not rutas:
            raise WallpaperError("XFCE no informó monitores para el fondo")
        for ruta in rutas:
            self._run("xfconf-query", "-c", "xfce4-desktop", "-p", ruta, "-s", str(path))
            self._run("xfconf-query", "-c", "xfce4-desktop", "-p", ruta.replace("last-image", "image-style"), "-s", style)
