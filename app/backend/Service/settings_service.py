from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from backend.Service.xdg_service import obtener_carpeta_configuracion


class SettingsService:
    """Guarda preferencias pequeñas sin mezclar esta lógica con la interfaz."""

    VALORES_INICIALES = {
        "tema": "sistema",
        "mostrar_regla": False,
        "mostrar_cuadricula": False,
        "mostrar_barra_estado": True,
        "dibujo_en_capa_aparte": True,
        "mostrar_panel_capas": False,
        "zoom": 100,
        "archivos_recientes": [],
        "colores_personalizados": [],
        "tamanos_herramienta": {},
        "ventana": {},
    }

    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or (obtener_carpeta_configuracion() / "settings.json")
        self.datos = deepcopy(self.VALORES_INICIALES)
        self.cargar()

    @classmethod
    def _normalizar_valor(cls, llave: str, valor):  # noqa: ANN001, ANN206
        predeterminado = cls.VALORES_INICIALES[llave]
        if llave == "tema":
            texto = str(valor).lower()
            return texto if texto in {"sistema", "claro", "oscuro"} else predeterminado
        if llave.startswith("mostrar_"):
            return valor if isinstance(valor, bool) else predeterminado
        if llave == "zoom":
            try:
                return max(10, min(800, int(valor)))
            except (TypeError, ValueError, OverflowError):
                return predeterminado
        if llave == "ventana":
            if not isinstance(valor, dict):
                return {}
            limpio: dict[str, object] = {}
            for clave in ("x", "y", "ancho", "alto"):
                if isinstance(valor.get(clave), int):
                    limpio[clave] = max(-10000, min(20000, int(valor[clave])))
            limpio["maximizada"] = bool(valor.get("maximizada", False))
            return limpio
        if llave == "colores_personalizados":
            if not isinstance(valor, list):
                return []
            colores = [str(item) for item in valor if isinstance(item, str) and item.startswith("#")]
            return [item[:9] for item in colores][:10]
        if llave == "tamanos_herramienta":
            if not isinstance(valor, dict):
                return {}
            tamanos: dict[str, float] = {}
            for familia in ("pencil", "brush", "eraser", "shape"):
                try:
                    numero = float(valor[familia])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                if numero == numero and abs(numero) != float("inf"):
                    tamanos[familia] = max(1.0, min(256.0, numero))
            return tamanos
        if llave == "archivos_recientes":
            if not isinstance(valor, list):
                return []
            return [str(item) for item in valor if isinstance(item, str) and item.strip()][:10]
        return deepcopy(predeterminado)

    def cargar(self) -> None:
        if not self.ruta.exists():
            return

        try:
            contenido = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return

        if not isinstance(contenido, dict):
            return

        for llave in self.VALORES_INICIALES:
            if llave in contenido:
                self.datos[llave] = self._normalizar_valor(llave, contenido[llave])

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor, nombre_temporal = tempfile.mkstemp(
            prefix=".settings-",
            suffix=".json",
            dir=str(self.ruta.parent),
        )
        os.close(descriptor)
        temporal = Path(nombre_temporal)

        try:
            temporal.write_text(
                json.dumps(self.datos, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            temporal.replace(self.ruta)
        finally:
            temporal.unlink(missing_ok=True)

    def obtener(self, llave: str, valor=None):  # noqa: ANN001, ANN201
        return deepcopy(self.datos.get(llave, valor))

    def cambiar(self, llave: str, valor) -> None:  # noqa: ANN001
        self.datos[llave] = (
            self._normalizar_valor(llave, valor)
            if llave in self.VALORES_INICIALES
            else valor
        )
        self.guardar()

    def agregar_archivo_reciente(self, ruta: Path) -> None:
        ruta_texto = str(Path(ruta).expanduser().resolve())
        archivos = list(self.datos.get("archivos_recientes", []))
        archivos = [item for item in archivos if item != ruta_texto and Path(item).exists()]
        archivos.insert(0, ruta_texto)
        self.datos["archivos_recientes"] = archivos[:10]
        self.guardar()
