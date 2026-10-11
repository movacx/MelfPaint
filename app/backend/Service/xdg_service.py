from __future__ import annotations

import os
from pathlib import Path


NOMBRE_CARPETA = "melfpaint"


def obtener_carpeta_configuracion() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / NOMBRE_CARPETA


def obtener_carpeta_datos() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / NOMBRE_CARPETA


def obtener_carpeta_cache() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / NOMBRE_CARPETA


def preparar_carpetas() -> None:
    carpetas = [
        obtener_carpeta_configuracion(),
        obtener_carpeta_datos(),
        obtener_carpeta_cache(),
        obtener_carpeta_cache() / "recuperacion",
    ]

    for carpeta in carpetas:
        carpeta.mkdir(parents=True, exist_ok=True)

